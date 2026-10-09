"""
Anvik Cortex Engine
===================
Proprietary Institutional Quantitative Financial Architecture.

Encapsulates four core proprietary quantitative and forensic valuation algorithms:
1. Dynamic Statutory Yield Wedge (Statutory FCF Yield vs Sovereign / Monetary Baselines)
2. Reverse DCF Hurdle Deconstruct (Numerical Root Solver for Market-Implied Growth CAGRs)
3. PEAD Quant Drift Velocity (Post-Earnings Announcement Drift, Delivery Signature & Persistence)
4. Fiduciary Governance Scoring Index (RPT, Promoter Pledge Velocity, Auditor Quality, Contingent Risk)
"""

from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
import math
import logging

logger = logging.getLogger(__name__)


# ==============================================================================
# 1. Dynamic Statutory Yield Wedge
# ==============================================================================

@dataclass
class StatutoryYieldWedgeResult:
    symbol: str
    statutory_fcf_cr: float
    enterprise_value_cr: float
    statutory_fcf_yield_pct: float
    rbi_repo_rate_pct: float
    gsec_10y_yield_pct: float
    effective_tax_drag_pct: float
    gsec_spread_bps: float
    repo_wedge_bps: float
    hurdle_threshold_bps: float
    yield_hurdle_pass: bool
    regime: str  # "STATUTORY_EXPANSIONARY", "FAIR_VALUE_EQUILIBRIUM", "COMPRESSED_YIELD_DEFICIT"
    summary: str


class DynamicStatutoryYieldWedge:
    """
    Evaluates an asset's statutory cash generation yield relative to Indian macroeconomic
    anchors: the RBI Policy Repo Rate, 10Y Benchmark Sovereign G-Sec Yield, and Statutory
    corporate tax drag wedges.
    """

    DEFAULT_RBI_REPO_RATE: float = 6.50
    DEFAULT_10Y_GSEC_YIELD: float = 7.05
    DEFAULT_HURDLE_BPS: float = 250.0  # 2.50% statutory equity risk premium over G-Sec

    @classmethod
    def evaluate(
        cls,
        symbol: str,
        operating_cash_flow_cr: float,
        maintenance_capex_cr: float,
        enterprise_value_cr: float,
        effective_tax_drag_pct: float = 25.17,  # Standard Indian corporate statutory tax rate
        rbi_repo_rate_pct: Optional[float] = None,
        gsec_10y_yield_pct: Optional[float] = None,
        hurdle_threshold_bps: Optional[float] = None,
    ) -> StatutoryYieldWedgeResult:
        repo = rbi_repo_rate_pct if rbi_repo_rate_pct is not None else cls.DEFAULT_RBI_REPO_RATE
        gsec = gsec_10y_yield_pct if gsec_10y_yield_pct is not None else cls.DEFAULT_10Y_GSEC_YIELD
        hurdle = hurdle_threshold_bps if hurdle_threshold_bps is not None else cls.DEFAULT_HURDLE_BPS

        ev = max(enterprise_value_cr, 1.0)
        statutory_fcf = max(0.0, operating_cash_flow_cr - maintenance_capex_cr)
        
        # Calculate statutory FCF yield
        statutory_fcf_yield_pct = round((statutory_fcf / ev) * 100.0, 2)
        
        # Spreads in basis points (1% = 100 bps)
        gsec_spread_bps = round((statutory_fcf_yield_pct - gsec) * 100.0, 1)
        repo_wedge_bps = round((statutory_fcf_yield_pct - repo) * 100.0, 1)

        yield_hurdle_pass = gsec_spread_bps >= hurdle

        if yield_hurdle_pass:
            regime = "STATUTORY_EXPANSIONARY"
            summary = (
                f"{symbol.upper()} statutory FCF yield ({statutory_fcf_yield_pct:.2f}%) generates a "
                f"+{gsec_spread_bps:.0f} bps wedge over 10Y Indian Sovereign Benchmark ({gsec:.2f}%), "
                f"exceeding the {hurdle:.0f} bps statutory risk premium hurdle."
            )
        elif gsec_spread_bps >= -100.0:
            regime = "FAIR_VALUE_EQUILIBRIUM"
            summary = (
                f"{symbol.upper()} statutory FCF yield ({statutory_fcf_yield_pct:.2f}%) trades near "
                f"sovereign parity ({gsec_spread_bps:+.0f} bps vs 10Y G-Sec). Modest margin of safety."
            )
        else:
            regime = "COMPRESSED_YIELD_DEFICIT"
            summary = (
                f"{symbol.upper()} statutory FCF yield ({statutory_fcf_yield_pct:.2f}%) incurs a "
                f"{gsec_spread_bps:.0f} bps deficit relative to 10Y Sovereign Yield ({gsec:.2f}%). "
                f"High valuation hurdle demands aggressive multi-year earnings execution."
            )

        return StatutoryYieldWedgeResult(
            symbol=symbol.upper(),
            statutory_fcf_cr=round(statutory_fcf, 2),
            enterprise_value_cr=round(ev, 2),
            statutory_fcf_yield_pct=statutory_fcf_yield_pct,
            rbi_repo_rate_pct=repo,
            gsec_10y_yield_pct=gsec,
            effective_tax_drag_pct=effective_tax_drag_pct,
            gsec_spread_bps=gsec_spread_bps,
            repo_wedge_bps=repo_wedge_bps,
            hurdle_threshold_bps=hurdle,
            yield_hurdle_pass=yield_hurdle_pass,
            regime=regime,
            summary=summary,
        )


