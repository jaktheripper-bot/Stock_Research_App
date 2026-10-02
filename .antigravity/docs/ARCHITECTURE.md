# System Architecture & Technical Knowledge Base

## 1. Core Architectural Directives
* **Zero-Hallucination Data Integrity:** Synthetic or AI-estimated financial metrics (P/E, Market Cap, 52-Week Range) are strictly prohibited. The system must enforce hard stops when live exchange quotes fail[cite: 2].
* **Two-Tier Caching & Delta Gating:** Expensive qualitative LLM regenerations trigger only on material events: price moves >= 5%, new BSE filings, or a report age > 14 days[cite: 2].

## 2. Scrip Resolution & Data Ingestion
* **5-Tier BSE Resolution:** Queries map to 6-digit BSE codes via: (1) Direct 6-Digit Code, (2) `dynamic_aliases.json`, (3) Static `PRIMARY_BSE_MAP`, (4) Active Master Universe `bse_scrips_cache.json`, and (5) Just-In-Time Gemini Grounded Search[cite: 2].
* **Ingestion:** Primary data is fetched via direct BSE exchange APIs. Missing valuation fields fall back to a consolidated `yfinance` parser, returning "N/A" rather than guessing if data is unavailable[cite: 6].

## 3. Persistence & AI Routing
* **Database Dual-Binding:** Transparent failover between PostgreSQL (Supabase) for production and SQLite (`reports.db`) for local development[cite: 2].
* **Multi-Provider Failover:** Gemini models route through a dynamic Flash cascade (defaulting to the latest compatible Flash model, filtering out single-purpose variants). If Google API exhausts retries, it fails over to Perplexity's `sonar-pro` model[cite: 2].

## 4. Modular Domain Architecture & Persistence Facade
* **Modular `core/db/` Package:** Database operations are modularized into domain-specific modules adhering to Single Responsibility:
  * `core/db/connection.py`: Thread-safe connection pooling (`_PooledConnectionProxy`), SQLite WAL fallback, dual schema migrations (v001–v006).
  * `core/db/compliance.py`: SEBI safe-harbor disclaimer and immutable compliance audit logging.
  * `core/db/reports.py`: Snapshot archiving, time-series differential revisions, and structured query retrieval.
  * `core/db/watchlist.py`: Watched scrips, automated surveillance scan timestamps, and tracking status.
  * `core/db/alerts.py`: BSE material surveillance event ledger, notification counts, and user dismissals.
  * `core/db/telemetry.py`: Privacy-preserving user action journeys, geographic/device demographics, and API credit cost savings.
  * `core/db/settings.py`: Dynamic system configuration key-value storage.
* **Zero-Breaking-Change Root Facade (`db.py`):** The root `db.py` exposes a 100% backwards-compatible facade re-exporting all symbols from `core.db`, ensuring existing scripts, test suites, and preflight checks operate with zero import breakage.
