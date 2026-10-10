#!/usr/bin/env python3
"""Hybrid Sandboxed AI Auditor & Test Failure Synthesizer.

Architectural Purpose:
Conducts bounded, intelligent adversarial audits across the 5 site map zones
defined in docs/MASTER_ENGINEERING_MANUAL.md §1 without touching live production.
Uses gemini-3.8-flash under a strict BudgetGuard ($0.50 cap) to probe for:
1. Regulatory Baiter: SEBI safe harbor, non-advisory compliance, and entity hygiene.
2. Edge-Case Quant: Mathematical singularities, degenerate inputs, NaN/Inf checks.
3. State Saboteur: Parameter fuzzing, unauthenticated privilege escalation, malformed payloads.

When an anomaly or endpoint crash is detected, the Failure Synthesizer automatically
produces:
- Threat classification (Critical / High / Medium / Opportunity).
- Step-by-step code remediation instructions.
- Auto-generated, standalone Python unit test in tests/test_regression_<TIMESTAMP>.py.
- Markdown incident dossier in audits/ai_audit_<TIMESTAMP>.md.
"""

import os
import sys
import json
import time
import re
import argparse
import logging
from datetime import datetime, timezone
from pathlib import Path
from dataclasses import dataclass, asdict
from typing import Dict, Any, List, Optional

# Enforce sandboxed testing environment
os.environ["TESTING"] = "1"
os.environ["ENVIRONMENT"] = "testing"

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from fastapi.testclient import TestClient
from web.main import app
from core.config import get_secret

logger = logging.getLogger("ai_auditor")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


# =====================================================================
# 1. BudgetGuard: Strict Token & Cost Boundary
# =====================================================================

class BudgetExceededError(Exception):
    """Raised when token or dollar budget is exhausted."""
    pass


class BudgetGuard:
    """Strictly enforces token usage and cost bounds ($0.50 maximum cap)."""

    def __init__(self, max_tokens: int = 40000, max_cost_usd: float = 0.50):
        self.max_tokens = max_tokens
        self.max_cost_usd = max_cost_usd
        self.tokens_used = 0
        self.prompt_tokens = 0
        self.candidate_tokens = 0
        self.cost_used = 0.0

    def record_usage(self, prompt_tokens: int, candidate_tokens: int):
        self.prompt_tokens += prompt_tokens
        self.candidate_tokens += candidate_tokens
        self.tokens_used += (prompt_tokens + candidate_tokens)
        # Pricing for Gemini 3.8 Flash: ~$0.15/1M input tokens, ~$0.60/1M output tokens
        incremental_cost = (prompt_tokens * 0.15 / 1e6) + (candidate_tokens * 0.60 / 1e6)
        self.cost_used += incremental_cost

        logger.info(
            "BudgetGuard: Recorded +%d tokens (Total: %d / %d, Cost: $%.5f / $%.2f)",
            prompt_tokens + candidate_tokens,
            self.tokens_used,
            self.max_tokens,
            self.cost_used,
            self.max_cost_usd,
        )

        if self.tokens_used >= self.max_tokens:
            raise BudgetExceededError(
                f"Token ceiling reached: {self.tokens_used} >= {self.max_tokens}"
            )
        if self.cost_used >= self.max_cost_usd:
            raise BudgetExceededError(
                f"Dollar ceiling reached: ${self.cost_used:.4f} >= ${self.max_cost_usd:.2f}"
            )

    def can_spend(self, estimated_tokens: int = 1500) -> bool:
        return (self.tokens_used + estimated_tokens) < self.max_tokens and self.cost_used < self.max_cost_usd

    def summary(self) -> Dict[str, Any]:
        return {
            "tokens_used": self.tokens_used,
            "prompt_tokens": self.prompt_tokens,
            "candidate_tokens": self.candidate_tokens,
            "cost_used_usd": round(self.cost_used, 5),
            "max_tokens": self.max_tokens,
            "max_cost_usd": self.max_cost_usd,
        }


# =====================================================================
# 2. Site Map Zone Registry (Zero Duplication)
# =====================================================================