# ==============================================================================
# 2. Reverse DCF Hurdle Deconstruct
# ==============================================================================

@dataclass
class ReverseDcfHurdleResult:
    symbol: str
    current_price: float
    current_fcf_per_share: float
    wacc_pct: float
    terminal_growth_pct: float
    forecast_years: int
    implied_fcf_growth_cagr_5y_pct: float
    historical_fcf_growth_cagr_5y_pct: Optional[float]
    expectation_gap_pct: Optional[float]
    hurdle_difficulty: str  # "LOW_HURDLE", "MODERATE_HURDLE", "HERCULEAN_HURDLE"
    margin_of_safety_pct: float
    summary: str


class ReverseDcfHurdleDeconstruct:
    """
    Deconstructs current equity price into the market-implied 5-year FCF CAGR hurdle
    using a numerical root solver (Bisection / Secant iteration), eliminating arbitrary
    subjective forward projections.
    """

    DEFAULT_WACC_PCT: float = 12.0  # Indian cost of equity / WACC baseline
    DEFAULT_TERMINAL_GROWTH_PCT: float = 6.0  # Clamped to long-term Indian nominal GDP corridor

    @classmethod
    def _dcf_intrinsic_value(
        cls,
        fcf_0: float,
        g: float,
        wacc: float,
        g_terminal: float,
        years: int = 5,
    ) -> float:
        """Computes DCF present value for a given Stage-1 CAGR g."""
        pv_stage1 = 0.0
        fcf_t = fcf_0
        for t in range(1, years + 1):
            fcf_t = fcf_0 * ((1.0 + g) ** t)
            pv_stage1 += fcf_t / ((1.0 + wacc) ** t)

        # Terminal value at end of year N
        fcf_terminal_next = fcf_t * (1.0 + g_terminal)
        denominator = max(wacc - g_terminal, 0.01)
        terminal_value = fcf_terminal_next / denominator
        pv_terminal = terminal_value / ((1.0 + wacc) ** years)

        return pv_stage1 + pv_terminal

    @classmethod
    def solve_implied_growth(
        cls,
        current_price: float,
        fcf_per_share: float,
        wacc_pct: float = DEFAULT_WACC_PCT,
        terminal_growth_pct: float = DEFAULT_TERMINAL_GROWTH_PCT,
        years: int = 5,
    ) -> float:
        """Numerically solves for implied growth CAGR g such that DCF_value(g) = current_price."""
        if current_price <= 0 or fcf_per_share <= 0:
            return 0.0

        wacc = wacc_pct / 100.0
        g_term = terminal_growth_pct / 100.0

        # Bound search between -50% and +150% growth CAGR
        low_g = -0.50
        high_g = 1.50

        # Check bounds
        val_low = cls._dcf_intrinsic_value(fcf_per_share, low_g, wacc, g_term, years)
        val_high = cls._dcf_intrinsic_value(fcf_per_share, high_g, wacc, g_term, years)

        if current_price <= val_low:
            return round(low_g * 100.0, 2)
        if current_price >= val_high:
            return round(high_g * 100.0, 2)

        # Bisection solver with 1e-4 tolerance
        for _ in range(60):
            mid_g = (low_g + high_g) / 2.0
            val_mid = cls._dcf_intrinsic_value(fcf_per_share, mid_g, wacc, g_term, years)
            if abs(val_mid - current_price) < 0.01:
                return round(mid_g * 100.0, 2)
            if val_mid < current_price:
                low_g = mid_g
            else:
                high_g = mid_g

        return round(((low_g + high_g) / 2.0) * 100.0, 2)

    @classmethod
    def evaluate(
        cls,
        symbol: str,
        current_price: float,
        current_fcf_per_share: float,
        historical_fcf_growth_cagr_5y_pct: Optional[float] = None,
        wacc_pct: Optional[float] = None,
        terminal_growth_pct: Optional[float] = None,
        forecast_years: int = 5,
    ) -> ReverseDcfHurdleResult:
        wacc = wacc_pct if wacc_pct is not None else cls.DEFAULT_WACC_PCT
        g_terminal = terminal_growth_pct if terminal_growth_pct is not None else cls.DEFAULT_TERMINAL_GROWTH_PCT

        implied_cagr = cls.solve_implied_growth(
            current_price=current_price,
            fcf_per_share=current_fcf_per_share,
            wacc_pct=wacc,
            terminal_growth_pct=g_terminal,
            years=forecast_years,
        )

        expectation_gap: Optional[float] = None
        margin_of_safety_pct: float = 0.0

        if historical_fcf_growth_cagr_5y_pct is not None:
            expectation_gap = round(implied_cagr - historical_fcf_growth_cagr_5y_pct, 2)
            # Positive margin of safety if historical growth exceeds implied required growth
            denom = max(abs(historical_fcf_growth_cagr_5y_pct), 1.0)
            margin_of_safety_pct = round(((historical_fcf_growth_cagr_5y_pct - implied_cagr) / denom) * 100.0, 1)

        # Classify hurdle difficulty
        if implied_cagr > 25.0 or (expectation_gap is not None and expectation_gap > 10.0):
            hurdle_difficulty = "HERCULEAN_HURDLE"
            summary = (
                f"Current price of ₹{current_price:,.2f} bakes in an aggressive {implied_cagr:.1f}% "
                f"5-year FCF CAGR. "
                + (f"Exceeds historical track record ({historical_fcf_growth_cagr_5y_pct:.1f}%) by {expectation_gap:+.1f}%. " if expectation_gap is not None else "")
                + "Leaves virtually zero room for macro or execution disappointments."
            )
        elif implied_cagr < 12.0 or (expectation_gap is not None and expectation_gap < -2.0):
            hurdle_difficulty = "LOW_HURDLE"
            summary = (
                f"Current price of ₹{current_price:,.2f} requires a modest {implied_cagr:.1f}% "
                f"5-year FCF CAGR. "
                + (f"Below historical track record ({historical_fcf_growth_cagr_5y_pct:.1f}%) by {abs(expectation_gap):.1f}%. " if expectation_gap is not None else "")
                + "Provides an asymmetric statutory margin of safety."
            )
        else:
            hurdle_difficulty = "MODERATE_HURDLE"
            summary = (
                f"Current price of ₹{current_price:,.2f} implies a balanced {implied_cagr:.1f}% "
                f"5-year FCF CAGR, roughly aligned with historical operational velocity."
            )

        return ReverseDcfHurdleResult(
            symbol=symbol.upper(),
            current_price=round(current_price, 2),
            current_fcf_per_share=round(current_fcf_per_share, 2),
            wacc_pct=round(wacc, 2),
            terminal_growth_pct=round(g_terminal, 2),
            forecast_years=forecast_years,
            implied_fcf_growth_cagr_5y_pct=implied_cagr,
            historical_fcf_growth_cagr_5y_pct=round(historical_fcf_growth_cagr_5y_pct, 2) if historical_fcf_growth_cagr_5y_pct is not None else None,
            expectation_gap_pct=expectation_gap,
            hurdle_difficulty=hurdle_difficulty,
            margin_of_safety_pct=margin_of_safety_pct,
            summary=summary,
        )


