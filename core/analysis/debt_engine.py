"""Institutional 5-Pillar Credit & Solvency Core Engine for Debt, NCDs, and SDIs.

Implements rigorous fixed-income mathematics:
- Cash flow projection by coupon frequency
- Precise Yield-to-Maturity (YTM) solver
- Macaulay Duration, Modified Duration, and Convexity
- Rate shock price sensitivity modeling (delta P / P)
- 5-Pillar Credit & Solvency Matrix (Rating Drift, Seniority/ACR, ICR/DSCR, Duration, Recovery/SDI FLDG)

Complies with SEBI (Issue and Listing of Non-Convertible Securities) Regulations.
"""

import math
import logging
from datetime import datetime, date
from typing import Dict, Any, List, Optional, Tuple

logger = logging.getLogger(__name__)

# Benchmark 10-Year Government of India (G-Sec) sovereign yield reference
DEFAULT_BENCHMARK_10Y_GSEC_YIELD = 7.10  # 7.10%

# Standardized Credit Rating Agency Score Weights (0 to 100)
RATING_SCORES = {
    "AAA": 100.0,
    "AA+": 88.0,
    "AA": 78.0,
    "AA-": 68.0,
    "A+": 55.0,
    "A": 45.0,
    "A-": 35.0,
    "BBB+": 25.0,
    "BBB": 20.0,
    "BBB-": 15.0,
    "BB": 5.0,
    "D": 0.0
}

# Frequency to periods per year
FREQUENCY_PERIODS = {
    "ANNUAL": 1,
    "SEMI_ANNUAL": 2,
    "QUARTERLY": 4,
    "MONTHLY": 12,
    "CUMULATIVE": 1
}


# ==============================================================================
# 1. Fixed-Income Mathematical Core
# ==============================================================================

def calculate_time_to_maturity_years(maturity_date_str: str, from_date: Optional[date] = None) -> float:
    """Calculates exact fractional years from reference date to maturity date."""
    if not from_date:
        from_date = date.today()
    if isinstance(maturity_date_str, str):
        # Handle formats 'YYYY-MM-DD' or 'YYYY-MM-DDTHH:MM:SS'
        clean_str = maturity_date_str[:10]
        mat_dt = datetime.strptime(clean_str, "%Y-%m-%d").date()
    elif isinstance(maturity_date_str, (date, datetime)):
        mat_dt = maturity_date_str if isinstance(maturity_date_str, date) else maturity_date_str.date()
    else:
        return 1.0

    delta_days = (mat_dt - from_date).days
    if delta_days <= 0:
        return 0.01  # Minimum floor for matured or maturing debt
    return round(delta_days / 365.25, 4)


def generate_cash_flows(
    face_value: float,
    coupon_rate_pct: float,
    coupon_frequency: str,
    time_to_maturity_years: float
) -> List[Tuple[float, float]]:
    """
    Generates scheduled cash flows as list of (time_in_years, cash_flow_amount).
    """
    k = FREQUENCY_PERIODS.get(coupon_frequency.upper(), 1)
    coupon_per_period = (face_value * (coupon_rate_pct / 100.0)) / k

    cash_flows = []
    total_periods = max(1, int(math.ceil(time_to_maturity_years * k)))
    period_length = 1.0 / k

    for p in range(1, total_periods + 1):
        t = round(p * period_length, 4)
        if t > time_to_maturity_years:
            t = time_to_maturity_years

        if p == total_periods:
            # Final period includes principal redemption
            cash_flows.append((t, coupon_per_period + face_value))
        else:
            cash_flows.append((t, coupon_per_period))

    return cash_flows


