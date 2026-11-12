# Platform Roadmap & Pending Tasks Register
**Moatnomics — Multi-Asset Investment Research Platform**  
*Document Target:* [`docs/PENDING_TASKS.md`](file:///Users/lyndonpinto/Documents/Stock_Research_App/docs/PENDING_TASKS.md)  
*Last Updated:* 2026-11-12 20:45:00 IST

---

## 1. Active, In-Progress & Parked Tasks

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
- **Status:** `In Progress` (Phases 1–3 shipped 2026-10-20; `/terms` statutory 7-section realignment shipped 2026-10-23; visual hero/portal integration & emoji cleanup shipped 2026-10-24)
- **Details:**
  1. Decide whether to migrate stored values (`SURGICAL_REFRESH`, `FULL_SYNTHESIS`, contact category `synthesis`, existing `BSE Surveillance` alert rows) to the new wording; needs a data migration.
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