# ==============================================================================
# 3. PEAD Quant Drift Velocity
# ==============================================================================

@dataclass
class PeadDriftVelocityResult:
    symbol: str
    reported_pat_cr: float
    consensus_or_prior_pat_cr: float
    standardized_unexpected_earnings_pct: float
    volume_surge_ratio: float
    delivery_percentage: float
    delivery_surge_pct: float
    drift_velocity_score: float  # 0 to 100
    momentum_persistence_days: int
    pead_signal: str  # "ACCELERATING_INSTITUTIONAL_DRIFT", "NEUTRAL_CONSOLIDATION", "EXHAUSTION_REVERSAL"
    summary: str


class PeadQuantDriftVelocity:
    """
    Evaluates Post-Earnings Announcement Drift (PEAD) persistence, unexpected earnings surprise
    (SUE), volume expansion, and institutional delivery accumulation signatures for Indian equities.
    """

    @classmethod
    def evaluate(
        cls,
        symbol: str,
        reported_pat_cr: float,
        consensus_or_prior_pat_cr: float,
        post_volume: float,
        avg_50d_volume: float,
        post_delivery_pct: float,
        baseline_delivery_pct: float = 40.0,
    ) -> PeadDriftVelocityResult:
        denom_pat = max(abs(consensus_or_prior_pat_cr), 1.0)
        sue_pct = round(((reported_pat_cr - consensus_or_prior_pat_cr) / denom_pat) * 100.0, 2)

        vol_denom = max(avg_50d_volume, 1.0)
        vol_surge_ratio = round(post_volume / vol_denom, 2)

        delivery_surge = round(post_delivery_pct - baseline_delivery_pct, 1)

        # Composite Scoring (0 - 100)
        # Component A: Earnings Surprise (max 40 pts)
        if sue_pct > 25.0:
            sue_score = 40.0
        elif sue_pct > 10.0:
            sue_score = 30.0 + (sue_pct - 10.0) * (10.0 / 15.0)
        elif sue_pct > 0.0:
            sue_score = 15.0 + sue_pct * (15.0 / 10.0)
        elif sue_pct > -10.0:
            sue_score = 10.0
        else:
            sue_score = 0.0

        # Component B: Volume Surge Expansion (max 30 pts)
        if vol_surge_ratio >= 2.5:
            vol_score = 30.0
        elif vol_surge_ratio >= 1.5:
            vol_score = 20.0 + (vol_surge_ratio - 1.5) * 10.0
        elif vol_surge_ratio >= 1.0:
            vol_score = 10.0 + (vol_surge_ratio - 1.0) * 20.0
        else:
            vol_score = 5.0

        # Component C: Institutional Delivery Surge Signature (max 30 pts)
        if post_delivery_pct >= 60.0 or delivery_surge >= 15.0:
            del_score = 30.0
        elif post_delivery_pct >= 45.0 or delivery_surge >= 5.0:
            del_score = 20.0
        elif post_delivery_pct >= 30.0:
            del_score = 10.0
        else:
            del_score = 0.0

        total_score = round(min(100.0, max(0.0, sue_score + vol_score + del_score)), 1)

        if total_score >= 65.0:
            signal = "ACCELERATING_INSTITUTIONAL_DRIFT"
            persistence_days = 35
            summary = (
                f"{symbol.upper()} displays strong PEAD acceleration (Score: {total_score}/100) "
                f"with {sue_pct:+.1f}% earnings surprise, {vol_surge_ratio:.1f}x volume surge, "
                f"and {post_delivery_pct:.1f}% delivery accumulation signature."
            )
        elif total_score >= 40.0:
            signal = "NEUTRAL_CONSOLIDATION"
            persistence_days = 15
            summary = (
                f"{symbol.upper()} exhibits moderate post-earnings consolidation (Score: {total_score}/100). "
                f"Surprise ({sue_pct:+.1f}%) accompanied by baseline liquidity turnover."
            )
        else:
            signal = "EXHAUSTION_REVERSAL"
            persistence_days = 5
            summary = (
                f"{symbol.upper()} signals post-earnings drift exhaustion or negative drag (Score: {total_score}/100). "
                f"Subdued institutional delivery with earnings contraction ({sue_pct:+.1f}%)."
            )

        return PeadDriftVelocityResult(
            symbol=symbol.upper(),
            reported_pat_cr=round(reported_pat_cr, 2),
            consensus_or_prior_pat_cr=round(consensus_or_prior_pat_cr, 2),
            standardized_unexpected_earnings_pct=sue_pct,
            volume_surge_ratio=vol_surge_ratio,
            delivery_percentage=round(post_delivery_pct, 1),
            delivery_surge_pct=delivery_surge,
            drift_velocity_score=total_score,
            momentum_persistence_days=persistence_days,
            pead_signal=signal,
            summary=summary,
        )


