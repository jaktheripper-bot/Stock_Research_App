# Workspace Directives & Agent Rules

## 1. Mandatory Backup Protocol
**Create exactly ONE backup AFTER committing changes.**

- **Pre-Commit:**
  - Verify that tests pass (`python3 -m unittest discover -s tests`).
  - Do NOT create a pre-commit backup.
- **Post-Commit:**
  - Immediately execute exactly one backup via `./run.sh backup` (which tars `web/` and `reports.db` to `backups/<TIMESTAMP>/`) to archive the newly committed state.
  - Sync with local tracking branches / checkpoints (`./run.sh checkpoint` or sync to `dev`).
  - Push commit to remote `origin` to secure work in cloud storage.

## 2. Zero-Hallucination & Entity Registration Directives
- **Not Registered Anywhere:** We are an independent software tool and are **NOT registered anywhere**. Never imply corporate registration, corporate entities, physical office addresses, phone numbers, or GST SAC service codes anywhere on the platform or in documents.
- **Support Channels:** Strictly through the on-site Feedback & Complaints Form (`/contact`). NEVER feature email IDs, phone numbers, or external contact details on the site. All inquiries and complaints are reviewed directly by the user/owner via the Admin Console.
- **Name Placeholder Hygiene:** Do NOT feature the user's personal name (`Lyndon Pinto`) in UI templates or form examples. Use generic Indian names like `Rahul Sharma`.
- **Approachable Language:** Maintain professional, user-friendly language without condescending or unapproachable jargon.

## 3. Mandatory Living Documentation Synchronization Protocol
**Every time ANY code, route, engine, database schema, or feature is updated, the corresponding system documentation MUST be updated synchronously before committing.**

