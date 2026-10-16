# Platform Roadmap & Pending Tasks Register
**Stock Research App — Institutional Multi-Asset Research Platform**  
*Document Target:* [`docs/PENDING_TASKS.md`](file:///Users/lyndonpinto/Documents/Stock_Research_App/docs/PENDING_TASKS.md)  
*Last Updated:* 2026-10-17 00:10:00 IST  

---

## 1. High-Priority Features & Product Extensions

### 📬 Task 1: Subscribed Users Research Bouquet & Morning Digest with Custom Domain Tracking
- **Category:** Retention, Engagement & Investor Relations
- **Status:** `Pending / Planned`
- **Origin / Request:** Owner Directive (2026-10-17)
- **Functional Scope:**
  1. **Curated Research Bouquet Compilation:**
     - Periodic automated email dispatch (e.g., Weekly Market Digest or Daily 9:00 AM Morning Discovery Reel).
     - Curates a multi-asset intelligence bouquet:
       * Today's top under-the-radar equity picks from the Morning Discovery Reel.
       * Newly inducted mutual fund look-through audits and constituent coverage gains.
       * 10Y G-Sec sovereign yield curve movements, policy rate wedges, and new corporate debt / SDI issuances.
       * Highlighted unlisted MSME manufacturing champions from industrial clusters.
  2. **Subscriber Audience Filtering & Preference Management:**
     - Filter registered users for active Pro / Subscriber entitlements (`is_subscriber = True` in `user_accounts`).
     - Provide subscription preferences and statutory 1-click unsubscribe links (`/api/notifications/unsubscribe?token=...`) per IT Rules and anti-spam standards.
  3. **Branded Open & Click Tracking Subdomain (Resend + Cloudflare DNS):**
     - Configure custom tracking subdomain (e.g. `links.moatnomics.com` or `track.moatnomics.com`) via Cloudflare DNS CNAME to Resend.
     - Ensures tracking redirect links match the primary sending domain (`@moatnomics.com`), maximizing SPF/DKIM alignment and preventing emails from being flagged by corporate spam filters.
     - Captures email open rates, click-through rates (CTR) on stock dossiers, and reader engagement metrics.
  4. **Admin Console Dispatch Desk:**
     - Preview upcoming bouquet newsletter in HTML / Plain-Text.
     - Send test digest to admin email (`lyndnpnto@gmail.com`).
     - Trigger manual broadcast or enable autonomous background cron scheduling.
- **Architectural Dependencies:**
  - `core/notify.py` (Resend template synthesis & batch dispatch)
  - `web/routers/admin.py` (Broadcast controls)
  - Cloudflare DNS (`links.moatnomics.com` CNAME record)

---

## 2. Operational & Hygiene Backlog

### 🎨 Task 2: Vector SVG Sprite Glyphs Migration (Priority 3)
- **Category:** UI / Design System Tokens
- **Status:** `Active Backlog`
- **Details:** Migrate remaining legacy OS Unicode emojis across secondary templates to institutional SVG vector sprite glyphs (`#glyph-*`) to achieve 100% vector rendering across all operating systems.

### 🛡️ Task 3: Upstream `yfinance` 403 Policy Error Hardening
- **Category:** Data Ingestion & Gateway Resilience
- **Status:** `Active Backlog`
- **Details:** Refactor secondary fundamentals fallback probes in `core/analysis/fundamentals.py` and `scripts/run_project_audit.py` to gracefully bypass Yahoo Finance policy 403 blocks in favor of Angel One SmartAPI and cached database fundamentals.

### 📱 Task 4: Mobile Brief Mode (Parked P3)
- **Category:** Mobile Experience
- **Status:** `Parked (Deferred pending user demand)`
- **Details:** Compact, read-only "brief" response style for the Forensic Intelligence Desk on a mobile-first page (e.g. `/m`): 3–4 line headline score + top risk flag + link to the full desktop dossier, keeping strict SEBI non-advisory guardrails.