# ==============================================================================
# 4. Fiduciary Governance Scoring Index
# ==============================================================================

@dataclass
class FiduciaryGovernanceResult:
    symbol: str
    fiduciary_score: float  # 0 to 100
    governance_tier: str  # "TIER_1_PRISTINE", "TIER_2_ACCEPTABLE", "TIER_3_ELEVATED_SCRUTINY", "TIER_4_RED_FLAG_DEFICIT"
    rpt_revenue_ratio_pct: float
    promoter_pledge_pct: float
    pledge_velocity_quarterly_delta: float
    board_independence_ratio_pct: float
    contingent_liabilities_to_networth_pct: float
    auditor_qualification_flag: bool
    flags: List[str] = field(default_factory=list)
    summary: str = ""


class FiduciaryGovernanceScoringIndex:
    """
    Forensic governance assessment indexing related-party transactions (RPT), promoter pledge
    velocity, board independence composition, contingent liability wedges, and statutory audit qualifications.
    """

    @classmethod
    def evaluate(
        cls,
        symbol: str,
        rpt_revenue_ratio_pct: float = 0.0,
        promoter_pledge_pct: float = 0.0,
        pledge_velocity_quarterly_delta: float = 0.0,
        board_independence_ratio_pct: float = 50.0,
        contingent_liabilities_to_networth_pct: float = 0.0,
        auditor_qualification_flag: bool = False,
    ) -> FiduciaryGovernanceResult:
        score = 100.0
        flags: List[str] = []

        # 1. Related Party Transactions (RPT)
        if rpt_revenue_ratio_pct > 25.0:
            score -= 30.0
            flags.append(f"Severe RPT exposure ({rpt_revenue_ratio_pct:.1f}% of revenue) indicates high promoter entanglement.")
        elif rpt_revenue_ratio_pct > 10.0:
            score -= 15.0
            flags.append(f"Elevated RPT transactions ({rpt_revenue_ratio_pct:.1f}% of revenue) requires close scrutiny.")

        # 2. Promoter Pledge & Pledge Velocity
        if promoter_pledge_pct > 50.0:
            score -= 35.0
            flags.append(f"Critical promoter pledge encumbrance ({promoter_pledge_pct:.1f}% of promoter holding pledged).")
        elif promoter_pledge_pct > 20.0:
            score -= 15.0
            flags.append(f"Notable promoter pledge ({promoter_pledge_pct:.1f}% encumbered).")

        if pledge_velocity_quarterly_delta > 2.0:
            score -= 10.0
            flags.append(f"Accelerating pledge velocity (+{pledge_velocity_quarterly_delta:.1f}% increase in pledged shares QoQ).")

        # 3. Board Independence
        if board_independence_ratio_pct < 33.3:
            score -= 25.0
            flags.append(f"Deficient board independence ({board_independence_ratio_pct:.1f}% independent directors vs 33.3% statutory minimum).")
        elif board_independence_ratio_pct < 50.0:
            score -= 10.0
            flags.append(f"Board independence below optimal parity ({board_independence_ratio_pct:.1f}%).")

        # 4. Contingent Liabilities
        if contingent_liabilities_to_networth_pct > 100.0:
            score -= 30.0
            flags.append(f"Outsized contingent liabilities ({contingent_liabilities_to_networth_pct:.1f}% of net worth).")
        elif contingent_liabilities_to_networth_pct > 50.0:
            score -= 15.0
            flags.append(f"High contingent claims against net worth ({contingent_liabilities_to_networth_pct:.1f}%).")

        # 5. Auditor Qualification / Adverse Remarks
        if auditor_qualification_flag:
            score -= 25.0
            flags.append("Statutory auditor filed qualifications, adverse remarks, or emphasis of matter.")

        final_score = round(max(0.0, min(100.0, score)), 1)

        if final_score >= 80.0:
            tier = "TIER_1_PRISTINE"
            summary = f"{symbol.upper()} demonstrates pristine fiduciary governance (Score: {final_score}/100) with minimal encumbrances."
        elif final_score >= 60.0:
            tier = "TIER_2_ACCEPTABLE"
            summary = f"{symbol.upper()} maintains acceptable governance compliance (Score: {final_score}/100) with minor observation points."
        elif final_score >= 40.0:
            tier = "TIER_3_ELEVATED_SCRUTINY"
            summary = f"{symbol.upper()} exhibits elevated statutory governance scrutiny (Score: {final_score}/100). Review RPT and pledge disclosures."
        else:
            tier = "TIER_4_RED_FLAG_DEFICIT"
            summary = f"{symbol.upper()} raises critical red-flag forensic deficits (Score: {final_score}/100). Fiduciary safety is compromised."

        return FiduciaryGovernanceResult(
            symbol=symbol.upper(),
            fiduciary_score=final_score,
            governance_tier=tier,
            rpt_revenue_ratio_pct=round(rpt_revenue_ratio_pct, 2),
            promoter_pledge_pct=round(promoter_pledge_pct, 2),
            pledge_velocity_quarterly_delta=round(pledge_velocity_quarterly_delta, 2),
            board_independence_ratio_pct=round(board_independence_ratio_pct, 2),
            contingent_liabilities_to_networth_pct=round(contingent_liabilities_to_networth_pct, 2),
            auditor_qualification_flag=auditor_qualification_flag,
            flags=flags,
            summary=summary,
        )


