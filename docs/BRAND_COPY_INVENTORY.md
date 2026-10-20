# Moatnomics Sitewide Copy Inventory & Brand House Alignment Sheet

> **Reference Standard:** `docs/BRAND_HOUSE_AND_VOICE_GUIDE.md`
> - **Creative Territory:** *Less noise, more nuance.*
> - **Tagline:** *Less noise, more nuance.* is the only public tagline. *Audit the Asset. Protect the Allocator.* was retired on 20 Oct 2026 and removed from the site, brand code and AI prompts.
> - **Category Descriptor:** *Multi-asset investment research*
> - **Core Brand Promise:** *Understand the evidence. Examine the trade-offs. Know what deserves a closer look.*
> - **Voice Guardrails:** Direct declarative sentences, plain English, calm analytical restraint. Avoid hype, dramatic phrasing (*"wealth destruction"*, *"what shocked you"*), robotic server jargon (*"computational processing tokens"*, *"surgical refreshes"*, *"synthesize"*), unsubstantiated absolutes (*"zero-hallucination"*), and regulatory landmines (*"fiduciary recommendation"*).

> **Note:** This file contains zero personal paths, API keys, or sensitive data and is safe to share with external writing/editorial tools.

---

## Priority 0: Immediate Brand House & Regulatory Red-Flag Copy Fixes

Before redrafting page-level headers, these specific phrases across the site directly conflict with Section 7 (*Product Claims* & *Tonality*) of the Brand House or SEBI non-advisory rules:

> **Re-located 20 Oct 2026 against `main` @ `9aee965`.** `base.html` grew by 73 lines after this sheet was written, so the original line numbers had drifted. Only this table has been re-located. Sections 1–6 get re-located wave by wave. Rule from the owner: replace anything that could contradict SEBI wording rules with a similar-meaning, neutral term.

