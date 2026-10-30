---
name: implication-preflight
description: >-
  Mandatory pre-development filter for major or structural requests on Moatnomics.
  Activate BEFORE planning or writing code whenever a request adds a feature, page or engine;
  touches two or more modules/layers; changes schemas, scoring, valuation, classification or
  forensic math; alters ingestion, schedulers or LLM synthesis; affects SEBI-sensitive surfaces,
  billing, auth or user data; or converts a research document into features. Interviews the user
  in grill-me mode (one question at a time) to pin down intent, maps 2nd/3rd-order implications
  across 9 lenses, runs read-only permutation probes across the full corpus to expose
  contradictions and loopholes, and produces an Implication Brief for approval. No workspace
  edits until the brief is approved.
---

# Implication Preflight (Think-Before-Build Filter)

## Why This Exists
The same metric is often computed in several places (Python engine, client JS sandbox, XLSX/PDF
export, LLM prose, hardcoded constants vs live DB), and new features land next to existing panels.
The costly failures here are rarely crashes. They are **contradictions** (a bull claim next to a
forensic red flag; UI vs export valuation drift), **regulatory drift** (alerts turning into trade
triggers) and **broken promises** (paywall copy selling a metric that doesn't exist). This filter
surfaces them on paper and in scratch, before any code is written.

## Step 0 — Triage
Run the **FULL** preflight if ANY of these apply:
- New user-facing feature, page, modal, alert, or analytical engine
- Touches ≥ 2 modules or layers (engine + template, Python + JS, DB + export, backend + copy)
- Schema change, migration, new table, or Supabase `SYNC_TABLE_SPECS` change
- Scoring, valuation, classification, forensic, taxonomy, or threshold math
- Ingestion, scheduler, cadence, TTL, or LLM synthesis behaviour
- SEBI-sensitive surface: advice-adjacent copy, alerts, AI co-pilot, legal pages, paywall promises
- Billing, credits, auth, privacy, or user-data handling
- A research document, competitor teardown, or "ideas list" being turned into features

**LITE** (Steps 1 + 2 condensed into chat; no artifact): single-file bug with a clear repro, or copy
edits with no regulatory angle. **SKIP**: typos, formatting, docs-only.

Open with one line, e.g.
`Preflight: FULL — touches valuation_radar.py + dossier.html JS + xlsx_exporter.py`.

## Step 1 — Grill-Me Intent Interview (one question at a time, no fixed limit)
Goal: understand what the user is trying to **create**, not just what they typed.
1. **Explore first.** Answer everything the codebase or DB can answer yourself. Never ask the user for facts you can grep.
2. **Draft an Intent Ladder** (internal): Outcome (what changes for the end user) → Persona & surface
   (which investor, which page) → Success signal (how we'd know it worked) → Non-goals → Hard
   constraints (SEBI safe harbor, fail-closed data, cost, cadence).
3. **Ask via `ask_question`, ONE question per call**, with the `(Recommended)` option first. Each
   question must resolve a real design branch: scope cut, framing, data source, delivery channel,
   phasing, trade-off. If neither answer would change the plan, don't ask it.
4. **Show the evidence before the question.** One or two lines: what you found, why it matters.
5. **Push back when warranted.** If the request as framed creates risk, say so and offer the resilient
   alternative as one of the options.
6. **No question cap.** Keep going until no remaining answer would change the plan, then stop. If the
   user skips or cancels a question, adopt the Recommended option and record it as an explicit
   **Assumption** in the brief. Never assume silently.

## Step 2 — Implication Map (9 Lenses)
For each candidate feature, answer every lens (N/A only with a reason). Use grep and file reads, not memory.
1. **Intent fit:** Does it serve the Step 1 outcome, or is it scope creep?
2. **Consumer graph:** Every caller, template, JS function, API route, XLSX/PDF export, serialized
   blob (`report_text`, `dossier_text`, `pillar_breakdown_json`), sync spec, test and living doc
   that consumes the touched data.
3. **Single source of truth:** Is the same metric or constant computed elsewhere (Python vs JS vs
   export vs prose vs hardcoded vs live DB)? Any divergence is a contradiction waiting to happen.
4. **Cross-engine coherence:** Can the output sit beside existing panels (bull/bear, forensic sieve,
   valuation radar, Chanakya, peer comparison) without disagreeing? Does it **build on** them?
5. **Domain validity across regimes:** Does the math hold for every archetype in
   [permutation_archetypes.md](references/permutation_archetypes.md)? Look for sign flips, zero
   denominators, threshold false positives and reporting-calendar gaps.
6. **Data availability & freshness:** Do the inputs exist today at the needed granularity and history?
   If not, plan new ingestion or a fail-closed `PENDING`. Never use proxies or defaults.
7. **Regulatory & promise surface:** SEBI IA/RA safe harbor, AI accountability, privacy policy, legal
   copy, and existing UI/doc promises this change fulfils or breaks.
8. **User interpretation risk:** Could a retail user read the output as advice (target price, alpha as
   a buy signal, alert as a trade trigger)? How does the framing prevent that?
9. **Operations & reversibility:** Scheduler and env guards, LLM/API cost, migration safety, tests,
   living docs, phasing, rollback.

## Step 3 — Theoretical Permutation & Loophole Probes (scratch, read-only)
1. Write probes in `<appDataDir>/brain/<conversation-id>/scratch/`. Open the DB read-only
   (`sqlite3.connect("file:reports.db?mode=ro", uri=True)`) or use a scratch clone. **Never mutate
   the workspace DB.**
2. Build the matrix: **archetypes × proposed features × existing engines**. Select archetypes with SQL
   queries (e.g. `pe_ratio > 120`, `debt_to_equity IS NULL`, BFSI sectors). Don't hand-pick tickers.
3. Run on **100% of relevant corpus rows** and report numbers, e.g. "155/337 dossiers contradict".
4. Simulate interactions:
   - UI parameter sweeps vs server math vs export
   - Feature A's output rendered next to feature B's
   - Degraded inputs (`None`, `0`, `"N/A"`, `{}`, empty API keys)
   - Formula edge cases
5. Log each finding as **Loophole ID → interaction tested → evidence (numbers, file:line) → guardrail
   → planned test.**

## Step 4 — Rank & Phase
- **Easy Kills:** high value, low effort, fixes live contradictions, no new data needed.
- **High-Differentiation:** needs new data, schema or parsers.
- **Deferred:** high fragility or high compliance surface. State the reason.

List dependencies for every item, so no phase ships something a later phase contradicts.

## Step 5 — Implication Brief & Approval Gate
1. Write `<artifact dir>/implication_brief.md` from
   [implication_brief_template.md](references/implication_brief_template.md) with
   `RequestFeedback=true, UserFacing=true`. If `/plan` is active, fold it into `implementation_plan.md`.
2. **Zero workspace edits** (code, templates, docs, DB) until the user explicitly approves. Read-only
   exploration and scratch probes are allowed.
3. After approval, hand off to `consequence-sandbox-testing` (implementation gates) and
   `outside-in-testing` (UI contracts). Every Loophole ID becomes a test case.

## Exit Criteria (all required before development starts)
- [ ] Triage stated; intent ladder confirmed or assumptions logged
- [ ] All 9 lenses answered for every in-scope feature
- [ ] Permutation probes run on the full corpus, with numbers
- [ ] Every loophole has a guardrail and a planned test
- [ ] Ranked, phased plan with dependencies
- [ ] Explicit user approval
