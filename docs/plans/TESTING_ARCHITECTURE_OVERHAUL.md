# Plan: Overhaul the testing architecture

## Context

`reports/Why our audits missed issues.md` found that every escaped bug had a nearby check that tested a stand-in, and that the same agents wrote the code, the tests, the gates and the score. Three read-only explorations on 13 Nov confirmed and extended that:

- **Nothing is enforced.** No git hooks, no Claude hooks, no CODEOWNERS. Render deploys every push to `main` (web, 7 crons, 1 worker) whether CI is green or red. 29 production deploys since 10 Nov, no staging.
- **Test mode is a different program.** 96 `TESTING` checks in 34 production files. Several loosen security: fixed OTP `123456` (`core/auth/otp.py:139,233`), unsigned tokens accepted (`core/auth/supabase_auth.py:234`), admin endpoints open when `"pytest" in sys.modules` (`web/routers/admin.py:591,654,692,2169`), paywall bypass via `?test_access=1` / `x-unlock-preview` (`web/common.py:423,463,512`), simulated payment signatures (`core/billing/razorpay.py:307`).
- **Gates match text, not behaviour.** About 15 of ~60 checks in `scripts/verify_reality_audit.py` run code; the scan covers only `core/` and `web/`. Gate 6.1 passes any `except` that calls something with "info" or "log" in its name; Gate 8.1 passes if the word "idempotent" appears.
- **The score measures nothing about security.** `core/audit/project_auditor.py:182-322`; a probe that crashes counts as a pass.
- **Claims have no evidence.** The manual cites 44 script/test paths that don't exist at the stated path (about 31 exist nowhere); 94 "100/100" claims; 10 ledger SHAs don't exist in git.
- **Tests run on one engine.** All 1,207 tests run on a shared, never-reset SQLite file (`./test_reports.db`); CI has no Postgres. 440 dialect branches in `core/`. SQLite "now" is UTC while Postgres sessions are IST. CI is Python 3.12; production is 3.14.

**Extra risks from how this project is built (not in the report):**

1. **Local commands reach the production database.** `core/config.py:18-21` loads `.env` on import; `core/db/connection.py:64-71` then uses the production URL for any process not detected as a test, and runs all migrations on first use (`:480-486`). `./run.sh start`, any `scripts/*.py`, and a test file run directly (`python tests/unit/test_x.py`; 20 unit files never set `TESTING`) all hit production. Three different "am I a test?" checks disagree (`config.py:52`, `notify.py:23`, `connection.py:45`).
2. **A broken push takes effect at the next cron**, and three crons send real email to subscribers.
3. **`./run.sh rollback` force-pushes `main`** with no tests (`ci/checkpoint_manager.py:302-372`); `--skip-checks` bypasses checkpoint preflight.
4. **The repo folder is synced by Google Drive**, including `.git/`, `.env`, the 167 MB `reports.db` (real support tickets and OTP rows) and 124 DB snapshots in `.checkpoints/`.
5. **Multiple agents, no attribution.** Only Claude commits carry a trailer; rules live in three places that have drifted (`AGENTS.md`, `.agents/rules/`, `.antigravity/hooks.json`, two `PENDING_TASKS.md`).
6. **No time control in tests.** No test freezes the clock; 9 AM, weekend and holiday branches are untested, and `/discovery` results depend on the time of day.
7. **Order-dependent tests.** 29 files set `TESTING=1` at import and 30 places unset it mid-run, re-opening network paths.
8. **Inline JS and giant files.** `admin.html` is 6,888 lines with inline scripts; no browser test exists (`selenium` is in requirements, unused).

**Your decisions (13 Nov):** deploys wait for CI; a Claude hook blocks edits to protected files and you approve changes in chat, with CI flagging changes from other agents; CI gets a free throwaway Postgres, and local commands default to SQLite.

**Goal:** separate the roles that collapsed into one. Agents keep writing code; a small protected layer they can't quietly change judges it; production itself is checked on a schedule; and no claim is recorded without evidence.

## Design: five layers

| Layer | Runs where | Blocks deploy? | Agent-editable? |
|---|---|---|---|
| L0 Safety rails (prod DB opt-in, deploy gate) | laptop, Render | yes | no (protected) |
| L1 Fast suite (existing unit/integration, cleaned up) | laptop, CI | yes | yes |
| L2 Protected contract suite (negative security, money, promises) with `TESTING` unset, on Postgres | CI | yes | **no** |
| L3 Static scans (widened gates + third-party linters, doc-claim check) | CI | yes | gate scripts protected |
| L4 Production checks (scheduled, read-only) | GitHub schedule → live site | opens an issue | protected |

