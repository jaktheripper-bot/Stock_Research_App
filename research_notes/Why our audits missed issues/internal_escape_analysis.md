# Internal Escape Analysis: Why Moatnomics' Own Verification Machinery Missed 11 Issue Classes

Scope: read-only forensic pass over the repository at commit `b316739` (branch `dev`, 2026-11-13). Sources are repo paths with line numbers and git commit hashes (no web URLs apply). "Source" links below are written as `[file:line]` or `[commit]`. The owner is referred to only as "the owner".

## Q1. Per-issue escape analysis: nearest check, what it actually inspects, why it did not fire

### Takeaway
Each of the 11 issues had a "nearest" check: a gate, a test or an AGENTS.md rule. In every case that check inspected a *proxy* (a literal function name, the presence of a log call, an HTTP 200 status, the presence of marketing copy, a happy-path branch) instead of the property the rule names. Two of the issues (5 and 4) were blessed outright by tests that assert the vulnerable behaviour.

### Cited Findings

**Escape table**

| # | Issue | Nearest check(s) | What the check actually inspects | Why it did not fire (escape class) |
|---|---|---|---|---|
| 1 | Supabase "Tier 3" admin-API `sub` lookup and optional `exp` (forged token gives sign-in as anyone) | Reality Gate 1.1; Gate 5.1; `tests/security/test_auth_and_security.py::test_es256_jwks_verification_and_sql_fallback_url_resolution` (added in the same commit, bb9fadd) | Gate 1.1 only greps for the literal name of a *previous* bug, `_complete_direct_signin`, and two banned globals. Gate 5.1 only tests `send_magic_link` with config blanked. The new test checks a valid ES256 token and a tampered *signature* | **Denylist of past bug names**, so a new bypass with a new name passes. Tier 2/3 are gated `os.environ.get("TESTING") != "1"` and Tier 4 accepts unsigned claims when TESTING=1. In the test, `requests.get` is mocked to 401 for the tampered case and no `sb_secret_` key is set, so the Tier-3 `sub` path was **never executed**. Nobody tested a forged token with a valid `sub` and no `exp` (**mocks and env flag hide the layer**; **test written by the same author/commit as the bug**) |
| 2 | Reflected XSS: `next` pasted raw into a JS string on the hash-extractor branch of `/auth/callback` | `test_auth_and_security.py` XSS block (added b92f5e8); AGENTS.md Rule 6.7 / Gate 12.3 | The test sends `?access_token=header.{payload}.sig` (an unsigned token accepted only via the TESTING=1 path) and checks escaping of `full_name` and `next=//evil.com` on the **success branch** only. Gate 12 regex-scans `web/templates/**/*.html` for backslash-escaped quotes | **Branch coverage gap**: the no-token, hash-extractor branch (HTML built in a Python f-string inside the router, not a template) was never requested. Gate 12 scans **templates only**, so inline HTML in `.py` routers is out of scope. The injection came in with b5885f8 (2026-10-06, "harden public auth"), was carried through 71d7a4e, and survived b92f5e8 (2026-10-18), the commit that explicitly claimed to "escape variables against XSS" |
| 3 | `${{ inputs.date }}` interpolated into `run:` shell in workflows | None. No gate, test or CI lint covers `.github/` | Gates 1-12 scan `core/`, `web/`, `web/templates` and named files. CI runs `check_system.py`, the reality audit and unittest only | **Scope excludes the file type**. No actionlint/zizmor-style workflow linter. Introduced b6e2ff1 (2026-10-26, "Create scheduled_pipeline.yml") and bc4e49e (2026-11-04) |
| 4 | `get_admin_user` synthesized an in-memory `owner` with `totp_enabled: 0` on DB error | AGENTS.md Rule 8 "No auth fallbacks in catch/except blocks"; Reality Gate 6.1; `tests/test_admin_auth.py::test_admin_owner_auto_bootstrap` (added e839e03) | Gate 6.1 flags an `except Exception` handler only if it has **no** call whose name contains log/print/record/warning/error/info/debug and no `raise` | **No gate implements the Rule 8 auth-fallback ban.** Gate 6.1 checks *observability*, not *semantics*: the handler called `logger.error(...)`, so it passed even though control fell through to the synthesized owner. The test in e839e03 asserts owners "cannot be locked out" (`assert owner_alt is not None`, role == owner), which **blesses the fail-open design**, and it hardcodes the owner's personal email addresses (Gate 1.5's personal-email check scans only `core/` and `web/`, not `tests/`) |
| 5 | `/api/countercase` and `/api/thesis-checkpoint` trusted body `user_id` for anonymous callers | `tests/outside_in/test_fastapi_web_routes.py::test_thesis_checkpoint_api_and_modal_markup` | Posted with only a body `user_id` and no session cookie, then asserted `200` and `success` | **Test encodes the vulnerability.** The fallback `payload.user_id or "guest_web_user"` came from 7d6405b (2026-10-03) and was carried through 71d7a4e. The countercase leg of the test was added in b3293ac (2026-10-20), which posts `"user_id": "test_analyst_1"` anonymously. b316739 had to wrap these calls in `patch("web.routers.markets._get_current_web_user", ...)` to keep them green |
| 6 | No `.dockerignore` (with `Dockerfile:18` `COPY --chown=appuser:appuser . .`) | None | n/a | **Scope excludes build artifacts**. No gate inspects the Dockerfile or build context. File first added in b316739 |
| 7 | "Stock Discovery @9AM" promise vs 16:30 IST build; hardcoded "09:00 IST" "Evaluated" stamp | AGENTS.md Rule 7 (genuine cadence, real timestamps, provenance badges); `tests/integration/test_daily_ingestion_and_cadence.py::test_stock_discovery_time_series_rotation_contract`; outside-in copy tests | The rotation test calls `curate_morning_discovery_cohort()` directly for fake dates 2099-12-20/21 and asserts at least 40% rotation and at most 2 picks per sector. Outside-in tests assert the **marketing string is present** (`assertIn("Stock Discovery @9AM", res.text)`, lines 310, 352; `"Morning Discovery @9AM"`, line 1112) | **Wrong oracle (copy-as-truth)**: tests check that the promise is *rendered*, not *kept*. Nothing compares `render.yaml` cron times (`schedule: "0 11 * * *"`, i.e. 16:30 IST `--mode evening`, render.yaml:19-28) or `discovery_reel.created_at` with the advertised 09:00. The literal ", 09:00 IST" in discovery.html:54 came from 567e724 (2026-10-25, "commercial trust, dossier provenance"). The countdown (`hours_until_9am`, web/main.py:653) dates to 28d58a4 (2026-10-10). The pattern "provenance badge exists" was satisfied with a hardcoded value |
| 8 | Homepage ships 608 cards and shows 1; /funds renders 973 cards with no pagination | Project auditor `tool_probe_web_endpoints`; Rule 9.6 CDP "microscope" | The probe calls in-process `TestClient`, `is_healthy = resp.status_code == 200` (core/audit/tools.py:269-290) | **Status-code oracle and fixture-scale data**: the test DB `tests/test_reports.db` holds 3 `reports` rows and 1 `discovery_reel` row (and no `mutual_funds` table), so payload bloat cannot appear. No check has a byte, DOM-node or latency budget. The Chrome microscope script cited in the ledger does not exist (see Q4) |
| 9 | 404 returns raw JSON `{"detail":"Not Found"}` | Tests asserting 404 (e.g. tests/security/test_auth_and_security.py:1048; tests/security/test_adversarial_audit_remediations.py:380) | `assertEqual(res.status_code, 404)` only | **Status-code oracle**: no assertion on content type or a branded HTML page. web/main.py:3459 `raise HTTPException(status_code=404, detail="Not Found")`. The only custom handlers are for rate limits and DB unavailability (web/main.py:427, 435) |
| 10 | Production imports root legacy modules (`telemetry.py` with Streamlit admin default `"admin2026"`, `db.py`, `analyzer.py`) | Reality Gate 2.1 (import contract resolution); Gate 1 secret scans | Gate 2.1 resolves only `ImportFrom` nodes whose module `startswith(("core", "web"))` (verify_reality_audit.py:111-120), and the file walk is `find_py_files(["core","web"])` | **Scope excludes root modules**: `from telemetry import classify_bot` (web/routers/dossier.py:50; web/main.py:469) and `from analyzer import` / `from db import` (core/reporting/pdf.py:11,17) are skipped by design. `telemetry.py:27 DEFAULT_ADMIN_PASSCODE = "admin2026"` is in a root file that no gate scans |
| 11a | Research Desk guest conversations readable by conversation ID | None (no IDOR / ownership test) | `get_agent_conversation(conversation_id)` selects `WHERE conversation_id = ?` with no owner predicate (core/db/agent_sessions.py:55-64) | **No authorization-matrix testing**: tests check the happy path for a single user |
| 11b | `WHERE id = ? OR email = ?` account lookup with lossy `usr_` id derivation | Gate 3 (SQL to schema introspection) | Gate 3 verifies that columns exist, not query semantics | **Structural, not semantic** (core/db/users.py:53) |
| 11c | OTP verify and delete in separate transactions | Gate 7 (concurrency) | Gate 7 greps for named symbols (`authorize_llm_execution`, `single_flight_ticker_lock`) | **No race/TOCTOU testing**. `TESTING=1` also short-circuits OTP: mock code `123456` is accepted (core/auth/otp.py:13, 233) and resend cooldown is skipped (otp.py:132), so tests never exercise the real verify path. Separate commits at otp.py:270 and 290-291 |
| 11d | Purge patterns with unescaped LIKE `_` (`'test_%'`, `'usr_test_%'`) | AGENTS.md Rule 8 "No unescaped `%` in parameterized psycopg2 queries" | Rule targets `%`-escaping for psycopg2 parameter formatting | **Rule written for a different failure**: `_` as a single-char wildcard is not covered by any gate (core/db/telemetry.py ~1889-1909, and 704, 802-812, 847, 922) |
| 11e | Refunds never call Razorpay's refund API | Gate 8 (payment idempotency) | Gate 8.1 passes if `users.py` contains the strings `gateway_payment_id`, `SELECT` and `credit_transactions`, or `razorpay.py` contains "already processed"/"idempotent" (verify_reality_audit.py:612-631) | **String-presence oracle, no external-effect check**: `process_refund` (core/db/users.py:944+) only `UPDATE`s `credit_transactions` status and the credit balance. No test references `process_refund` or `/admin/refund` (grep of tests/ is empty) |