def solve_ytm(
    current_price: float,
    face_value: float,
    coupon_rate_pct: float,
    coupon_frequency: str,
    time_to_maturity_years: float,
    max_iter: int = 100,
    tol: float = 1e-6
) -> float:
    """
    Solves for Yield to Maturity (annualized %) using the Newton-Raphson method with bisection fallback.
    """
    if time_to_maturity_years <= 0 or current_price <= 0:
        return coupon_rate_pct

    cash_flows = generate_cash_flows(face_value, coupon_rate_pct, coupon_frequency, time_to_maturity_years)
    k = FREQUENCY_PERIODS.get(coupon_frequency.upper(), 1)

    # Initial guess
    y = max(0.001, coupon_rate_pct / 100.0)

    for _ in range(max_iter):
        pv = 0.0
        dpv = 0.0  # derivative w.r.t yield

        for t, cf in cash_flows:
            discount = (1.0 + y / k) ** (k * t)
            pv += cf / discount
            dpv += -t * cf / (discount * (1.0 + y / k))

        diff = pv - current_price
        if abs(diff) < tol:
            return round(y * 100.0, 2)

        if abs(dpv) < 1e-12:
            break

        y_next = y - diff / dpv
        if y_next <= -0.5:
            y_next = y / 2.0
        y = y_next

    # Bisection fallback if Newton didn't converge
    low, high = 0.0001, 1.0
    for _ in range(100):
        mid = (low + high) / 2.0
        pv = sum(cf / ((1.0 + mid / k) ** (k * t)) for t, cf in cash_flows)
        if abs(pv - current_price) < 0.01:
            return round(mid * 100.0, 2)
        if pv > current_price:
            low = mid
        else:
            high = mid

    return round(y * 100.0, 2)


def compute_duration_and_convexity(
    current_price: float,
    face_value: float,
    coupon_rate_pct: float,
    coupon_frequency: str,
    time_to_maturity_years: float,
    ytm_pct: float
) -> Dict[str, float]:
    """
    Computes Macaulay Duration, Modified Duration, and Convexity.
    """
    if current_price <= 0 or time_to_maturity_years <= 0:
        return {"macaulay_duration": 0.0, "modified_duration": 0.0, "convexity": 0.0}

    cash_flows = generate_cash_flows(face_value, coupon_rate_pct, coupon_frequency, time_to_maturity_years)
    k = FREQUENCY_PERIODS.get(coupon_frequency.upper(), 1)
    y = max(0.0001, ytm_pct / 100.0)

    weighted_time_sum = 0.0
    convexity_sum = 0.0

    for t, cf in cash_flows:
        pv_cf = cf / ((1.0 + y / k) ** (k * t))
        weighted_time_sum += t * pv_cf
        convexity_sum += pv_cf * (t ** 2 + t / k)

    macaulay_duration = weighted_time_sum / current_price
    modified_duration = macaulay_duration / (1.0 + y / k)
    convexity = convexity_sum / (current_price * ((1.0 + y / k) ** 2))

    return {
        "macaulay_duration": round(macaulay_duration, 2),
        "modified_duration": round(modified_duration, 2),
        "convexity": round(convexity, 2)
    }


def compute_rate_shock_scenarios(
    current_price: float,
    modified_duration: float,
    convexity: float,
    rate_shifts_bps: Optional[List[int]] = None
) -> List[Dict[str, Any]]:
    """
    Simulates bond price and percentage change under arbitrary RBI rate shock scenarios.
    Using Taylor expansion: delta P / P ≈ -D_mod * delta_y + 0.5 * C * (delta_y)^2
    """
    if rate_shifts_bps is None:
        rate_shifts_bps = [-100, -50, -25, 0, 25, 50, 100, 200]

    scenarios = []
    for bps in rate_shifts_bps:
        dy = bps / 10000.0  # 1 bps = 0.0001
        pct_change = (-modified_duration * dy + 0.5 * convexity * (dy ** 2)) * 100.0
        new_price = current_price * (1.0 + pct_change / 100.0)
        scenarios.append({
            "rate_shift_bps": bps,
            "rate_shift_label": f"{'+' if bps > 0 else ''}{bps / 100.0:+.2f}%",
            "pct_price_change": round(pct_change, 2),
            "estimated_price": round(new_price, 2)
        })

    return scenarios


# ==============================================================================
# 2. 5-Pillar Credit & Solvency Matrix Core
# ==============================================================================

