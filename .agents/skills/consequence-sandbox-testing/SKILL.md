---
name: consequence-sandbox-testing
description: >-
  Pre-implementation consequence prediction and scratch-sandbox verification framework.
  Activate BEFORE modifying any data ingestion, LLM synthesis, financial scoring,
  taxonomy/regex classification, database migration, or background scheduler code
  to predict 2nd-order side effects and validate against cloned corpus data in scratch/.
---

# Consequence Prediction & Sandbox Verification Framework

## Core Principle

> **Prerequisite:** For major/structural requests, the `implication-preflight` brief must be approved first. Its Loophole IDs seed Gates 3–5 here as concrete test cases.

Never validate analytical or ingestion code solely on happy-path unit inputs or structural container checks (`HTTP 200`, `len(text) >= 500`, presence of `## Pillar 1`). Every non-trivial backend or data change must pass **5 Consequence Gates** inside `<appDataDir>/brain/<conversation-id>/scratch/` before touching production state or committing.

---

## Gate 1: The 5-Point Blast-Radius Trace (Before Writing Code)

Before editing target function `F`, explicitly list:
1. **Upstream Degradation Matrix:** What happens when `F` receives `None`, `0.0`, `"N/A"`, `""`, `{}` or HTTP `429`/`503`?
2. **Gate & Exception Interaction:** Does changing `F`'s return value trip a downstream gate (e.g. `pass_pre_screening_gates`) or `except` block that triggers an unintended fallback?
3. **Dual State Sync (Columns vs. Blobs):** If updating structured columns (`baseline_price`, `cached_fundamentals`, `aum_crores`), do serialized text/JSON columns (`report_text`, `dossier_text`, `citations_json`, `pillar_breakdown_json`) hold stale contradicting numbers?
4. **Process Lifecycle Trigger:** Could `F` be triggered unintentionally during FastAPI `lifespan()` boot, `TestClient` startup, or `sync_to_supabase.py`?
5. **Fail-Closed Contract:** If `F` cannot obtain verified inputs or grounded synthesis, does it cleanly abort/queue (`PENDING`) with **zero** fabricated database writes?

---

## Gate 2: Isolated Sandbox Database Clone

Never test ingestion, remediation, or migration logic directly against workspace `reports.db`. Clone it into `scratch/` first:

```python
import shutil
from pathlib import Path

scratch_db = Path("<appDataDir>/brain/<conversation-id>/scratch/sandbox_reports.db")
scratch_db.parent.mkdir(parents=True, exist_ok=True)
shutil.copy2("reports.db", scratch_db)
```

Point scratch test scripts at `DB_PATH=str(scratch_db)` (with `SUPABASE_DB_URL=""`) to verify exact row mutations safely.

---

## Gate 3: Full-Corpus Distribution & Counterexample Probe

Whenever writing or editing a sector detector, ETF/fund categorizer, ticker normalizer, or metric parser, run it across **100% of rows** in `sandbox_reports.db` and print:
1. **Category frequency distribution** (flag any single bucket capturing an implausible share, e.g., `> 35%` of all equities landing in `IT_TECH`).
2. **5 random samples per output bucket** — read the actual `(name, input, predicted_bucket)` tuples to catch substring collisions (`"IT"` inside `"LIMITED"` or `"ADITYA"`, `"EV"` inside `"BEVERAGES"`, `"GAS"` inside `"GASKET"`).
3. **Word-boundary invariant:** All short acronym matchers (`<= 4` chars) must use compiled `\bTOKEN\b` regexes, never `token in text`.

---

## Gate 4: Fault-Injection / Degraded-Mode Simulation

Execute the modified pipeline in `scratch/` under simulated dependency failure:
- `GEMINI_API_KEY=""` and `PERPLEXITY_API_KEY=""`
- Empty/unavailable live quote payload (`current_price=None, market_cap=None`)

**Pass Criteria:**
- `0` new rows containing static template prose or default numeric placeholders (`100.0`, `500.0`, `22.4%`, `0.15x`).
- Existing valid archived dossiers are **never** overwritten by degraded runs.
- Unresolved candidates remain cleanly in `PENDING` state for next scheduled retry.

---

## Gate 5: Payload Substance & Cross-Layer Parity Audit

Run [corpus_substance_probe.py](./scripts/corpus_substance_probe.py) against `sandbox_reports.db` (or `reports.db` in read-only audit mode) to assert three quantitative payload invariants:

1. **N-Gram Entropy (Anti-Boilerplate):**
   Computes 8-word shingles across generated `report_text` / `dossier_text`. Fails if distinct tickers/schemes share `> 25%` shingle Jaccard similarity or match banned boilerplate phrases.
2. **Header-to-Prose Numerical Parity:**
   Extracts `₹` prices and market caps (`Cr`) cited in `report_text` and flags rows contradicting `cached_fundamentals` / `baseline_price` beyond drift tolerance.
3. **Constituent Portfolio Distinctness:**
   Groups `mutual_fund_holdings` by `scheme_code` and flags any distinct schemes sharing identical `(identifier, weight_pct)` vectors.