| # | Current Phrase on Site | Exact File & Line | Why It Conflicts with the Brand House | Suggested Direction |
|---|---|---|---|---|
| 0.1 | `&copy; 2026 Stock Research App. All rights reserved.` | `web/templates/base.html:871`; also `web/legal_content.py:16,19,92,141`, `core/reporting/pdf.py:362` | Uses legacy app name instead of **Moatnomics** (Brand House §10.1: *"Moatnomics as the single brand identity"*). | `&copy; 2026 Moatnomics. All rights reserved.`  **Done 20 Oct:** `base.html` footer, legal pages, PDF footer now say Moatnomics (docstrings and the TOTP issuer remain on the backend backlog). |
| 0.2 | `7-Pillar zero-hallucination institutional research dossiers` & `Our repository maintains zero-hallucination standards.` | `web/templates/search_results.html:151`, `web/templates/dossier_pending.html:51` | Brand House §7 explicitly forbids claiming that Moatnomics *"eliminates hallucinations"* or *"guarantees accuracy"*. | Describe traceable sourcing: *"Stock reports built from exchange filings, with sources and calculations you can check."*  **Done 20 Oct (Track 3, site + reports).** Identifiers/keys behind this wording are renamed in the backend phase. |
| 0.3 | `Fiduciary Recommendation`, `6-Pillar Fiduciary Look-Through Engine`, `Fiduciary Takeaway`, `Fiduciary Fragility Warning` | `web/templates/fund_overlap.html:106`, `fund_directory.html:3,5,20,23`, `fund_dossier.html:94,114,118,727,779`, `web/static/js/copilot.js:124,260`, `web/static/js/main.js:644` | "Fiduciary" implies a registered advisory duty, and "Recommendation" violates non-advisory boundaries. | Replace with *"Portfolio Look-Through"*, *"Cost & Fee Takeaway"*, *"What the Overlap Shows"*, and *"Accounting Risk Flag"*.  **Done 20 Oct (Track 3, site + reports).** Identifiers/keys behind this wording are renamed in the backend phase. |
| 0.4 | `Intermediary Fee Drag & Wealth Destruction` | `web/templates/fund_dossier.html:605,611`; also user-visible verdict in `core/analysis/net_real_tax_calculator.py:205` | Overly dramatic/sensationalist tone (Brand House §7: *"Avoid hype... Do not use a dramatic tone"*). | *"Direct vs. Regular Plan Expense Drag"* or *"10-Year Expense & Commission Cost"*.  **Done 20 Oct (Track 3, site + reports).** Identifiers/keys behind this wording are renamed in the backend phase. |
| 0.5 | `Computational Research Credits: Server compute units for live 7-pillar AI syntheses` / `computational processing tokens` / `Surgical Price & Announcement Refreshes` | `web/templates/base.html:509,554,688`, `index.html:562,598`, `pricing.html:71,109,170`, `web/static/js/main.js:507`, `web/legal_content.py:141` | Robotic internal engineering jargon that makes the reader work harder instead of explaining what a credit does in plain English. | *"Research Credits: Used only when you generate a fresh report from the latest filings. Reading existing reports is free."* / *"Price & Filing Updates"*.  **Done 20 Oct (Track 3, site + reports).** Identifiers/keys behind this wording are renamed in the backend phase. |
| 0.6 | `💥 What Shocked You?` / `💀 Thesis Destruction Failure Modes` / `Pre-Mortem Inversion` | `web/templates/partials/copilot_modal.html:855,866,872,897-903`, `web/static/js/copilot.js:18-25,93,178,242-246,325-329`, `dossier.html:717-723,758` (also names a person: *Charlie Munger*), `reit_dossier.html:405-435`, `etf_dossier.html:320`, `msme_dossier.html:237,259` | Clickbait/performative phrasing and unexplained jargon (`Pre-Mortem Inversion`). | *"What Stands Out?"*, *"What Could Go Wrong? (Countercase)"*, *"Key Risks & Assumptions That Could Fail"*.  **Done 20 Oct (Track 3, site + reports).** Identifiers/keys behind this wording are renamed in the backend phase. |
| 0.7 | `Surveillance` (user-facing), `Danger scorecard`, `Nominal returns are an illusion` | `web/templates/base.html:463,766-777`, `fund_dossier.html:118`, `tax_calculator.html:21` | *Surveillance* is SEBI/exchange terminology (ASM/GSM) and can read as regulatory action; the others are hype. | *Monitoring*; calm descriptive labels.  **Done 20 Oct (Track 3, site + reports).** Identifiers/keys behind this wording are renamed in the backend phase. |
| 0.8 | Named-person attribution: `Charlie Munger Pre-Mortem Inversion Engine (Charlie Munger Anti-Thesis)` | `web/templates/dossier.html:717,723` | Implies an endorsement by a named individual. | *Countercase: What Could Go Wrong*.  **Done 20 Oct:** now *Countercase Stress Test: What Could Go Wrong*. |
| 0.9 | Raw emojis still live in the Research Desk (`💀`, `⚖️`, …) | `web/static/js/copilot.js` (prompt chips, headings) | Contradicts the zero-emoji rule (Visual Guide §7) and the calm tone. | Use the inline sprite icons.  **Done 20 Oct for `copilot.js`:** all 156 emojis replaced by sprite icons via `brandGlyph()`. Still open elsewhere: `main.js` (`🔒`), `fund_dossier.html`, `copilot_modal.html`. |

---

## 1. Global Shell, Navigation, Footer & Modals (`web/templates/base.html` & `partials/`)

