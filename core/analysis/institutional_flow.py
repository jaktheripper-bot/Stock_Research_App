"""
Institutional Flow & Market Depth Sieve
=======================================
Ingests real-time exchange Level-2 order books via Angel One SmartAPI to diagnose:
1. Institutional Accumulation vs Distribution regimes (Order Imbalance Ratio).
2. True Market Liquidity & Execution Friction (Bid-Ask Spread in Basis Points).
3. Circuit Limit Freeze Proximity (Upper & Lower Circuit Buffers).
"""

from typing import Dict, Any, List, Optional
import math
import logging

logger = logging.getLogger("equity_research.core.analysis.institutional_flow")


def _safe_float(v: Any, default: float = 0.0) -> float:
    if v is None:
        return default
    if isinstance(v, (int, float)):
        if math.isnan(v) or math.isinf(v):
            return default
        return float(v)
    try:
        clean = str(v).strip().replace(",", "").replace("%", "")
        f = float(clean)
        return default if (math.isnan(f) or math.isinf(f)) else f
    except (ValueError, TypeError):
        return default


def analyze_institutional_flow(
    quote_data: Optional[Dict[str, Any]]
) -> Dict[str, Any]:
    """
    Transforms raw Level-2 order depth data into actionable institutional flow diagnostics.
    Hardened against nulls, non-dict payloads, commas, strings, and NaN/inf numbers.
    """
    if not quote_data or not isinstance(quote_data, dict):
        return {
            "status": "UNAVAILABLE",
            "score": 50.0,
            "flow_regime": "DATA_UNAVAILABLE",
            "badge_color": "#64748b",
            "imbalance_ratio": 0.50,
            "spread_bps": 0.0,
            "circuit_status": "NORMAL_BAND",
            "lower_circuit_buffer_pct": 10.0,
            "upper_circuit_buffer_pct": 10.0,
            "narrative": "Institutional Level-2 depth unavailable outside exchange trading hours or pending feed sync.",
            "bid_book": [],
            "ask_book": [],
        }

    ltp = _safe_float(quote_data.get("ltp"))
    total_buy = _safe_float(quote_data.get("total_buy_qty"))
    total_sell = _safe_float(quote_data.get("total_sell_qty"))
    upper_circuit = _safe_float(quote_data.get("upper_circuit"))
    lower_circuit = _safe_float(quote_data.get("lower_circuit"))
    spread_bps = _safe_float(quote_data.get("bid_ask_spread_bps"))
    imbalance_ratio = max(0.0, min(1.0, _safe_float(quote_data.get("order_imbalance_ratio"), default=0.50)))
    regime = str(quote_data.get("depth_pressure_regime") or "EQUILIBRIUM")

    # Circuit limit buffer calculation
    lower_buffer_pct = 0.0
    upper_buffer_pct = 0.0
    if ltp > 0:
        if lower_circuit > 0:
            lower_buffer_pct = round(((ltp - lower_circuit) / ltp) * 100.0, 1)
        if upper_circuit > 0:
            upper_buffer_pct = round(((upper_circuit - ltp) / ltp) * 100.0, 1)

    circuit_warning = "NORMAL_BAND"
    if lower_buffer_pct > 0 and lower_buffer_pct <= 2.0:
        circuit_warning = "NEAR_LOWER_CIRCUIT_FREEZE"
    elif upper_buffer_pct > 0 and upper_buffer_pct <= 2.0:
        circuit_warning = "NEAR_UPPER_CIRCUIT_LOCK"

    # Compute 0-100 Institutional Flow Health Score
    # Neutral is 50. High accumulation pushes towards 90+. Heavy distribution pushes down.
    base_flow_score = imbalance_ratio * 70.0  # 0 to 70
    liquidity_score = 20.0 if spread_bps <= 15.0 else max(5.0, 20.0 - (spread_bps - 15.0) * 0.5)
    circuit_penalty = 15.0 if circuit_warning == "NEAR_LOWER_CIRCUIT_FREEZE" else 0.0
    
    flow_score = round(max(5.0, min(100.0, base_flow_score + liquidity_score - circuit_penalty)), 1)

    if regime == "ACCUMULATION_DOMINANT" or imbalance_ratio >= 0.65:
        flow_regime = "INSTITUTIONAL_ACCUMULATION"
        badge_color = "#10b981"
        narrative = (
            f"Strong institutional buying interest. Order imbalance of {imbalance_ratio*100:.1f}% buy-depth "
            f"indicates aggressive absorption on bid tiers."
        )
    elif regime == "DISTRIBUTION_DOMINANT" or imbalance_ratio <= 0.35:
        flow_regime = "SUPPLY_OVERHANG_DISTRIBUTION"
        badge_color = "#ef4444"
        narrative = (
            f"Distribution pressure detected. Ask side dominates with { (1.0 - imbalance_ratio)*100:.1f}% "
            f"of total 5-tier book quantity on the sell queue."
        )
    else:
        flow_regime = "ORDER_BOOK_EQUILIBRIUM"
        badge_color = "#38bdf8"
        narrative = (
            f"Balanced market depth. Buy/sell liquidity in equilibrium with a tight {spread_bps:.1f} bps spread."
        )

    if circuit_warning != "NORMAL_BAND":
        narrative += f" Warning: Stock is currently {circuit_warning.replace('_', ' ').title()}."

    return {
        "status": "LIVE",
        "score": flow_score,
        "flow_regime": flow_regime,
        "badge_color": badge_color,
        "imbalance_ratio": round(imbalance_ratio, 3),
        "spread_bps": spread_bps,
        "circuit_status": circuit_warning,
        "lower_circuit_buffer_pct": lower_buffer_pct,
        "upper_circuit_buffer_pct": upper_buffer_pct,
        "narrative": narrative,
        "bid_book": quote_data.get("depth_buy_5", []),
        "ask_book": quote_data.get("depth_sell_5", []),
        "source": quote_data.get("source", "Exchange Feed"),
    }
