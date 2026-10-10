# Sitewide Google Antigravity SDK Implementation Plan [ARCHIVED & SHELVED]
## Transforming Stock Research App into an Autonomous Multi-Agent Institutional Intelligence Platform

**Document Identifier:** `docs/sitewide_antigravity_sdk_implementation_plan.md`  
**Target System:** `Jaktheripper-bot/Stock_Research_App`  
**Engine:** Google Antigravity SDK (`google.antigravity`)  
**Status:** **ARCHIVED & SHELVED (EXECUTIVE ARCHITECTURAL DECISION — OCTOBER 8, 2026)**  
**Decision Summary:** Per explicit founder/owner directive, autonomous agents will **NOT** be deployed across public site research surfaces. The production codebase remains anchored to tried, tested, deterministic Python pipelines with targeted, single-pass Gemini structured synthesis.

---

> [!IMPORTANT]
> ### Architectural Decision Record (ADR): Rejection of Sitewide Autonomous Agents
> 1. **SEBI Regulatory & Audit Immunity:** Under SEBI (Research Analysts) Regulations, 2014, an unregistered analytical tool must remain strictly factual, non-prescriptive, and grounded in official exchange filings. Autonomous agent loops introduce non-deterministic, open-ended reasoning that risks drifting into advisory language, failing SEBI audits.
> 2. **Token Economics & Compounding Context Tax:** Autonomous ReAct loops consume 10x to 20x more tokens per dossier (25,000–60,000+ tokens vs. 2,500 deterministic tokens), destroying unit economics and triggering frequent upstream rate limits.
> 3. **Latency & Determinism Budget:** Deterministic Server-Side Rendered (SSR) pipelines deliver rich research dossiers in 2–4 seconds with 99.9% reliability, whereas agentic multi-tool loops introduce 35–90+ second wait times without delivering proportionately superior insights.
> 4. **Retained Scope:** Single-turn structured Gemini extraction for qualitative synthesis, deterministic algorithmic engines for quantitative ratios, and interactive Copilot RAG (`/api/copilot/chat`) provide 100% of user value at minimal risk.

---

## 1. Executive Summary & Strategic Rationale (Historical Archive)

### 1.1 The Architectural Transition [Deprioritized]
Currently, the **Stock Research App** operates as a high-performance FastAPI Server-Side Rendered (SSR) web application with fragmented AI touchpoints: single-turn Gemini API calls for equity synthesis, rule-based engines for debt and REITs, and our newly built Google Antigravity Project Auditor (`core/audit/project_auditor.py`).

This archived plan previously explored implementing the **Google Antigravity SDK (`google.antigravity`) sitewide**, transitioning the platform into an autonomous multi-agent network. It has been shelved in favor of maintaining deterministic pipeline integrity and regulatory safety.

---

## 2. High-Level Multi-Agent System Topology

```mermaid
graph TD
    subgraph "Meta-Governance & Continuous QA"
        Auditor["ChiefProjectAuditor<br/>(Every 24h & CI/CD Gate)"]
        Auditor --> StratAud["StrategyAuditor"]
        Auditor --> CodeAud["CodeAuditor"]
        Auditor --> UIAud["UIUXAuditor"]
    end

    subgraph "Domain Research Squads (Autonomous)"
        EquitySquad["Equity Forensic Squad<br/>(Accounting + Governance + Reverse DCF)"]
        FundSquad["Fund Look-Through Squad<br/>(Constituent Aggregation + Style Drift)"]
        DebtSquad["Credit & Fixed Income Squad<br/>(Covenants + ACR + Contagion)"]
        RealAssetSquad["Real Assets & SM REIT Squad<br/>(NDCF + WALE + Sec. 115UA)"]
        MacroSquad["Macro & Yield Curve Squad<br/>(RBI Corridor + FBIL + SDL Disparity)"]
    end

    subgraph "Proactive Event Triggers & Watchers"
        BSEWatcher["BSE Announcement Watcher<br/>(triggers.every 300s)"]
        DiscoveryTrigger["9 AM Discovery Reel Scheduler<br/>(triggers.every 24h at 08:45 IST)"]
        AMFISync["AMFI NAV Sync Watcher<br/>(triggers.every 24h at 23:15 IST)"]
    end

    subgraph "Investor Interaction & Terminal Surfaces"
        ForensicDesk["Forensic Intelligence Desk<br/>(AgentBehavior.INTERACTIVE)"]
        WebViews["FastAPI SSR Terminal Views<br/>(/, /dossier, /funds, /opportunities, /admin)"]
    end

    BSEWatcher -->|Material Event| EquitySquad
    BSEWatcher -->|Top Holding Event| FundSquad
    DiscoveryTrigger --> EquitySquad
    EquitySquad --> WebViews
    FundSquad --> WebViews
    DebtSquad --> WebViews
    RealAssetSquad --> WebViews
    MacroSquad --> WebViews
    ForensicDesk <--> WebViews
    Auditor -.->|Surveillance| WebViews
    Auditor -.->|Surveillance| Domain Research Squads
```