| # | Component | Current Copy | What Needs to Be Drafted (Brand House Job) |
|---|---|---|---|
| 1.1 | **Meta Title & OpenGraph Defaults** (`base.html:6,16,17`) | Title: `Moatnomics \| Audit the Asset. Protect the Allocator.`<br>OG Desc: `Moatnomics Dual-Mandate fundamental intelligence: We audit the economic moat of the asset, while constructing a cognitive moat for the allocator.` | Align `og_desc` and Schema.org description (`base.html:39`) with the updated plain-language `meta_desc` (*"Moatnomics is independent research on Indian stocks, mutual funds and corporate bonds. See the evidence, the risks and what to check before you invest."*). |
| 1.2 | **Markets Dropdown Descriptions** (`base.html:155-208`) | • Equities: `All verified BSE & NSE institutional dossiers & screener`<br>• Mutual Funds: `Dual-sleeve look-through, active share & fee drag`<br>• ETFs: `NAV premium/discount, tracking error & liquidity depth`<br>• Debt: `SEBI ₹10K fixed income, senior secured yields & YTMs`<br>• Sovereign: `RBI T-Bills, 10Y G-Sec & SDL auction benchmarks`<br>• REITs: `Fractional real estate, NDCF purity & gold parity`<br>• Opportunities: `Cross-asset discovery, spread heatmap & risk-yield frontier`<br>• MSME: `Udyam registry, industrial clusters & turnover tiers` | Shorten and translate insider acronyms (`NDCF purity`, `Dual-sleeve`) into clear, plain-English 1-line descriptions of what the reader can examine on each page. |
| 1.3 | **Research Tools & Governance Dropdowns** (`base.html:225-301`) | • Morning Discovery: `Daily screening of under-the-radar BSE equities`<br>• Peer Comparison: `Side-by-side financial metrics & valuation disparity`<br>• Net Real Tax Calculator: `Post-tax returns deflated by MOSPI CPI inflation`<br>• Retail Safety Radar: `Danger scorecard for gold leasing & P2P lending`<br>• Terms: `Computational credit rules & platform usage` | Replace `"Danger scorecard"` and `"Computational credit rules"` with calm, descriptive labels (*"Risk checks on gold leasing, P2P lending & high-yield products"*, *"Account terms, credits & platform usage"*). |
| 1.4 | **Checkout Modal** (`base.html:330-378`) | `Computational Research Credits: Server compute units for live 7-pillar AI syntheses and valuation models.` | Plain-English explanation of what credits unlock, how INR settlement works, and what stays free. |
| 1.5 | **Sign-In Modal** (`base.html:386-456`) | `🎁 Welcome Bonus: 2 Free Research Credits granted instantly upon sign-in.` / `Safe-Harbor Privacy: No personal financial or bank credentials collected.` | Calm, welcoming onboarding copy explaining that signing in gives 2 free credits to generate new reports or unlock deep-dive sections. |
| 1.6 | **Generate Report Modal** (`base.html:464-501`) | `Generate Institutional Dossier` / `Computational Research Engine: Ingests live BSE exchange disclosures and synthesizes a full 7-pillar qualitative thesis...` / `Synthesize Institutional Dossier (1 Credit)` | Replace *"Synthesize Institutional Dossier"* with clear action copy (*"Generate Stock Report (1 Credit)"* + plain explanation of what sources are checked). |
| 1.7 | **30s Progress HUD Overlay** (`base.html:514-538`, `main.js:585-655`) | `Forensic Intelligence Engine` / `Synthesizing Institutional Dossier` / `Ingesting live BSE exchange filings, executing forensic diagnostic matrix analysis (01–07)...` | Rewrite the 4 progress steps in `base.html` and `main.js` into transparent, human-readable stages (*"Step 1: Reading exchange filings"*, *"Step 2: Checking cash flow, debt & valuation"*, etc.). |
| 1.8 | **Surveillance Feed Modal** (`base.html:549-587`) | `Surveillance Engine • Active Daemons` / `🛰️ Autonomous Surveillance Feed` / `Background daemons continuously monitor official exchange filings...` | Reframe around the **Monitor** stage of the Brand House (*"What Changed? — Filing & Portfolio Updates"*), removing *"Active Daemons"* jargon. |
| 1.9 | **Footer Brand Blurb & Disclaimer** (`base.html:595-611`) | `Audit the Asset. Protect the Allocator. Dual-Mandate fundamental research: We audit the economic moat of the asset, while constructing a cognitive moat for the investor.` | Align with the Brand House positioning statement and category descriptor (*"Multi-asset investment research"*). |

---

## 2. Homepage Copy (`web/templates/index.html`)

*(Note: Hero and the 4-card Trust Strip in `index.html:6-86` were just updated; the sections below from line 88 to 600 still use legacy copy.)*

| # | Section | Current Copy | What Needs to Be Drafted (Brand House Job) |
|---|---|---|---|
| 2.1 | **7-Pillar Framework Header & Cards** (`index.html:92-135`) | `The 7-Check Institutional Health Matrix` / `Every equity dossier is synthesized across 7 rigorous strategic dimensions...` + 7 pillar blurbs | Reframe as *"How We Examine a Stock: Seven Questions Behind Every Report"*. Rewrite the 7 card descriptions so both professionals and serious individual investors see the *question* each pillar answers (e.g., *"Is growth turning into cash?"*, *"What is already priced in?"*). |
| 2.2 | **Stock Discovery @9AM Section** (`index.html:145-164`) | `INSTITUTIONAL QUALITY SURVEILLANCE` / `Stock Discovery @9AM` / `High-ROCE, conservative leverage companies across varied sectors operating under institutional sell-side radar.` | Align with the **Discover** stage of the Brand House (*"Know what deserves a closer look"* — explain the screening criteria clearly without promising winners). |
| 2.3 | **Stock Reports Browser Section** (`index.html:222-230`) | `Public Research Repository • Institutional Dossiers` / `Browse Verified Stock Research Reports` / `Filter by sector, search tickers, and inspect 7-pillar scorecards with reverse DCF margin of safety and DuPont ROE decompositions.` | Plain-language introduction inviting readers to browse existing stock reports for free, explaining what metrics (`ROCE`, `D/E`, `P/E`) are shown on each card. |
| 2.4 | **Homepage Pricing Section** (`index.html:520-605`) | `Transparent Monetization` / `Research Credits & Subscriptions` / `On-demand compute credits power live AI syntheses...` + 4 plan card descriptions & feature bullets | Rewrite plan descriptions and bullets in clear, non-jargon language (replace *"1 Full 7-Pillar AI Synthesis"*, *"Surgical Price & Announcement Refreshes"*, *"Differential Analysis Audits"* with clear user outcomes). |