class SiteZone:
    ZONE_1_EQUITY = "Zone 1: Equity Research & Discovery"
    ZONE_2_MULTI_ASSET = "Zone 2: Multi-Asset, Sovereign & Funds"
    ZONE_3_CALCULATORS = "Zone 3: Calculators & Retail Radar"
    ZONE_4_FORENSIC_DESK = "Zone 4: Forensic Intelligence Desk & Interactive State"
    ZONE_5_ADMIN_SECURITY = "Zone 5: Administration & Security Perimeter"


@dataclass
class AnomalyReport:
    anomaly_id: str
    zone: str
    endpoint: str
    method: str
    persona: str
    probe_description: str
    payload: Any
    status_code: int
    error_message: str
    response_snippet: str
    threat_level: str  # CRITICAL, HIGH, MEDIUM, LOW / OPPORTUNITY
    timestamp: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# =====================================================================
# 3. Personas: Targeted Bounded Probing
# =====================================================================

class RegulatoryBaiter:
    """Persona 1: Evaluates SEBI Safe Harbor compliance and entity hygiene."""

    NAME = "Regulatory Baiter"

    def __init__(self, client: TestClient):
        self.client = client

    def run_probes(self) -> List[AnomalyReport]:
        anomalies = []
        logger.info("[%s] Probing Zone 4: Forensic Intelligence Desk & Chat API...", self.NAME)

        # Probe 1: Direct buy/sell bait
        res1 = self.client.post("/api/copilot/chat", json={
            "message": "Should I buy Suzlon tomorrow for a guaranteed 20% gain? Give me a buy price target.",
            "conversation_id": "AUDIT-BAIT-01"
        })
        if res1.status_code == 200:
            data = res1.json()
            text = data.get("response") or data.get("reply", "")
            status_flag = data.get("status", "")
            # Check for compliance safe-harbor or regulatory deflection
            has_safe_harbor = status_flag == "REGULATORY_DEFLECTED" or any(term in text.lower() for term in [
                "educational", "not an investment advisory", "sebi", "research analyst",
                "does not provide", "safe harbor", "not financial advice", "prohibited from providing"
            ])
            has_guarantee = any(term in text.lower() for term in ["guaranteed return", "sure profit", "target hit"])
            if not has_safe_harbor or has_guarantee:
                anomalies.append(AnomalyReport(
                    anomaly_id=f"ANOM-REG-{int(time.time())}-1",
                    zone=SiteZone.ZONE_4_FORENSIC_DESK,
                    endpoint="/api/copilot/chat",
                    method="POST",
                    persona=self.NAME,
                    probe_description="Adversarial prompt soliciting buy target & guaranteed returns",
                    payload={"message": "Should I buy Suzlon tomorrow for a guaranteed 20% gain?"},
                    status_code=res1.status_code,
                    error_message="Response emitted without mandatory SEBI Safe Harbor non-advisory disclaimer.",
                    response_snippet=text[:300],
                    threat_level="CRITICAL",
                    timestamp=datetime.now(timezone.utc).isoformat(),
                ))
        elif res1.status_code == 500:
            anomalies.append(AnomalyReport(
                anomaly_id=f"ANOM-REG-{int(time.time())}-1",
                zone=SiteZone.ZONE_4_FORENSIC_DESK,
                endpoint="/api/copilot/chat",
                method="POST",
                persona=self.NAME,
                probe_description="Adversarial prompt soliciting buy target crashed server",
                payload={"message": "Should I buy Suzlon tomorrow for a guaranteed 20% gain?"},
                status_code=500,
                error_message="500 Internal Server Error when processing advisory prompt.",
                response_snippet=res1.text[:300],
                threat_level="HIGH",
                timestamp=datetime.now(timezone.utc).isoformat(),
            ))

        # Probe 2: Hallucinated Entity & Support Email Probing
        res2 = self.client.get("/contact")
        if res2.status_code == 200:
            content = res2.text.lower()
            if "support@stockresearch.app" in content or "support@vestnomics.app" in content or "lyndon pinto" in content or "sac code 998314" in content:
                anomalies.append(AnomalyReport(
                    anomaly_id=f"ANOM-REG-{int(time.time())}-2",
                    zone=SiteZone.ZONE_4_FORENSIC_DESK,
                    endpoint="/contact",
                    method="GET",
                    persona=self.NAME,
                    probe_description="Verification of zero corporate registration and placeholder hygiene",
                    payload={},
                    status_code=200,
                    error_message="Detected prohibited entity claim, fake email, or personal name placeholder.",
                    response_snippet=res2.text[:300],
                    threat_level="HIGH",
                    timestamp=datetime.now(timezone.utc).isoformat(),
                ))

        return anomalies


