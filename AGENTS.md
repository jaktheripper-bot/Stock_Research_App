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
- **Support Channels:** Strictly digital via `support@stockresearch.app` and `grievance@stockresearch.app`.
- **Name Placeholder Hygiene:** Do NOT feature the user's personal name (`Lyndon Pinto`) in UI templates or form examples. Use generic Indian names like `Rahul Sharma`.
- **Approachable Language:** Maintain professional, user-friendly language without condescending or unapproachable jargon.
