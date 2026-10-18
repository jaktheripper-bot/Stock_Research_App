# Backup and Safety Protocol

## Rule 1: Mandatory Backup Protocol
**Create exactly ONE backup AFTER committing changes.**

- **Pre-Commit:**
  - Verify that tests pass (`python3 -m unittest discover -s tests`).
  - Verify outside-in UI-to-code contracts for any modified templates or routes.
  - Do NOT create a pre-commit backup.
- **Post-Commit:**
  - Immediately execute exactly one backup via `./run.sh backup` (which tars `web/` and `reports.db` to `backups/<TIMESTAMP>/`) to archive the newly committed state.
  - Sync with local tracking branches / checkpoints (`./run.sh checkpoint` or sync to `dev`).
  - Push commit to remote `origin` to secure work in cloud storage.

## Rule 2: Zero-Hallucination & Entity Registration Directives
- **Not Registered Anywhere:** We are an independent software tool and are **NOT registered anywhere**. Never imply corporate registration, corporate entities, physical office addresses, phone numbers, or GST SAC service codes anywhere on the platform or in documents.
- **Support Channels:** Strictly through the on-site Feedback & Complaints Form (`/contact`). NEVER feature email IDs, phone numbers, or external contact details on the site. All inquiries and complaints are reviewed directly by the user/owner via the Admin Console.
- **Name Placeholder Hygiene:** Do NOT feature the user's personal name (`Lyndon Pinto`) in UI templates or form examples. Use generic Indian names like `Rahul Sharma`.
- **Approachable Language:** Maintain professional, user-friendly language without condescending or unapproachable jargon.

## Rule 3: Mandatory Living Documentation Synchronization Protocol
Whenever any code, route, analytical engine, database schema, or feature is updated, system documentation must be updated synchronously in the same commit:
- **`docs/MASTER_ENGINEERING_MANUAL.md`**: Section 1 (Routes/Modals), Section 2 (Components), Section 3 (Flows), Section 4 (Code Matrix & Fixes), Section 6 (Build Ledger).
- **`docs/REPORT_EVALUATION_FRAMEWORKS.md` & `.antigravity/docs/EVALUATION_FRAMEWORKS.md`**: Mathematical formulations, criteria, data sources.
- **`.antigravity/docs/ARCHITECTURE.md`**: Active architectural components and SSR controllers.
- **Strict Anti-Hallucination Guardrail in Documentation:** Never document planned features, offline prototypes, or standalone experiments as live inline production pipelines until fully integrated and tested on `main`.

## Rule 4: Proactive Critical Thinking, Intent Clarification & Constructive Pushback
- **Pre-Execution Brief Dissection:** Before touching code or proposing solutions, systematically break down the user's brief. If ANY requirement, edge case, data source, or intended cadence is ambiguous or underspecified, STOP and ask clarifying questions first.
- **Challenge Suboptimal Briefs & Push Back:** If a user request has hidden risks, regulatory pitfalls (e.g. SEBI compliance), architectural anti-patterns, or will result in static facades / stale data, DO NOT passively execute it. Explicitly push back, explain the root cause, and propose a resilient alternative.
- **Forbid Assumptions & Shortcuts:** Never substitute an end-to-end dynamic workflow with a one-time static seed or mock unless explicitly instructed that a static prototype is desired.
- **Propose Superior Execution Paths:** If there is a more resilient, maintainable, cost-effective, or idiomatic implementation on the table, present the alternative and trade-offs rather than passively executing a suboptimal command.

## Rule 5: Mandatory Empirical Verification Protocol Before Declaring Task Completion
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

## Rule 6: Mandatory Outside-In Testing Protocol (UI-to-Code Contracts)
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
4. **Modal Centering & Viewport Architecture:**
   - Every modal MUST adhere to the standardized `.modal-backdrop` and `.modal-dialog` contract.
   - Modals must NEVER be nested inside containers with `overflow: hidden`, `overflow-x: auto`, or relative layout traps that clip them outside the viewport upon scrolling.
   - Every modal MUST include a functional close button, backdrop-click dismissal, and `Escape` key listener.
5. **Client-Side API Route Contracts:**
   - Every AJAX `fetch('/api/...')` target in JavaScript or inline scripts must be cross-referenced against active, registered FastAPI server routes with valid parameter payloads.
6. **Substantive Analytical Depth (Value Covenant):**
   - Interactive modals, deep-dive cards, and analytical drawers must render genuine domain intelligence (credit risk ratios, working capital cycles, benchmark deltas, moat scores, failure mode alerts), never trivial data echoes or hollow placeholder text.
7. **Template Attribute & Rendering Hygiene:**
   - Rendered HTML must be audited with BeautifulSoup to assert zero unrendered Jinja expressions (`{{` or `{%`) leak into `href`, `onclick`, `id`, `class`, or `data-*` attributes.

## Rule 7: Anti-Staleness & Data Freshness Invariant (Zero Static Facades)
**If the platform's mission is asset discovery and shielding allocators from bad data, stale data is a catastrophic failure mode.**

Whenever authoring, refactoring, or maintaining scheduled pipelines, discovery feeds, directories, or catalog screeners:
1. **Zero Static Facades:** Never implement a static seed, hardcoded mock pool, or one-off database script and present it as a live, dynamic, or scheduled daily feed.
2. **Genuine Cadence & Rotation:** Any feature advertised with a cadence (e.g. "Morning Discovery @9AM", "Daily MSME Ingestion", "Nightly AMFI Sync") must implement active background scheduling that rotates entities, ingests fresh records, or records real-time execution timestamps.
3. **No Test Scheduler Blindspots:** Schedulers must not be tested solely by checking if the app boots with `TESTING=1`. Tests must directly invoke the scheduler worker functions without mocks, asserting that database record counts increase or time-series timestamps advance.
4. **Data Provenance & Freshness Badges:** Every rendered asset card or directory must explicitly display its data provenance and last-updated timestamp (`last_updated` / `edition_date`).

## Rule 8: Zero-Illusion Reality Verification & Forbidden Patterns (AST Gate)

### 8.1 Mandatory Pre-Completion Verification Gate
- Never claim a task, bug fix, or feature is complete based solely on `py_compile`, syntax checks, or mocked unit tests.
- Before ending ANY turn that modifies `.py` files in `core/` or `web/`, you MUST execute:
  `python3 scripts/verify_reality_audit.py`
- If `verify_reality_audit.py` returns a non-zero exit code, you MUST fix all reported `[GATE-1]` through `[GATE-5]` failures before yielding back to the user.

### 8.2 Forbidden Code Patterns (Enforced by AST Gate & CI Pipeline)
- **No Auth Fallbacks:** Never create a session or log a user in inside a `catch`/`except` or non-200 fallback block.
- **No Module-Level Session Globals:** Never store user identity in module-level variables (`_BARE_USER_SESSION`, `_BARE_AUTH_TOKEN`). Always use request-scoped `contextvars.ContextVar` or signed `HttpOnly` cookies.
- **No Unverified TLS:** Never use `ssl._create_unverified_context()`; always use `ssl.create_default_context(cafile=certifi.where())`.
- **No Silent Exception Swallowing:** Every `except Exception as e:` block in `core/` or `web/` must log via `logger.error(...)` or `logger.warning(...)` and never return fabricated financial/ESG metrics (`82/80/88`, `0.0% Pledged`, or synthetic `UDYAM-MH-26-*` entities).
- **No Audit Gaming:** Never set or check `AUDIT_RECURSION_GUARD` to return hardcoded test counts or mock-pass statements.
