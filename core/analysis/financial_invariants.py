"""Mathematical and model guardrails for Fisher real returns, convexity, Active Share, and fund coverage."""
from dataclasses import dataclass
import math
import re
from typing import Any, Dict, List, Optional, Set

RAW_ISIN_RE = re.compile(r"^[A-Z]{2}[A-Z0-9]{9}[0-9]$")


def real_return(nominal_rate: float, inflation_rate: float) -> float:
    """Fisher real return `(1 + r) / (1 + i) - 1` for DECIMAL rates (e.g. 0.05 for 5%).
    Domain: inflation_rate > -1.0. Under deflation (i < 0), real return legitimately exceeds nominal.
    Use `real_return_pct` when inputs are percentage points (e.g. 5.0, -2.0).
    """
    if isinstance(nominal_rate, bool) or isinstance(inflation_rate, bool):
        raise TypeError("rates must be numeric")
    if not (math.isfinite(nominal_rate) and math.isfinite(inflation_rate)):
        raise ValueError("rates must be finite")
    if inflation_rate <= -1.0:
        raise ValueError("inflation_rate <= -100% (-1.0 decimal) is outside the deflator domain")
    return (1.0 + nominal_rate) / (1.0 + inflation_rate) - 1.0


def real_return_pct(nominal_pct: float, inflation_pct: float) -> float:
    """Fisher real return in percentage points (e.g. nominal_pct=5.0, inflation_pct=-2.0 -> 7.1429%).
    Matches `_pct` column storage so negative CPI % (deflation) never collides with -1.0.
    """
    if isinstance(nominal_pct, bool) or isinstance(inflation_pct, bool):
        raise TypeError("rates must be numeric")
    if not (math.isfinite(nominal_pct) and math.isfinite(inflation_pct)):
        raise ValueError("rates must be finite")
    if inflation_pct <= -100.0:
        raise ValueError("inflation_pct <= -100.0% is outside the deflator domain")
    return round(real_return(nominal_pct / 100.0, inflation_pct / 100.0) * 100.0, 4)


def requires_positive_convexity(
    *, is_option_free: bool, is_perpetual: bool = False, has_floating_reset: bool = False,
) -> bool:
    """Positive convexity invariant applies only to option-free fixed-cash-flow instruments."""
    return bool(is_option_free and not is_perpetual and not has_floating_reset)


@dataclass(frozen=True)
class ActiveShareResult:
    active_share_pct: Optional[float]
    is_estimate: bool
    unmatched_weight_pct: float
    methodology_label: str


def compute_active_share(
    fund_weights_pct: Dict[str, float],
    benchmark_weights_pct: Dict[str, float],
    *,
    is_proxy_benchmark: bool = False,
    same_disclosure_date: bool = True,
) -> ActiveShareResult:
    """Compute Active Share = 0.5 * sum(|w_fund - w_bench|) over normalized equity weights."""
    f_clean = {
        k: float(v) for k, v in fund_weights_pct.items()
        if not isinstance(v, bool) and math.isfinite(float(v)) and float(v) > 0
    }
    b_clean = {
        k: float(v) for k, v in benchmark_weights_pct.items()
        if not isinstance(v, bool) and math.isfinite(float(v)) and float(v) > 0
    }
    f_sum = sum(f_clean.values())
    b_sum = sum(b_clean.values())
    if f_sum <= 0 or b_sum <= 0:
        return ActiveShareResult(None, True, 100.0, "unavailable: empty portfolio or benchmark")
    f_norm = {k: (v / f_sum) * 100.0 for k, v in f_clean.items()}
    b_norm = {k: (v / b_sum) * 100.0 for k, v in b_clean.items()}
    universe = set(f_norm) | set(b_norm)
    diff_sum = sum(abs(f_norm.get(k, 0.0) - b_norm.get(k, 0.0)) for k in universe)
    active_share = round(min(100.0, max(0.0, 0.5 * diff_sum)), 2)
    unmatched = round(sum(v for k, v in f_norm.items() if k not in b_norm), 2)
    is_est = bool(is_proxy_benchmark or not same_disclosure_date)
    label = "proxy/date-mismatched estimate" if is_est else "disclosed benchmark active share"
    return ActiveShareResult(active_share, is_est, unmatched, label)


