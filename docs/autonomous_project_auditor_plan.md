# Autonomous Project Auditor Architecture & Implementation Plan
## Continuous Multi-Pillar Auditing for Stock Research App via Google Antigravity SDK

**Document Identifier:** `docs/autonomous_project_auditor_plan.md`  
**Target System:** `Jaktheripper-bot/Stock_Research_App`  
**Engine:** Google Antigravity SDK (`google.antigravity`)  
**Status:** Architectural Blueprint & Implementation Specification — *For Evaluation Prior to Live Activation*  
**Date:** October 7, 2026  

---

## 1. Executive Feasibility Assessment

### Can We Build an Agent to Audit the Project Regularly?
**Yes, absolutely.** The Google Antigravity Python SDK (`google.antigravity`, verified active and importable in this environment) is specifically architected for autonomous, long-running agent workflows with:
1. **Multi-Agent Delegation (`SubagentConfig` / `SubagentCapabilities`):** A hierarchical architecture where a root coordinator agent (`ChiefProjectAuditor`) delegates domain-specific audits to specialized subagents.
2. **Periodic & Event-Driven Triggers (`triggers.every` / `triggers.on_file_change`):** Native asynchronous triggers that execute recurring inspections in the background without blocking server operations.
3. **Deterministic Tool Grounding:** Direct execution of filesystem inspection (`view_file`, `search_directory`), shell test suites (`run_command`), live HTTP endpoint probes, and AST/regex code scanners.
4. **Zero-Hallucination Fallback:** Dual-layer auditing where deterministic rule engines verify hard invariants (e.g., test passes, status codes, regex term scans) while Gemini cognitive models synthesize strategic and design evaluations.

---

## 2. Tri-Pillar Audit Taxonomy

To satisfy the user objective across **strategy**, **implementation**, and **UI/UX**, the autonomous auditor divides its verification workload into three dedicated pillars:

```
                            ┌────────────────────────────────────────┐
                            │          ChiefProjectAuditor           │
                            │   (google.antigravity Root Agent)     │
                            └──────────────────┬─────────────────────┘
                                               │
             ┌─────────────────────────────────┼─────────────────────────────────┐
             │                                 │                                 │
             ▼                                 ▼                                 ▼
┌──────────────────────────┐     ┌──────────────────────────┐     ┌──────────────────────────┐
│     StrategyAuditor      │     │       CodeAuditor        │     │       UIUXAuditor        │
├──────────────────────────┤     ├──────────────────────────┤     ├──────────────────────────┤
│ • SEBI Safe Harbor       │     │ • DB Schema Dual-Binding │     │ • Behavioral Research    │
│ • Zero-Condescension     │     │ • Zero-Hallucination AST │     │ • Design Tokens & Theme  │
│ • 7-Pillar Alignment     │     │ • Full Test Suite (129+) │     │ • Endpoint DOM Latency   │
│ • Roadmap & Licensing    │     │ • Security & Auth Gates  │     │ • Responsive Breakpoints │
└──────────────────────────┘     └──────────────────────────┘     └──────────────────────────┘
             │                                 │                                 │
             └─────────────────────────────────┼─────────────────────────────────┘
                                               │
                                               ▼
                            ┌────────────────────────────────────────┐
                            │    Audit Synthesis & Persistence       │
                            │ • DB Table: project_audit_logs         │
                            │ • Markdown: audits/audit_YYYYMMDD.md   │
                            │ • Backlog: audit_findings.md (updated) │
                            │ • Web UI: /admin/audit dashboard       │
                            └────────────────────────────────────────┘
```

---

### Pillar 1: Strategy & Regulatory Guardrails Audit (`StrategyAuditor`)
Audits philosophical, editorial, regulatory, and commercial alignment.

1. **SEBI Safe Harbor Non-Advisory Compliance:**
   - **Prohibited Prescriptive Words:** Scans all web templates, API responses, PDF exports, and AI prompt templates for forbidden terms: `BUY`, `SELL`, `HOLD`, `Target Price`, `Price Prediction`, `Guaranteed Return`, `Strong Buy`.
   - **Immutable Disclaimer Verification:** Verifies that all 73 web routes and PDF exports include the mandatory SEBI Research Analyst Regulations 2014 Section 2(u) non-advisory disclaimer.
   - **Zero User Personalization:** Confirms that no forms or routes collect user net worth, risk profile, or portfolio weights to deliver personalized investment advice.
