# Platform Roadmap & Pending Tasks Register
**Moatnomics — Multi-Asset Investment Research Platform**  
*Document Target:* [`docs/PENDING_TASKS.md`](file:///Users/lyndonpinto/Documents/Stock_Research_App/docs/PENDING_TASKS.md)  
*Last Updated:* 2026-11-13 08:45:00 IST

---

## 1. Active, In-Progress & Parked Tasks

### Task 10: Daily "Why It Moved" Evaluation for the Day's Major Stock Movements
- **Category:** Research Content / Market Close Wrap
- **Status:** `Not started — needs an implication-preflight brief before any code` (added 2026-11-13)
- **Goal:** For each trading day, explain the major price moves in the stocks we cover, citing the public evidence behind each one, so readers learn what drove the move rather than just seeing the number.
- **Open questions to settle in the preflight interview:**
  1. **What counts as a major move:** a fixed threshold (for example ±5% on the day), the top N gainers and losers in our coverage, or a move that's large relative to the stock's own typical daily swing. Should volume spikes qualify too?
  2. **Universe:** only stocks with a published report, or every listed stock we hold prices for.
  3. **Where it appears:** a new Market Close Wrap section (19:30 IST), a dated "Why it moved" note on each stock's report page, a `/discovery` panel, or a combination.
- **Evidence to check for each move (fail closed when nothing is found):**
  - the company's own exchange filings that day (results, board outcomes, orders, rating changes, pledges, management changes);
  - bulk and block deals;
  - index and sector moves, to separate a stock-specific move from a market or sector one;
  - ex-dividend, split or bonus dates, which move the price mechanically;
  - news, cited only from reliable sources and never presented as a filing.
  - When no public cause is found, say so: "No company-specific disclosure found; the move tracked its sector." Never infer a reason without evidence (AGENTS.md "Pending Over Potemkin").
- **Risks to cover in the brief:**
  - **SEBI:** wording must explain what happened and must not read as a buy or sell call, or as a forecast.
  - **Timing:** some filings land after the 3:30 PM close, so the 16:30 IST close run may miss them. Decide whether a late-filing re-check is needed before the 19:30 send.
  - **Cost:** model calls per mover per day.
  - **Prose uniqueness and number parity:** move percentages must match closing prices (AGENTS.md Rule 8).
- **Done when:** a dated record per mover is saved with its cited sources and generation time, shown in the chosen places with a provenance badge, covered by tests (including the "no cause found" path and an upstream outage), and the living docs are updated.

### Task 9: Security, Data & UX Remediation (merged patch list from three audits)
- **Category:** Security, Billing Integrity, Data Operations, Promise-vs-Execution & UX
- **Status:** `Wave 1 shipped and verified live 2026-11-13 (b316739); everything else open`
- **Sources** (tag after each item):
  - **[A]** full-codebase audit, 2026-11-12 23:15 (14 P0, 20 P1, 19 P2, 12 P3), ids such as `A:P0-11`;
  - **[B]** database audit at `0914737`, 2026-11-13 (live read-only catalog, statistics and grants);
  - **[C]** live audit, 2026-11-13 (production logs, read-only DB timestamps, live crawl and real-browser checks at desktop and 375 px).
- Overlapping findings are merged into one line with every source listed. Spot checks confirmed 13 of A's 14 P0s; A's line numbers have drifted, and A:P0-06 is overstated (only admins can reach it). A sample of 12 of A's lower-priority claims found 6 accurate, 3 overstated (P1-13, P1-14, P0-06) and 3 wrong (P2-01, P2-05, P1-20's cause), so confirm each A item in code before fixing it.

**1. ~~Wave 1: containment~~ (done 2026-11-13, verified live)**
- ~~Sign-in token fallback removed and `exp` required [A:P0-01]~~
- ~~`/auth/callback` reflected XSS [A:P0-02 part]~~
- ~~Workflow input shell injection, read-only CI permissions [A:P0-03]~~
- ~~Admin lookup fails closed [A:P0-05 part]~~
- ~~Thesis, countercase and telemetry identity from the session only [A:P0-07]~~
- ~~`.dockerignore` [A:P0-09 part]~~

