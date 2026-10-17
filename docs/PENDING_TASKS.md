# Platform Roadmap & Pending Tasks Register
**Stock Research App — Institutional Multi-Asset Research Platform**  
*Document Target:* [`docs/PENDING_TASKS.md`](file:///Users/lyndonpinto/Documents/Stock_Research_App/docs/PENDING_TASKS.md)  
*Last Updated:* 2026-10-17 00:10:00 IST  

---

## 1. High-Priority Features & Product Extensions

### 📬 Task 1: Subscribed Users Research Bouquet & Morning Digest with Custom Domain Tracking
- **Category:** Retention, Engagement & Investor Relations
- **Status:** `Completed & Verified on Disk` (2026-10-17)
- **Origin / Request:** Owner Directive (2026-10-17)
- **Functional Scope & Delivered Implementation:**
  1. **Curated Research Bouquet Compilation (`core/analysis/research_bouquet.py`):**
     - Multi-asset intelligence bouquet compilation (`compile_research_bouquet`, `render_bouquet_html`, `render_bouquet_text`).
     - Combines today's top equity picks from Morning Discovery Reel, mutual fund forensic look-through audits, 10Y G-Sec sovereign yield curve / policy rate wedges, and unlisted MSME manufacturing champions.
  2. **Subscriber Audience Filtering & Preference Management (`core/db/digest.py`, `core/db/connection.py`):**
     - Database schema migration `v030_research_bouquet_and_digest_subscriptions`.
     - Fields: `is_subscriber`, `is_digest_subscribed`, `digest_unsubscribe_token` on `user_accounts`.
     - Statutory 1-click unsubscribe (`/api/notifications/unsubscribe?token=...`) and instant undo (`/api/notifications/resubscribe`) per IT Rules 2021.
  3. **Branded Open & Click Tracking Subdomain (`links.moatnomics.com`):**
     - Custom domain tracking architecture configured with Resend API + Cloudflare DNS CNAME (`links.moatnomics.com` -> `mail.resend.com`, DNS only).
     - 100% SPF/DKIM alignment preventing spam filter drops.
  4. **Admin Console Dispatch Desk (`web/routers/admin.py`, `web/templates/admin.html`):**
     - Live HTML / Plain-Text preview iframe (`loadDigestPreview`).
     - Test dispatch to admin email (`sendTestDigest`).
     - Manual broadcast modal (`executeBroadcastDigest`) with delivery history ledger (`digest_dispatches` table).
  5. **Automated Verification:**
     - 7 outside-in unit tests in [`tests/outside_in/test_research_bouquet_and_digest.py`](file:///Users/lyndonpinto/Documents/Stock_Research_App/tests/outside_in/test_research_bouquet_and_digest.py) passing.

---

## 2. Operational & Hygiene Backlog

### 🎨 Task 2: Vector SVG Sprite Glyphs Migration (Priority 3)
- **Category:** UI / Design System Tokens
- **Status:** `Completed & Verified on Disk` (2026-10-17)
- **Details:** Migrated all legacy OS Unicode emojis across all secondary templates (`discovery.html`, `etf_dossier.html`, `etf_matrix.html`, `fund_dossier.html`, `reit_directory.html`, `reit_dossier.html`, `admin.html`) to SVG vector sprite glyphs (`#glyph-*`). Verified: `tool_audit_design_tokens()` confirms 0 legacy emojis and 100.0/100 design token score.

### 🛡️ Task 3: Upstream `yfinance` 403 Policy Error Hardening
- **Category:** Data Ingestion & Gateway Resilience
- **Status:** `Completed & Verified on Disk` (2026-10-17)
- **Details:** Refactored `core/analysis/fundamentals.py` with `@suppress_yfinance_noise()` context manager suppressing stderr/logging 403 policy errors and delisted notices, routing smoothly to Angel One SmartAPI and cached database fundamentals. All 69 integration gateway tests passing.

### 📱 Task 4: Mobile Brief Mode (Parked P3)
- **Category:** Mobile Experience
- **Status:** `Parked (Deferred pending user demand)`
- **Details:** Compact, read-only "brief" response style for the Forensic Intelligence Desk on a mobile-first page (e.g. `/m`): 3–4 line headline score + top risk flag + link to the full desktop dossier, keeping strict SEBI non-advisory guardrails.