---

## 3. Asset Directory & Screener Pages (8 Pages)

Each directory page needs a cohesive **Tag → H1 → Lead Paragraph (Context, Evidence, Trade-offs) → Methodology Footnote** aligned with the Brand House:

| # | Page & Template | Current H1 & Lead Copy | Brand House Redraft Focus |
|---|---|---|---|
| 3.1 | **Equities Directory** (`equities_directory.html:10-45`) | `Institutional Equities Directory` — `Exhaustive institutional equity research repository covering verified Indian equities...` | Explain what is covered, how stocks are grouped by sector and market-cap tier, and how to use ROCE, debt, and valuation together rather than relying on a single ratio. |
| 3.2 | **Mutual Funds Directory** (`fund_directory.html:15-45`) | `Mutual Fund Look-Through & Fiduciary Screener` — `Never evaluate mutual funds as opaque past-performance black boxes. Our 6-Pillar Fiduciary Look-Through Engine...` | Replace *"Fiduciary"* and *"wealth destruction"*. Frame around the Brand House tension: *past returns vs. what a fund actually owns, how much it deviates from its benchmark (Active Share), and what fees cost over time.* |
| 3.3 | **National ETF Matrix** (`etf_matrix.html:11-50`) | `National ETF Performance & Liquidity Matrix` — `Surveillance of all AMFI-registered Exchange Traded Funds...` | Frame around the core ETF trade-off: *a low expense ratio helps, but trading at a premium to NAV, wide bid-ask spreads, or high tracking error can quietly cost more than the fee saved.* |
| 3.4 | **Corporate Bonds & SDIs** (`debt_directory.html:11-50`) | `Corporate Bonds & Securitized Debt Directory` (Title: `Democratized Corporate Debt & SDI Directory`) | Frame around the Brand House bond example (§3): *A higher yield may compensate you for taking more credit risk; it does not automatically make the bond more attractive. Examine security cover, cash flow cushion, and rating history.* |
| 3.5 | **Sovereign Curve & T-Bills** (`sovereign_curve.html:11-45`) | `Indian Sovereign Debt & Macro Terminal` — `The definitive risk-free benchmark for Indian sovereign debt...` | Explain why the sovereign yield curve matters to every investor: *it is the baseline return against which every equity, corporate bond, and REIT risk spread should be judged.* |
| 3.6 | **SM REITs, InvITs & SGBs** (`reit_directory.html:11-55`) | `Alternative Real Assets, SM REITs & Sovereign Gold Terminal` | Clarify how commercial REITs, infrastructure trusts (InvITs), and secondary-market SGBs work, focusing on cash-flow distribution rules, tax treatment (Section 115UA), and occupancy/parity trade-offs. |
| 3.7 | **Opportunity Terminal** (`opportunity_terminal.html:11-55`) | `Multi-Asset Opportunity Terminal & Arbitrage Scanner` | Reframe away from *"Arbitrage Scanner"* hype toward **Cross-Asset Comparison** (Brand House §5.5): *comparing post-tax, post-inflation yields and risk across asset classes against the 10-year G-Sec benchmark.* |
| 3.8 | **Unlisted MSME Directory** (`msme_directory.html:11-50`) | `Unlisted MSME & Emerging SME Directory` | Explain what Udyam registry and industrial cluster data show—and clearly state the boundary (public registry & working-capital indicators, not audited listed-company disclosures). |

---

## 4. Research Tools & Decision-Support Pages (5 Pages)

