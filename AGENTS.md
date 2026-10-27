# Workspace Directives & Agent Rules

## 1. Mandatory Backup Protocol
**Create exactly ONE backup AFTER committing changes.**
- **Pre-Commit:** Verify tests pass (`python3 -m unittest discover -s tests`). Do NOT create a pre-commit backup.
- **Post-Commit:** Execute exactly one backup via `./run.sh backup` (archives `web/` and `reports.db` to `backups/<TIMESTAMP>/`). Sync branches (`./run.sh checkpoint` or sync to `dev`) and push to `origin`.

## 2. Zero-Hallucination & Entity Registration Directives
- **Not Registered Anywhere:** We are an independent software utility and are **NOT registered anywhere**. Never imply corporate registration, corporate entities, physical office addresses, phone numbers, or GST SAC service codes anywhere.
- **Support Channels:** Strictly through on-site Feedback & Complaints Form (`/contact`). NEVER feature email IDs, phone numbers, or external contact details.
- **Name Placeholder Hygiene:** Do NOT feature personal name `Lyndon Pinto`. Use generic Indian names like `Rahul Sharma`.
- **Approachable Language:** Maintain professional, user-friendly language without condescending or unapproachable jargon.

## 3. Living Documentation Synchronization Protocol (Pre-Commit / Release Gate)
**All code, route, schema, or engine updates MUST be documented synchronously before committing or at PR/checkpoint release gate.** (To conserve AI tokens, living docs are batched at the pre-commit/release stage rather than on every intermediate tool turn).
- **Master Engineering Manual ([`docs/MASTER_ENGINEERING_MANUAL.md`](file:///Users/lyndonpinto/Documents/Stock_Research_App/docs/MASTER_ENGINEERING_MANUAL.md)):** Update Section 1 (Route Directory), Section 2 (Architectural Layers), Section 4 (Code-to-Feature Directory), Section 6 (Append latest checkpoint to Master Build Ledger).
- **Evaluation Frameworks ([`docs/REPORT_EVALUATION_FRAMEWORKS.md`](file:///Users/lyndonpinto/Documents/Stock_Research_App/docs/REPORT_EVALUATION_FRAMEWORKS.md)):** Update formulas, ingestion gateways, TTLs, and invalidation rules for report calculation mechanics.
- **System Architecture ([`.antigravity/docs/ARCHITECTURE.md`](file:///Users/lyndonpinto/Documents/Stock_Research_App/.antigravity/docs/ARCHITECTURE.md)):** Synchronize architectural directives and persistence mechanisms.
- **Strict Anti-Hallucination Guardrail:** NEVER document planned features or offline prototypes as live pipelines until merged and active on `main`.

## 4. Pre-Implementation Consequence & Blast-Radius Protocol (Think Before Coding)
**Never write or modify code until 2nd- and 3rd-order consequences are traced end-to-end.** For any change to ingestion, scoring, classification, schemas, or synthesis, activate the `consequence-sandbox-testing` skill first.
- **Brief Dissection:** Clarify underspecified briefs, edge cases, and cadences before executing.
- **Constructive Pushback:** If a request has hidden risks, regulatory pitfalls (e.g. SEBI compliance), architectural anti-patterns, or creates static facades / stale data, explain the root cause and propose a resilient alternative.
- **Forbid Shortcuts:** Never substitute an end-to-end dynamic workflow with a one-time static seed unless explicitly instructed.
- **End-to-End Consumer & Failure Trace:** Before editing any function, map:
  1. *Degraded Inputs:* Exact behavior when upstream APIs/caches return `None`, `0`, `"N/A"`, `{}` or timeout.
  2. *Downstream Chain:* Every caller, screening gate, `except` handler, persisted column **AND serialized prose/JSON blob** (`report_text`, `dossier_text`, `pillar_breakdown_json`), and UI template consuming that data.
- **Fail-Closed Domain Integrity ("Pending Over Potemkin"):** NEVER write fallback templates, proxy portfolio clones, or default financial metrics (`price=100`, `roce=22.4`, `revenue_cr=100`) when live data or LLM synthesis fails. Fail closed to an explicit `PENDING` / unarchived state and retry next cycle; never emit `[VERIFIED FACT]` or `[CALCULATED METRIC]` on fallback values.
- **Process & Environment Isolation:** Background ingestion/mutation schedulers must NEVER auto-fire on local web server boot or test runs without an explicit `ENABLE_BACKGROUND_SCHEDULERS=1` opt-in guard.

## 5. Mandatory Sandbox Simulation & Empirical Verification Protocol
**Work out edge cases in `<appDataDir>/brain/<conversation-id>/scratch/` against cloned data BEFORE mutating workspace databases or committing.**
- **Phase 0 (Compliance Check):** Re-read brief line-by-line; construct requirement vs file:line matrix.
- **Phase 0.5 (Sandbox Blast-Radius Simulation):**
  - Clone `reports.db` to `scratch/` (or run read-only scratch probes) and execute new classifiers, regexes, scorers, or migrations across **100% of corpus rows** (never 2–3 happy-path tickers). Inspect category distributions and outliers (e.g. catching `"IT"` matching `"LIMITED"` or `"ADITYA"`).
  - Simulate degraded/offline upstream responses (`API_KEY=""`, empty quote dict) in sandbox and verify **0** template/fabricated rows are persisted.
- **Phase 1 (Ground Truth):** Inspect modified lines in destination files; verify zero forgotten items.
- **Phase 2 (Runtime, Substance & Test Validation):** Run unit/integration tests (`python3 -m unittest discover -s tests`), `scripts/run_project_audit.py --quick`, and payload substance checks (prose uniqueness + header-vs-prose numerical parity).
- **Phase 3 (Git State):** Confirm clean tree (`git status`) and aligned tracking branches.

## 6. Mandatory Outside-In Testing Protocol (UI-to-Code Contracts)
**Always test from user interaction down to code contract (never inside-out HTTP 200 checks alone).**
1. **Trigger Affordance & JS Wiring:** Buttons must have tactile classes (`.btn`, `.btn-primary`); every `onclick="handler()"` must map to an active, valid JS function in loaded scripts.
2. **Interaction & Progress State:** Async actions must show loading/progress states and restore gracefully upon completion/failure.
3. **DOM Element Binding Contracts:** Every `document.getElementById('xyz')` queried by client scripts must exist in target rendered DOM.
4. **Modal Centering & Inert Ancestor Guard:** Modals must adhere to `.modal-backdrop` and `.modal-dialog` contracts under `<body>` (or hoisted via `document.body.appendChild(modal)`), never nested inside containers with `overflow: hidden` or an ancestor with `.inert = true` / `aria-hidden="true"`. Must call `.focus({ preventScroll: true })` synchronously on click, enforce input `font-size >= 16px`, and support `Escape` + backdrop dismissal.
5. **Client-Side API Contracts:** Every AJAX `fetch('/api/...')` must match registered server routes with valid payloads.
6. **Substantive Analytical Depth:** Modals and cards must render genuine domain intelligence, never trivial echoes.
7. **Template Attribute & Rendering Hygiene:** Zero unrendered Jinja (`{{` or `{%`) in attributes; NO backslash-escaped quotes (`\"` or `\'`) inside HTML tag attributes; inline `<svg>` must have explicit `.glyph` classes or dimensions.
8. **Real Pointer Hit-Testing in Browser Audits:** Use real Playwright pointer actions (`page.locator(trigger).click()`), never `page.evaluate()` bypasses.
9. **Universal Hover-to-Click Card Affordance:** Any card with hover elevation/pointer (`.card.asset-card-accent`, `.pillar-card`, `.bento-card`) must resolve to a valid primary link or modal trigger.
10. **Two-Tier Navigation Contract:** Tier 1 (Directory & Static Pages) uses top progress ribbon (`#pageNavProgressRibbon`) + `@view-transition`; Tier 2 (Deep-Dive Asset Dossiers) uses Evaluation HUD (`#synthesizingOverlay`) with background pre-fetching.
11. **Authenticated Route Layout Parity:** Test admin consoles (`/admin`) with session cookies for zero layout clipping and button bounds `<= 400px`.

## 7. Anti-Staleness & Data Freshness Invariant
- **Zero Static Facades:** Never implement static seed pools as live feeds.
- **Genuine Cadence & Rotation:** Cadenced features ("Morning Discovery @9AM", "AMFI Sync") must implement active background scheduling with real timestamps.
- **No Test Scheduler Blindspots:** Test scheduler workers directly without mocks, asserting count/timestamp progression.
- **Data Provenance Badges:** Render explicit data provenance and last-updated timestamps (`last_updated` / `edition_date`).

## 8. Zero-Illusion Reality Verification & Forbidden Patterns (AST Gate)
- **Pre-Completion Gate:** Execute `python3 scripts/verify_reality_audit.py` before completing any turn modifying `.py`, `.js`, `.html`, or `.css`. Must resolve all `[GATE-1]` through `[GATE-12]` failures.
- **Forbidden Patterns:**
  - No auth fallbacks in catch/except blocks.
  - No deterministic Mad-Libs prose fallbacks, cloned proxy holdings across distinct schemes, or synthetic numeric defaults in analytical engines.
  - No unanchored substring taxonomy matching (`"IT" in text`) for short tokens; enforce strict `\b...\b` regex word boundaries.
  - No module-level user session globals (use `ContextVar` or signed `HttpOnly` cookies).
  - No unverified TLS (`ssl._create_unverified_context()` forbidden; use `certifi.where()`).
  - No silent exception swallowing (log via `logger.error`/`logger.warning`; never fabricate metrics).
  - No audit gaming (`AUDIT_RECURSION_GUARD` checks forbidden).
  - No unencoded `JSONResponse` on DB dicts (wrap with `fastapi.encoders.jsonable_encoder(data)`).
  - No unescaped `%` in parameterized `psycopg2` queries (bind `LIKE` patterns as parameters).
  - No backslash-escaped attribute quotes in HTML templates (`<tag attr=\"val\">` forbidden by AST Gate 12.3).
- **Exhaustive Glob Over Manual Lists:** Enumerate 100% of templates via `Path("web/templates").rglob("*.html")`.
- **Zero Computed-But-Unscored Metrics:** All metrics in `pillar_breakdown_json` must factor into scoring and Markdown reports.
- **Zero Hardcoded Metadata:** Query test counts and migration versions dynamically from runtime state.
- **Payload Substance & Cross-Layer Parity:** Dossier prose (`report_text` / `dossier_text`) must pass N-gram uniqueness (`< 25%` 8-gram overlap across distinct entities) and match structured header metrics (`current_price`, `market_cap`, `pe_ratio`, `roce`) within drift tolerance.

## 9. Mandatory UI, Theme & Brand Changeover Protocol
Complete all 6 gates on visual identity or theme updates:
1. **Multi-Theme Computed Contrast:** WCAG contrast (`>= 4.5:1` normal text, `>= 3.0:1` badge text) across `html[data-theme="light"]`, `html[data-theme="dark"]`, and `.dossier-ivory-surface`.
2. **Pseudo-Element & Overflow Hygiene:** Ambient glows must not render as clipped rectangles; enforce `overflow-x: auto !important; max-width: 100%` on `.table-sticky-wrap`.
3. **Cross-Asset Directory Layout Parity:** All 9 directories default to 3-column Biscuit Card Grid (`.card.asset-card-accent`) with optional `Compact Table` toggle.
4. **Multi-Format Brand Asset Sync:** Regenerate `favicon.svg`, `logo-mark.svg`, `favicon-32x32.png`, `favicon-64x64.png`, `apple-touch-icon.png`, and `favicon.ico` together; bump `?v=YYYYMMDD_HHMM` cache-bust.
5. **Information Architecture & Confident Copy:** Keep *Our Core Competence* distinct from *The Assets We Cover*. Never use filler words (`"Try:"`) or unverified superlatives.
6. **Full-Site Chrome CDP Microscope Sign-Off:** Assert 0 console errors, 0 failed network requests, 0 horizontal overflows, 0 dead hover cards, 0 contrast failures.