2. **Editorial Tone & Zero-Condescension Filter:**
   - Detects and flags patronizing conversational fluff (e.g., *"Don't worry, investing is simple!"*, *"Here's a plain-English explainer for beginners"*, exclamation mark inflation).
   - Enforces an institutional, objective, diagnostic tone (e.g., *"Solvency Posture: Deteriorating"*, *"Moat: Narrow"*).
3. **7-Pillar Forensic Philosophy Adherence:**
   - Verifies that equities, corporate debt, and mutual funds are evaluated using structural health parameters (Moat, Accounting Forensics, Margin of Safety, Capital Allocation, Promoter Pledging) rather than commodity momentum or historical return chasing.
4. **Roadmap Coherence & Upstream Licensing Risk:**
   - Audits `audit_findings.md` and `docs/` against current code state to flag abandoned priorities or scope drift.
   - Monitors commercial risk exposure (e.g., flagging unauthenticated scraping of Yahoo Finance/BSE when commercial monetization via Razorpay is enabled, tracking progress toward Angel One SmartAPI).

---

### Pillar 2: Technical Architecture & Code Implementation Audit (`CodeAuditor`)
Audits software craftsmanship, stability, performance, and security.

1. **Database Schema Dual-Binding & Migration Sanity:**
   - Verifies schema compatibility between PostgreSQL (Supabase production) and SQLite (`reports.db` local).
   - Validates that all migrations (`v001` through `v021_fund_forensic_dossiers`) execute idempotently without data loss.
   - Inspects table indices (`idx_reports_ticker`, `idx_revisions_ticker`, `idx_fund_forensics_code`) for query optimization.
2. **Zero-Hallucination & Hardcoding AST Inspector:**
   - Runs static Python AST analysis and pattern matching across `core/analysis/` and `core/ingestion/` to detect hardcoded financial constants (e.g., checking that no module uses hardcoded scores like `score = 82.0`).
   - Ensures mathematical derivations (WACC, DCF, Modified Duration, ASRI) rely on validated inputs or raise clean exceptions rather than hallucinating fallbacks.
3. **Automated Test Suite & Regression Health:**
   - Executes the full automated test suite (`python3 -m unittest discover -s tests`).
   - Verifies that all 129+ unit and integration tests pass with 0 failures and 0 errors.
   - Validates test isolation (verifying `TESTING=1` routes database transactions strictly to `test_reports.db`).
4. **Security, Secrets & Authentication Hardening:**
   - Scans git staging and source files for leaked API keys (`GEMINI_API_KEY`, `RAZORPAY_KEY_SECRET`, `SUPABASE_DB_URL`).
   - Audits authentication routes (`/api/auth/send-otp`, `/api/auth/verify-otp`, `/auth/google`) for rate-limiting, token expiration, and CSRF origin verification on POST mutations.
5. **Reliability, Resilience & Fallback Cascades:**
   - Audits LLM fallbacks (Gemini Flash cascade -> Perplexity Sonar).
   - Verifies HTTP 2-tier caching headers (`Cache-Control: public, max-age=...`) and delta-gating (preventing costly AI regenerations if reports are <14 days old and stock moves <5%).

---

### Pillar 3: UI/UX, Design Aesthetics & Front-End Ergonomics Audit (`UIUXAuditor`)
Audits user interface craftsmanship, behavioral research compliance, and front-end performance.

1. **Behavioral Research Compliance (`BEHAVIORAL_RESEARCH_STUDY.md`):**
   - **Tabular Lining Numerals:** Verifies that financial data tables across all templates enforce `tabular-nums` / `tnum` font styling to prevent ocular drift.
   - **3-Tier Disparity Gates:** Ensures PEAD drift bands and Pre-Mortem inversion modules are visible and functional to counter Sunk Cost Fallacy and Disposition Effect.
   - **Color Scarcity:** Flags overuse of non-critical saturated reds and greens; ensures color is reserved for structural signals.
2. **Visual Design System & Token Uniformity:**
   - Audits `web/static/css/style.css` for consistent design tokens (`--bg-primary`, `--accent-cyan`, `--border-subtle`, glassmorphic backdrops).
   - Scans for deprecated OS-dependent Unicode emojis (🏰, ⚖️, 📊, 🏦) in headers and cards, verifying replacement with institutional SVG icons.