| # | Page & Template | Current H1 & Lead Copy | Brand House Redraft Focus |
|---|---|---|---|
| 4.1 | **Morning Discovery @9AM** (`discovery.html:10-90`) | `Stock Discovery @9AM` — `Today's 9:00 AM Edition is Reserved for Subscribed Members` | Align with Brand House §5.3 (*Market & Opportunity Notes*): explain *why* these companies surfaced today, what metrics qualified them, and what questions an investor should investigate next. |
| 4.2 | **Peer Comparison** (`compare.html:10-55`) | `Cross-Company Peer Comparator & Disparity Diagnostic` | Align with Brand House §5.5 (*Comparison & Decision Support*): *"Do not manufacture a winner when evidence does not support one. Make trade-offs between business quality and valuation visible."* |
| 4.3 | **Mutual Fund Overlap** (`fund_overlap.html:10-115`) | `Mutual Fund Portfolio Overlap & Duplication Diagnostic` + `Fiduciary Recommendation` | Frame around the Brand House franchise *"Beneath the Surface: Five funds. How many distinct bets?"* Remove *"Fiduciary Recommendation"*. |
| 4.4 | **Net Real Tax Calculator** (`tax_calculator.html:11-50`) | `Net Real Post-Tax Return Engine` — `Nominal returns are an illusion...` | Replace dramatic phrasing (*"Nominal returns are an illusion"*) with calm analytical clarity: *comparing pre-tax headline returns with what remains after statutory tax slabs and CPI inflation.* |
| 4.5 | **Retail Safety Radar** (`safety_radar.html:11-50`) | `Alternative Yield & Shadow-Banking Risk Radar` | Replace sensationalist labels with an evidence-led breakdown of unregulated gold leasing, P2P lending, and AT1 bonds: *what the product promises, where the legal/credit risk sits, and what regulated alternatives exist.* |

---

## 5. Individual Asset Dossier Templates & Copilot Desk (8 Templates + JS)

| # | Template / Script | Current Copy Elements | Brand House Redraft Focus |
|---|---|---|---|
| 5.1 | **Equity Dossier** (`dossier.html`) | Section headers, `Synthesize Refresh`, `Pre-Mortem Inversion`, `Institutional Unlocked`, `Mandatory SEBI Safe-Harbor` | Frame sections around Brand House §5.4 (*Executive conclusion, Decision snapshot, Evidence base, Valuation & scenarios, Countercase, Risk & integrity checks, Monitoring triggers*). |
| 5.2 | **Pending Equity Dossier** (`dossier_pending.html`) | `Why is this dossier pending? Our repository maintains zero-hallucination standards...` / `Synthesize Forensic Dossier (1 Credit)` | Remove *"zero-hallucination"* claim; explain calmly that Moatnomics generates reports on demand from primary exchange filings rather than pre-filling unreviewed summaries. |
| 5.3 | **Mutual Fund Dossier** (`fund_dossier.html`) | `Fiduciary Surveillance Alerts`, `05: Intermediary Fee Drag & Wealth Destruction`, `Fiduciary Takeaway`, `Honest Fiduciary Banner` | Replace all *"Fiduciary"* and *"Wealth Destruction"* labels with neutral, evidence-led headings (*"Portfolio Coverage Notice"*, *"Expense Ratio & Commission Impact"*, *"Key Takeaway"*). |
| 5.4 | **Corporate Debt Dossier** (`debt_dossier.html`) | `What Am I Looking At?`, `Credit Contagion Radar: Equity-to-Debt Spillover Analysis`, `Credit & Solvency Diagnostic Matrix (01–05)` | Keep the helpful *"What Am I Looking At?"* plain-English explainer; refine section subheads so credit risk, security cover, and parent-group exposure read clearly. |
| 5.5 | **ETF Dossier** (`etf_dossier.html`) | `Live Premium / Discount Surveillance`, `Tracking Error & Fee Drag Audit`, `Structural Failure Modes & Risk Monitorables` | Frame around whether the secondary-market price accurately tracks the underlying basket and what to check before placing an exchange order. |
| 5.6 | **REIT / InvIT Dossier** (`reit_dossier.html`) | `Section 115UA Tax Waterfall Simulator`, `NDCF Payout Purity & Penal Clause Surveillance`, `Structural Failure Modes` | Translate `NDCF Payout Purity` and `WALE` in the section subheads so non-specialists immediately grasp lease expiry risk and cash-flow pass-through rules. |
| 5.7 | **MSME Dossier** (`msme_dossier.html`) | `01. Working Capital & Cash Conversion`, `02. Sector Offtake Universe`, `03. Solvency, Margins & TReDS Liquidity`, `04. Cluster Moat & Pre-Mortem Inversion` | Replace *"Pre-Mortem Inversion"* with *"Countercase & Key Operational Risks"* and clearly distinguish registry facts from sector estimates. |
| 5.8 | **Forensic Desk / AI Copilot Drawer** (`partials/copilot_modal.html`, `web/static/js/copilot.js`) | `Forensic Intelligence Desk`, `Welcome to the Forensic Intelligence Desk. I can assist in stress-testing your investment thesis...`, prompt chips (`💥 What Shocked You?`, `🐻 Bear Thesis`, `💀 Pre-Mortem Inversion`, `⚖️ Fiduciary Takeaway`) | Align the Copilot persona with the Brand House Master AI Prompt (§7): *an analytical research partner that helps examine the evidence, test assumptions, and explore the countercase—without theatrical emojis or fiduciary claims.* |
| 5.9 | **Deep-Dive Unlock Card** (`partials/asset_unlock_card.html`) | `lock_title`, `lock_blurb`, `lock_points` passed from `web/main.py` | Ensure the unlock prompt clearly states what additional analysis is inside (e.g., constituent-level breakdown, scenario sensitivity, countercase) without hard-sell urgency. |