- **Master Engineering Manual ([`docs/MASTER_ENGINEERING_MANUAL.md`](file:///Users/lyndonpinto/Documents/Stock_Research_App/docs/MASTER_ENGINEERING_MANUAL.md)):**
  - **Section 1 (Site Inventory & Route Directory):** Keep sitemap topology and route matrix strictly aligned with active `web/main.py` routes, modals, and templates.
  - **Section 2 (Architecture & Component Breakdown):** Document all new or modified analytical engines, coordinators, gateways, and architectural layers.
  - **Section 3 (Operational Process Flows):** Keep Mermaid sequence diagrams accurate to real runtime execution flows and caller handshakes.
  - **Section 4 (Code-to-Feature Directory):** Maintain exact function names, file paths, entry points, caller locations, and known failure modes with diagnostic fixes.
  - **Section 6 (Master Historical Build Ledger):** Append the new release checkpoint tag, git commit hash, timestamp, and summary of changes.
- **Report Evaluation Frameworks ([`docs/REPORT_EVALUATION_FRAMEWORKS.md`](file:///Users/lyndonpinto/Documents/Stock_Research_App/docs/REPORT_EVALUATION_FRAMEWORKS.md) & [`.antigravity/docs/EVALUATION_FRAMEWORKS.md`](file:///Users/lyndonpinto/Documents/Stock_Research_App/.antigravity/docs/EVALUATION_FRAMEWORKS.md)):**
  - Update mathematical formulations, ingestion gateways, TTLs, and invalidation rules whenever report calculation mechanics or data feeds change.
- **System Architecture ([`.antigravity/docs/ARCHITECTURE.md`](file:///Users/lyndonpinto/Documents/Stock_Research_App/.antigravity/docs/ARCHITECTURE.md)):**
  - Keep architectural directives, persistence mechanisms, and presentation controller layers synchronized with production code.
- **Strict Anti-Hallucination Guardrail in Documentation:**
  - NEVER document planned features, offline prototypes, or standalone experiments as live inline production pipelines or autonomous background daemons until they are fully integrated, tested, and active on `main`.

## 4. Proactive Critical Thinking, Intent Clarification & Constructive Pushback
- **Pre-Execution Brief Dissection:** Before touching code or proposing solutions, systematically break down the user's brief. If ANY requirement, edge case, data source, or intended cadence is ambiguous or underspecified, STOP and ask clarifying questions first.
- **Challenge Suboptimal Briefs & Push Back:** If a user request has hidden risks, regulatory pitfalls (e.g. SEBI compliance), architectural anti-patterns, or will result in static facades / stale data, DO NOT passively execute it. Explicitly push back, explain the root cause, and propose a resilient alternative.
- **Forbid Assumptions & Shortcuts:** Never substitute an end-to-end dynamic workflow with a one-time static seed or mock unless explicitly instructed that a static prototype is desired.
- **Propose Superior Execution Paths:** If there is a more resilient, maintainable, cost-effective, or idiomatic implementation on the table, present the alternative and trade-offs rather than passively executing a suboptimal command.

## 5. Mandatory Empirical Verification Protocol Before Declaring Task Completion
**NEVER state or declare that a task, feature, or remediation is completed without first empirically double-checking and verifying that every single change discussed in the session is actually implemented on disk and active in code.**

### Phase 0: Pre-Testing Brief Compliance Re-Check Gate (MANDATORY)
BEFORE executing unit tests or declaring work ready:
1. Re-read the user's original request and all subsequent refinements line-by-line.
2. Construct a side-by-side compliance matrix: `[Original Requirement] vs. [Exact File & Line Implemented]`.
3. Forbid shortcuts, half-script stubs, or mock-only bypasses.
4. Verify that the implementation solves the ROOT CAUSE and not just a superficial symptom.

### Phase 1: Ground-Truth File Inspection
- Directly inspect the modified lines in destination files using file viewing or search tools before summarizing results. Never assume an edit succeeded based on intent alone.
- Compare the live diff and working tree against every action item, discussion point, and user request raised in the session to ensure zero unaddressed or forgotten items.

### Phase 2: Runtime & Test Validation
- Execute the test suite and verification tools (`python3 -m unittest discover -s tests`, `scripts/run_project_audit.py --quick`) and inspect actual runtime outputs before reporting completion.
- Zero Premature Conclusions: If any change is partial, blocked, or pending further user input, explicitly disclose its exact state rather than asserting that the task is finished.

### Phase 3: Git State & Remote Alignment
- Confirm working tree is clean (`git status`), commits and annotated tags are pushed, and tracking branches (`main`, `dev`, `origin`) are strictly aligned.

## 6. Mandatory Outside-In Testing Protocol (UI-to-Code Contracts)
**Never test simply from the inside-out (validating backend mathematical functions and asserting HTTP 200). Always test from the outside-in (user interaction contract down to code).**

Whenever authoring, refactoring, or verifying web pages, modals, buttons, or interactive forms, the test suite and verification workflow MUST empirically validate:
1. **Trigger Affordance & JS Wiring:**
   - Every `<button>` or interactive trigger must feature valid tactile classes (`.btn`, `.btn-primary`, `.btn-secondary`), clear user-facing labels, and non-empty action attributes.
   - Every `onclick="handler()"` attribute in HTML templates must map to an active, syntactically valid JavaScript function in loaded scripts, preventing undefined ReferenceErrors.
2. **Interaction & Progress State:**
   - User actions that trigger async operations must immediately reflect an active loading/progress state (e.g. disabling the trigger, showing `"Analyzing..."` or a spinner) and restore gracefully upon completion or failure.
3. **DOM Element Binding Contracts (Zero Null References):**
   - Every `document.getElementById('xyz')` queried by client scripts must be statically verified or runtime-asserted against the target rendered DOM.
   - Forbid tests that pass HTTP 200 while client-side scripts throw runtime `TypeError: Cannot set property 'innerText' of null`.
4. **Modal Centering, Top-Layer Portaling & Inert Ancestor Guard:**
   - Every modal MUST adhere to the standardized `.modal-backdrop` and `.modal-dialog` contract and reside directly under `<body>` (outside `<main>`), or dynamically hoist itself via `document.body.appendChild(modal)` on load/open.
   - Modals must NEVER be nested inside containers with `overflow: hidden`, `overflow-x: auto`, `contain: layout/paint`, or any ancestor that sets `.inert = true` or `aria-hidden="true"` (`if (mainEl && !mainEl.contains(modal)) mainEl.inert = true`). Setting `.inert = true` on an ancestor of an open modal locks out all pointer/touch events and traps the user.
   - Every modal with a text input/textarea MUST call `.focus({ preventScroll: true })` synchronously within the user click gesture tick (never solely inside `setTimeout`, which drops the mobile virtual keyboard gesture token) and enforce `font-size >= 16px` (`1rem`).
   - Every modal MUST include a functional close button (`type="button"`), backdrop-click dismissal, and `Escape` key listener.
5. **Client-Side API Route Contracts:**
   - Every AJAX `fetch('/api/...')` target in JavaScript or inline scripts must be cross-referenced against active, registered FastAPI server routes with valid parameter payloads.
6. **Substantive Analytical Depth (Value Covenant):**
   - Interactive modals, deep-dive cards, and analytical drawers must render genuine domain intelligence (credit risk ratios, working capital cycles, benchmark deltas, moat scores, failure mode alerts), never trivial data echoes or hollow placeholder text.
7. **Template Attribute & Rendering Hygiene:**
   - Rendered HTML must be audited with BeautifulSoup to assert zero unrendered Jinja expressions (`{{` or `{%`) leak into `href`, `onclick`, `id`, `class`, or `data-*` attributes.
8. **Real Pointer Hit-Testing in Browser Audits (Zero `page.evaluate()` Bypasses):**
   - When verifying modals, drawers, inputs, or buttons in Chrome/Playwright, NEVER use `page.evaluate(() => openModal())` or `page.evaluate(() => closeModal())` to simulate user interaction. Direct JS invocation bypasses browser hit-testing (`[inert]`, `pointer-events: none`, z-index obscuration, off-screen clipping).
   - Always use real Playwright pointer/keyboard actions (`page.locator(trigger).click()`, `page.locator(input).click()`, `page.keyboard.type(...)`, `page.locator(closeBtn).click()`) and assert `document.activeElement === input` and `!modal.closest('[inert]')`.
9. **Universal Hover-to-Click Card Affordance Invariant (Zero Dead Hover Cards):**
   - Any card or container that visually elevates, shifts border color, or displays `cursor: pointer` on `:hover` (`.pillar-card`, `.asset-card-accent`, `.discovery-card`, `.bento-card`, `.pricing-card`) MUST resolve to a valid primary navigation link or modal trigger when clicked anywhere on its body (via `resolveCardPrimaryAction` / `data-href` / inner `a[href]` or `button[onclick]`). Never style a static, non-interactive informational box with interactive hover elevation unless it is exclusively inside the `.core-competence-showcase`.
10. **Two-Tier Navigation Contract (Instant Page Transitions vs. Report Synthesis HUD):**
   - **Tier 1 (Directory, Tool & Static Pages):** Navigating between top-level directories (`/equities`, `/funds`, `/etfs`, `/debt`, `/sovereign`, `/reits`, `/opportunities`, `/msme`, `/safety-radar`, `/discovery`, `/calculator/tax`, `/pricing`) MUST use the non-blocking top progress ribbon (`#pageNavProgressRibbon`) and CSS `@view-transition`, NEVER a blocking full-screen timer modal.
   - **Tier 2 (Deep-Dive Asset Dossiers & Pairwise Overlaps):** The full-screen Evaluation HUD (`#synthesizingOverlay`) is reserved strictly for individual asset report synthesis/loading (`/dossier/{ticker}`, `/funds/{code}`, `/debt/{isin}`, `/reits/{symbol}`, `/etfs/{symbol}`, `/msme/{uin}`, `/compare?a=...&b=...`, `/funds/compare/overlap?scheme_a=...&scheme_b=...`) and must continue pre-fetching in the background (`✓ Ready — Open Report →`) if dismissed early.

## 7. Anti-Staleness & Data Freshness Invariant (Zero Static Facades)
**If the platform's mission is asset discovery and shielding allocators from bad data, stale data is a catastrophic failure mode.**

Whenever authoring, refactoring, or maintaining scheduled pipelines, discovery feeds, directories, or catalog screeners:
1. **Zero Static Facades:** Never implement a static seed, hardcoded mock pool, or one-off database script and present it as a live, dynamic, or scheduled daily feed.
2. **Genuine Cadence & Rotation:** Any feature advertised with a cadence (e.g. "Morning Discovery @9AM", "Daily MSME Ingestion", "Nightly AMFI Sync") must implement active background scheduling that rotates entities, ingests fresh records, or records real-time execution timestamps.
3. **No Test Scheduler Blindspots:** Schedulers must not be tested solely by checking if the app boots with `TESTING=1`. Tests must directly invoke the scheduler worker functions without mocks, asserting that database record counts increase or time-series timestamps advance.
4. **Data Provenance & Freshness Badges:** Every rendered asset card or directory must explicitly display its data provenance and last-updated timestamp (`last_updated` / `edition_date`).

## 8. Zero-Illusion Reality Verification & Forbidden Patterns (AST Gate)

### 8.1 Mandatory Pre-Completion Verification Gate
- Never claim a task, bug fix, or feature is complete based solely on `py_compile`, syntax checks, or mocked unit tests.
- Before ending ANY turn that modifies `.py`, `.js`, `.html`, or `.css` files in `core/` or `web/`, you MUST execute:
  `python3 scripts/verify_reality_audit.py`
- If `verify_reality_audit.py` returns a non-zero exit code, you MUST fix all reported `[GATE-1]` through `[GATE-12]` failures before yielding back to the user.

### 8.2 Forbidden Code Patterns (Enforced by AST Gate & CI Pipeline)
- **No Auth Fallbacks:** Never create a session or log a user in inside a `catch`/`except` or non-200 fallback block.
- **No Module-Level Session Globals:** Never store user identity in module-level variables (`_BARE_USER_SESSION`, `_BARE_AUTH_TOKEN`). Always use request-scoped `contextvars.ContextVar` or signed `HttpOnly` cookies.
- **No Unverified TLS:** Never use `ssl._create_unverified_context()`; always use `ssl.create_default_context(cafile=certifi.where())`.
- **No Silent Exception Swallowing:** Every `except Exception as e:` block in `core/` or `web/` must log via `logger.error(...)` or `logger.warning(...)` and never return fabricated financial/ESG metrics (`82/80/88`, `0.0% Pledged`, or synthetic `UDYAM-MH-26-*` entities).
- **No Audit Gaming:** Never set or check `AUDIT_RECURSION_GUARD` to return hardcoded test counts or mock-pass statements.
- **No Unencoded `JSONResponse` on DB Dicts (SQLite-vs-Postgres Parity):** Never pass raw database row dicts directly to `JSONResponse(content=data)` without wrapping in `fastapi.encoders.jsonable_encoder(data)`. SQLite returns `DATE`/`TIMESTAMP` as `str`, whereas PostgreSQL (`psycopg2`) returns `datetime.date`/`datetime.datetime`/`Decimal`, causing HTTP 500 `TypeError` in production if unencoded.

### 8.3 Zero-Blindspot & "Audit-the-Auditor" Invariant
- **Exhaustive Glob Over Manual Lists:** Whenever executing a site-wide sweep (visual tokens, SVG sprites, compliance copy, or route audits), ALWAYS enumerate `100%` of files via `Path("web/templates").rglob("*.html")` (including admin sub-templates like `admin_audit.html`) and `app.routes`, never a partial hand-picked list or sample emoji subset.
- **Zero Computed-But-Unscored Metrics:** Every diagnostic metric computed in `core/audit/tools.py` and stored in `pillar_breakdown_json` (such as `unlogged_exceptions_count`) MUST be wired into both the pillar score calculation and the rendered Markdown report in `core/audit/project_auditor.py`. Furthermore, `verify_reality_audit.py` and `core/audit/tools.py` must enforce identical AST rules.
- **Zero Hardcoded Metadata in Audit Reports:** Audit report generators and admin consoles (`core/audit/project_auditor.py`, `web/templates/admin_audit.html`) must never hardcode historical test counts (`129+`), migration versions (`v022`), or defunct route labels (`/discovery`). All counts and versions must be dynamically queried from runtime state.
- **Inspect the Persisted Report, Stderr & DB Side-Effects:** Never rely solely on an audit script's `0` exit code or stdout summary banner. Always read the persisted `project_audit_logs` record (`pillar_breakdown_json` and `full_markdown_report`), treat SDK/runtime warnings in stderr as actionable defects, and ensure audit probes do not pollute live `site_usage_events` telemetry.

## 9. Mandatory UI, Theme & Brand Changeover Protocol
Whenever executing a site-wide visual identity, theme, layout, or copy changeover, you MUST complete all 6 gates before declaring completion:
1. **Multi-Theme Computed Contrast Audit (`Light` + `Dark` + `Ivory`):** Verify via headless Google Chrome (`getComputedStyle`) across all 30 routes and 8 modals that every text element meets WCAG contrast thresholds (`>= 4.5:1` normal text, `>= 3.0:1` large/badge text) in `html[data-theme="light"]`, `html[data-theme="dark"]`, and `.dossier-ivory-surface`. Watch specifically for inline `style="color:..."` attributes in Python parsers (`core/analysis/parser.py`, `web/legal_content.py`) and ensure every `[data-asset-class]` token has both Light Mode and luminous Dark Mode definitions.
2. **Pseudo-Element & Overflow Hygiene:** Inspect all `::before` / `::after` pseudo-elements and corner decorative `<div>` overlays when switching background themes so dark-mode ambient glows do not render as clipped geometric rectangles in Light Mode. Enforce `overflow-x: auto !important; max-width: 100%` on all `.table-sticky-wrap` containers so wide tables never bleed outside card borders (`scrollWidth <= clientWidth`).
3. **Cross-Asset Directory Layout & Filter Tab Parity:** All 9 asset directories (`/equities`, `/funds`, `/etfs`, `/debt`, `/sovereign`, `/reits`, `/opportunities`, `/msme`, `/safety-radar`) must default to the uniform 3-column **Snapshot Biscuit Card Grid** (`.card.asset-card-accent`) with an optional `Compact Table` toggle where dense comparison is needed. Every filter tab URL (e.g., `/debt?is_sdi=true`, `/debt?seniority=SENIOR_SECURED`) must be tested to assert `> 0` rendered cards and auto-seed fallback if only test rows exist in the table.
4. **Multi-Format Favicon & Brand Asset Sync:** Updating any brand mark or favicon requires regenerating **all** formats simultaneously (`favicon.svg`, `logo-mark.svg`, `favicon-32x32.png`, `favicon-64x64.png`, `apple-touch-icon.png`, and root `/favicon.ico`) and bumping the `?v=YYYYMMDD_HHMM` cache-bust query string in `web/templates/base.html`.
5. **Information Architecture & Confident Copy Hygiene:** Keep **Our Core Competence** (methodology, deterministic solvers, grounded glass-box multi-agent AI, epistemic falsification) structurally distinct from **The Assets We Cover**. Never use tentative filler words (`"Try:"`) or unverified superlatives.
6. **Full-Site Chrome CDP Microscope Sign-Off:** Run the automated Chrome CDP Microscope across all 30 routes and 8 modals asserting `0` console errors, `0` uncaught page errors, `0` failed network requests, `0` horizontal overflows, `0` dead hover cards, and `0` contrast failures.