def extract_base_rating_symbol(raw_rating: str) -> str:
    """Normalizes agency-prefixed rating (e.g., 'CRISIL AAA' -> 'AAA', 'ICRA AA+' -> 'AA+')."""
    clean = str(raw_rating).upper().strip()
    for prefix in ["CRISIL", "ICRA", "CARE", "IND", "ACUITE", "BWR"]:
        clean = clean.replace(prefix, "").strip()
    return clean or "BBB"


def evaluate_pillar_1_credit_quality(
    credit_rating: str,
    rating_history: Optional[List[Dict[str, Any]]] = None,
    ytm_pct: float = 8.0,
    benchmark_yield: float = DEFAULT_BENCHMARK_10Y_GSEC_YIELD
) -> Dict[str, Any]:
    """Pillar 1: Credit Agency Rating, Trajectory Drift, and G-Sec Spread."""
    base_symbol = extract_base_rating_symbol(credit_rating)
    base_score = RATING_SCORES.get(base_symbol, 20.0)

    # 1. Rating Drift over historical events
    trajectory_score = 0
    drift_label = "STABLE"
    recent_actions = rating_history or []
    if recent_actions:
        latest = recent_actions[0]
        act_type = latest.get("action_type", "").upper()
        outlook = latest.get("outlook", "").upper()
        if "UPGRADE" in act_type:
            trajectory_score = 10
            drift_label = "UPGRADE_MOMENTUM"
        elif "DOWNGRADE" in act_type:
            trajectory_score = -25
            drift_label = "DOWNGRADE_STRESS"
        elif "WATCH_NEGATIVE" in outlook or "NEGATIVE" in outlook:
            trajectory_score = -15
            drift_label = "NEGATIVE_OUTLOOK"
        elif "POSITIVE" in outlook:
            trajectory_score = 5
            drift_label = "POSITIVE_OUTLOOK"

    score_p1 = max(0.0, min(100.0, base_score + trajectory_score))

    # 2. Credit spread over sovereign benchmark
    credit_spread_bps = round((ytm_pct - benchmark_yield) * 100.0, 0)
    spread_warning = None
    if base_symbol not in ["AAA", "AA+"] and credit_spread_bps < 75:
        spread_warning = "Uncompensated Credit Risk: Yield spread over 10Y G-Sec is dangerously thin (<75 bps) for non-AAA credit."
    elif credit_spread_bps > 500:
        spread_warning = "Distressed Credit Alert: Yield spread >500 bps suggests severe market solvency skepticism."

    return {
        "pillar": "Pillar 1: Credit Quality & Rating Drift",
        "score": round(score_p1, 1),
        "credit_rating": credit_rating,
        "base_symbol": base_symbol,
        "drift_status": drift_label,
        "credit_spread_bps": credit_spread_bps,
        "benchmark_10y_gsec": benchmark_yield,
        "warning": spread_warning,
        "is_investment_grade": base_symbol in ["AAA", "AA+", "AA", "AA-", "A+", "A", "BBB+", "BBB"]
    }


