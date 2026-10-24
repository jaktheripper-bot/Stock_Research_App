# Platform Roadmap & Pending Tasks Register
**Moatnomics — Multi-Asset Investment Research Platform**  
*Document Target:* [`docs/PENDING_TASKS.md`](file:///Users/lyndonpinto/Documents/Stock_Research_App/docs/PENDING_TASKS.md)  
*Last Updated:* 2026-10-24 12:24:00 IST  

---

## 1. Active, In-Progress & Parked Tasks

### Task 5: Track 3 Language & Voice, Open Items
- **Category:** Brand, Copy & Compliance Wording
- **Status:** `In Progress` (Phases 1–3 shipped 2026-10-20; `/terms` statutory 7-section realignment shipped 2026-10-23; items below remain open)
- **Details:**
  1. Reference the hero banners (`img/heroes/*.webp`) and portal plates (`img/brand/portal-*.webp`) from their pages, after a browser review of text contrast.
  2. Replace the remaining raw emojis in `web/main.py` server messages and `web/templates/admin.html` console with sprite icons.
  3. Decide whether to migrate stored values (`SURGICAL_REFRESH`, `FULL_SYNTHESIS`, contact category `synthesis`, existing `BSE Surveillance` alert rows) to the new wording; needs a data migration.
  4. ~~Owner decision on whether to retain or update the phrase `"computational financial research synthesis software utility"` inside `MANDATORY_SEBI_DISCLAIMER` (`core/db/compliance.py`) — updated to `"independent multi-asset investment research platform and software utility"` (`Completed 2026-10-24`).~~
  5. Hindi: per-language voice rules, string catalogues and the `language` parameter of `get_system_prompt()` (deferred).
  6. ~~Replace remaining raw emojis in public templates, `web/static/js/main.js`, and `web/static/js/opportunity_terminal.js` with sprite icons (`Completed 2026-10-21`).~~
  7. ~~Update `/terms` legal characterisation in `web/legal_content.py` to `"multi-asset investment research platform"` and `"independent software utility, not a registered fiduciary"` (`Completed 2026-10-23`).~~

### 📱 Task 4: Mobile Brief Mode (Parked P3)
- **Category:** Mobile Experience
- **Status:** `Parked (Deferred pending user demand)`
- **Details:** Compact, read-only "brief" response style for the Research Desk on a mobile-first page (e.g. `/m`): 3–4 line headline score + top risk flag + link to the full desktop dossier, keeping strict SEBI non-advisory guardrails.

---

## 2. Completed Tasks (Moved to Bottom)

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

