"""
Setu Cross-Asset Capital Structure Matrix
========================================
Phase 3 Proprietary Architecture (Anvik Cortex Engine).

An on-demand cross-asset relational transmission engine that:
1. Links an equity ticker to its broader enterprise capital structure:
   - Senior Secured Corporate Debt / NCDs (Yield to Maturity & Seniority)
   - Indian Sovereign 10Y Benchmark G-Sec (7.05%)
   - Commercial Real Estate & Infrastructure Yields (REITs / InvITs)
   - Institutional Mutual Fund Velocity & Net Delivery Concentration
2. Computes Capital Seniority Spreads:
   - Equity FCF Yield vs Senior Debt YTM
   - Corporate Credit Spread vs Sovereign Risk-Free Benchmark
3. Detects Capital Structure Inversions & Arbitrage Dislocations:
   - Identifies when residual equity is mispriced below senior secured claims of the exact same enterprise.
4. Lightweight and on-demand: Zero persistent in-memory graph overhead to preserve Render 512MB constraints.
"""

from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
import math
import logging

logger = logging.getLogger(__name__)


@dataclass
class CapitalTranche:
    tier: str  # "SOVEREIGN", "SENIOR_SECURED_NCD", "SUBORDINATED_DEBT", "HYBRID_REIT", "RESIDUAL_EQUITY"
    instrument_name: str
    nominal_yield_pct: float
    post_tax_yield_pct: float
    seniority_rank: int  # 1 = Highest (Sovereign), 5 = Lowest (Equity)
    rating: str = "SOV"


@dataclass
class CapitalStructureAnomaly:
    anomaly_type: str
    severity: str  # "INFO", "WARNING", "CRITICAL"
    description: str


@dataclass
class SetuMatrixResult:
    symbol: str
    equity_fcf_yield_pct: float
    senior_debt_ytm_pct: float
    gsec_10y_benchmark_pct: float
    seniority_spread_bps: float  # (Equity FCF Yield - Senior Debt YTM) * 100
    credit_spread_bps: float     # (Senior Debt YTM - 10Y G-Sec) * 100
    capital_posture_regime: str  # "PRISTINE_CAPITAL_HIERARCHY", "CAPITAL_STRUCTURE_INVERSION", "CREDIT_STRESS_DISLOCATION"
    tranches: List[CapitalTranche] = field(default_factory=list)
    anomalies: List[CapitalStructureAnomaly] = field(default_factory=list)
    institutional_mf_velocity_score: float = 50.0  # 0 to 100
    summary: str = ""