---

## 3. Five-Tier Sitewide Implementation Architecture

### Tier 1: Multi-Asset Autonomous Research Squads (Domain Intelligence)

Each asset class is equipped with an autonomous research squad operating under `AgentBehavior.AUTONOMOUS` with hierarchical subagent delegation:

#### 1.1 Equity Forensic Research Squad (`core/agents/equity/`)
- **Squad Lead:** `ChiefEquityForensicOfficer` (orchestrator)
- **Subagents (`SubagentConfig`):**
  1. `accounting_auditor`: Examines Beneish M-Score, working capital inflation, cash flow divergence (OCF vs PAT), and off-balance sheet liabilities.
  2. `governance_detective`: Scrutinizes promoter pledging trajectory, related-party transactions (RPTs), auditor churn, and board independence.
  3. `valuation_stress_analyst`: Conducts reverse DCF (deriving required terminal growth rates at CMP), ROIC-WACC spreads, and downside Margin of Safety (MoS) scenarios.
- **Custom Tools:**
  - `tool_fetch_bse_disclosures(ticker)`: Direct BSE exchange filing retrieval.
  - `tool_compute_beneish_mscore(ticker)`: Deterministic mathematical derivation.
  - `tool_reverse_dcf(ticker, wacc, terminal_growth)`: Intrinsic value stress testing.
- **Safe-Harbor Output:** 7-Pillar Health Scorecard (Moat, Management, Financials, Solvency, Valuation, Capital Allocation, Risks) with strictly descriptive diagnostic classifications (Zero Buy/Sell/Hold).

#### 1.2 Mutual Fund 7-Pillar Look-Through Squad (`core/agents/funds/`)
- **Squad Lead:** `FundLookThroughDirector`
- **Subagents:**
  1. `portfolio_lookthrough_agent`: Aggregates underlying company health scores from `reports.db` to calculate Weighted Moat Index, Accounting & Solvency Risk Index (ASRI), and Portfolio Margin of Safety.
  2. `style_drift_detector`: Compares historical scheme holdings across 12 months to detect market-cap creep, turnover churn, and sector concentration risk.
- **Trigger Integration:** Listens for material BSE filings across top 10 portfolio holdings; re-audits the fund automatically if constituent risk spikes.

#### 1.3 Corporate Debt & Credit Risk Squad (`core/agents/debt/`)
- **Squad Lead:** `CreditForensicAnalyst`
- **Capabilities:**
  - Audits Listed Corporate NCDs, Banking Tier-II capital, and Securitized Debt Instruments (SDIs).
  - Verifies Asset Coverage Ratio (ACR $\ge 1.25\times$), cash flow debt serviceability (DSCR), and debt seniority rank.
  - Flags shadow-banking counterparty contagion (P2P platforms, unrated NBFC paper).

#### 1.4 Real Assets, SM REITs & InvITs Squad (`core/agents/reits/`)
- **Squad Lead:** `RealAssetsAnalyst`
- **Capabilities:**
  - Enforces SEBI (REIT) Regulations 2024 compliance gate: occupancy $\ge 95\%$, NDCF payout $\ge 95\%$, LTV $\le 49\%$.
  - Analyzes tenant concentration risk, lease maturity schedules (WALE), and Net Operating Income (NOI) yields.
  - Computes Section 115UA multi-component tax breakdown (Dividend, Interest, SPV Amortization, Rental Income).
  - Scans Sovereign Gold Bonds (SGBs) across 10 secondary tranches for parity discounts and Section 47(viic) tax-free capital gains.