**2. Wave 2: money and identity** (run the implication-preflight skill first; these touch billing and auth)
- **Refunds never reach Razorpay.** No code calls the refund API. The Admin Copilot "refund" only flips `status`. `process_refund` does `int(target_ref)` on `tx_...` ids and crashes on Postgres. There is no row lock, Pro and unlocked reports aren't revoked, refunds aren't idempotent, and the balance comes from a separate read. [A:P0-11, B]
- **Credit races.** `add_user_credits` reads, changes and writes the balance; the unlock spans three connections; gateway order/payment ids have no unique constraint; welcome credits aren't idempotent. [A:P0-11, B]
- **Free Pro access** when `subscription_expires_at` is missing or can't be parsed. [A:P0-11]
- **Order intent saved after the Razorpay order is created.** A database error at that moment leaves a customer charged with no credits. [A:P0-12]
- **Daily generation cap counted before the credit check.** Zero-credit users can use up everyone's quota, and there's no per-ticker lock (duplicate paid calls). [A:P0-13]
- **Account identity.** The lookup matches `id = ? OR email = ?`, and `usr_` ids are built lossily (`a.b@x` and `a_b@x` collide), so one person can be served another person's profile. [B]
- **One-time codes.** Verify and delete run in separate transactions (a code can be used twice); the resend throttle isn't atomic; codes are hashed without a salt; the attempt counter can race; expired rows are never purged. [B, A:P1-05]
- **Research Desk guest chats.** Readable and appendable by conversation id; guest ids come from IP addresses (shared IPs collide); turn positions use `COUNT(*)` with no unique key or foreign key; the model gets the oldest turns instead of the latest. 26 of 44 live conversations are ownerless. [B, A:P1-02]

**3. Wave 2: test and tooling safety**
- **Test database isolation.** Add `tests/conftest.py` with a temporary database. `verify_reality_audit.py`, `check_system.py` and `remediation_squad.py` can touch live data. [A:P0-10]
- **Test mode switched on by imports.** `scripts/ai_auditor.py` and `check_system.py` set `TESTING=1` at import time, and `ai_auditor` writes `.py` files into `tests/`. [A:P0-14]
- **Admin test-data purge.** `LIKE` patterns with unescaped `_` can delete real accounts and transactions. Purge only rows with explicit test provenance, and preview row counts first. [A:P1-09, B]

**4. Remaining P0 work in Wave 1's areas** [A]
- **P0-02:** debt ingest writes to the shared table; Markdown rendered with `| safe`; admin console and Opportunity Terminal DOM sinks; `'unsafe-inline'` CSP; no CDN SRI.
- **P0-05:** hardcoded `admin@moatnomics.com` owner; no rate limit on `/admin/auth/direct-verify`; legacy root `telemetry.py` admin with the `admin2026` default password. Production still imports this file, see section 7.
- **P0-04:** agent tool policies (substring `pytest` command approval, workspace file reads, SSRF).
- **P0-06:** SQL built from strings in telemetry time filters and admin email exclusions.
- **P0-08:** PDF `root="."`, white-label fields not escaped, watermark fails open.

**5. Promise vs execution and UX** [C unless noted]
- **Stock Discovery @9AM** is promised daily at 9:00 AM IST (homepage, Pro perk on `/pricing`, nav, live countdown). The edition is built in the 16:30 IST run, and live `discovery_reel.created_at` shows creation between 19:55 the same day and the next afternoon. `discovery.html:54` shows a hardcoded "Evaluated: … 09:00 IST" (AGENTS.md Rule 7). After 9 AM the page still says "check back at 9:00 AM". **Decision pending:** change the wording to the real release time, or produce the edition by 9 AM.
- **Page weight.** The homepage sends 608 cards (3.5 MB, 27k elements) and shows 1; `/funds` renders 973 cards (3.8 MB, 30k elements) with no paging; `/etfs` is 3.4 MB. Add paging or lazy loading and a page-size budget. [C, A:P1-16]
- **404 page** returns raw `{"detail":"Not Found"}`. Needs a branded not-found page with navigation.
- **Sitemap** has 3 unescaped `&` (936 URLs; a sample of 38 all return 200). [A:P2-06, confirmed live]
- **Unverifiable claims in the manual.** It cites a non-existent `scripts/chrome_interactive_audit.py` ("43/43 checks"), and its audit scores have no reproducible artifacts.