---

## 6. Pricing, Support & Legal Pages (`pricing.html`, `contact.html`, `policy.html`)

| # | Page & Template | Current Copy Elements | Brand House Redraft Focus |
|---|---|---|---|
| 6.1 | **Pricing Page** (`pricing.html`) | `TRANSPARENT MONETIZATION`, `Choose the computational power you need...`, FAQ (`What is a Research Credit? Research credits are computational processing tokens...`) | Rewrite the hero lead, plan cards, Enterprise desk blurb, and FAQs in warm, plain English—explaining why reading is free and why generating a new report uses a credit. |
| 6.2 | **Contact & Grievance Desk** (`contact.html`) | `We're Here to Help`, category cards (`Billing & Credits`, `Technical Issue`, `Research Feedback`, `Regulatory Grievance`), form labels | Already friendly; ensure form helper copy reinforces that readers can flag data discrepancies or challenge an analytical assumption in any report. |
| 6.3 | **Legal & Policy Pages** (`policy.html` + policy dicts in `web/main.py`) | `/disclaimer`, `/terms`, `/privacy`, `/refund-policy`, `/shipping-policy` | Verify consistent use of **Moatnomics** (zero references to `Stock Research App`), non-registered independent software utility status (`AGENTS.md` §2), and plain-English clarity alongside statutory clauses. |

---

## 7. Status & Open Items (20 Oct 2026, Track 3 Phases 1-3)

**Done:** priority-0 rows 0.1-0.9; meta/OG title, footer and homepage hero use the single tagline; `og:image` / `twitter:image` / `apple-touch-icon` wired and tested; unused `glyph-castle` removed; Research Desk renamed end to end (module `research_desk.py`, `process_research_desk_turn`, DOM ids, tests); Countercase, Governance Scoring Index and Monitoring Feed identifiers renamed to match the site; AI call sites carry the brand context (`delta.py` added); the 7 unreferenced `ui/copilot-*` and `ui/hud-*` icon files removed. `python3 scripts/audit_doc_line_refs.py` is the post-implementation reference audit.

**Open (not done, and why):**

| Item | State |
|---|---|
| Hero banners (`img/heroes/*.webp`) and portal plates (`img/brand/portal-*.webp`) are not referenced by any page | Needs a visual review in a browser (text contrast over the images). Not wired blind. |
| Raw emojis outside `copilot.js` (public templates, `web/static/js/main.js`, `opportunity_terminal.js`, `web/main.py` messages, admin console) | About 300 remain, none replaced yet. Needs an emoji-to-sprite map per context. |
| Stored values: `SURGICAL_REFRESH`, `FULL_SYNTHESIS` (credit/telemetry action types), contact category `synthesis`, existing `BSE Surveillance` alert rows | Deliberately not renamed: renaming needs a data migration. Display text already uses the new wording. |
| API paths `/api/copilot/chat`, `/api/admin/*` scan routes | Unchanged by policy (Manual 4A). `/api/premortem` was renamed to `/api/countercase` with the old path kept as an alias. |
| Generic engineering word *synthesis* in function and constant names (`synthesize_bull_bear_thesis`, `MAX_SYNTHESIS_PER_USER_HOUR`, ...) | Not user-visible; left as is. |
| Legal pages still call the product a "computational financial research synthesis software utility" | Left: it is the legal characterisation of the service. Needs the owner's call before any change. |
| Hindi voice rules and string catalogues; language parameter of `get_system_prompt()` | Deferred as agreed. |