def evaluate_pillar_2_capital_hierarchy(
    seniority_tier: str,
    asset_cover_ratio: float = 1.25,
    is_sdi: bool = False
) -> Dict[str, Any]:
    """Pillar 2: Seniority Waterfall, Loss Absorption & Asset Cover Ratio (ACR)."""
    tier = seniority_tier.upper().strip()
    critical_warning = None

    if tier == "SENIOR_SECURED":
        tier_score = 100.0
        hierarchy_label = "Senior Secured (First Charge on Tangible Assets)"
    elif tier == "SENIOR_UNSECURED":
        tier_score = 75.0
        hierarchy_label = "Senior Unsecured (General Corporate Claim)"
    elif tier in ["SUBORDINATED_TIER_2", "TIER_2"]:
        tier_score = 45.0
        hierarchy_label = "Subordinated Tier-II (Subordinate to Depositors and Senior Debt)"
    elif tier in ["PERPETUAL_AT1", "AT1"]:
        tier_score = 10.0
        hierarchy_label = "Perpetual Additional Tier-1 (AT1) Capital"
        critical_warning = (
            "CRITICAL REGULATORY ALERT: Perpetual Additional Tier-1 (AT1) instrument. "
            "Subject to permanent contractual principal write-down or equity conversion at the Point of Non-Viability (PONV) "
            "under RBI Basel III guidelines without unitholder or equity shareholder approval (e.g., Yes Bank AT1 write-off)."
        )
    else:
        tier_score = 50.0
        hierarchy_label = "Standard Subordinated Debt"

    # ACR covenant evaluation
    covenant_breach = False
    if tier == "SENIOR_SECURED":
        if asset_cover_ratio < 1.0:
            covenant_breach = True
            tier_score = max(0.0, tier_score - 40.0)
            acr_status = f"CRITICAL BREACH: ACR {asset_cover_ratio:.2f}x is below 1.00x par cover."
        elif asset_cover_ratio < 1.25:
            tier_score -= 15.0
            acr_status = f"Marginal Coverage: ACR {asset_cover_ratio:.2f}x is below standard 1.25x covenant benchmark."
        else:
            acr_status = f"Robust Coverage: ACR {asset_cover_ratio:.2f}x provides substantial asset cushion."
    else:
        acr_status = "N/A (Unsecured / Subordinated Debt)"

    return {
        "pillar": "Pillar 2: Capital Hierarchy & Seniority Cover",
        "score": round(tier_score, 1),
        "seniority_tier": tier,
        "hierarchy_label": hierarchy_label,
        "asset_cover_ratio": asset_cover_ratio,
        "acr_status": acr_status,
        "covenant_breach": covenant_breach,
        "critical_warning": critical_warning
    }


