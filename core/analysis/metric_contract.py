"""Shared metric and research provenance contract.

Keeps evidence kind, freshness, and access independent; never coerces null to 0;
blocks internal vendor names from leaking onto public source references; and
neutralizes spreadsheet formula prefixes without corrupting negative numbers.
"""
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from enum import Enum
import math
import re
from typing import Optional, Tuple, Union


class EvidenceKind(str, Enum):
    REPORTED = "reported"        # Disclosed observation from source filing/feed
    CALCULATED = "calculated"    # Deterministic output from disclosed inputs
    SCENARIO = "scenario"        # Conditional/assumed projection
    UNAVAILABLE = "unavailable"  # Missing or unverified evidence


class FreshnessStatus(str, Enum):
    AVAILABLE = "available"      # Within MEASURE_MAX_AGE display window
    STALE = "stale"              # Dated observation outside display window (historical)
    UNAVAILABLE = "unavailable"  # No usable observation


class AccessState(str, Enum):
    PUBLIC = "public"
    LOCKED = "locked"            # Entitled research exists; payload gated
    ENTITLED = "entitled"        # Unlocked for current owner


MEASURE_MAX_AGE_DAYS = {
    "CONTRACTUAL_YTM": 7,
    "CONTRACTUAL_COUPON_ON_ISSUE": 7,
    "AUCTION_CUTOFF_YIELD": 45,
    "DISTRIBUTION_YIELD_TTM": 7,
    "HISTORICAL_CAGR_3Y": 45,
    "EARNINGS_YIELD_TTM": 7,
    "DIVIDEND_YIELD_TTM": 7,
}

FORBIDDEN_PUBLIC_VENDOR_TOKENS = (
    "yfinance",
    "yahoo",
    "mfapi",
    "mfforecast",
    "smartapi",
    "angelone",
    "vertexaisearch",
    "morningstar",
    "screener.in",
    "trendlyne",
    "tickertape",
    "valueresearch",
    "moneycontrol",
)


def has_forbidden_vendor_token(source_ref: Optional[str]) -> bool:
    """Return True if a source string leaks an internal scraper/vendor identifier."""
    if not source_ref:
        return False
    lowered = source_ref.lower()
    return any(tok in lowered for tok in FORBIDDEN_PUBLIC_VENDOR_TOKENS)


@dataclass(frozen=True)
class MetricContract:
    instrument_id: str
    measure_type: str
    value: Optional[float]
    unit: str
    evidence_kind: EvidenceKind
    freshness: FreshnessStatus
    access: AccessState = AccessState.PUBLIC
    period: Optional[str] = None
    observation_date: Optional[str] = None
    publication_date: Optional[str] = None
    retrieval_date: Optional[str] = None
    source_ref: Optional[str] = None
    methodology_version: Optional[str] = None
    snapshot_id: Optional[str] = None
    run_id: Optional[str] = None
    coverage_eligible_pct: Optional[float] = None
    coverage_full_nav_pct: Optional[float] = None
    limitations: Optional[str] = None
    unavailable_reason: Optional[str] = None

    def __post_init__(self) -> None:
        if isinstance(self.value, bool) or (self.value is not None and not math.isfinite(self.value)):
            raise ValueError("value must be a finite float or None")
        if (self.value is None) != (self.freshness is FreshnessStatus.UNAVAILABLE):
            raise ValueError("value must be None iff freshness is UNAVAILABLE")
        if (self.value is None) != (self.evidence_kind is EvidenceKind.UNAVAILABLE):
            raise ValueError("evidence_kind must be UNAVAILABLE iff value is None")
        if self.value is not None:
            if not self.observation_date or not self.source_ref:
                raise ValueError("available/stale observations require observation_date and source_ref")
            if has_forbidden_vendor_token(self.source_ref):
                raise ValueError(f"source_ref leaks internal vendor identifier: {self.source_ref!r}")
            date.fromisoformat(self.observation_date)
        if self.access is AccessState.LOCKED and self.freshness is FreshnessStatus.UNAVAILABLE:
            raise ValueError("cannot lock an unavailable metric (never sell access to missing evidence)")

    @property
    def current_value(self) -> Optional[float]:
        return self.value if self.freshness is FreshnessStatus.AVAILABLE else None

    @property
    def historical_value(self) -> Optional[float]:
        return self.value if self.freshness is FreshnessStatus.STALE else None

    def display(self) -> str:
        if self.freshness is FreshnessStatus.UNAVAILABLE or self.value is None:
            return f"Unavailable ({self.unavailable_reason or 'missing source evidence'})"
        formatted = f"{self.value:.2f}{self.unit}" if self.unit == "%" else f"{self.value:g}{self.unit}"
        if self.freshness is FreshnessStatus.STALE:
            return f"{formatted} (historical, as of {self.observation_date})"
        return formatted