#### 1.5 Macro & Yield Curve Squad (`core/agents/macro/`)
- **Squad Lead:** `MacroCurveStrategist`
- **Capabilities:**
  - Tracks RBI Monetary Policy Corridor (Repo 6.50%, SDF 6.25%, MSF 6.75%).
  - Evaluates FBIL Par Yield curve shifts (Current vs 1M vs 1Y ago) and inversion warning signals.
  - Evaluates State Development Loan (SDL) fiscal disparity matrix across 10 borrowing states.

---

### Tier 2: Proactive Event Triggers & Autonomous Background Watchers

Using the Google Antigravity SDK native triggers (`google.antigravity.triggers.every` and `triggers.on_file_change`), the system operates proactively without requiring human invocation:

| Watcher / Trigger | Cadence | Engine Mechanism | Operational Objective |
| :--- | :--- | :--- | :--- |
| **BSE Exchange Filing Watcher** | Every 5 minutes (`every(300)`) | `core/agents/watchers/bse_watcher.py` | Polls official BSE corporate announcements. If a material filing occurs (fraud, auditor resignation, default, acquisition), dispatches an automated re-audit task to the Equity Squad. |
| **Morning 9 AM Discovery Reel** | Daily at 08:45 IST | `core/agents/watchers/discovery_watcher.py` | Screens 500+ scrips across 7-pillar quality filters, checks liquidity and 2-tier disparity gates, and publishes the curated daily 9 AM cohort to `/discovery`. |
| **AMFI NAV Statutory Synchronizer** | Nightly at 23:15 IST | `core/agents/watchers/amfi_watcher.py` | Downloads statutory `NAVAll.txt` from AMFI portal, updates scheme NAVs, and detects NAV tracking error anomalies. |
| **Overnight Project Auditor** | Nightly at 03:00 IST | `core/audit/project_auditor.py` | Runs full multi-pillar system health audit (Strategy, Code, UI/UX) and writes immutable dossiers to `audits/` and `project_audit_logs`. |

---

### Tier 3: Interactive Forensic Intelligence Desk (`AgentBehavior.INTERACTIVE`)

To empower allocators and researchers without violating SEBI Safe Harbor, the platform provides the **Forensic Intelligence Desk** (short form: **Forensic Desk**) on `/dossier/{ticker}` (keyboard shortcut: `⌘K` / `Ctrl+K`):

1. **Collaborative Research Mode:**
   - Configured with `capabilities=CapabilitiesConfig(agent_behavior=AgentBehavior.INTERACTIVE)`.
   - Equipped with `BuiltinTools.ASK_QUESTION` to seek clarifications when inquiries are ambiguous.
2. **Behavioral Bias Inversion Engine:**
   - When a user asks about an underperforming stock, the Forensic Desk automatically invokes the **Pre-Mortem Inversion Tool**:
     *"Before analyzing upside scenarios, let us examine the 3 primary structural failure modes identified in recent filings..."*
   - Actively counters Sunk Cost Fallacy and Disposition Effect.
3. **Strict Non-Advisory Guardrails:**
   - Intercepts and rejects prompts asking: *"Should I buy?"*, *"What is the target price?"*, *"Is this a good investment?"*.
   - Responds with factual diagnostic health matrices and scenario-based reverse DCF models under SEBI RA Section 2(u).

---

### Tier 4: Sitewide Autonomous System Governance & Continuous QA

The `ChiefProjectAuditor` (developed and tested in `core/audit/project_auditor.py`) is elevated to a sitewide **Meta-Governor**:

1. **Continuous 24-Hour Cadence:**
   - Audits Strategy (100% compliance with non-advisory language), Code (137+ unit tests, DB dual-binding, AST hygiene), and UI/UX (25+ live routes, tabular numbers, design tokens).
2. **Pre-Flight Release Gatekeeper:**
   - Integrated into `run.sh` and CI/CD pre-flight checks. Any git commit or deployment attempt with an audit score `< 85.0` or any failing unit test is blocked automatically.
3. **Telemetry & Admin Workspace:**
   - Surfaced at `/admin/audit` with real-time scorecards, active remediation checklists, and historical run ledgers.

