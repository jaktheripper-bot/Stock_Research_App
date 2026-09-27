# Strategic Roadmap & Differential Engine

## 1. Multi-Asset Product Roadmap
* **Tier 1 (Equities Thesis):** Automated qualitative equity engine grounding 7-pillar reports[cite: 5].
* **Tier 2 (Mutual Fund Look-Through):** Ingesting mutual fund disclosures to score funds based on the forward-looking business quality and moat metrics of their underlying equity holdings[cite: 5].
* **Tier 3 & Capstone:** Scaling to fixed income and unifying into a holistic, qualitative portfolio audit[cite: 5].

## 2. Differential Tracking Engine
* **Append-Only Archiving:** To support qualitative time-series tracking, database rows are immutable. New material events trigger new entries in a `report_revisions` table, preserving historical text and timestamps[cite: 3].
* **High-Value Correlations:** The engine compares historical snapshots to detect "Value Traps" (qualitative downgrades occurring alongside valuation expansions) and tracks Mutual Fund Style Drift over successive quarters[cite: 3].