**6. Database and data operations** [B unless noted]
- **Supabase client roles** (`anon`, `authenticated`) have broad grants on all 65 tables and 33 sequences (including `TRUNCATE`) plus default grants. The app runs as `postgres` and does DDL at runtime. Revoke unneeded grants and move schema changes to a deploy step.
- **Backups.**
  - The SQLite file is copied while in WAL mode, so copies can be incomplete. Use `sqlite3 .backup`.
  - Files are mode `0644`, and admin TOTP seeds are stored in plain text.
  - There has been no restore drill, and the uploader targets a bucket that doesn't exist.
  - The local `backups/` folder is 28 GB with no retention. Keep the last 5 automatically. [B, A:script inventory, C]
- **Foreign keys.** A:P1-20's stated cause (an `INTEGER` id at `users.py:58`) is wrong, but B's measured findings stand: SQLite runs with foreign keys off; `fund_audit_jobs.user_id` has no foreign key in Postgres; `mf_current_disclosures.snapshot_id` has no index. [B, A:P1-20]
- **Query cost** (measured since 25 Oct). Measure before and after each change. [B, A:P1-16]
  - Report revisions: about 2,125 s over 41k calls.
  - BSE resolution routine: about 765 s; the predicates don't use indexes (267k sequential scans).
  - Telemetry: about 100 MB, 65 MB of it indexes. One 7.8 MB index has zero scans, and the top-users query does N+1 profile lookups.
  - Fund holdings: about 11k dead rows.
  - 10 duplicate indexes.
- **Sync scripts.** A 55 MB report preload is unused on Postgres; push and pull list different tables (26 vs 22); the REST pull overwrites newer local rows; partial failures are reported as success; the sequence reset can race. [B, A:script inventory]
- **Schema work at runtime.** The savings reconciliation runs three times; `support_canned_responses` is missing on a fresh database; `init_db()` runs on every typeahead keystroke. [B, A:P2-03]
- **Digest subscription helper** still accepts an email address. That path can't be reached (routes check the token first), but narrow it to token-only. [B]

**7. Wave 3: rest of audit A** (open unless marked)
- **P1:**
  - P1-01 viewer role escalation and Copilot prompt injection
  - P1-03 pool and SQLite deadlocks
  - P1-04 `Cache-Control: public` without `Vary: Cookie`
  - P1-05 OAuth token in the GET query, no state/PKCE, predictable secret fallback, cookie `Secure` flags, CSRF passes when headers are missing
  - P1-06 brokerage credentials in plain text
  - P1-07 quota drain, 5-minute BSE re-synthesis loop, alias poisoning
  - P1-08 fabricated financial figures
  - P1-10 email HTML injection; the admin sample email stores a real subscriber's unsubscribe token (`notify.py:609`); mock sends counted as sent
  - P1-11 archive bombs and `defusedxml`
  - P1-12 `pytest` inside the admin audit
  - P1-13 fuzzy `LIKE` primary keys
  - P1-14 global watchlist
  - P1-15 SSE duplication
  - P1-17 `-A trust` Postgres in tests
  - P1-18 secrets and PII in `scratch/`
  - P1-19 reality audit blind spots
- **P2:** P2-01 to P2-19. P2-06 is listed in section 5. Not real or already done: P2-01 (only one scan-runs route exists, `admin.py:2266`) and P2-05 (the holiday calendar fetches NSE live; there is no hardcoded 2026 list).
- **P3:**
  - P3-01 SAC `998314` default (`connection.py:1048`)
  - P3-02 personal name in source and tests
  - P3-03 vendor metadata in `data/`
  - P3-04 orphan `.pyc` files
  - P3-05 `backups/` in git hygiene
  - P3-06 website service missing from `render.yaml`
  - P3-07 to P3-09
  - P3-10 legacy root modules: confirmed that production imports them (`web/main.py` and `web/routers/dossier.py` import root `telemetry.py`; `core/reporting/pdf.py` imports root `db.py` and `analyzer.py`; synthesis imports `screener.py` and `checker.py`) [A, C]
  - P3-11 and P3-12