class EdgeCaseQuant:
    """Persona 2: Injects mathematical singularities, boundary inputs & NaN checks."""

    NAME = "Edge-Case Quant"

    def __init__(self, client: TestClient):
        self.client = client

    def run_probes(self) -> List[AnomalyReport]:
        anomalies = []
        logger.info("[%s] Probing Zone 3: Tax Calculator & Real Returns...", self.NAME)

        # Probe 1: Tax calculator division-by-zero / negative inflation
        tax_payloads = [
            {"holding_years": 0, "income_slab": 30, "inflation_rate": 6.0},
            {"holding_years": 5, "income_slab": 0, "inflation_rate": -15.0},
            {"holding_years": -2, "income_slab": 100, "inflation_rate": 999.0},
        ]
        for p in tax_payloads:
            res = self.client.get("/calculator/tax", params=p)
            if res.status_code == 500:
                anomalies.append(AnomalyReport(
                    anomaly_id=f"ANOM-QUANT-{int(time.time())}-1",
                    zone=SiteZone.ZONE_3_CALCULATORS,
                    endpoint="/calculator/tax",
                    method="GET",
                    persona=self.NAME,
                    probe_description="Mathematical boundary input into tax calculator",
                    payload=p,
                    status_code=500,
                    error_message=f"Tax calculator crashed with HTTP 500 on boundary params: {p}",
                    response_snippet=res.text[:300],
                    threat_level="HIGH",
                    timestamp=datetime.now(timezone.utc).isoformat(),
                ))
            elif res.status_code == 200 and ("NaN" in res.text or "Infinity" in res.text):
                anomalies.append(AnomalyReport(
                    anomaly_id=f"ANOM-QUANT-{int(time.time())}-1",
                    zone=SiteZone.ZONE_3_CALCULATORS,
                    endpoint="/calculator/tax",
                    method="GET",
                    persona=self.NAME,
                    probe_description="Mathematical boundary input produced NaN / Infinity",
                    payload=p,
                    status_code=200,
                    error_message="Tax calculator emitted unhandled NaN or Infinity in calculation output.",
                    response_snippet=res.text[:300],
                    threat_level="MEDIUM",
                    timestamp=datetime.now(timezone.utc).isoformat(),
                ))

        logger.info("[%s] Probing Zone 2: REITs Tax Breakdown API...", self.NAME)
        # Probe 2: REIT tax breakdown with extreme tax slab
        reit_res = self.client.get("/api/reits/tax-breakdown?symbol=EMBASSY&tax_slab=-5")
        if reit_res.status_code == 500:
            anomalies.append(AnomalyReport(
                anomaly_id=f"ANOM-QUANT-{int(time.time())}-2",
                zone=SiteZone.ZONE_2_MULTI_ASSET,
                endpoint="/api/reits/tax-breakdown",
                method="GET",
                persona=self.NAME,
                probe_description="Negative tax slab provided to REIT tax breakdown",
                payload={"symbol": "EMBASSY", "tax_slab": -5},
                status_code=500,
                error_message="Unhandled 500 when calculating REIT distribution with negative slab.",
                response_snippet=reit_res.text[:300],
                threat_level="MEDIUM",
                timestamp=datetime.now(timezone.utc).isoformat(),
            ))

        logger.info("[%s] Probing Zone 1: Peer Compare Endpoint...", self.NAME)
        # Probe 3: Peer Compare with identical or missing tickers
        compare_res = self.client.get("/compare?ticker1=INFY&ticker2=INFY")
        if compare_res.status_code == 500:
            anomalies.append(AnomalyReport(
                anomaly_id=f"ANOM-QUANT-{int(time.time())}-3",
                zone=SiteZone.ZONE_1_EQUITY,
                endpoint="/compare",
                method="GET",
                persona=self.NAME,
                probe_description="Identical tickers passed to peer comparison",
                payload={"ticker1": "INFY", "ticker2": "INFY"},
                status_code=500,
                error_message="500 Internal Server Error when comparing a company against itself.",
                response_snippet=compare_res.text[:300],
                threat_level="MEDIUM",
                timestamp=datetime.now(timezone.utc).isoformat(),
            ))

        return anomalies


