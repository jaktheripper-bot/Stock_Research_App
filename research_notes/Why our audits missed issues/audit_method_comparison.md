# Audit Method Comparison: Why Three Audits of One Codebase Found Different Issues

Source abbreviations used below:
- **A** = Gemini/Antigravity "Full-Codebase Security, Reliability & Code-Quality Audit", 2026-11-12 23:15 — [A](file:///Users/lyndonpinto/.gemini/antigravity/brain/a88aca8e-89d0-46bb-afb6-a9596ed5b893/codebase_security_and_quality_audit.md)
- **B** = Codex "Moatnomics database audit", 2026-11-13, checkout `0914737` — [B](file:///Users/lyndonpinto/.codex/.chatgpt-projects/g-p-6aeb6e9f46388191a43eb3a1cf1ea4fb/Moatnomics_Database_Audit_2026-11-13.md)
- **C** = Claude Code third pass, 2026-11-13 (no file; facts taken from the task brief, marked "[C-brief]"; where I re-checked them in the repository I cite the file).
- **Repo checks** = read-only `git grep`/`sed` runs I did against `/Users/lyndonpinto/Documents/Stock_Research_App` at HEAD `b316739` and at `7dcc8e5` (the last commit before A's timestamp, 2026-11-12 23:14:54 +0530).

Timing context: A was written at 23:15 on 11-12, right after commit `7dcc8e5`; commits `a16f692`, `84ce132`, `0914737` followed within the hour, B audited `0914737`, and `b316739` ("audit Wave 1 containment (P0-01/02/03/05/07/09)", 00:25 on 11-13) applied fixes from A before C ran — [git log](file:///Users/lyndonpinto/Documents/Stock_Research_App/.git). So the three audits saw slightly different code; some "disagreements" are just time.

## Q1. Method-by-finding matrix: which audit found what, with which technique, and why the others missed it

### Takeaway
Each audit found what its access let it see. A, reading source only, found the widest range of code-level flaws. B was the only one with live database catalog and statistics access, so it alone could count rows, measure query cost and read grants. C was the only one that looked at the running site, production logs, and site copy against schedules, so it alone found the "9 AM" promise mismatch and the page-weight problems. No single method would have caught all three sets.

### Cited Findings

**Matrix legend for technique:** SR = static code reading; GR = pattern grep; DB = live DB catalog/statistics; LOG = production logs; HTTP = live HTTP probing; BR = real-browser measurement; COPY = site copy vs schedule/DB timestamps; GIT = git history; FS = filesystem/missing-file scan; EMP = local empirical run (compile, migrate, integrity check).

| # | Finding | Found by | Technique | Missed by / why |
|---|---|---|---|---|
| 1 | Unverified JWT Tier-3 fallback (account takeover) | A (P0-01) | SR | B: scope (DB-focused; auth reviewed only for OTP/account lookup). C verified it and **added** LOG evidence: all real sign-ins in 30 days used ES256 JWKS, so Tier 3 was unused and safe to delete [C-brief] |
| 2 | Reflected XSS on `/auth/callback`, stored XSS via `/api/debt/ingest`, `\| safe` Markdown, admin DOM XSS | A (P0-02) | SR | B: out of scope. C: re-checked the fix with a live HTTP probe (script payload came back escaped) [C-brief] |
| 3 | GitHub Actions `${{ inputs.* }}` shell injection | A (P0-03) | SR (YAML) | B: scope. C: did not re-examine |
| 4 | Agent `run_command` substring allowlist, SSRF, secret file read | A (P0-04) | SR | B, C: scope |
| 5 | Shadow owner, fail-open admin auth in `except`, legacy `admin2026` Streamlit admin | A (P0-05) | SR | B: scope. C went further: legacy root `telemetry.py` is **imported by production code** — `web/routers/dossier.py:50`, `web/main.py:469`, `core/db/telemetry.py:10` — and still has `DEFAULT_ADMIN_PASSCODE = "admin2026"` at `telemetry.py:27` — [dossier.py](file:///Users/lyndonpinto/Documents/Stock_Research_App/web/routers/dossier.py), [telemetry.py](file:///Users/lyndonpinto/Documents/Stock_Research_App/telemetry.py) |
| 6 | SQL string building in telemetry/admin queries | A (P0-06) | SR/GR | C: severity overstated because only admins can reach it [C-brief]. Repo check agrees: the admin route types `days` as `int = Query(30, ge=1, le=365)` (`web/routers/admin.py:513`), but `_build_telemetry_time_filter` still puts `{num_days}` and admin emails into SQL with f-strings (`core/db/telemetry.py:789-795`) — [admin.py](file:///Users/lyndonpinto/Documents/Stock_Research_App/web/routers/admin.py), [telemetry.py](file:///Users/lyndonpinto/Documents/Stock_Research_App/core/db/telemetry.py) |
| 7 | Unauthenticated IDOR on `/api/countercase`, `/api/thesis-checkpoint` | A (P0-07) | SR | C confirmed the fix with a live HTTP probe (forged `user_id` → 401) [C-brief] |
| 8 | PDF export LFI/SSRF (`root="."`) | A (P0-08) | SR | B, C: scope |
| 9 | Missing `.dockerignore` | A (P0-09) | FS | Fixed in `b316739` (file dated 00:17, 11-13) — [git log](file:///Users/lyndonpinto/Documents/Stock_Research_App/.dockerignore) |
| 10 | Tests/audit scripts mutate live DB (no `conftest.py`) | A (P0-10) | SR | B ran only four offline tests on copies, so it did not test this. C: not examined |
| 11 | Refunds: fake Copilot refund, `int(target_ref)` crash, no row lock, no Pro revoke | A (P0-11) | SR | **Overlap with B** (see Q2). `int(target_ref)` still at `core/db/users.py:988` — [users.py](file:///Users/lyndonpinto/Documents/Stock_Research_App/core/db/users.py) |
| 12 | Razorpay order created before intent saved | A (P0-12) | SR | B/C: scope |
| 13 | Research Desk conversation IDOR | A (P1-02 item 3) and B (High #1) | A: SR; B: SR **+ DB count** (26 of 44 conversations have turns and no owner) | B narrowed the facts (see Q2) |
| 14 | OTP flaws | A (P1-05 item 5: unsalted sha256, no row lock) and B (High #2: consume in separate transaction, one expired OTP live) | A: SR; B: SR + DB row count | Overlap; different emphasis |
| 15 | Account lookup returns another email's profile; welcome credit not idempotent | B only (High #3) | SR (tracing ID normalisation through `core/db/users.py:31`, `web/common.py:277`) | A: missed despite reading the same files — A's method lists many flaws per file but did not trace the identity-binding path end to end |
| 16 | Supabase RLS on, zero policies, but `anon`/`authenticated` still hold broad grants on 65 tables and 33 sequences; default grants; `postgres` role DSN | B only | DB (catalog, grants, RLS) | A: no DB access (pure source). C: did not query catalog |
| 17 | TLS off on pooler-to-database leg | B only | DB (`pg_stat_ssl`-type check) | Needs a live connection |
| 18 | Zero Storage buckets though uploader targets `backups` | B only | DB/platform inventory | Needs platform access |
| 19 | `fund_audit_jobs.user_id` FK missing in live PG; `mf_current_disclosures.snapshot_id` FK lacks index; SQLite FK enforcement off on fresh and upgraded copies | B (measured) and A (P1-20, claimed from code) | B: DB + EMP; A: SR | Overlap (see Q2) |
| 20 | Query cost: report revisions ~2,125 s / 41,450 calls; BSE resolution ~765 s / 222,793 calls; telemetry 140,225 events, 100 MiB, 7.8 MiB zero-scan index; fund holdings 11,250 dead tuples | B only | DB (pg_stat_statements, pg_stat_user_tables/indexes) | A could only guess at hot paths (P1-16 OOM vectors, P2-03 `init_db()` per keystroke). C measured page weight instead |
| 21 | Ten duplicate indexes (296 KiB) | B only | DB + EMP | Needs catalog |
| 22 | Fresh v054 DB lacks `support_canned_responses` that live/upgraded DB have | B only | EMP (fresh vs upgraded migration run) | Needs to actually run migrations |
| 23 | Sync push lists 26 tables vs pull 22; 55.1 MiB preload unused by PG path | B only (A P1-09 only said scripts lack confirmation) | SR + DB sizes | A saw the scripts but judged them on safety, not contract |
| 24 | Purge test data uses LIKE patterns that match real rows | A (P1-09) and B (High #4) | SR/GR | Overlap, **different predicates** (see Q2) |
| 25 | Backup copies SQLite while in WAL mode | A (P1-06 item 3, `scripts/backup.sh`) and B (Medium, `run.sh:67` + `backup.sh:29`) | SR | Overlap; B added `0644` file modes (FS) and zero buckets (DB) |
| 26 | Unsubscribe | A (P1-10: live subscriber token stored in digest sample HTML) ; B (helper `set_user_digest_subscription(token_or_email)` still accepts email) | SR | Different facets. Route was fixed in `84ce132` (23:56, after A, before B), which is why B only flags the helper — `core/db/digest.py:168` [digest.py](file:///Users/lyndonpinto/Documents/Stock_Research_App/core/db/digest.py) |
| 27 | "Stock Discovery @9AM" promised daily at 9:00 AM IST but built in 16:30 evening run; hardcoded "09:00 IST" timestamp | C only | COPY + DB (read-only `discovery_reel.created_at`) + HTTP | A and B never compared promises with schedules. Repo check confirms: `web/templates/discovery.html:48` ("released every morning at 9:00 AM IST"), `:54` (`Evaluated: … 09:00 IST` literal), `pricing.html:56`, `index.html:191`, vs `render.yaml:19` ("16:30 IST: main close run (… discovery reel …)") — [discovery.html](file:///Users/lyndonpinto/Documents/Stock_Research_App/web/templates/discovery.html), [render.yaml](file:///Users/lyndonpinto/Documents/Stock_Research_App/render.yaml). Note A **did** flag a different 9AM facade: MSME "Daily 9AM Udyam Gazette Ingestion" rotating a hardcoded 60-company array (A P1-08 item 4) |
| 28 | Homepage 608 cards / 3.5 MB / 27k DOM nodes with 1 visible; `/funds` 973 cards / 30k nodes | C only | BR + HTTP (desktop and 375 px) [C-brief] | Only a rendered page shows this |
| 29 | 404 returns raw JSON | C only | HTTP [C-brief]. Repo check: no 404 handler in `web/main.py` (only `RateLimitExceeded` at :427 and `_AuthoritativeDatabaseUnavailable` at :435) — [main.py](file:///Users/lyndonpinto/Documents/Stock_Research_App/web/main.py) |
| 30 | Unescaped `&` in sitemap | A (P2-06, code) and C (3 live instances in 936 URLs, 38 sampled all 200) | A: SR; C: HTTP | Agree. Repo: `<loc>{base_url}/dossier/{t}</loc>` etc. with no escaping (`web/main.py` ~3216-3250) |
| 31 | Docs cite `scripts/chrome_interactive_audit.py`, which does not exist | C only | FS | Repo confirms: file missing; cited in `docs/MASTER_ENGINEERING_MANUAL.md:740` ("43/43 live Google Chrome interactive checks passed via … `scripts/chrome_interactive_audit.py`") and `docs/PENDING_TASKS.md` — [manual](file:///Users/lyndonpinto/Documents/Stock_Research_App/docs/MASTER_ENGINEERING_MANUAL.md). A and B never cross-checked docs against the file tree |
| 32 | All 302 .py compile; 213 routes vs 140 template/JS URLs all resolve | C only | EMP + SR [C-brief] | A asserted 100% coverage but did not run anything |
| 33 | Weekly "Market Close Wrap" email lands in Gmail Promotions | Owner, not an audit | Manual inbox check [C-brief] | No audit had inbox access |
| 34 | Mailer heartbeat "unknown url type" (quoted env values) | Earlier Claude session | LOG [C-brief] | Only visible in Render logs |

### Inferences
- The decisive variable was **access**, not model quality. B's 10 "only B" items all need a database connection (grants, TLS, sizes, row counts, migration runs). C's "only C" items all need the running site, logs, or a check of copy against schedules.
- A's unique value was **breadth of code-path reading** (CI YAML, agent tool policies, PDF engine, Docker packaging, scripts). Neither B nor C attempted that breadth.
- A and B both read `core/db/users.py`, but only B traced how an email becomes an account ID and then a profile (#15). Volume-first reading can miss logic that only shows when you follow one value end to end.

### Gaps
- I could not re-run C's live crawl, log checks or production query (constraint: no production connection). C's live numbers are taken from the brief.
- B's DB numbers (row counts, seconds, sizes) cannot be checked without database access.

## Q2. Overlapping findings: do the audits agree on facts and severity?

### Takeaway
They agree that the problems exist but differ on detail and severity. A tends to rate higher and describe the worst-case chain. B states narrower, measured claims and is explicit about what it did not verify. In two overlaps they looked at **different lines of the same function**, so the overlaps add to each other rather than repeat.

### Cited Findings
- **Refunds:** A rates P0 (fake Copilot refund never calls Razorpay; `int(target_ref)` crash on `tx_...` IDs; no `FOR UPDATE`; no Pro revoke) — [A P0-11](file:///Users/lyndonpinto/.gemini/antigravity/brain/a88aca8e-89d0-46bb-afb6-a9596ed5b893/codebase_security_and_quality_audit.md). B folds it into a High item: status checked before update and balance computed from a separate read, so not idempotent — [B](file:///Users/lyndonpinto/.codex/.chatgpt-projects/g-p-6aeb6e9f46388191a43eb3a1cf1ea4fb/Moatnomics_Database_Audit_2026-11-13.md). Facts agree (non-atomic); A goes further. Repo: `int(target_ref)` present at `core/db/users.py:988`.
- **Purge LIKE patterns:** A flags `NOT LIKE '% %'` deleting real tickets with no spaces and date-string LIKEs on telemetry (`telemetry.py:1872-1891`, `2014-2022`). B flags unescaped underscores acting as wildcards and no production provenance (`telemetry.py:1895`). Repo shows both are real in the same function: `TRIM(message) NOT LIKE '% %'` (line 1883), `user_id LIKE 'test_%'`, `'usr_test_%'`, `'order_test_%'` (lines ~1902-1905), `summary LIKE '%2026-10-25%'` (2018) — [telemetry.py](file:///Users/lyndonpinto/Documents/Stock_Research_App/core/db/telemetry.py). Severity: A P1, B High. Agreement.
- **Backup in WAL mode:** A P1 (`scripts/backup.sh` hot `cp`, also tars `.env*`, key on command line); B Medium (`run.sh:67` and `backup.sh:29`, plus `0644` modes and zero Storage buckets). Repo: `run.sh` backup does `tar -czf … web/ reports.db` — [run.sh](file:///Users/lyndonpinto/Documents/Stock_Research_App/run.sh). Facts agree; A rates one tier higher.
- **FK divergence:** A P1-20 claims SQLite never enables FKs and that `credit_transactions.id` is `INTEGER PRIMARY KEY AUTOINCREMENT` at `users.py:58`, "directly causing" the PG crash. **Repo check: false at audit time** — `git grep "INTEGER PRIMARY KEY AUTOINCREMENT" 7dcc8e5 -- core/db/users.py` returns nothing; `users.py` only INSERTs into `credit_transactions` (lines 70, 103, 553), and both `connection.py` definitions use `id TEXT PRIMARY KEY` (846, 899). B instead measured: SQLite FK off on fresh and upgraded copies; live PG has 3 FKs; `fund_audit_jobs.user_id` FK missing only in PG. B's claim is narrower and measured; A's root-cause story is wrong.
- **Unsubscribe:** A (P1-10) — sample HTML for `subscribers[0]` stored as digest `html_content` (repo: `core/notify.py:609` and `:652`), possibly leaking that subscriber's token. B — the shared helper still accepts an email. Different facets; no conflict. The route-level fix landed between A and B (`84ce132`).
- **Conversation IDOR:** A (P1-02) says history loads by `conversation_id` with no `user_id` check. B is more exact: owned conversations are checked; **guest** conversations fall back to an IP-hash ID (repo: `CONV-ANON-{sha256(client_ip)}` in `web/routers/admin.py` ~765) and helpers fetch by ID alone; 26 of 44 live conversations are ownerless. B ranks it top priority; A puts it at P1 inside a paywall item. B also says plainly that whether anyone was actually exposed is unknown.
- **OTP:** A (P1-05) unsalted sha256 and no row lock on attempts; B consume-on-separate-connection (repo: `DELETE FROM auth_otps` at `core/auth/otp.py:290`, separate from verify at :208). Consistent.

### Inferences
- Where both looked, B's statements are usually checkable and scoped ("the count establishes the affected class … whether anyone accessed … is unknown"). A's statements chain several assumptions into an impact story, which raises the severity rating and the error rate.
- Overlaps found by different predicates in the same function show that each pass reads only part of a function. Two passes are not redundant.

### Gaps
- No overlap on CI, agents, PDF or Docker, so severity agreement could not be tested there.

## Q3. Which of audit A's claims are verifiable vs unverifiable from the code (sample of 12, P1–P3)

### Takeaway
Of 12 sampled A claims, 6 checked out, 3 were partly right but overstated or misdescribed, and 3 were wrong at the time A wrote them (P2-01 duplicate route, P2-05 hardcoded 2026 holidays, and the P1-20 `users.py:58` schema claim). Line numbers were mostly accurate (several exact), so A's main failure is **invented or stale facts, not drifting line numbers**. The wrong claims look like they came from an older memory of the code or from pattern-completion, not from reading the current file.

### Cited Findings (all checked read-only at `7dcc8e5` and HEAD)
| A claim | Verdict | Evidence |
|---|---|---|
| P3-01 SAC `'998314'` default at `core/db/connection.py:1048`; "official Indian tax invoice" in legal copy | **Verified, exact line** | `connection.py:1048` and `:1066` `sac_code TEXT DEFAULT '998314'`; `web/legal_content.py:153` "An official Indian tax invoice receipt…", `:67` "issue tax invoices" — [connection.py](file:///Users/lyndonpinto/Documents/Stock_Research_App/core/db/connection.py), [legal_content.py](file:///Users/lyndonpinto/Documents/Stock_Research_App/web/legal_content.py) |
| P2-07 `HeadMethodMiddleware` rewrites HEAD→GET (`main.py:446-458`) | **Verified, exact line** | `web/main.py:446-450` sets `request.scope["method"] = "GET"` |
| P2-06 unescaped `&` in sitemap (`main.py:3218-3278`) | **Verified** (range ~20 lines off: route starts at 3198) | f-string `<loc>{base_url}/dossier/{t}</loc>` with no escape; C saw 3 live instances [C-brief] |
| P3-04 twelve orphaned `.pyc` in `core/analysis/__pycache__/` | **Verified count; severity overstated** | 12 orphans: bull_bear, comparator, debt_crawler, discovery, engine, equity_dossier_intelligence, etf_engine, fund_forensic_auditor, mutual_fund_engine, reit_engine, safety_radar, tax_calculator. But `__pycache__/` is git-ignored (`.gitignore:1`), so it is local-only and does not reach CI |
| P2-16 CORS allows `http://localhost:8000` with credentials in prod | **Verified** | `web/main.py:414-421`, no environment gate |
| P0-06/P1 SQL f-string time filter at `telemetry.py:769` | **Verified location; severity overstated** | Function at `:769`; route bounds `days` (`admin.py:513`); admin-only |
| P1-14 global `watchlist`, "ticker alone is the PRIMARY KEY", "every watchlist addition … leaking watched tickers across users" | **Partly right, overstated** | No `user_id` column is true, but PK is `id` with `ticker TEXT UNIQUE` (`connection.py:570-572`, `639-641`). No web route calls `add_to_watchlist`/`get_watchlist`; callers are only `db.py`, `benchmark.py`, `core/db/__init__.py`, `core/agents/watchers/bse_watcher.py`. No user-facing leak path exists |
| P1-13 MF fallback `LIKE UPPER(%{code}%)` at `mutual_funds.py:686` | **Partly right, code misquoted** | Line 687 uses **bound** parameters `(f"{clean_code}%", f"%{clean_code}%")`; not interpolated. The wrong-scheme fallback and unescaped `%`/`_` are real — [mutual_funds.py](file:///Users/lyndonpinto/Documents/Stock_Research_App/core/db/mutual_funds.py) |
| P1-09 `NOT LIKE '% %'` and date LIKEs in purge | **Verified** | `telemetry.py:1883`, `2018-2020` |
| P2-01 duplicate `GET /api/admin/assets/scan-runs` at lines 2220 and 2324 | **False** | Only one registration, at `web/routers/admin.py:2266`, in both `7dcc8e5` and HEAD |
| P2-05 "hardcodes only 2026 exchange holidays" in `market_calendar.py:18-65` | **False** | `core/ingestion/market_calendar.py` was created in `21e595c` (20:15 on 11-12, before A) and fetches NSE `holiday-master` live, storing results in `system_settings` (`nse_equity_holidays`). No hardcoded 2026 holiday set existed in `21e595c^` either |
| P1-20 `credit_transactions.id INTEGER PRIMARY KEY AUTOINCREMENT` at `users.py:58` | **False** | No CREATE TABLE for `credit_transactions` in `users.py`; lines 55-62 are a welcome-grant SELECT |

Claims that cannot be checked from code alone: impact chains that depend on deployment (P0-01 Tier 3 reachability depends on which keys are set in production, which C settled with logs); "167 MB PII reports.db baked into images" (needs the built image); P1-16 "historical OOM incidents" (needs logs); P2-17/P2-08 abuse scenarios (need load). A's "100% coverage" claim also cannot be checked: it gives no file list or tool trace.

### Inferences
- A's error modes: (1) **invented specifics** (duplicate route, hardcoded holiday set, INTEGER PK) stated with exact line numbers, which makes them look checked; (2) **severity inflation through chaining** (P0-06, P1-14, P3-04); (3) **code misquotation** that turns a bound parameter into apparent injection (P1-13). Stale line numbers were a small problem in this sample (most were exact at `7dcc8e5`); C's observation of shifted lines applies mainly after `b316739` edited the P0 files.
- Because A had no runtime access, it could not tell "reachable in production" from "present in source". C's log check on P0-01 is the clearest example of runtime evidence changing the decision (safe to delete, nobody uses it).

### Gaps
- Sample is 12 of 51 P1–P3 claims; the error rate (3 false / 12) should not be extrapolated precisely.
- I did not re-verify A's P0 items beyond P0-06/P0-09/P0-11; C reports 13 of 14 checked.

## Q4. What classes of issue did none of the three audits examine?

### Takeaway
All three audits looked at the **engineering surface** (code, database, live pages). None checked **business and user-facing truth**: whether pricing promises match what billing grants, whether legal copy is accurate, whether pages are accessible, how emails render and where they land, how much LLM and infrastructure spend is going out, and whether a backup can actually be restored. Several of these came up only by accident (the owner checking their inbox, a log read for another reason).

### Cited Findings
- **Pricing claims vs billing grants:** pricing copy promises "Daily Morning Discovery @9AM stock screener" as a Pro perk (`web/templates/pricing.html:56`) — [pricing.html](file:///Users/lyndonpinto/Documents/Stock_Research_App/web/templates/pricing.html). C caught the timing, but no audit mapped each pricing bullet to the code that grants it (credit amounts, Pro tier checks in `core/db/users.py`).
- **Legal copy accuracy:** A flagged only the SAC/invoice wording as an AGENTS.md rule breach (P3-01). Nobody checked whether the terms, refund, shipping and privacy pages (sitemap lists `/terms`, `/privacy`, `/refund-policy`, `/shipping-policy`, `/disclaimer`, `web/main.py` ~3225-3230) match real refund behaviour. A's own P0-11 shows refunds don't fully work.
- **Accessibility:** no WCAG, keyboard, screen-reader or contrast checks in any audit (A has 0 "WCAG" mentions; B and C none), even though AGENTS.md Rule 9.1 requires contrast checks — [AGENTS.md](file:///Users/lyndonpinto/Documents/Stock_Research_App/AGENTS.md).
- **Email rendering and deliverability:** A looked at email HTML injection (P1-10) but not how emails render or where they land. The Promotions-tab issue was found only by the owner [C-brief].
- **Cost / LLM spend:** A flagged quota-drain vectors (P0-13, P1-07) and spend-accounting bugs (`ai_spends.py` 85/15 splits, A P1-08), but no audit pulled actual provider bills or token usage against budget.
- **Disaster recovery drills:** B said backups exist but "managed backup recovery" was out of scope and recommended "verify restore capability"; no audit restored a backup. A mentions "restore" only for `checkpoint_manager.py`.
- **Scheduler/cron reality:** C compared one schedule claim with DB timestamps. Nobody checked every Render cron in `render.yaml` against its job's last-run timestamps.
- **Third-party and data-source terms:** scraping NSE/BSE/AMFI (e.g. `NSE_HOLIDAY_URL` in `market_calendar.py:19`) was not reviewed for rate limits, terms, or failure modes beyond A's P2-11 size caps.
- **SEBI regulatory surface:** A mentions SEBI risk around fabricated metrics (P1-08) but no audit checked research content against SEBI research-analyst rules.

### Inferences
- The blind spots share one cause: each audit's prompt and tools framed the target as "the code" or "the database". Problems that only appear when you compare two artefacts (copy vs schedule, pricing vs grants, docs vs file tree, backup vs restore) need a deliberate cross-artefact method. C's "promise vs execution" grep is the only example, and it found a real user-facing issue.
- A cheap follow-up method: list every user-visible promise (times, counts, perks, refund terms) and pair each with a check against code, schedule and DB timestamps.

### Gaps
- I did not find any record of an accessibility, DR-restore or cost-reconciliation exercise in the repository; absence is inferred from the three audit texts and the brief, not proven project-wide.