**Not yet audited by anyone:** pricing copy vs what billing grants, paid unlock and checkout flows end to end (needs a signed-in test account), accessibility, email rendering across clients, restore drills.

### Task 8: Mailer Monitoring Setup (Better Stack Heartbeats & Resend Webhook)
- **Category:** Monitoring & Email Deliverability
- **Status:** `Configured 2026-11-12, awaiting first live verification` (Better Stack URL monitor "Moatnomics Mailers" on `/api/health/mailers` every 180 s, Up; Resend webhook enabled for `email.delivered`, `email.delivery_delayed`, `email.bounced`, `email.complained`, `email.opened`; `RESEND_WEBHOOK_SECRET` set on the website; unsigned POST returns 401). Close once step 5 holds after the 2026-11-13 07:30 IST Fund NAV Update.
- **Origin:** Checks run 2026-11-12. Better Stack has only the general "Morning Discovery & Ingestion Pipeline" heartbeat. Resend has no webhook configured, and the website has no `RESEND_WEBHOOK_SECRET`, so `digest_recipient_events` has never recorded a delivery, bounce, complaint or open, and hard-bounce/complaint auto-pause cannot trigger.
- **Details:**
  1. **Better Stack URL monitor (free, replaces two paid heartbeats):** add an uptime monitor on `https://moatnomics.com/api/health/mailers` (alert when the URL is unavailable / returns non-2xx, check every 3 minutes). The endpoint (`core/mailer_health.py`, shipped 2026-11-12) returns 200 when the latest due Market Close Wrap (by 21:00 IST) and Fund NAV Update (by 08:45 IST next day) went out, counting weekends and NSE holidays as expected skips, and 503 when either is late or the ledger cannot be read.
  2. The per-sender variables `BETTER_STACK_HEARTBEAT_URL_MARKET_CLOSE` / `_FUND_NAV` are no longer required; leaving them empty only logs a notice.
  3. **Resend webhook:** in Resend, go to Webhooks → Add endpoint, enter `https://moatnomics.com/api/webhooks/resend`, and select the delivered, bounced, complained and opened events.
  4. Copy the webhook's signing secret into a new `RESEND_WEBHOOK_SECRET` variable on the **Moatnomics.com** website service in Render. The endpoint fails closed (401) without it.
  5. **Verify:** after the next send, `digest_recipient_events` shows `sent` and `delivered` rows and the admin Digest tab shows the delivery funnel; the Better Stack mailer URL monitor shows "Up".