## Phase 0 — Finish in-flight work (first, ~30 min)

Uncommitted: `core/log_privacy.py`, `core/__init__.py`, `scripts/run_paid_fund_audit_worker.py`, `tests/unit/test_log_privacy.py`, three docs. The reality audit fails on `core/log_privacy.py:40` (an `except` with no logging). Fix by narrowing to `except (TypeError, ValueError)` and writing a one-line notice to `sys.stderr` (logging from inside the record factory would recurse). Then run tests and gates, commit, push, one backup, and confirm masked addresses and worker "alive" lines in Render logs.

## Phase 1 — Safety rails (day 1)

1. **Production database becomes opt-in on any non-hosted machine.** In `core/db/connection.py:get_configured_supabase_url`, return the URL only when `is_hosted_production_runtime()` is true or `ALLOW_PRODUCTION_DB=1` is set; otherwise use SQLite and log one warning line. `GITHUB_ACTIONS` manual workflows set the flag explicitly in their YAML. Replace the three test-detection functions with one shared `core/runtime.py:is_test_runtime()` used by `config.py`, `notify.py`, `connection.py`, `web/main.py`.
   - Blast radius to trace first (AGENTS.md §4): `scripts/sync_to_supabase.py`, `sync_from_supabase.py`, `run_scheduled_pipeline.py` local failover, `send_subscription_reminder.py --live-email`, and my own read-only production queries, which will need the flag.
2. **Deploy gate (you, in the Render dashboard):** set Auto-Deploy to "After CI Checks Pass" on the web service, the worker and each cron. I'll add `autoDeployTrigger: checksPass` to the services declared in `render.yaml` so the file matches.
3. **Rollback safety:** `ci/checkpoint_manager.py rollback` asks for a typed confirmation and runs the L2 suite on the target commit before force-pushing; remove `--skip-checks` or make it print a loud ledger entry.
4. **CI parity:** Python 3.14 in both workflows (matching `Dockerfile`), and stop running the full suite twice (merge `p0_release_gate.yml` steps into `ci.yml` as separate jobs).

## Phase 2 — Protected contract suite (days 2–4)

New folder `tests/contracts/` (protected). Every test states a rule from outside the code (OWASP ASVS item, a page promise, or a past escape) in its docstring.

- **Harness** `tests/contracts/harness.py`:
  - starts the app with `TESTING` unset and `ALLOW_TEST_KEYS=1`, against the CI Postgres service;
  - issues real signed session and admin cookies with the existing signers `web/common.py:245 _generate_user_session_token` and `:319 _generate_admin_token`;
  - signs Supabase-style ES256 tokens with a test key pair served from a local JWKS stub (so the real Tier 1 path in `supabase_auth.py:211` runs);
  - blocks all outbound sockets except localhost;
  - freezes time with a small clock helper (see Phase 3).
- **Negative security tests** (extend `tests/security/test_wave1_hardening.py`, which moves here): forged/unsigned/expired/no-`exp` tokens rejected; every `/auth/callback` branch escapes a script payload; user A cannot read or write user B's ledger, Research Desk threads, audits or orders; admin routes refuse without a real admin cookie plus TOTP; DB failure during admin lookup refuses; every bypass header and query parameter (`x-admin-key`, `test_access`, `unlocked`, `x-unlock-preview`, `sr_dev_` keys, `sig_sim_*`, OTP `123456`) is refused when `TESTING` is unset.
- **Route inventory test:** walks every registered route (recursing into included routers) and requires each to be listed in `tests/contracts/route_policy.yaml` as public, signed-in, subscriber or admin; an unlisted or mismatched route fails. New routes can't ship without a declared policy.
- **Money and races (on Postgres):** 20 simultaneous OTP verifications and credit spends produce exactly one success; a refund counts only with a Razorpay refund ID; webhook replay is idempotent by behaviour, not by the word "idempotent". Reuse `tests/integration/test_postgres_credit_grant_concurrency.py`.
- **Migrations:** run `init_db()` from an empty Postgres and from an empty SQLite; compare table and column sets; fail on drift. Also fixes the stale docstring at `connection.py:494`.
- **Promise registry** `tests/contracts/claims.yaml` + test: each public promise maps to a check. First entries: Discovery timing copy vs the `close-run` cron in `render.yaml` (UTC→IST); email send times vs their crons; each pricing-page perk vs the entitlement code that grants it; refund policy wording vs refund code; no literal clock time next to "released/updated/evaluated" in templates.