def evaluate_pillar_3_cash_flow_solvency(
    issuer_fundamentals: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """Pillar 3: Interest Coverage (ICR), DSCR, and Net Debt to EBITDA."""
    fund = issuer_fundamentals or {}

    # Extract or estimate key credit solvency ratios
    icr = fund.get("interest_coverage") or fund.get("icr")
    dscr = fund.get("dscr")
    net_debt_to_ebitda = fund.get("net_debt_to_ebitda") or fund.get("debt_to_equity")

    score = 75.0  # neutral benchmark if missing
    notes = []

    if icr is not None:
        try:
            icr_val = float(icr)
            if icr_val >= 3.5:
                score += 15.0
                notes.append(f"Strong ICR ({icr_val:.1f}x): EBIT comfortably covers debt interest expense.")
            elif icr_val < 1.5:
                score -= 35.0
                notes.append(f"Distressed ICR ({icr_val:.1f}x): Cash flow dangerously insufficient to service interest.")
            elif icr_val < 2.0:
                score -= 15.0
                notes.append(f"Tight ICR ({icr_val:.1f}x): Narrow margin of safety against revenue declines.")
        except Exception:
            pass

    if dscr is not None:
        try:
            dscr_val = float(dscr)
            if dscr_val >= 1.30:
                score += 10.0
            elif dscr_val < 1.10:
                score -= 20.0
                notes.append(f"Weak DSCR ({dscr_val:.2f}x): Principal repayment shortfall risk.")
        except Exception:
            pass

    score = max(0.0, min(100.0, score))

    return {
        "pillar": "Pillar 3: Cash Flow Solvency & Coverage",
        "score": round(score, 1),
        "interest_coverage_ratio": icr,
        "debt_service_coverage_ratio": dscr,
        "net_debt_to_ebitda": net_debt_to_ebitda,
        "notes": notes
    }


def evaluate_pillar_4_duration_risk(
    macaulay_duration_years: float,
    modified_duration_years: float,
    time_to_maturity_years: float
) -> Dict[str, Any]:
    """Pillar 4: Macaulay Duration, Modified Duration & Rate Sensitivity."""
    mod_dur = modified_duration_years

    if mod_dur <= 1.0:
        duration_posture = "ULTRA_LOW_DURATION"
        duration_desc = "Minimal interest rate sensitivity. Capital insulated from RBI repo rate hikes."
        score = 95.0
    elif mod_dur <= 2.5:
        duration_posture = "SHORT_TO_MEDIUM_DURATION"
        duration_desc = "Optimal balance of yield vs. moderate interest rate sensitivity."
        score = 85.0
    elif mod_dur <= 4.5:
        duration_posture = "MEDIUM_DURATION"
        duration_desc = "Noticeable capital sensitivity to monetary policy rate shifts."
        score = 65.0
    else:
        duration_posture = "LONG_DURATION"
        duration_desc = "High interest rate risk. Significant capital drawdown if sovereign yields rise."
        score = 45.0

    return {
        "pillar": "Pillar 4: Duration & Interest Rate Sensitivity",
        "score": round(score, 1),
        "macaulay_duration_years": round(macaulay_duration_years, 2),
        "modified_duration_years": round(modified_duration_years, 2),
        "time_to_maturity_years": round(time_to_maturity_years, 2),
        "duration_posture": duration_posture,
        "description": duration_desc
    }


def evaluate_pillar_5_recovery_and_pool_quality(
    is_sdi: bool = False,
    fldg_pct: float = 0.0,
    originator: Optional[str] = None,
    exchange: str = "BSE",
    seniority_tier: str = "SENIOR_SECURED"
) -> Dict[str, Any]:
    """Pillar 5: Recovery Reality, Exchange RFQ Liquidity, and SDI Pool Buffers."""
    score = 75.0
    sdi_details = {}

    if is_sdi:
        # Securitized Debt Instrument pool evaluation
        if fldg_pct >= 5.0:
            score += 15.0
            fldg_status = f"Strong Credit Enhancement: First Loss Default Guarantee (FLDG) of {fldg_pct:.1f}% absorbs initial pool defaults."
        elif fldg_pct > 0.0:
            fldg_status = f"Moderate Credit Enhancement: FLDG of {fldg_pct:.1f}%."
        else:
            score -= 20.0
            fldg_status = "Zero FLDG Buffer: Investors fully exposed to underlying borrower pool default rate."

        sdi_details = {
            "originator": originator or "Licensed NBFC Originator",
            "fldg_pct": fldg_pct,
            "fldg_status": fldg_status,
            "clearing_house": "NSCCL / ICCL (Direct Demat Credit)",
            "bankruptcy_remoteness": "Held in SPV Trust (Insulated from Originator Bankruptcy)"
        }
    else:
        # Corporate Bond recovery profile
        if seniority_tier == "SENIOR_SECURED":
            recovery_desc = "High historical IBC recovery expectation due to registered first charge on physical collateral."
        else:
            recovery_desc = "Unsecured/subordinated status implies substantial haircut under IBC liquidation."

        sdi_details = {
            "exchange": exchange,
            "trading_mechanism": "Exchange RFQ Platform (Settled via Clearing Corporation)",
            "recovery_expectation": recovery_desc
        }

    return {
        "pillar": "Pillar 5: Recovery Reality & Securitization Pool Quality",
        "score": round(min(100.0, max(0.0, score)), 1),
        "is_sdi": is_sdi,
        "details": sdi_details
    }


def evaluate_5_pillar_credit_posture(
    security: Dict[str, Any],
    rating_history: Optional[List[Dict[str, Any]]] = None,
    issuer_fundamentals: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Synthesizes the complete 5-Pillar Credit & Solvency Matrix for a Corporate Bond or SDI.
    """
    isin = security.get("isin", "").upper()
    face_val = float(security.get("face_value", 10000.0))
    coupon = float(security.get("coupon_rate_pct", 8.0))
    freq = security.get("coupon_frequency", "ANNUAL")
    mat_date = security.get("maturity_date", "2028-12-31")
    price = float(security.get("last_traded_price", face_val))

    # Time to maturity
    ttm = calculate_time_to_maturity_years(mat_date)

    # Solve YTM
    ytm = float(security.get("ytm_pct") or solve_ytm(price, face_val, coupon, freq, ttm))

    # Duration & Convexity
    dur_dict = compute_duration_and_convexity(price, face_val, coupon, freq, ttm, ytm)
    m_dur = dur_dict["macaulay_duration"]
    mod_dur = dur_dict["modified_duration"]
    cvx = dur_dict["convexity"]

    # Rate shock sensitivity scenarios
    rate_shocks = compute_rate_shock_scenarios(price, mod_dur, cvx)

    # Evaluate 5 Pillars
    p1 = evaluate_pillar_1_credit_quality(
        security.get("credit_rating", "AAA"),
        rating_history,
        ytm
    )
    p2 = evaluate_pillar_2_capital_hierarchy(
        security.get("seniority_tier", "SENIOR_SECURED"),
        float(security.get("asset_cover_ratio", 1.25)),
        bool(security.get("is_sdi", False))
    )
    p3 = evaluate_pillar_3_cash_flow_solvency(issuer_fundamentals)
    p4 = evaluate_pillar_4_duration_risk(m_dur, mod_dur, ttm)
    p5 = evaluate_pillar_5_recovery_and_pool_quality(
        bool(security.get("is_sdi", False)),
        float(security.get("fldg_pct", 0.0)),
        security.get("originator"),
        security.get("exchange", "BSE"),
        security.get("seniority_tier", "SENIOR_SECURED")
    )

    # Weighted Composite Credit Score (P1: 30%, P2: 25%, P3: 20%, P4: 15%, P5: 10%)
    composite_score = round(
        p1["score"] * 0.30 +
        p2["score"] * 0.25 +
        p3["score"] * 0.20 +
        p4["score"] * 0.15 +
        p5["score"] * 0.10,
        1
    )

    # Composite Posture Classification
    if composite_score >= 82.0:
        posture = "INSTITUTIONAL_PRIME"
        posture_badge = "Institutional Prime (Highest Capital Safety)"
        badge_color = "#10b981"  # Emerald
    elif composite_score >= 65.0:
        posture = "INVESTMENT_GRADE"
        posture_badge = "Investment Grade (Solid Compounding)"
        badge_color = "#3b82f6"  # Blue
    elif composite_score >= 45.0:
        posture = "SPECULATIVE_YIELD"
        posture_badge = "Speculative Yield (Higher Volatility / Spread)"
        badge_color = "#f59e0b"  # Amber
    else:
        posture = "DISTRESSED_VULNERABLE"
        posture_badge = "Distressed / High Solvency Risk"
        badge_color = "#ef4444"  # Red

    # Collect all flags & warnings
    warnings = []
    if p2.get("critical_warning"):
        warnings.append(p2["critical_warning"])
    if p1.get("warning"):
        warnings.append(p1["warning"])
    if p2.get("covenant_breach"):
        warnings.append(p2["acr_status"])
    for note in p3.get("notes", []):
        if "Distressed" in note or "Tight" in note or "Weak" in note:
            warnings.append(note)

    return {
        "isin": isin,
        "instrument_name": security.get("instrument_name", ""),
        "ticker": security.get("ticker", ""),
        "seniority_tier": security.get("seniority_tier", ""),
        "credit_rating": security.get("credit_rating", ""),
        "face_value": face_val,
        "last_traded_price": price,
        "coupon_rate_pct": coupon,
        "coupon_frequency": freq,
        "ytm_pct": ytm,
        "time_to_maturity_years": ttm,
        "macaulay_duration_years": m_dur,
        "modified_duration_years": mod_dur,
        "convexity": cvx,
        "composite_score": composite_score,
        "posture": posture,
        "posture_badge": posture_badge,
        "badge_color": badge_color,
        "rate_shock_scenarios": rate_shocks,
        "warnings": warnings,
        "pillars": {
            "p1_credit_quality": p1,
            "p2_capital_hierarchy": p2,
            "p3_solvency": p3,
            "p4_duration": p4,
            "p5_recovery": p5
        }
    }
