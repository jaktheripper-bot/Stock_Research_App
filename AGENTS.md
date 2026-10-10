# Workspace Directives & Agent Rules

## 1. Mandatory Backup Protocol
**Always create a backup BEFORE and AFTER committing changes.**

- **Pre-Commit:**
  - Execute `./run.sh backup` (which tars `web/` and `reports.db` to `backups/<TIMESTAMP>/`).
  - Verify that tests pass (`python3 -m unittest discover -s tests`).
- **Post-Commit:**
  - Immediately execute `./run.sh backup` to archive the new state.
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