**Removing security `TESTING` branches (the report's item 5):** for the ~35 auth, paywall and billing branches, replace "if testing, accept X" with injected test configuration (test signing key, test OTP secret, test Razorpay keys) so tests exercise the production path. Do this file by file after the matching contract test exists and fails without the fix: `core/auth/otp.py`, `core/auth/supabase_auth.py`, `web/routers/admin.py`, `web/common.py`, `web/routers/markets.py`, `web/routers/dossier.py`, `core/billing/razorpay.py`, `web/routers/auth_billing.py`. The ~60 remaining branches (LLM stubs, network isolation, schedulers) stay for now and are listed in a tracked allowlist; a CI check fails if a new `TESTING` reference appears outside it. This touches auth and billing, so it starts with the `implication-preflight` skill.

## Phase 3 — Clean up the fast suite (days 4–5)

- `tests/conftest.py`-equivalent for unittest: a `tests/base.py` with `IsolatedDbTestCase` that copies a seeded template DB to a temp path per test class (`TEST_DB_PATH`), so tests stop sharing and mutating `./test_reports.db`. Delete the stale `tests/test_reports.db`.
- Set `TESTING=1` once in the runner (`tests/__init__.py`), remove the 36 import-time assignments, and replace the 30 mid-test unsets with a context manager that also blocks sockets.
- **Clock control:** add `core/clock.py:now_ist()` and route the wall-clock gates through it (`core/db/discovery.py:165,277`, `web/main.py:527,646`, weekend and hour cut-offs in `scripts/run_scheduled_pipeline.py:209-253`, `core/mailer_health.py`). Tests set the clock; add cases for before/after the gate, Friday evening, Monday morning, an NSE holiday, and 31 Dec → 1 Jan (`core/ingestion/market_calendar.py:114`).
- **Realistic-size fixture:** a generated, personal-data-free database with production-like row counts (about 300 reports, 15-row discovery editions, 2,000 schemes) for page tests, with byte and DOM-node budgets on `/`, `/funds`, `/etfs`, `/discovery`.
- **Browser smoke test (CI only):** Playwright against the app on the fixture: sign-in page, a dossier, the pricing modal, `/discovery`, `/admin` with a real admin cookie; assert zero console errors and that every `onclick` handler resolves. Remove the unused `selenium` pin. Fix `pytest.ini` paths that don't exist.
- **LLM paths:** record three real model outputs as golden files and run the existing quality checks (`verify_stock_report`, prose uniqueness, number parity) against them with production strictness, instead of the loosened `TESTING` branch.

## Phase 4 — Static scans that can't be talked round (day 6)

- `scripts/verify_reality_audit.py`: walk the whole repo (root modules, `scripts/`, `ci/`, `tests/`), keep the gates as a lint, and fix the three weakest: Gate 6.1 flags any `except` in auth, billing or admin code that returns a truthy value or a user object; Gates 8.1/8.3 are replaced by the behaviour tests in Phase 2; Gate 7.5 points at the QoS module actually imported.
- Add third-party scanners as CI jobs: `actionlint` and `zizmor` for workflows, `bandit` for Python, `pip-audit` for dependencies, and a secret scanner. They weren't written by these agents.
- **Doc-claims check** `scripts/check_doc_claims.py` (extend the existing `scripts/audit_doc_line_refs.py`): fail if a doc cites a script or test path that doesn't exist; fail if a new ledger row contains "N/N", "100/100" or "gates passed" without a CI run link or commit SHA that exists. Existing history is grandfathered by line number; the 44 broken references are corrected or marked "(removed)".
- Stop presenting the project-audit score as a quality claim: `core/audit/project_auditor.py` reports findings and an explicit "not a security assessment" line; probe exceptions become findings.

## Phase 5 — Lock it (half a day)

- **Claude Code hook** (`.claude/settings.json`, PreToolUse on Edit/Write/Bash): block changes to `tests/contracts/**`, `scripts/verify_reality_audit.py`, `scripts/check_doc_claims.py`, `.github/workflows/**`, `.claude/settings.json`, `render.yaml` deploy keys. The agent must explain the needed change and you approve in chat; I then make the edit with the hook temporarily lifted by you. A Stop hook runs the fast suite and gates when code changed.
- **CI "protected paths" job:** on every push, list changes under protected paths in the job summary and fail unless the commit message contains `Protected-Change-Approved: <your initials + date>`. This is what catches Gemini and Codex, which don't run Claude hooks.
- **Commit trailers:** each agent's rules require `Agent: <name>`; CI warns on commits without one.
- **One rulebook:** `AGENTS.md` trimmed to judgement rules plus a pointer table ("this rule is enforced by: hook / CI job / contract test"); `.agents/rules/backup_protocol.md`, `.antigravity/hooks.json` and `.antigravity/docs/PENDING_TASKS.md` reduced to pointers. Add the three rules from the report (negative test first; justify any 200 on another user's ID; flag every fallback in auth, payments or data access).
- `ESCAPES.md`: one row per bug found after merge (what, found by, which check should have caught it, new guard). Seeded with the November findings.

## Phase 6 — Watch production (day 7)

`.github/workflows/production_checks.yml` (protected, scheduled hourly, read-only, opens a GitHub issue on failure) running `scripts/production_checks.py`:

- latest Discovery edition's publish time falls in the promised window on trading days;
- `/api/health/mailers` is 200 and both editions sent;
- a nonsense URL returns a branded HTML 404;
- page weight and DOM budgets on `/`, `/funds`, `/etfs`;
- security headers on `/login` and `/admin`;
- sitemap parses as XML;
- a forged-token and a foreign-`user_id` request are refused on the live site (harmless negative probes).

Monthly audit rotation by access (source incl. CI/Docker; database grants/RLS/slow queries; live site and logs; quarterly business truth: pricing vs grants, refund policy, a real backup restore, email rendering). Each finding needs a reproducer before it enters `PENDING_TASKS.md`.

## Separate hygiene items (your call, outside the test code)

- Move the repo out of the Google Drive-synced folder, or exclude `.git/`, `.env`, `*.db`, `backups/`, `.checkpoints/`, `scratch/` from sync. Git plus `./run.sh backup` already cover recovery.
- Delete stale agent context: `moatnomics_codebase.txt`, empty `prod.db`/`web.db`/`analytics.db`, `apply_p0_credit_hardening.sh`, and old `audits/` reports.

## Order and effort

| Phase | Effort | Why this order |
|---|---|---|
| 0 Finish in-flight | 30 min | clean tree |
| 1 Safety rails | 1 day | stops accidental production writes and red deploys today |
| 5 (hook + CI protected-paths only) | 2 hours | lock the judge before writing it |
| 2 Contract suite + auth `TESTING` removal | 3–4 days | closes the most escape classes |
| 4 Static scans + doc claims | 1 day | cheap, independent |
| 3 Fast-suite cleanup, clock, fixtures, browser smoke | 2 days | reliability and UX coverage |
| 6 Production checks + rest of 5 | 1 day | closes promise-vs-reality |

Each phase is its own commit series with tests, living-docs update, one backup, and a line in `PENDING_TASKS.md` (new Task 11, linked from Task 9).

## Verification

- **Phase 1:** with `.env` present and no flag, `python -c "from core.db.connection import get_db_connection, is_postgres_connection; print(is_postgres_connection(get_db_connection()))"` prints `False`; with `ALLOW_PRODUCTION_DB=1` it prints `True`. Push a commit with a deliberately failing test on a throwaway branch pointed at a test service, or confirm in Render's event log that a deploy shows "waiting for checks".
- **Phase 2:** the contract job runs with `TESTING` unset on Postgres. Prove it has teeth by mutation: re-introduce each November bug on a scratch branch (Tier 3 token fallback, body `user_id`, fail-open admin lookup, unescaped `next`) and confirm the suite goes red for each. Record the red/green run links in `ESCAPES.md`.
- **Phase 3:** run the suite twice in random order (`python -m unittest` with shuffled module order) and at two frozen times; results identical. Page budgets fail on the current 608-card homepage until Task 9's fix lands (expected; mark as known-failing with the Task 9 link, not skipped silently).
- **Phase 4:** the doc-claims check fails on the current manual, then passes after the 44 references are corrected. `zizmor`/`actionlint` pass on the hardened workflows.
- **Phase 5:** attempt an edit to `tests/contracts/` from Claude Code and see it blocked; push a protected change without the approval line and see CI fail.
- **Phase 6:** run the workflow manually; temporarily point one check at a wrong expectation to confirm an issue is opened, then revert.
- Throughout: `python3 -m unittest discover -s tests`, `scripts/verify_reality_audit.py`, and the new CI jobs green before each push.