---

### Tier 5: Safety Policies, Sandboxing & Budget Governance

To prevent accidental modifications, runaway API costs, or security risks:

1. **Declarative Tool Policies (`google.antigravity.hooks.policy`):**
   ```python
   policies = [
       policy.deny_all(),
       policy.allow("view_file"),
       policy.allow("search_directory"),
       policy.allow("read_url_content"),
       policy.workspace_only(["/Users/lyndonpinto/Documents/Stock_Research_App"]),
       policy.allow("run_command", when=lambda args: "unittest" in args.get("CommandLine", "")),
   ]
   ```
2. **OS-Level Command Sandboxing:**
   - Shell commands (`run_command`) run with `enable_sandbox=True` on `RunCommandConfig`, preventing any modification to system files outside the workspace.
3. **Session Budget Controls (`BudgetConfig`):**
   ```python
   budget_config = types.BudgetConfig(
       max_model_calls=12,
       max_tool_calls=25,
       max_total_tokens=150_000,
   )
   ```
   Ensures predictable inference costs across all domain squads.
4. **Multi-Provider Failover:**
   - Primary: Gemini Flash cascade (`gemini-3.5-flash-lite` -> `gemini-3.8-flash`).
   - Secondary: Perplexity `sonar-pro` with grounded web search.
   - Tertiary: Deterministic offline fallback routines.

---

## 4. Database Schema Expansion & State Persistence

To support stateful multi-agent interactions, the database requires dual-binding migrations (`connection.py`):

### Migration `v023_agent_transcripts_and_sessions`
```sql
-- PostgreSQL / SQLite dual-mode
CREATE TABLE IF NOT EXISTS agent_conversations (
    id SERIAL PRIMARY KEY,
    conversation_id VARCHAR(100) UNIQUE NOT NULL,
    user_id VARCHAR(100),
    agent_type VARCHAR(64) NOT NULL, -- 'equity_copilot', 'debt_analyst', 'pre_mortem'
    context_ticker VARCHAR(32),
    turn_count INTEGER DEFAULT 0,
    total_tokens INTEGER DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS agent_conversation_turns (
    id SERIAL PRIMARY KEY,
    conversation_id VARCHAR(100) NOT NULL REFERENCES agent_conversations(conversation_id),
    turn_index INTEGER NOT NULL,
    sender_role VARCHAR(32) NOT NULL, -- 'user', 'agent', 'subagent', 'system'
    content TEXT NOT NULL,
    tool_calls_json TEXT,
    created_at TIMESTAMPTZ DEFAULT now()
);
```

### Migration `v024_autonomous_event_ledger`
```sql
CREATE TABLE IF NOT EXISTS autonomous_event_ledger (
    id SERIAL PRIMARY KEY,
    event_id VARCHAR(100) UNIQUE NOT NULL,
    event_type VARCHAR(64) NOT NULL, -- 'bse_filing', 'price_shock', 'scheduled_audit'
    ticker VARCHAR(32),
    trigger_source VARCHAR(64) NOT NULL,
    action_taken VARCHAR(64) NOT NULL, -- 're_audited', 'alert_dispatched', 'skipped_cache'
    summary TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT now()
);
```

---

## 5. Phased Rollout Roadmap & Evaluation Gates

The sitewide rollout is structured across five sequential, non-breaking phases. **Each phase requires explicit review and approval before execution begins.**

```
Phase 1: Agent Infrastructure & Safety Governance (Policies, Budgets, Migrations v023-v024)
   │
   ▼
Phase 2: Domain Research Squads (Equities, Debt, Funds, REITs, Macro Agents)
   │
   ▼
Phase 3: Proactive Background Watchers (BSE Filings, 9 AM Discovery Reel, AMFI Sync)
   │
   ▼
Phase 4: Interactive Forensic Intelligence Desk & Pre-Mortem Dialog (/dossier/{ticker})
   │
   ▼
Phase 5: Sitewide Integration, CI/CD Gate Enforcement & Live Production Deployment
```

---

