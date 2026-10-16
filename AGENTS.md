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
- **Clarify When Unsure:** Whenever requirements, edge cases, or desired end states are ambiguous or under-specified, proactively ask clarifying questions before executing speculative changes.
- **Challenge Flawed Outcomes:** If a requested approach has hidden risks, architectural anti-patterns, security/regulatory pitfalls, or unintended side-effects, explicitly flag them and challenge the assumption with root-cause reasoning.
- **Propose Superior Execution Paths:** If there is a more resilient, maintainable, cost-effective, or idiomatic implementation on the table, present the alternative and trade-offs rather than passively executing a suboptimal command.

## 5. Mandatory Empirical Verification Protocol Before Declaring Task Completion
**NEVER state or declare that a task, feature, or remediation is completed without first empirically double-checking and verifying that every single change discussed in the session is actually implemented on disk and active in code.**

- **Ground-Truth File Inspection:** Directly inspect the modified lines in destination files using file viewing or search tools before summarizing results. Never assume an edit succeeded based on intent alone.
- **Exhaustive Scope Checklist:** Compare the live diff and working tree against every action item, discussion point, and user request raised in the session to ensure zero unaddressed or forgotten items.
- **Runtime & Test Validation:** Execute the test suite and verification tools (`python3 -m unittest discover -s tests`, `scripts/run_project_audit.py --quick`) and inspect actual runtime outputs before reporting completion.
- **Git State & Remote Alignment:** Confirm working tree is clean (`git status`), commits and annotated tags are pushed, and tracking branches (`main`, `dev`, `origin`) are strictly aligned.
- **Zero Premature Conclusions:** If any change is partial, blocked, or pending further user input, explicitly disclose its exact state rather than asserting that the task is finished.

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