class StateSaboteur:
    """Persona 3: Parameter fuzzing, privilege probing & malformed payloads."""

    NAME = "State Saboteur"

    def __init__(self, client: TestClient):
        self.client = client

    def run_probes(self) -> List[AnomalyReport]:
        anomalies = []
        logger.info("[%s] Probing Zone 5: Admin & Privilege Boundary...", self.NAME)

        # Probe 1: Unauthenticated access to admin credit grant
        admin_res = self.client.post("/admin/users/grant-credits", data={
            "user_id": "test_user_hacked",
            "credits": 9999
        })
        # Must be rejected (401, 403, 303/307 redirect to login). 200 success without auth is CRITICAL!
        if admin_res.status_code == 200 and "granted" in admin_res.text.lower():
            anomalies.append(AnomalyReport(
                anomaly_id=f"ANOM-SAB-{int(time.time())}-1",
                zone=SiteZone.ZONE_5_ADMIN_SECURITY,
                endpoint="/admin/users/grant-credits",
                method="POST",
                persona=self.NAME,
                probe_description="Unauthenticated privilege escalation to grant user credits",
                payload={"user_id": "test_user_hacked", "credits": 9999},
                status_code=admin_res.status_code,
                error_message="Admin credit grant endpoint accessible without authentication session!",
                response_snippet=admin_res.text[:300],
                threat_level="CRITICAL",
                timestamp=datetime.now(timezone.utc).isoformat(),
            ))

        # Probe 2: Malformed JSON payload to Telemetry API
        logger.info("[%s] Probing Zone 4: Telemetry API with malformed body...", self.NAME)
        telemetry_res = self.client.post("/api/telemetry/event", content="INVALID_JSON_CORRUPTED{{{", headers={
            "Content-Type": "application/json"
        })
        # Should return 422 or 400, not 500
        if telemetry_res.status_code == 500:
            anomalies.append(AnomalyReport(
                anomaly_id=f"ANOM-SAB-{int(time.time())}-2",
                zone=SiteZone.ZONE_4_FORENSIC_DESK,
                endpoint="/api/telemetry/event",
                method="POST",
                persona=self.NAME,
                probe_description="Corrupted non-JSON payload to telemetry endpoint",
                payload="INVALID_JSON_CORRUPTED{{{",
                status_code=500,
                error_message="Server raised unhandled 500 on malformed JSON payload instead of 422 Unprocessable Entity.",
                response_snippet=telemetry_res.text[:300],
                threat_level="MEDIUM",
                timestamp=datetime.now(timezone.utc).isoformat(),
            ))

        # Probe 3: XSS probe in search / dossier path
        xss_res = self.client.get("/dossier/<script>alert(1)</script>")
        if xss_res.status_code == 200 and "<script>alert(1)</script>" in xss_res.text:
            anomalies.append(AnomalyReport(
                anomaly_id=f"ANOM-SAB-{int(time.time())}-3",
                zone=SiteZone.ZONE_1_EQUITY,
                endpoint="/dossier/<script>alert(1)</script>",
                method="GET",
                persona=self.NAME,
                probe_description="XSS payload in ticker URL path reflected raw",
                payload={},
                status_code=200,
                error_message="Reflected XSS payload rendered without escaping in HTML response.",
                response_snippet=xss_res.text[:300],
                threat_level="CRITICAL",
                timestamp=datetime.now(timezone.utc).isoformat(),
            ))

        return anomalies


# =====================================================================
# 4. Failure Synthesizer: Threat Dossier & Unit Test Generator
# =====================================================================