### Task 7: Research Emails Land in Gmail Promotions
- **Category:** Email Deliverability
- **Status:** `In Progress` (2026-11-12: List-Unsubscribe one-click headers + POST handler, dedicated "Moatnomics Research" sender and "move to Primary" footer shipped. Owner declined removing UTM links / CTA button. Cloudflare Email Routing enabled 2026-11-12: root MX `route1-3.mx.cloudflare.net`, SPF `include:_spf.mx.cloudflare.net`, rules `research@` and `desk@moatnomics.com` forward to the owner's inbox (catch-all: drop). Remaining: after a few weeks of clean sending move DMARC from `p=none` to `p=quarantine`; judge Gmail tab placement over the next few editions.)
- **Origin:** Owner report (2026-11-12). The 2026-11-12 Market Close Wrap was delivered by Resend at 19:58 IST, but Gmail filed it under Promotions rather than Primary.
- **Details:**
  1. Review what makes Gmail treat the Market Close Wrap and Fund NAV Update as marketing: image and link density, promotional wording in subjects and headers, missing plain-text part, sender-name consistency, and `List-Unsubscribe` / `List-Unsubscribe-Post` headers.
  2. Check `desk@moatnomics.com` domain authentication in Resend (SPF, DKIM, DMARC alignment).
  3. Once the Resend webhook records opens (`digest_recipient_events`), compare open rates before and after any change.
  4. Optional: a one-line "move this to Primary" hint for subscribers in the email footer.

### Task 5: Track 3 Language & Voice, Open Items
- **Category:** Brand, Copy & Compliance Wording
- **Status:** `Parked` (Phases 1–3 shipped 2026-10-20; `/terms` statutory 7-section realignment shipped 2026-10-23; visual hero/portal integration & emoji cleanup shipped 2026-10-24; stored-value migration decided against 2026-11-13. Only the Hindi item remains, parked until an audience request.)
- **Details:**
  1. ~~Decide whether to migrate stored values (`SURGICAL_REFRESH`, `FULL_SYNTHESIS`, contact category `synthesis`, existing `BSE Surveillance` alert rows) to the new wording (`Decided 2026-11-13: keep internal identifiers, no migration`). Production check (read-only): 6 `FULL_SYNTHESIS` credit-ledger rows, 0 `SURGICAL_REFRESH`, 3 `synthesis` support tickets, 0 surveillance alert rows. None are user-facing (display text already uses the new wording), and `FULL_SYNTHESIS` backs the charge-once unlock check in `core/db/users.py`, so renaming adds risk with no visible benefit.~~
  2. **Parked (Pending Audience Request):** Hindi per-language voice rules, string catalogues and the `language` parameter of `get_system_prompt()`.
  3. ~~Reference the hero banners (`img/heroes/*.webp`) and portal plates (`img/brand/portal-*.webp`) from their pages, after a browser review of text contrast (`Completed 2026-10-24`).~~
  4. ~~Replace the remaining raw emojis in `web/main.py` server messages and `web/templates/admin.html` console with clean text and sprite icons (`Completed 2026-10-24`).~~
  5. ~~Owner decision on whether to retain or update the phrase `"computational financial research synthesis software utility"` inside `MANDATORY_SEBI_DISCLAIMER` (`core/db/compliance.py`) — updated to `"independent multi-asset investment research platform and software utility"` (`Completed 2026-10-24`).~~
  6. ~~Replace remaining raw emojis in public templates, `web/static/js/main.js`, and `web/static/js/opportunity_terminal.js` with sprite icons (`Completed 2026-10-21`).~~
  7. ~~Update `/terms` legal characterisation in `web/legal_content.py` to `"multi-asset investment research platform"` and `"independent software utility, not a registered fiduciary"` (`Completed 2026-10-23`).~~

---

## 2. Completed Tasks (Moved to Bottom)

### ~~🏦 Task 6: Unified Fixed Savings, Term Deposits, Small Savings & Retirement Universe (`/savings`)~~
- ~~**Category:** 8th Asset Class Expansion, DICGC Sec 16(1) Safety & Cross-Surface Macro Parity~~
- ~~**Status:** `Completed & Verified on Disk` (Shipped 2026-11-09)~~
- ~~**Details:** Dual-dialect migration `v049_fixed_savings_and_deposit_universe`, `34` curated fixed-rate & retirement instruments (`core/db/savings.py`, `data/savings_rates/baseline_savings_universe.json`), Finance Act 2025 dual-regime tax waterfall, DICGC ₹5,00,000 principal + accrued-interest multi-charter ladder, FD ↔ Senior NCD ↔ Equity contagion bridge, pure Sec 112A arbitrage vs FoF guard (zero fabricated MF returns), shared `get_live_macro_anchors()`, 8-Asset Omni-Search, and full SSR `/savings` + `/savings/{instrument_id}` views.~~

### ~~📱 Task 4: Mobile Brief Mode (`/m`)~~
- ~~**Category:** Mobile Experience & High-Density Commuter Research~~
- ~~**Status:** `Completed & Verified on Disk` (Shipped 2026-10-24 in commit `1fda96e`)~~
- ~~**Details:** Compact, read-only multi-asset brief experience across all 5 asset classes (Equities, Funds, Debt, REITs, MSMEs) with zero-LLM deterministic compiler (`core/analysis/mobile_brief.py`), shorthand route `/m/{ticker}`, paywall-aware status pills, dossier integration, and 11 outside-in unit tests passing.~~

### ~~📬 Task 1: Subscribed Users Research Bouquet & Morning Digest with Custom Domain Tracking~~
- ~~**Category:** Retention, Engagement & Investor Relations~~
- ~~**Status:** `Completed & Verified on Disk` (2026-10-17; 09:00–09:59 AM IST window & `has_edition_been_dispatched` idempotency guard hardened 2026-10-24)~~
- ~~**Origin / Request:** Owner Directive (2026-10-17)~~
- ~~**Functional Scope & Delivered Implementation:**~~
  1. ~~**Curated Research Bouquet Compilation (`core/analysis/research_bouquet.py`):**~~
     - ~~Multi-asset intelligence bouquet compilation (`compile_research_bouquet`, `render_bouquet_html`, `render_bouquet_text`).~~
     - ~~Combines today's top equity picks from Morning Discovery Reel, mutual fund forensic look-through audits, 10Y G-Sec sovereign yield curve / policy rate wedges, and unlisted MSME manufacturing champions.~~
  2. ~~**Subscriber Audience Filtering & Preference Management (`core/db/digest.py`, `core/db/connection.py`):**~~
     - ~~Database schema migration `v030_research_bouquet_and_digest_subscriptions`.~~
     - ~~Fields: `is_subscriber`, `is_digest_subscribed`, `digest_unsubscribe_token` on `user_accounts`.~~
     - ~~Statutory 1-click unsubscribe (`/api/notifications/unsubscribe?token=...`) and instant undo (`/api/notifications/resubscribe`) per IT Rules 2021.~~
     - ~~Database-backed dispatch idempotency guard (`has_edition_been_dispatched`) and 24-hour distributed scheduler lease (`morning_bouquet_{today_str}`).~~
  3. ~~**Branded Open & Click Tracking Subdomain (`links.moatnomics.com`):**~~
     - ~~Custom domain tracking architecture configured with Resend API + Cloudflare DNS CNAME (`links.moatnomics.com` -> `mail.resend.com`, DNS only).~~
     - ~~100% SPF/DKIM alignment preventing spam filter drops.~~
  4. ~~**Admin Console Dispatch Desk (`web/routers/admin.py`, `web/templates/admin.html`):**~~
     - ~~Live HTML / Plain-Text preview iframe (`loadDigestPreview`).~~
     - ~~Test dispatch to admin email (`sendTestDigest`).~~
     - ~~Manual broadcast modal (`executeBroadcastDigest`) with delivery history ledger (`digest_dispatches` table).~~
  5. ~~**Automated Verification:**~~
     - ~~9 outside-in unit tests in [`tests/outside_in/test_research_bouquet_and_digest.py`](file:///Users/lyndonpinto/Documents/Stock_Research_App/tests/outside_in/test_research_bouquet_and_digest.py) passing.~~

### ~~🎨 Task 2: Vector SVG Sprite Glyphs Migration (Priority 3)~~
- ~~**Category:** UI / Design System Tokens~~
- ~~**Status:** `Completed & Verified on Disk` (2026-10-17; expanded to all 62 canonical brand/nav/pillar/sector/pricing SVGs + `#glyph-link` on 2026-10-24)~~
- ~~**Details:** Migrated all legacy OS Unicode emojis across all secondary templates (`discovery.html`, `etf_dossier.html`, `etf_matrix.html`, `fund_dossier.html`, `reit_directory.html`, `reit_dossier.html`, `admin.html`) to SVG vector sprite glyphs (`#glyph-*`). Verified: `tool_audit_design_tokens()` confirms 0 legacy emojis and 100.0/100 design token score.~~

### ~~🛡️ Task 3: Upstream `yfinance` 403 Policy Error Hardening~~
- ~~**Category:** Data Ingestion & Gateway Resilience~~
- ~~**Status:** `Completed & Verified on Disk` (2026-10-17; historical EOD candles routed via Angel One SmartAPI ahead of `yfinance` on 2026-10-24)~~
- ~~**Details:** Refactored `core/analysis/fundamentals.py` with `@suppress_yfinance_noise()` context manager suppressing stderr/logging 403 policy errors and delisted notices, routing smoothly to Angel One SmartAPI (`get_eod_summary` / `get_historical_candles`) and cached database fundamentals. All integration gateway tests passing.~~