### Phase 1: Agent Infrastructure, Safety Policies & Database Migrations
- **Objective:** Establish the foundational Google Antigravity SDK infrastructure, security policies, token budgets, and session persistence schemas.
- **Deliverables:**
  - `core/agents/config.py`: Shared base configurations, safety policies (`policy.allow`/`policy.deny`), and budget boundaries (`BudgetConfig`).
  - `core/agents/tools_base.py`: Standardized tool decorators and JSON serialization.
  - Migrations `v023` and `v024` in `core/db/connection.py` and repository `core/db/agent_sessions.py`.
- **Evaluation Gate:** Unit tests verify budget limits, safety policies block unauthorized commands, and dual-binding DB schemas initialize idempotently.

---

### Phase 2: Autonomous Domain Research Squads
- **Objective:** Deploy specialized multi-agent squads across Equities, Debt, Mutual Funds, SM REITs, and Macro.
- **Deliverables:**
  - `core/agents/equity/`: `chief_equity_officer`, `accounting_auditor`, `governance_detective`, `valuation_stress_analyst`.
  - `core/agents/funds/`: `fund_lookthrough_director`, `style_drift_detector`.
  - `core/agents/debt/`: `credit_forensic_analyst` (ACR, covenant tracking).
  - `core/agents/reits/`: `real_assets_analyst` (NDCF payout, WALE, Sec. 115UA).
  - `core/agents/macro/`: `macro_curve_strategist` (RBI corridor, FBIL curve, SDLs).
- **Evaluation Gate:** Full verification that all squads produce SEBI Safe-Harbor compliant diagnostic reports without any hardcoded heuristic values or prescriptive ratings.

---

### Phase 3: Proactive Background Watchers & Event Triggers
- **Objective:** Activate event-driven triggers to make research updates continuous and proactive.
- **Deliverables:**
  - `core/agents/watchers/bse_watcher.py`: 5-minute BSE announcement polling and delta-gating.
  - `core/agents/watchers/discovery_watcher.py`: 08:45 IST autonomous screening for the 9 AM Discovery Reel.
  - `core/agents/watchers/amfi_watcher.py`: 23:15 IST statutory NAV synchronization.
  - Wiring watchers to FastAPI lifespan scheduler in `web/main.py`.
- **Evaluation Gate:** Verify zero CPU spin, proper asyncio non-blocking execution, and seamless event-driven re-audits.

---

### Phase 4: Interactive Forensic Intelligence Desk & Pre-Mortem Dialog
- **Objective:** Equip web dossiers (`/dossier/{ticker}`) with the interactive Forensic Intelligence Desk that actively mitigates investor behavioral biases.
- **Deliverables:**
  - `core/agents/copilot/`: Interactive copilot agent (`AgentBehavior.INTERACTIVE`).
  - `web/static/js/copilot.js` & `web/templates/partials/copilot_modal.html`: Institutional chat sidebar with streaming responses and Pre-Mortem inversion triggers.
  - REST endpoints: `POST /api/copilot/chat` and `GET /api/copilot/history`.
- **Evaluation Gate:** Strict validation that Forensic Desk refuses to answer Buy/Sell questions, enforces SEBI Section 2(u) disclaimers, and properly invokes Pre-Mortem prompts.

---

### Phase 5: Sitewide Release Gate, CI/CD Hardening & Live Production
- **Objective:** Unify all tiers under continuous automated auditing, enforce release gates, and deploy live on Render.
- **Deliverables:**
  - Integration of `ChiefProjectAuditor` into `run.sh` and CI pre-flight checks.
  - Updating `/admin/audit` to display real-time status across all 5 tiers.
  - Comprehensive documentation updates in `audit_findings.md` and user manual.
- **Evaluation Gate:** 100% green test suite (150+ automated tests), zero regressions, composite health score $\ge 90/100$, and complete user sign-off.

---

## 6. Evaluation Checklist Prior to Taking Sitewide Implementation Live

Before giving authorization to execute Phase 1:
- [ ] **Architecture Approval:** Review the 5-tier topology and multi-agent squad structure.
- [ ] **Regulatory Alignment:** Confirm all outputs adhere strictly to SEBI Safe Harbor non-advisory classifications.
- [ ] **Budget & Cost Boundaries:** Confirm `BudgetConfig` token and tool limits per agent tier.
- [ ] **Execution Policy:** Acknowledge that **no code modifications will take place until explicit approval is granted**.