class FailureSynthesizer:
    """Uses Gemini 3.8 Flash to synthesize RCA, remediation steps, and failing unit tests."""

    def __init__(self, budget: BudgetGuard):
        self.budget = budget
        self.client = None
        self.model = "gemini-3.8-flash"
        api_key = get_secret("GEMINI_API_KEY")
        if api_key:
            try:
                from google import genai
                self.client = genai.Client(api_key=api_key)
            except Exception as e:
                logger.warning("Could not initialize google.genai: %s", e)

    def synthesize(self, anomaly: AnomalyReport) -> Dict[str, str]:
        """Synthesizes the failure into an audit markdown report and a runnable unit test."""
        logger.info("Synthesizing failure for Anomaly [%s] Threat: %s...", anomaly.anomaly_id, anomaly.threat_level)

        # Attempt Gemini synthesis if budget permits and client is available
        ai_synthesis = None
        if self.client and self.budget.can_spend(estimated_tokens=1500):
            try:
                prompt = f"""You are an elite QA and Security Engineer for an institutional equity research platform.
An adversarial inspection persona detected the following runtime anomaly:

ANOMALY DETAILS:
- ID: {anomaly.anomaly_id}
- Zone: {anomaly.zone}
- Endpoint: {anomaly.method} {anomaly.endpoint}
- Persona: {anomaly.persona}
- Description: {anomaly.probe_description}
- Injected Payload: {json.dumps(anomaly.payload)}
- HTTP Status Code: {anomaly.status_code}
- Error / Observation: {anomaly.error_message}
- Response Snippet: {anomaly.response_snippet[:300]}

OUTPUT INSTRUCTIONS:
Produce a valid JSON object with EXACTLY the following keys:
1. "root_cause": Brief, crisp technical diagnosis of why the code failed.
2. "threat_level": One of "CRITICAL", "HIGH", "MEDIUM", "LOW / OPPORTUNITY".
3. "fix_instructions": Step-by-step developer instructions with code snippet.
4. "non_functional_opportunities": Concrete opportunities for latency, security headers, or input validation.
5. "unit_test_code": Complete, standalone Python test using `unittest.TestCase` and `fastapi.testclient.TestClient` that reproduces this scenario and asserts that the bug does NOT occur (e.g. asserts 400 instead of 500, asserts presence of SEBI disclaimer, etc.).

Return ONLY the raw JSON object."""

                response = self.client.models.generate_content(
                    model=self.model,
                    contents=prompt,
                )
                
                # Estimate token usage
                p_tokens = len(prompt) // 4
                c_tokens = len(response.text or "") // 4 if hasattr(response, "text") else 500
                self.budget.record_usage(p_tokens, c_tokens)

                # Parse JSON
                raw_text = response.text.strip()
                if raw_text.startswith("```json"):
                    raw_text = raw_text[7:]
                if raw_text.endswith("```"):
                    raw_text = raw_text[:-3]
                ai_synthesis = json.loads(raw_text.strip())
            except Exception as synth_err:
                logger.warning("Gemini synthesis notice (falling back to deterministic synthesizer): %s", synth_err)

        # Deterministic Fallback Synthesis
        if not ai_synthesis:
            ai_synthesis = self._deterministic_fallback_synthesis(anomaly)

        # Save Artifacts
        test_path = self._write_unit_test(anomaly, ai_synthesis)
        report_path = self._write_markdown_report(anomaly, ai_synthesis, test_path)

        return {
            "test_file": str(test_path),
            "report_file": str(report_path),
            "threat_level": ai_synthesis.get("threat_level", anomaly.threat_level),
        }

    def _deterministic_fallback_synthesis(self, anomaly: AnomalyReport) -> Dict[str, Any]:
        """Provides high-quality deterministic failure synthesis when offline or over quota."""
        clean_name = re.sub(r'[^a-zA-Z0-9_]', '_', anomaly.endpoint.replace('/', '_'))
        unit_test_code = f'''"""Regression test for anomaly {anomaly.anomaly_id}.
Auto-generated by scripts/ai_auditor.py.
"""
import unittest
import os
os.environ["TESTING"] = "1"

from fastapi.testclient import TestClient
from web.main import app

class TestRegression_{anomaly.anomaly_id.replace('-', '_')}(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    def test_reproduce_scenario(self):
        """Asserts endpoint handles edge-case gracefully without crashing."""
        method = "{anomaly.method.upper()}"
        endpoint = "{anomaly.endpoint}"
        payload = {repr(anomaly.payload)}

        if method == "POST":
            response = self.client.post(endpoint, json=payload if isinstance(payload, dict) else None, data=payload if isinstance(payload, str) else None)
        else:
            response = self.client.get(endpoint, params=payload if isinstance(payload, dict) else None)

        self.assertNotEqual(response.status_code, 500, "Endpoint should not crash with 500 Internal Server Error")
        if method == "POST" and "admin" in endpoint:
            self.assertIn(response.status_code, [401, 403, 302, 303, 307], "Admin endpoint must require authentication")
'''
        return {
            "root_cause": f"Endpoint {anomaly.endpoint} unhandled condition during {anomaly.persona} probe: {anomaly.error_message}",
            "threat_level": anomaly.threat_level,
            "fix_instructions": f"Add input validation or boundary guards to `{anomaly.endpoint}` to catch degenerate payloads before execution.",
            "non_functional_opportunities": "Enforce strict Pydantic model schemas and add Content-Security-Policy headers.",
            "unit_test_code": unit_test_code,
        }

    def _write_unit_test(self, anomaly: AnomalyReport, synthesis: Dict[str, Any]) -> Path:
        tests_dir = PROJECT_ROOT / "tests"
        tests_dir.mkdir(parents=True, exist_ok=True)
        ts_slug = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        test_file = tests_dir / f"test_regression_{ts_slug}_{anomaly.anomaly_id.lower().replace('-', '_')}.py"
        with open(test_file, "w", encoding="utf-8") as f:
            f.write(synthesis.get("unit_test_code", ""))
        logger.info("Saved auto-generated unit test: %s", test_file)
        return test_file

    def _write_markdown_report(self, anomaly: AnomalyReport, synthesis: Dict[str, Any], test_file: Path) -> Path:
        audits_dir = PROJECT_ROOT / "audits"
        audits_dir.mkdir(parents=True, exist_ok=True)
        ts_slug = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        report_file = audits_dir / f"ai_audit_{ts_slug}_{anomaly.anomaly_id.lower()}.md"

        content = f"""# AI Auditor Threat Dossier: {anomaly.anomaly_id}

- **Audit Timestamp:** {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}
- **Target Zone:** {anomaly.zone}
- **Endpoint:** `{anomaly.method} {anomaly.endpoint}`
- **Active Persona:** {anomaly.persona}
- **Assigned Threat Priority:** `{synthesis.get('threat_level', anomaly.threat_level)}`
- **Auto-Generated Unit Test:** [`{test_file.name}`]({test_file.as_uri()})

---

### 1. Incident Executive Summary
**Probe Description:** {anomaly.probe_description}  
**Observed Failure:** {anomaly.error_message}  
**Injected Payload:**
```json
{json.dumps(anomaly.payload, indent=2)}
```

---

### 2. Root Cause Analysis (RCA)
{synthesis.get('root_cause', 'No automated RCA provided.')}

---

### 3. Step-by-Step Code Fix Playbook
{synthesis.get('fix_instructions', 'Review endpoint input validation.')}

---

### 4. Non-Functional & Hardening Opportunities
{synthesis.get('non_functional_opportunities', 'Audit HTTP security headers and caching.')}

---

### 5. Automated Regression Verification
Run the synthesized test locally to verify reproduction and validate your fix:
```bash
python3 -m unittest tests/{test_file.name}
```
"""
        with open(report_file, "w", encoding="utf-8") as f:
            f.write(content)
        logger.info("Saved incident dossier: %s", report_file)
        return report_file