def build_observed_metric(
    instrument_id: str,
    measure_type: str,
    raw_value: object,
    unit: str,
    observation_date: Optional[str],
    source_ref: Optional[str],
    *,
    today: date,
    evidence_kind: EvidenceKind = EvidenceKind.REPORTED,
    methodology_version: str = "terminal-v2",
    unavailable_reason: str = "no verified source observation",
) -> MetricContract:
    if isinstance(raw_value, bool) or not isinstance(raw_value, (int, float, Decimal)):
        return MetricContract(
            instrument_id=instrument_id, measure_type=measure_type, value=None, unit=unit,
            evidence_kind=EvidenceKind.UNAVAILABLE, freshness=FreshnessStatus.UNAVAILABLE,
            methodology_version=methodology_version, unavailable_reason=unavailable_reason,
        )
    numeric_val = float(raw_value)
    if not math.isfinite(numeric_val):
        return MetricContract(
            instrument_id=instrument_id, measure_type=measure_type, value=None, unit=unit,
            evidence_kind=EvidenceKind.UNAVAILABLE, freshness=FreshnessStatus.UNAVAILABLE,
            methodology_version=methodology_version, unavailable_reason=unavailable_reason,
        )
    try:
        obs_dt = date.fromisoformat(str(observation_date))
    except ValueError:
        obs_dt = None
    src = (source_ref or "").strip()
    if has_forbidden_vendor_token(src):
        return MetricContract(
            instrument_id=instrument_id, measure_type=measure_type, value=None, unit=unit,
            evidence_kind=EvidenceKind.UNAVAILABLE, freshness=FreshnessStatus.UNAVAILABLE,
            methodology_version=methodology_version,
            unavailable_reason="unverified or internal vendor source reference",
        )
    max_age = MEASURE_MAX_AGE_DAYS.get(measure_type)
    if obs_dt is None or not src or max_age is None or (today - obs_dt).days < 0:
        return MetricContract(
            instrument_id=instrument_id, measure_type=measure_type, value=None, unit=unit,
            evidence_kind=EvidenceKind.UNAVAILABLE, freshness=FreshnessStatus.UNAVAILABLE,
            methodology_version=methodology_version, unavailable_reason="missing or future observation date/source",
        )
    age_days = (today - obs_dt).days
    freshness = FreshnessStatus.AVAILABLE if age_days <= max_age else FreshnessStatus.STALE
    return MetricContract(
        instrument_id=instrument_id, measure_type=measure_type, value=numeric_val, unit=unit,
        evidence_kind=evidence_kind, freshness=freshness, observation_date=obs_dt.isoformat(),
        source_ref=src, methodology_version=methodology_version,
    )


def sort_key(m: MetricContract, *, comparison_group: str = "") -> Tuple[bool, str, float, str]:
    """Rank only available metrics within the same comparison group; stale and unavailable sort last."""
    ranked = bool(comparison_group) and m.freshness is FreshnessStatus.AVAILABLE and m.value is not None
    return (not ranked, comparison_group, -(m.value if ranked else 0.0), m.instrument_id)


def _format_finite_number(value: Union[int, float, Decimal]) -> str:
    if isinstance(value, int):
        return str(value)
    if isinstance(value, Decimal):
        dec = value
    else:
        if not math.isfinite(value):
            return ""
        dec = Decimal(str(value))
    if not dec.is_finite():
        return ""
    if dec.is_zero():
        return "0"
    text = format(dec.normalize(), "f")
    return "0" if text in ("", "-0") else text


def sanitize_csv_cell(value: object) -> str:
    """Export None as empty string (never 0) and neutralize spreadsheet formula injection
    on string cells without turning negative numeric values (-3.25) into text strings.
    """
    if value is None:
        return ""
    if isinstance(value, bool):
        text = "True" if value else "False"
        return f'"{text}"'
    if isinstance(value, (int, float, Decimal)):
        num_text = _format_finite_number(value)
        return f'"{num_text}"' if num_text else ""
    text = str(value)
    if not text:
        return ""
    safe = "'" + text if re.match(r"^[\s]*[=+@-]|^[\t\r\n]", text) else text
    return '"' + safe.replace('"', '""') + '"'