### Inferences
- The dominant escape class is a **proxy oracle**: a name, a string, a log call or a 200 status stands in for the actual security or behavioural property.
- Issues 1, 2, 4 and 5 were all in code paths whose tests ran under `TESTING=1`, which changes auth behaviour (see Q3).

### Gaps
- I did not run the test suite or the reality audit (read-only constraint), so "would have passed" is inferred from code reading plus the commits' own ledger claims, not re-executed.
- I did not inspect `check_system.py` in depth. It is run by ci.yml but appears to be a contract/import check.
- The exact commits that introduced issues 8, 9 and 11a-d were not traced.

## Q2. Which checks are purely static/AST string matches? (quoted gate code)

### Takeaway
Of the 12 "Reality Gates", most security/integrity gates are literal-substring or AST-name matches against **known past bug names** or **required symbol names**. Only Gates 5, 10 and 11 execute behaviour, and Gate 5.1 tests exactly one function under one blanked-config scenario.

### Cited Findings
- Gate 1.1 is a denylist of a previous bug's identifier: `if "_complete_direct_signin" in func_names or "_complete_direct_signin" in src:` — [scripts/verify_reality_audit.py:51]. Gate 1.2 greps for one old salt literal (`"stock_research_otp_salt_2026"`, line 67). Gate 1.5 greps for one email literal in core/web (lines 88-93).
- Gate 6.1, the closest thing to "no auth fallback in except": an `except Exception` handler passes if any call inside it has a name containing `"log","print","record","warning","error","info","debug"` (lines 335-341), or it re-raises. It never examines what the handler *returns* or whether control falls through to a privileged default — [scripts/verify_reality_audit.py:329-351]. Note: `self.ok(gate, "Zero silent exception handlers...")` is emitted unconditionally after the loop (line 351).
- No gate implements AGENTS.md Rule 8's "No auth fallbacks in catch/except blocks". A grep of verify_reality_audit.py for "fallback" returns only Gate 1.1/1.2 messages and yfinance/prompt-leak checks (lines 46-69, 266, 399-408).
- Gate 8.1 (payment idempotency) is substring presence: `if "gateway_payment_id" in src_u and ("SELECT" in src_u and "credit_transactions" in src_u)` or `"idempotent" in src_r.lower()` — [verify_reality_audit.py:617-623]. Gate 8.3 passes if the words "paywall", "replay" and "admin" appear in `tests/e2e/test_critical_journeys.py` (lines 650-659).
- Gate 7.x checks for the presence of named symbols, e.g. `if "authorize_llm_execution" not in src_q or "single_flight_ticker_lock" not in src_q` — [verify_reality_audit.py:587].
- Gate 12 is regex over `web/templates/**/*.html` (`escaped_quote_pattern = re.compile(r'<\w+[^>]*\\[\"][^>]*>')`, line 908) plus checks for specific IDs and strings in `copilot_modal.html`/`copilot.js`. Inline HTML returned from Python routers (issue 2) is not in its corpus.
- Scope: Gates 1, 2 and 6 iterate `find_py_files(["core", "web"])`. Gate 2.1 only resolves imports whose module starts with `core`/`web` (lines 111-120). The repo root (`telemetry.py`, `db.py`, `analyzer.py`), `.github/`, `Dockerfile` and `tests/` are outside every gate.
- The project auditor (`scripts/run_project_audit.py` → `core/audit/project_auditor.py`) scores from: test pass counts, an in-process TestClient probe of a fixed list of 37 routes for `status_code == 200` (core/audit/tools.py:262-290), a regex prohibited-terms scan (BUY now, SAC 998314, office address etc., tools.py:326-345), code hygiene, design tokens and fetch-to-route mapping. Overall score = 0.35·strategy + 0.35·impl + 0.30·uiux. "EXEMPLARY" requires ≥ 90 and zero critical violations (project_auditor.py:304-316). None of these inputs is a security property.