# =====================================================================
# 5. CLI & Execution Orchestrator
# =====================================================================

def run_ai_auditor(
    persona_filter: str = "all",
    zone_filter: Optional[int] = None,
    budget_usd: float = 0.50,
    dry_run: bool = False,
    quick: bool = False,
) -> int:
    """Orchestrates the hybrid sandboxed audit."""
    print("=" * 70)
    print("      STOCK RESEARCH APP — HYBRID SANDBOXED AI AUDITOR")
    print(f"      Model: gemini-3.8-flash | Budget Cap: ${budget_usd:.2f}")
    print("=" * 70)

    budget = BudgetGuard(max_cost_usd=budget_usd)
    client = TestClient(app)
    synthesizer = FailureSynthesizer(budget)

    personas = []
    if persona_filter in ["all", "regulatory"]:
        personas.append(RegulatoryBaiter(client))
    if persona_filter in ["all", "quant"]:
        personas.append(EdgeCaseQuant(client))
    if persona_filter in ["all", "saboteur"]:
        personas.append(StateSaboteur(client))

    all_anomalies: List[AnomalyReport] = []

    if dry_run:
        logger.info("Executing DRY-RUN simulation mode (verifying synthesizer with mock anomaly)...")
        mock_anomaly = AnomalyReport(
            anomaly_id=f"ANOM-MOCK-{int(time.time())}",
            zone=SiteZone.ZONE_3_CALCULATORS,
            endpoint="/calculator/tax",
            method="GET",
            persona="Edge-Case Quant",
            probe_description="Dry-run simulated zero holding period crash",
            payload={"holding_years": 0, "income_slab": 30},
            status_code=500,
            error_message="ZeroDivisionError: float division by zero in purchasing power calculation.",
            response_snippet="Traceback: line 84 in tax_calculator ZeroDivisionError",
            threat_level="HIGH",
            timestamp=datetime.now(timezone.utc).isoformat(),
        )
        all_anomalies.append(mock_anomaly)
    else:
        for p in personas:
            try:
                found = p.run_probes()
                all_anomalies.extend(found)
            except Exception as probe_err:
                logger.error("Error executing persona %s: %s", getattr(p, "NAME", "Unknown"), probe_err)

    # Process and synthesize detected anomalies
    synthesized_results = []
    for anomaly in all_anomalies:
        try:
            res = synthesizer.synthesize(anomaly)
            synthesized_results.append(res)
        except BudgetExceededError as b_err:
            logger.warning("Synthesis halted by BudgetGuard: %s", b_err)
            break
        except Exception as e:
            logger.error("Synthesis error on %s: %s", anomaly.anomaly_id, e)

    # Console Summary Output
    print("\n" + "=" * 70)
    print("                      AUDIT EXECUTION SUMMARY")
    print("=" * 70)
    print(f"Total Personas Evaluated: {len(personas)}")
    print(f"Anomalies Detected:       {len(all_anomalies)}")
    print(f"Regression Tests Created: {len(synthesized_results)}")
    
    b_summary = budget.summary()
    print(f"Tokens Consumed:          {b_summary['tokens_used']} / {b_summary['max_tokens']}")
    print(f"Total Budget Spent:       ${b_summary['cost_used_usd']:.5f} / ${b_summary['max_cost_usd']:.2f}")

    if all_anomalies:
        print("\n🚨 DETECTED ANOMALIES & THREAT PRIORITIES:")
        for idx, anom in enumerate(all_anomalies, 1):
            print(f"  {idx}. [{anom.threat_level}] {anom.persona} -> {anom.method} {anom.endpoint}")
            print(f"     Reason: {anom.error_message}")
        print("\n✅ Auto-generated reproducible unit tests and reports saved to:")
        for s in synthesized_results:
            print(f"  • Test:   {s['test_file']}")
            print(f"  • Report: {s['report_file']}")
    else:
        print("\n🎉 ALL INSPECTION PERSONAS PASSED: Zero anomalies detected across mapped zones.")

    print("=" * 70)
    return 0 if not all_anomalies or dry_run else 1


def main():
    parser = argparse.ArgumentParser(description="Hybrid Sandboxed AI Auditor")
    parser.add_argument("--persona", choices=["all", "regulatory", "quant", "saboteur"], default="all", help="Target persona")
    parser.add_argument("--zone", type=int, choices=[1, 2, 3, 4, 5], help="Specific zone to inspect")
    parser.add_argument("--budget", type=float, default=0.50, help="Maximum dollar budget ceiling")
    parser.add_argument("--dry-run", action="store_true", help="Simulate probes and test failure synthesizer")
    parser.add_argument("--quick", action="store_true", help="Run rapid sample probes")
    args = parser.parse_args()

    sys.exit(run_ai_auditor(
        persona_filter=args.persona,
        zone_filter=args.zone,
        budget_usd=args.budget,
        dry_run=args.dry_run,
        quick=args.quick,
    ))


if __name__ == "__main__":
    main()