# ==============================================================================
# Unified Anvik Cortex Engine Facade
# ==============================================================================

@dataclass
class CortexCompositeEvaluation:
    symbol: str
    yield_wedge: StatutoryYieldWedgeResult
    reverse_dcf: ReverseDcfHurdleResult
    pead_drift: PeadDriftVelocityResult
    governance: FiduciaryGovernanceResult
    institutional_cortex_score: float  # 0 to 100
    conviction_quadrant: str  # "ALPHA_LEADER", "DEFENSIVE_COMPOUNDER", "SPECULATIVE_MOMENTUM", "HIGH_RISK_DEFICIT"
    executive_verdict: str


class AnvikCortexEngine:
    """
    Unified proprietary institutional intelligence engine orchestrating all four Anvik
    cortex analytical methodologies into a cohesive equity verdict.
    """

    @classmethod
    def evaluate_asset(
        cls,
        symbol: str,
        current_price: float,
        current_fcf_per_share: float,
        operating_cash_flow_cr: float,
        maintenance_capex_cr: float,
        enterprise_value_cr: float,
        reported_pat_cr: float,
        consensus_or_prior_pat_cr: float,
        post_volume: float,
        avg_50d_volume: float,
        post_delivery_pct: float,
        historical_fcf_growth_cagr_5y_pct: Optional[float] = None,
        rpt_revenue_ratio_pct: float = 0.0,
        promoter_pledge_pct: float = 0.0,
        pledge_velocity_quarterly_delta: float = 0.0,
        board_independence_ratio_pct: float = 50.0,
        contingent_liabilities_to_networth_pct: float = 0.0,
        auditor_qualification_flag: bool = False,
    ) -> CortexCompositeEvaluation:
        # Run individual models
        wedge = DynamicStatutoryYieldWedge.evaluate(
            symbol=symbol,
            operating_cash_flow_cr=operating_cash_flow_cr,
            maintenance_capex_cr=maintenance_capex_cr,
            enterprise_value_cr=enterprise_value_cr,
        )

        dcf = ReverseDcfHurdleDeconstruct.evaluate(
            symbol=symbol,
            current_price=current_price,
            current_fcf_per_share=current_fcf_per_share,
            historical_fcf_growth_cagr_5y_pct=historical_fcf_growth_cagr_5y_pct,
        )

        pead = PeadQuantDriftVelocity.evaluate(
            symbol=symbol,
            reported_pat_cr=reported_pat_cr,
            consensus_or_prior_pat_cr=consensus_or_prior_pat_cr,
            post_volume=post_volume,
            avg_50d_volume=avg_50d_volume,
            post_delivery_pct=post_delivery_pct,
        )

        gov = FiduciaryGovernanceScoringIndex.evaluate(
            symbol=symbol,
            rpt_revenue_ratio_pct=rpt_revenue_ratio_pct,
            promoter_pledge_pct=promoter_pledge_pct,
            pledge_velocity_quarterly_delta=pledge_velocity_quarterly_delta,
            board_independence_ratio_pct=board_independence_ratio_pct,
            contingent_liabilities_to_networth_pct=contingent_liabilities_to_networth_pct,
            auditor_qualification_flag=auditor_qualification_flag,
        )

        # Calculate composite institutional score (0 - 100)
        # Weights: Governance (30%), Yield Wedge (25%), DCF Hurdle (25%), PEAD (20%)
        wedge_score = 100.0 if wedge.yield_hurdle_pass else (65.0 if wedge.regime == "FAIR_VALUE_EQUILIBRIUM" else 30.0)
        dcf_score = 100.0 if dcf.hurdle_difficulty == "LOW_HURDLE" else (65.0 if dcf.hurdle_difficulty == "MODERATE_HURDLE" else 30.0)
        pead_score = pead.drift_velocity_score
        gov_score = gov.fiduciary_score

        composite = round(
            (gov_score * 0.30) + (wedge_score * 0.25) + (dcf_score * 0.25) + (pead_score * 0.20),
            1,
        )

        # Determine conviction quadrant
        if gov.governance_tier in ("TIER_3_ELEVATED_SCRUTINY", "TIER_4_RED_FLAG_DEFICIT"):
            quadrant = "HIGH_RISK_DEFICIT"
            verdict = f"Forensic governance red flags preclude institutional conviction despite operational metrics."
        elif composite >= 75.0:
            quadrant = "ALPHA_LEADER"
            verdict = f"Pristine statutory profile, superior cash generation wedge, and positive institutional drift velocity."
        elif dcf.hurdle_difficulty == "LOW_HURDLE" and wedge.yield_hurdle_pass:
            quadrant = "DEFENSIVE_COMPOUNDER"
            verdict = f"Attractive margin of safety with cash flow yields exceeding sovereign benchmark hurdle."
        elif pead.pead_signal == "ACCELERATING_INSTITUTIONAL_DRIFT":
            quadrant = "SPECULATIVE_MOMENTUM"
            verdict = f"Elevated valuation hurdles offset in the short term by strong institutional drift velocity."
        else:
            quadrant = "DEFENSIVE_COMPOUNDER"
            verdict = f"Balanced fundamentals trading near fair valuation equilibrium."

        return CortexCompositeEvaluation(
            symbol=symbol.upper(),
            yield_wedge=wedge,
            reverse_dcf=dcf,
            pead_drift=pead,
            governance=gov,
            institutional_cortex_score=composite,
            conviction_quadrant=quadrant,
            executive_verdict=verdict,
        )