3. **Live Endpoint Health & DOM Structure:**
   - Executes automated headless HTTP requests against all 73+ registered FastAPI routes.
   - Verifies that every route returns HTTP 200 within strict latency budgets (<350ms locally).
   - Checks HTML validity: single `<h1>` per page, complete `<head>` meta tags (OpenGraph, Twitter, canonical URL), and absence of unrendered Jinja tags (e.g., `{{ undefined }}`).
4. **Responsive Breakpoints & Mobile Ergonomics:**
   - Inspects CSS media queries (`@media (max-width: 768px)`) for responsive layout integrity, horizontal scroll leaks, mobile navigation drawer ergonomics, and touch target minimums (44px x 44px).

---

## 3. Google Antigravity SDK Implementation Design

### 3.1 Agent Hierarchy Specification

```python
# Conceptual Architecture: core/audit/project_auditor.py

from google.antigravity import Agent, LocalAgentConfig, types
from google.antigravity.hooks import policy

# 1. Specialized Subagents
strategy_subagent = types.SubagentConfig(
    name="strategy_auditor",
    description="Audits SEBI safe-harbor compliance, tone neutrality, and investment philosophy alignment.",
    capabilities=types.SubagentCapabilities(
        enabled_tools=[
            types.BuiltinTools.VIEW_FILE,
            types.BuiltinTools.SEARCH_DIR,
        ],
        agent_behavior=types.AgentBehavior.AUTONOMOUS,
    ),
)

code_subagent = types.SubagentConfig(
    name="code_auditor",
    description="Audits database migrations, runs automated test suites, scans for hardcoded anti-patterns, and verifies security.",
    capabilities=types.SubagentCapabilities(
        enabled_tools=[
            types.BuiltinTools.VIEW_FILE,
            types.BuiltinTools.SEARCH_DIR,
            types.BuiltinTools.RUN_COMMAND,
        ],
        agent_behavior=types.AgentBehavior.AUTONOMOUS,
    ),
)

uiux_subagent = types.SubagentConfig(
    name="uiux_auditor",
    description="Audits web templates, design system tokens, endpoint latencies, and behavioral UX standards.",
    capabilities=types.SubagentCapabilities(
        enabled_tools=[
            types.BuiltinTools.VIEW_FILE,
            types.BuiltinTools.SEARCH_DIR,
            types.BuiltinTools.READ_URL_CONTENT,
        ],
        agent_behavior=types.AgentBehavior.AUTONOMOUS,
    ),
)

# 2. Root Chief Project Auditor
root_config = LocalAgentConfig(
    system_instructions="""You are the Chief Project Auditor for Stock Research App.
You orchestrate the strategy_auditor, code_auditor, and uiux_auditor subagents to conduct
systematic, objective, institutional-grade project audits. You synthesize their findings
into an overall System Health Score (0-100) and actionable remediation items.""",
    subagents=[strategy_subagent, code_subagent, uiux_subagent],
    capabilities=types.CapabilitiesConfig(
        enable_subagents=True,
        max_subagent_depth=2,
        allowed_subagents=["strategy_auditor", "code_auditor", "uiux_auditor"],
    ),
    policies=[
        policy.allow("view_file"),
        policy.allow("search_directory"),
        policy.allow("run_command", when=lambda args: "unittest" in args.get("CommandLine", "")),
        policy.allow("start_subagent"),
        policy.allow("read_url_content"),
    ],
)
```

---

### 3.2 Custom Tool Integration

The agent is equipped with deterministic Python tools to guarantee zero-hallucination ground truth:

1. `tool_execute_test_suite()`:
   Runs `python3 -m unittest discover -s tests` via subprocess, parses total tests executed, passed, failed, and execution time, and returns a structured JSON payload.
2. `tool_probe_web_endpoints()`:
   Sends automated HTTP requests to all registered endpoints (`/`, `/discovery`, `/funds`, `/opportunities`, `/sovereign`, `/reits`, `/etfs`, `/admin`), recording status codes, TTFB (time to first byte), HTML title tags, and missing template assets.
3. `tool_scan_prohibited_language()`:
   Scans all Python and HTML files for regulatory violations (`BUY`, `SELL`, `target price`) or patronizing condescension phrases, returning exact line numbers and file paths.
4. `tool_inspect_ast_code_hygiene()`:
   Scans AST of python files for silent exception swallowing (`except: pass`) and hardcoded financial metrics.