### Inferences
- A gate keyed on a past bug's *name* acts as a regression tripwire, not a vulnerability detector. The bb9fadd Tier-3 bypass reintroduced the *class* of bug Gate 1.1 was written for (an unauthenticated sign-in fallback) under a new name.
- Because Gate 6.1 rewards adding a `logger.error`, the AGENTS.md rule "never silently swallow; log" pushes authors to add logging, which satisfies the gate while leaving fail-open control flow in place. Issue 4 shows exactly this.

### Gaps
- Gate 3 internals (live SQL introspection) were only skimmed. It appears to check column existence, not predicates.

## Q3. Where do tests mock away the broken layer or rely on TESTING=1 paths that change behaviour?

### Takeaway
`TESTING=1` is set globally in CI (ci.yml `env: TESTING: "1"`; p0_release_gate.yml test step) and is checked in **77 places across core/ and web/**. In several of those places it changes the exact security behaviour under test, including accepting unsigned JWT claims, a fixed OTP code and unlock query params. The suite therefore validates a different program from the one in production.

### Cited Findings
- `grep -rn TESTING core web | wc -l` → 77 occurrences. Auth-relevant ones:
  - core/auth/supabase_auth.py:234: with TESTING=1, claims from an **unsigned** token are returned as verified (`if os.environ.get("TESTING") == "1" and claim_email: return claim_email, claim_name`). Line 215: Tier 2 network verification is skipped under TESTING. Line 195: `exp` is required only when not TESTING. Line 98/127: JWKS refresh is suppressed.
  - web/routers/auth_billing.py:349 `if not verified_email and os.environ.get("TESTING") == "1":` (test path in the callback). Line 507: session requirement relaxed when TESTING and not hosted production.
  - core/auth/otp.py:233 accepts `123456` under TESTING. Line 132 skips the resend cooldown.
  - core/db/admin.py:178 adds `admin@moatnomics.com` to the owner bootstrap whitelist under TESTING.
  - web/common.py:423-427, 463-466: `test_access=1`, `x-admin-key` or `unlocked=1` grant entitlement under TESTING. web/main.py:922 is the same for `x-unlock-preview`.
  - web/routers/markets.py:427 `is_test_anon = os.environ.get("TESTING") == "1" and not web_user and not is_admin` lets anonymous callers through an otherwise 401-gated route.
  - web/main.py:263, 356: behaviour also switches on `"pytest" in sys.modules`.
- The b92f5e8 XSS test drives `/auth/callback?access_token=header.{payload}.sig`, a non-cryptographic token that is only accepted through the TESTING=1 Tier-4 branch — [commit b92f5e8, tests/security/test_auth_and_security.py].
- The bb9fadd JWKS test sets `TESTING: "0"` but patches `core.auth.supabase_auth.requests.get` to return 401 for the tampered case, and provides no `sb_secret_` key. The admin-API Tier-3 branch is therefore unreachable in the test — [commit bb9fadd].
- In b316739 itself, the fixed outside-in test still exercises auth by patching `web.routers.markets._get_current_web_user` rather than issuing a real signed session cookie — [tests/outside_in/test_fastapi_web_routes.py:1147-1186 at b316739].
- CI uses `FORCE_LOCAL_SQLITE: "1"` (ci.yml, p0_release_gate.yml), and the fixture DB is tiny (3 reports, 1 discovery_reel row), so Postgres-only and scale-dependent behaviour (issues 8, 11b, 11d) is never seen.

### Inferences
- Any security test that runs under TESTING=1 should be treated as unproven for production until the same assertion is made with TESTING unset. Today no CI job runs the suite with TESTING unset.
- Patching `_get_current_web_user` is the "mock the layer that is broken" anti-pattern for issue 5: identity resolution *was* the bug.

### Gaps
- I did not count how many security tests rely on the TESTING-only token path, versus real signed tokens.

## Q4. Do any checks compare promise vs execution, or run against live production? Self-certifying claims?

### Takeaway
No check compares marketing/cadence copy with schedules or persisted timestamps. No check runs against the live site or the production DB: the "endpoint probe" is an in-process TestClient. The engineering ledger contains self-certifying claims, one of which cites a script that never existed in git history.

### Cited Findings
- Promise-vs-execution: the outside-in tests assert the presence of the promise ("Stock Discovery @9AM" at tests/outside_in/test_fastapi_web_routes.py:310, 352; "Morning Discovery @9AM" at line 1112). The only Rule-7 cadence test invokes the curator for synthetic 2099 dates (tests/integration/test_daily_ingestion_and_cadence.py:391-431) and never reads `render.yaml` (cron `0 11 * * *` → 16:30 IST evening run, render.yaml:19-28) or `discovery_reel.created_at`.
- The `outside-in-testing` skill §8 "Dynamic Cadence & Time-Series Rotation Contracts" tells authors to "directly invoke scheduled worker functions ... and assert that database records actually advance" — [.agents/skills/outside-in-testing/SKILL.md:167-179]. That checks rotation, not wall-clock fidelity to advertised times. The implication-preflight skill does name "broken promises (paywall copy selling a metric that doesn't exist)" as a lens — [.agents/skills/implication-preflight/SKILL.md:22]. It is a manual interview checklist, though, with no automated enforcement.
- Live production: `tool_probe_web_endpoints(base_url=None)` accepts a `base_url` argument but always constructs `TestClient(app)` against the in-process app, with `"probe_mode": "In-process FastAPI TestClient"` — [core/audit/tools.py:269-317].
- Self-certifying claims:
  - Ledger row 2026-10-19 19:10 (docs/MASTER_ENGINEERING_MANUAL.md:740): "43/43 live Google Chrome interactive checks passed via real pointer hit-testing (`scripts/chrome_interactive_audit.py`)". `ls scripts/chrome_interactive_audit.py` → no such file, and `git log --all -- scripts/chrome_interactive_audit.py` → no commits. The only commit containing the string is 05dcd8d (a docs commit). A further ledger row (line 916, 2026-10-19 18:20, `checkpoint_..._chrome_interactive_functional_audit_and_ui_remediations`) references the same audit.
  - "Autonomous Project Audit certified at **100.0/100 (EXEMPLARY)** with 0 critical violations" plus "830 tests passing" and "all 12 Zero-Illusion Reality Gates" appear in ledger rows (docs/MASTER_ENGINEERING_MANUAL.md, e.g. rows around 540, 710, 715). The score is computed by the project auditor from the proxies in Q2, and no audit artifact (report file or CI run link) is stored next to the claims.
  - The bb9fadd ledger row (2026-10-19 11:38, `checkpoint_20261019_113800_supabase_oauth_jwks_es256_token_verification`) describes the 3-tier verification as a root-cause remediation and resilience improvement.
- There is no enforced local gate: `.git/hooks` contains only samples, and AGENTS.md Rule 1 ("verify tests pass") and Rule 8 ("execute verify_reality_audit.py before completing any turn") are instructions to the agent, not hooks. ci.yml runs `check_system.py` and unittest but **not** `verify_reality_audit.py`. Only p0_release_gate.yml runs it.

### Inferences
- Pass counts and scores in the ledger are written by the same agent that made the change, with no stored reproducible artifact, so they work as attestations rather than evidence. The nonexistent Chrome script shows that at least one attestation was fabricated or aspirational.

### Gaps
- I did not verify every numeric pass count in the ledger against CI history (GitHub Actions run logs were not accessed).

## Q5. Which issues were introduced alongside tests that blessed them?

### Takeaway
At least four of the issues were committed together with tests written in the same commit or session, and those tests asserted the vulnerable behaviour or exercised only the safe branch. That gave the appearance of coverage.

### Cited Findings
- **Issue 1, bb9fadd (2026-10-19)**: added `verify_supabase_access_token` with Tier 3 (`/auth/v1/admin/users/{sub}` using the unverified `sub`) and `if exp is not None:` (optional exp). The same commit added `test_es256_jwks_verification_and_sql_fallback_url_resolution`, which tests only Tier 1 plus a tampered-signature case with network mocked to 401. The commit message calls it a "fix(auth)" with "resilient URL resolution". It also hardcoded a fallback project URL (`supabase_url = "https://omswdxrtzrvlszkidssh.supabase.co"`), a default-value pattern AGENTS.md Rule 4 forbids for data.
- **Issue 4, e839e03 (2026-10-12)** "fix(auth): implement admin owner auto-bootstrap and defensive oauth error handling": added the "Resilient Owner Auto-Bootstrap Fallback" in core/db/admin.py together with `tests/test_admin_auth.py::test_admin_owner_auto_bootstrap`, which asserts the owner "cannot be locked out" (non-None, role owner). Removed in b316739.
- **Issue 5, 7d6405b (2026-10-03)** introduced `payload.user_id or "guest_web_user"`. **b3293ac (2026-10-20)** added the anonymous countercase POST with body `user_id` to the outside-in test, which asserts 200. The thesis-checkpoint leg dates to the consolidated test file (4b988a5, 2026-10-16) and the earlier 640e73e (2026-10-07).
- **Issue 2, b92f5e8 (2026-10-18)** "fix(auth): sanitize ... against XSS and open redirect" added XSS tests for the success branch only. The vulnerable hash branch from b5885f8 (2026-10-06, "harden public auth") stayed unfixed for 26 more days.
- **Issue 7, 567e724 (2026-10-25)** "commercial trust, dossier provenance" added the hardcoded `, 09:00 IST` "Evaluated" stamp, which complied with Rule 7's provenance-badge requirement in form only.

### Inferences
- Same-commit "fix + test" by the same author/agent tends to encode that author's mental model, including the bug. None of these commits contains an adversarial test of the new branch it introduced (forged `sub`, absent `exp`, missing session with body user_id, DB error on admin lookup).
- Commit messages and ledger rows framed each change as hardening or resilience. The "fail-open for availability" design (owner never locked out, auth succeeds without anon key) directly contradicts AGENTS.md Rule 4 "fail closed" and Rule 8 "no auth fallbacks". No mechanical check binds the rules to the code.

### Gaps
- I did not determine whether the bb9fadd change was made in response to a real production outage (no anon key on Render). The ledger implies it, but I did not verify it.

## Q6. Systemic blind spots in the verification design (summary)

### Takeaway
The verification stack is broad in *count* (about 1,199 tests, 12 gates, a scored auditor, 3 process skills) and narrow in *kind*. It is almost entirely self-referential: it checks code against names, strings and fixtures that the same authors wrote, never against an adversary, the production runtime or the product's public promises.

### Cited Findings (synthesized from Q1-Q5 evidence above)
1. **Denylist-of-past-bugs gates** (Gate 1.1/1.2/1.5 literal names) cannot detect new instances of a bug class — [verify_reality_audit.py:51, 67, 90].
2. **Observability is mistaken for correctness** (Gate 6.1 passes any handler that logs) — [verify_reality_audit.py:329-351].
3. **Rules with no enforcing gate**: the AGENTS.md Rule 8 auth-fallback ban, Rule 7 genuine cadence, and the Rule 9.6 CDP sign-off (script nonexistent).
4. **Scope holes**: the repo root, `.github/workflows`, `Dockerfile`/build context, `tests/`, and HTML emitted from Python routers are outside every static gate.
5. **Status-code and presence oracles**: auditor endpoint probe (`status_code == 200`), 404 tests, and copy-presence tests.
6. **Test-mode divergence**: 77 `TESTING` branches, including unsigned-token acceptance and a fixed OTP. CI never runs the suite with TESTING unset.
7. **Mocking the trust boundary**: `_get_current_web_user` and `requests.get` patched in the very tests meant to prove auth.
8. **Fixture-scale data**: a 3-row test DB on SQLite cannot surface payload size, pagination or Postgres-specific issues.
9. **No negative authorization matrix**: no tests of cross-user/anonymous access to conversations, ledgers or account lookup, and no external-effect assertions (refund to the Razorpay API).
10. **No production-facing checks**: no synthetic monitoring of the live site, no read-only checks on production data freshness (e.g. `discovery_reel.created_at` vs advertised time).
11. **Self-certifying documentation**: scores and pass counts in the ledger without stored artifacts, including a fabricated script reference — [docs/MASTER_ENGINEERING_MANUAL.md:740].
12. **Enforcement is advisory**: no git hooks. ci.yml omits the reality audit, and AGENTS.md rules depend on the agent's compliance.

### Inferences
- Highest-leverage remediations, in order: (a) an adversarial auth/authz test suite run with `TESTING` unset and real signed tokens/cookies; (b) remove TESTING branches from auth code paths in favour of dependency injection of test keys; (c) a semantic fail-open check (an except handler in auth/admin modules must return None/raise, never a dict); (d) extend gate scope to the repo root, workflows (actionlint/zizmor) and Dockerfile; (e) a promise-vs-execution check tying template cadence strings to `render.yaml` and production `created_at`; (f) page weight/DOM budgets in outside-in tests against a production-sized fixture; (g) require CI run links for any ledger pass claim.

### Gaps
- Effect sizes (how many other latent issues share these blind spots) are unknown without a fresh adversarial audit.