@dataclass(frozen=True)
class FundCoverageSummary:
    eligible_equity_pct: float           # Covered weight as % of total disclosed equity sleeve
    full_nav_eligible_pct: float         # Covered weight as % of total scheme NAV (100% basis)
    disclosed_holdings_sum_pct: float    # Sum of disclosed positive holding weights (% of NAV)
    domestic_equity_nav_pct: float       # Synthesizable Indian NSE/BSE equity weight (% of NAV)
    foreign_equity_nav_pct: float        # Foreign equity weight (% of NAV; excluded from NSE synthesis)
    unresolved_isin_nav_pct: float       # Unmapped raw ISIN equity weight (% of NAV)
    uncovered_equity_pct: float          # Uncovered % of total equity sleeve
    max_single_uncovered_pct: float      # Largest single uncovered equity holding (% of NAV)
    meets_aggregate_gate: bool           # True iff eligible_equity_pct >= threshold AND max_uncov < 10%


KNOWN_FOREIGN_EQUITY_TICKERS = frozenset({
    "GOOGL", "GOOG", "META", "MSFT", "AMZN", "AAPL", "NVDA", "TSLA", "NFLX", "AVGO", "ASML", "TSM",
})


def is_synthesizable_domestic_ticker(
    identifier: Optional[str], holding_type: Optional[str] = "EQUITY",
) -> bool:
    """True only when holding is domestic Indian EQUITY with a resolved exchange ticker (not raw ISIN or foreign)."""
    htype = str(holding_type or "").strip().upper()
    ident = str(identifier or "").strip().upper()
    if htype != "EQUITY" or not ident:
        return False
    if RAW_ISIN_RE.match(ident) or ident in KNOWN_FOREIGN_EQUITY_TICKERS:
        return False
    return True


def evaluate_fund_coverage(
    holdings: List[Dict[str, Any]],
    eligible_tickers: Set[str],
    *,
    threshold_pct: float = 70.0,
    weights_are_pct_of_nav: bool = True,
) -> FundCoverageSummary:
    """Report both equity-sleeve and true full-NAV denominators plus uncovered concentration."""
    normalized_eligible = {str(t).strip().upper() for t in eligible_tickers if str(t).strip()}
    positive_rows = []
    for h in holdings:
        raw_w = h.get("weight_pct", 0.0)
        if isinstance(raw_w, bool):
            continue
        w = float(raw_w or 0.0)
        if math.isfinite(w) and w > 0:
            positive_rows.append((h, w))

    disclosed_sum = sum(w for _, w in positive_rows)
    if not weights_are_pct_of_nav and disclosed_sum > 0:
        scale = 100.0 / disclosed_sum
        positive_rows = [(h, w * scale) for h, w in positive_rows]
        disclosed_sum = 100.0

    eq_rows = []
    domestic_nav = 0.0
    foreign_nav = 0.0
    unresolved_isin_nav = 0.0
    for h, w in positive_rows:
        htype = str(h.get("holding_type", "")).strip().upper()
        ident = str(h.get("identifier", "")).strip().upper()
        if htype in ("EQUITY", "FOREIGN_EQUITY", "RAW_ISIN_EQUITY"):
            eq_rows.append((ident, htype, w))
            if htype == "FOREIGN_EQUITY":
                foreign_nav += w
            elif not ident or RAW_ISIN_RE.match(ident) or htype == "RAW_ISIN_EQUITY":
                unresolved_isin_nav += w
            else:
                domestic_nav += w

    eq_total_nav = sum(w for _, _, w in eq_rows)
    eq_cov_nav = sum(
        w for ident, htype, w in eq_rows
        if htype == "EQUITY" and ident and not RAW_ISIN_RE.match(ident) and ident in normalized_eligible
    )
    uncovered_weights = [
        w for ident, htype, w in eq_rows
        if not (htype == "EQUITY" and ident and not RAW_ISIN_RE.match(ident) and ident in normalized_eligible)
    ]

    elig_eq_pct = round((eq_cov_nav / eq_total_nav) * 100.0, 2) if eq_total_nav > 0 else 0.0
    full_nav_pct = round(min(100.0, eq_cov_nav), 2)
    max_uncov = round(max(uncovered_weights, default=0.0), 2)
    gate = eq_total_nav > 0 and elig_eq_pct >= threshold_pct and max_uncov < 10.0
    return FundCoverageSummary(
        eligible_equity_pct=elig_eq_pct,
        full_nav_eligible_pct=full_nav_pct,
        disclosed_holdings_sum_pct=round(disclosed_sum, 2),
        domestic_equity_nav_pct=round(domestic_nav, 2),
        foreign_equity_nav_pct=round(foreign_nav, 2),
        unresolved_isin_nav_pct=round(unresolved_isin_nav, 2),
        uncovered_equity_pct=round(max(0.0, 100.0 - elig_eq_pct), 2) if eq_total_nav > 0 else 0.0,
        max_single_uncovered_pct=max_uncov,
        meets_aggregate_gate=gate,
    )