5. `tool_validate_design_tokens()`:
   Parses `web/static/css/style.css` and template inline styles, validating color token usage and checking for OS Unicode emojis that need SVG replacement.

---

### 3.3 Execution Cadence & Trigger Mechanics

The auditor supports three operational modes:

| Mode | Trigger Mechanism | Description | Typical Use Case |
| :--- | :--- | :--- | :--- |
| **1. Autonomous Scheduled** | `google.antigravity.triggers.every` / Lifespan Scheduler | Runs daily at 03:00 IST in the background. | Detects overnight code drift, failing tests, or database degradation. |
| **2. CI/CD Pre-Flight Gate** | Git pre-commit or pre-push hook / `run.sh` | Executes before git commits or deployments. | Prevents broken endpoints or regulatory violations from reaching production. |
| **3. On-Demand Administrative** | CLI (`scripts/run_project_audit.py`) or REST API (`POST /api/admin/run-project-audit`) | Triggered manually via terminal or Admin Dashboard. | Instant executive health evaluation after major feature development. |

---

## 4. Telemetry, Database Storage & Deliverables

### 4.1 Database Persistence (`project_audit_logs`)
Every audit run is permanently recorded in PostgreSQL/SQLite:

```sql
CREATE TABLE IF NOT EXISTS project_audit_logs (
    id SERIAL PRIMARY KEY,
    audit_id VARCHAR(64) UNIQUE NOT NULL,
    overall_health_score NUMERIC(5, 2) NOT NULL,
    strategy_score NUMERIC(5, 2) NOT NULL,
    implementation_score NUMERIC(5, 2) NOT NULL,
    uiux_score NUMERIC(5, 2) NOT NULL,
    status VARCHAR(32) NOT NULL, -- 'EXEMPLARY', 'COMPLIANT', 'ACTION_REQUIRED', 'CRITICAL'
    tests_total INTEGER NOT NULL,
    tests_passed INTEGER NOT NULL,
    tests_failed INTEGER NOT NULL,
    endpoints_checked INTEGER NOT NULL,
    endpoints_healthy INTEGER NOT NULL,
    critical_violations JSONB,
    recommendations JSONB,
    full_markdown_report TEXT NOT NULL,
    audit_engine VARCHAR(64) DEFAULT 'google-antigravity-sdk',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
```

### 4.2 Deliverable Artifacts
1. **Timestamped Markdown Dossier:** Saved to `audits/project_audit_YYYYMMDD_HHMMSS.md`.
2. **Backlog Synchronization:** Updates the Executive Scorecard and Section 7.2 of `audit_findings.md`.
3. **Web Admin Dashboard:** Accessible at `/admin/audit` with visual health meters, category breakdowns, and 1-click on-demand re-audit triggers.

---

## 5. Phased Rollout Plan

- **Phase 1: Deterministic Engine & Tools Setup**
  - Implement deterministic tool functions (`tests`, `endpoints`, `prohibited_terms`, `design_tokens`) in `core/audit/tools.py`.
  - Add database table `project_audit_logs` via migration `v022_project_audit_logs`.
- **Phase 2: Antigravity Multi-Agent Orchestrator**
  - Construct `core/audit/project_auditor.py` with `ChiefProjectAuditor` and 3 subagents (`strategy_auditor`, `code_auditor`, `uiux_auditor`).
  - Implement deterministic fallback for offline or headless environments.
- **Phase 3: CLI Runner & Background Scheduler**
  - Build `scripts/run_project_audit.py` with `--quick`, `--full`, `--pillar` flags.
  - Wire nightly execution into FastAPI lifespan scheduler in `web/main.py`.
- **Phase 4: Admin Web UI & Public Health API**
  - Add `GET /admin/audit` and `POST /api/admin/run-project-audit` in `web/main.py`.
  - Render institutional audit scorecard with category breakdowns and trend graphs.
- **Phase 5: Verification & Calibration**
  - Run full test suite; calibrate scoring weights to ensure zero false positives.

---

## 6. Evaluation Checklist Prior to Going Live

Before taking this autonomous auditing agent live in production:
- [ ] User review and approval of the architectural plan and scoring criteria.
- [ ] Verification of token budget and rate-limit guardrails (`BudgetConfig` with `max_total_tokens=150_000` per audit run).
- [ ] Test isolation verification ensuring audit runs do not modify user-facing production records.
- [ ] Administrative access gate verification ensuring audit triggers require verified admin authentication.