class SetuMatrixEngine:
    """
    On-Demand Cross-Asset Capital Structure Matrix.
    """

    DEFAULT_GSEC_10Y: float = 7.05
    DEFAULT_REIT_YIELD: float = 7.80

    @classmethod
    def evaluate(
        cls,
        symbol: str,
        equity_fcf_yield_pct: float,
        senior_debt_ytm_pct: Optional[float] = None,
        debt_credit_rating: str = "AAA",
        gsec_10y_yield_pct: float = DEFAULT_GSEC_10Y,
        mutual_fund_net_flow_cr: float = 0.0,
        promoter_pledge_pct: float = 0.0,
        tax_slab_pct: float = 30.0,
    ) -> SetuMatrixResult:
        """
        Executes on-demand capital structure transmission evaluation.
        """
        # Estimate senior debt YTM from rating if not directly provided
        if senior_debt_ytm_pct is None:
            spread_map = {
                "AAA": 0.85,
                "AA+": 1.20,
                "AA": 1.65,
                "AA-": 2.25,
                "A+": 3.10,
                "A": 4.00,
                "BBB": 5.50,
            }
            spread = spread_map.get(debt_credit_rating.upper(), 1.50)
            senior_debt_ytm_pct = round(gsec_10y_yield_pct + spread, 2)

        # Seniority spread: Equity FCF Yield vs Senior Debt YTM
        seniority_spread_bps = round((equity_fcf_yield_pct - senior_debt_ytm_pct) * 100.0, 1)
        credit_spread_bps = round((senior_debt_ytm_pct - gsec_10y_yield_pct) * 100.0, 1)

        # Build capital tranches
        tax_drag = 1.0 - (tax_slab_pct / 100.0)
        tranches = [
            CapitalTranche(
                tier="SOVEREIGN",
                instrument_name="10Y Benchmark GOI G-Sec",
                nominal_yield_pct=gsec_10y_yield_pct,
                post_tax_yield_pct=round(gsec_10y_yield_pct * tax_drag, 2),
                seniority_rank=1,
                rating="SOV",
            ),
            CapitalTranche(
                tier="SENIOR_SECURED_NCD",
                instrument_name=f"{symbol} Senior Secured NCD",
                nominal_yield_pct=senior_debt_ytm_pct,
                post_tax_yield_pct=round(senior_debt_ytm_pct * tax_drag, 2),
                seniority_rank=2,
                rating=debt_credit_rating,
            ),
            CapitalTranche(
                tier="HYBRID_REIT",
                instrument_name="Commercial Real Estate Benchmark (REIT)",
                nominal_yield_pct=cls.DEFAULT_REIT_YIELD,
                post_tax_yield_pct=round(cls.DEFAULT_REIT_YIELD * 0.85, 2),  # Partial tax exemption under Sec 115UA
                seniority_rank=3,
                rating="AAA",
            ),
            CapitalTranche(
                tier="RESIDUAL_EQUITY",
                instrument_name=f"{symbol} Common Equity",
                nominal_yield_pct=equity_fcf_yield_pct,
                post_tax_yield_pct=round(equity_fcf_yield_pct * (1.0 - 0.125), 2),  # 12.5% LTCG under Sec 112A
                seniority_rank=5,
                rating="EQUITY_RESIDUAL",
            ),
        ]

        anomalies: List[CapitalStructureAnomaly] = []

        # 1. Capital Structure Inversion Check
        if equity_fcf_yield_pct < senior_debt_ytm_pct:
            regime = "CAPITAL_STRUCTURE_INVERSION"
            anomalies.append(CapitalStructureAnomaly(
                anomaly_type="CAPITAL_STRUCTURE_INVERSION",
                severity="WARNING",
                description=(
                    f"Capital structure inversion: Common equity FCF yield ({equity_fcf_yield_pct:.2f}%) is "
                    f"{abs(seniority_spread_bps):.0f} bps below senior secured debt ({senior_debt_ytm_pct:.2f}%). "
                    f"Residual risk is uncompensated relative to senior paper."
                ),
            ))
        elif credit_spread_bps > 350.0:
            regime = "CREDIT_STRESS_DISLOCATION"
            anomalies.append(CapitalStructureAnomaly(
                anomaly_type="CREDIT_SPREAD_BLOWOUT",
                severity="CRITICAL",
                description=(
                    f"Credit stress divergence: Senior debt spread ({credit_spread_bps:.0f} bps over G-Sec) "
                    f"signals elevated default or rating downgrade risk."
                ),
            ))
        else:
            regime = "PRISTINE_CAPITAL_HIERARCHY"

        # 2. Institutional Mutual Fund Flow Velocity
        # Standard score 50 (neutral), positive net flow increases score
        mf_score = 50.0
        if mutual_fund_net_flow_cr > 100.0:
            mf_score = min(100.0, 50.0 + (mutual_fund_net_flow_cr / 20.0))
        elif mutual_fund_net_flow_cr < -50.0:
            mf_score = max(0.0, 50.0 + (mutual_fund_net_flow_cr / 10.0))
            anomalies.append(CapitalStructureAnomaly(
                anomaly_type="DOMESTIC_INSTITUTIONAL_EXIT",
                severity="WARNING",
                description=f"Domestic institutional funds net sold ₹{abs(mutual_fund_net_flow_cr):.1f} Cr over the trailing period.",
            ))

        # 3. Promoter Pledge Encumbrance
        if promoter_pledge_pct > 25.0:
            anomalies.append(CapitalStructureAnomaly(
                anomaly_type="PROMOTER_ENCUMBRANCE_DRAG",
                severity="CRITICAL",
                description=f"Promoter pledge ({promoter_pledge_pct:.1f}%) risks capital structure margin liquidation.",
            ))

        summary = (
            f"Setu Transmission: {regime}. Seniority Spread: {seniority_spread_bps:+.0f} bps vs Senior NCD "
            f"({senior_debt_ytm_pct:.2f}%). Credit Spread: {credit_spread_bps:.0f} bps over 10Y G-Sec. "
            f"Anomalies detected: {len(anomalies)}."
        )

        return SetuMatrixResult(
            symbol=symbol,
            equity_fcf_yield_pct=round(equity_fcf_yield_pct, 2),
            senior_debt_ytm_pct=round(senior_debt_ytm_pct, 2),
            gsec_10y_benchmark_pct=round(gsec_10y_yield_pct, 2),
            seniority_spread_bps=seniority_spread_bps,
            credit_spread_bps=credit_spread_bps,
            capital_posture_regime=regime,
            tranches=tranches,
            anomalies=anomalies,
            institutional_mf_velocity_score=round(mf_score, 1),
            summary=summary,
        )
