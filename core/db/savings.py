"""Database repository, provenance ledger, staleness monitor, and automated certifi-verified
rate synchronization layer for Indian Fixed Savings, Term Deposits, Statutory Small Savings,
High-Yield Savings Accounts, and Statutory Retirement/Pension Instruments.

Canonical tables (v049 + v050 + v051):
- savings_instruments (includes override_epoch & active_observation_id)
- savings_rate_observations (append-only via globally unique content-addressed observation_id PK)
- tax_rule_registry
- savings_override_audit_log (immutable operator + reason audit ledger for forced overrides)

Complies with dual-dialect SQLite / PostgreSQL ON CONFLICT DO UPDATE / NOTHING bindings,
advisory/IMMEDIATE transactional locking, non-destructive legacy migration preservation,
future-dated rate scheduling, scoped page-level notification co-location, and SEBI Non-Advisory
Source-Grounded Provenance invariants.
"""

from __future__ import annotations

import hashlib
import html as html_lib
import ipaddress
import json
import logging
import re
import sqlite3
import ssl
import urllib.parse
import urllib.request
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import certifi

from core.db.connection import (
    IST,
    _get_raw_connection,
    get_configured_supabase_url,
    get_db_connection,
    get_db_path,
    get_placeholder,
    get_supabase_url,
    init_db,
    is_hosted_production_runtime,
    is_postgres_connection,
)

logger = logging.getLogger("equity_research.core.db.savings")

PROJECT_ROOT = Path(__file__).resolve().parents[2]
BASELINE_SAVINGS_JSON_PATH = PROJECT_ROOT / "data" / "savings_rates" / "baseline_savings_universe.json"
SAVINGS_INBOX_DIR = PROJECT_ROOT / "data" / "savings_rates" / "inbox"

SAVINGS_ADVISORY_LOCK_NS = 204901

SAVINGS_CATEGORY_LABELS: Dict[str, str] = {
    "SMALL_SAVINGS": "Post Office & Statutory Small Savings",
    "SOVEREIGN_DIRECT": "RBI Retail Direct Savings Bonds",
    "SCHEDULED_BANK_FD": "Scheduled Commercial Bank FDs",
    "SFB_FD": "Small Finance Bank FDs (DICGC Insured)",
    "CORPORATE_FD": "Corporate & NBFC Public Deposits",
    "HIGH_YIELD_SAVINGS": "High-Yield Savings Accounts",
    "RETIREMENT_PENSION": "Statutory Retirement & Pension (EPF / NPS)",
}

SAVINGS_CATEGORIES = tuple(SAVINGS_CATEGORY_LABELS.keys())

STATUTORY_QUARTERLY_CATEGORIES = frozenset({"SMALL_SAVINGS", "SOVEREIGN_DIRECT"})

_FORBIDDEN_VENDOR_TOKENS: Tuple[str, ...] = (
    "screener",
    "morningstar",
    "valueresearch",
    "yahoo",
    "moneycontrol",
    "groww",
    "zerodha",
    "etmoney",
    "paisabazaar",
    "bankbazaar",
)

# Official publisher domain registries (enforced with exact or dot-boundary subdomain matching)
CATEGORY_OFFICIAL_DOMAINS: Dict[str, Tuple[str, ...]] = {
    "SMALL_SAVINGS": (
        "dea.gov.in",
        "indiapost.gov.in",
        "finmin.nic.in",
        "rbi.org.in",
        "egazette.gov.in",
        "egazette.nic.in",
        "nsiindia.gov.in",
    ),
    "SOVEREIGN_DIRECT": (
        "rbiretaildirect.org.in",
        "rbi.org.in",
        "dea.gov.in",
        "finmin.nic.in",
    ),
    "RETIREMENT_PENSION": (
        "epfindia.gov.in",
        "npstrust.org.in",
        "pfrda.org.in",
        "finmin.nic.in",
    ),
}

TAX_RULE_OFFICIAL_DOMAINS: Tuple[str, ...] = (
    "incometaxindia.gov.in",
    "incometax.gov.in",
    "cbdt.gov.in",
    "finmin.nic.in",
    "indiabudget.gov.in",
    "egazette.gov.in",
    "egazette.nic.in",
)

ISSUER_OFFICIAL_DOMAINS: Dict[str, Tuple[str, ...]] = {
    "SBIN": ("sbi.co.in", "bank.sbi"),
    "HDFCBANK": ("hdfcbank.com",),
    "ICICIBANK": ("icicibank.com",),
    "KOTAKBANK": ("kotak.com", "kotakbank.com"),
    "AXISBANK": ("axisbank.com",),
    "IDFCFIRSTB": ("idfcfirstbank.com",),
    "INDUSINDBK": ("indusind.com",),
    "FEDERALBNK": ("federalbank.co.in",),
    "BANKBARODA": ("bankofbaroda.in",),
    "PNB": ("pnbindia.in",),
    "CANBK": ("canarabank.com",),
    "UNIONBANK": ("unionbankofindia.co.in",),
    "YESBANK": ("yesbank.in",),
    "RBLBANK": ("rblbank.com",),
    "BANDHANBNK": ("bandhanbank.com",),
    "SURYODAY": ("suryodaybank.com",),
    "UTKARSHBNK": ("utkarsh.bank",),
    "JSFB": ("janabank.com",),
    "UJJIVANSFB": ("ujjivansfb.in",),
    "EQUITASBNK": ("equitasbank.com",),
    "AUBANK": ("aubank.in",),
    "ESAFSFB": ("esafbank.com",),
    "BAJFINANCE": ("bajajfinserv.in",),
    "M&MFIN": ("mahindrafinance.com",),
    "SHRIRAMFIN": ("shriramfinance.in",),
    "SUNDARMFIN": ("sundaramfinance.in",),
    "LICHSGFIN": ("lichousing.com",),
    "PNBHOUSING": ("pnbhousing.com",),
    "MUTHOOTFIN": ("muthootfinance.com",),
}

_STATUTORY_AUTHORITY_PATTERNS: Dict[str, re.Pattern[str]] = {
    "SMALL_SAVINGS": re.compile(
        r"\b(?:dea|department\s+of\s+economic\s+affairs|ministry\s+of\s+finance|india\s+post|government\s+of\s+india|reserve\s+bank\s+of\s+india|rbi)\b",
        re.IGNORECASE,
    ),
    "SOVEREIGN_DIRECT": re.compile(
        r"\b(?:reserve\s+bank\s+of\s+india|rbi|government\s+of\s+india|ministry\s+of\s+finance|dea)\b",
        re.IGNORECASE,
    ),
    "RETIREMENT_PENSION": re.compile(
        r"\b(?:epfo|provident\s+fund|pfrda|nps\s+trust|ministry\s+of\s+finance|ministry\s+of\s+labour)\b",
        re.IGNORECASE,
    ),
    "TAX_RULE": re.compile(
        r"\b(?:cbdt|central\s+board\s+of\s+direct\s+taxes|ministry\s+of\s+finance|income\s+tax|government\s+of\s+india)\b",
        re.IGNORECASE,
    ),
}

_ISSUER_AUTHORITY_TOKENS: Dict[str, Tuple[str, ...]] = {
    "SBIN": ("state bank", "sbi"),
    "HDFCBANK": ("hdfc",),
    "ICICIBANK": ("icici",),
    "KOTAKBANK": ("kotak",),
    "AXISBANK": ("axis",),
    "IDFCFIRSTB": ("idfc",),
    "INDUSINDBK": ("indusind",),
    "FEDERALBNK": ("federal",),
    "BANKBARODA": ("baroda",),
    "PNB": ("punjab national", "pnb"),
    "CANBK": ("canara",),
    "UNIONBANK": ("union bank",),
    "YESBANK": ("yes bank",),
    "RBLBANK": ("rbl",),
    "BANDHANBNK": ("bandhan",),
    "SURYODAY": ("suryoday",),
    "UTKARSHBNK": ("utkarsh",),
    "JSFB": ("jana",),
    "UJJIVANSFB": ("ujjivan",),
    "EQUITASBNK": ("equitas",),
    "AUBANK": ("au small finance", "au bank"),
    "ESAFSFB": ("esaf",),
    "BAJFINANCE": ("bajaj",),
    "M&MFIN": ("mahindra",),
    "SHRIRAMFIN": ("shriram",),
    "SUNDARMFIN": ("sundaram",),
    "LICHSGFIN": ("lic housing", "lichfl"),
    "PNBHOUSING": ("pnb housing",),
    "MUTHOOTFIN": ("muthoot",),
}


def _now_ist_iso() -> str:
    return datetime.now(IST).isoformat()


def _parse_iso_date(raw: Optional[str]) -> Optional[date]:
    if not raw:
        return None
    clean = str(raw).strip()[:10]
    try:
        return date.fromisoformat(clean)
    except ValueError:
        return None


def _has_forbidden_vendor_token(text: str) -> bool:
    lower = (text or "").lower()
    return any(tok in lower for tok in _FORBIDDEN_VENDOR_TOKENS)


def _host_matches_approved_domains(hostname: str, approved_domains: Tuple[str, ...]) -> bool:
    host = (hostname or "").strip().lower().rstrip(".")
    if not host or not approved_domains:
        return False
    try:
        ipaddress.ip_address(host)
        return False
    except ValueError:
        pass
    for dom in approved_domains:
        clean_dom = dom.strip().lower().rstrip(".")
        if host == clean_dom or host.endswith("." + clean_dom):
            return True
    return False


def _validate_https_official_url(url: str, approved_domains: Tuple[str, ...], context_label: str) -> str:
    clean_url = str(url or "").strip()
    if not clean_url:
        raise ValueError(f"{context_label} requires a non-empty HTTPS source_url.")
    parsed = urllib.parse.urlsplit(clean_url)
    if parsed.scheme.lower() != "https":
        raise ValueError(f"{context_label} requires an HTTPS official source_url (got '{clean_url}').")
    if parsed.username or parsed.password:
        raise ValueError(f"{context_label} source_url must not embed credentials ('{clean_url}').")
    if parsed.port not in (None, 443):
        raise ValueError(f"{context_label} source_url must use standard HTTPS port 443 ('{clean_url}').")
    hostname = (parsed.hostname or "").strip().lower().rstrip(".")
    if not hostname:
        raise ValueError(f"{context_label} source_url has no valid hostname ('{clean_url}').")
    if not _host_matches_approved_domains(hostname, approved_domains):
        raise ValueError(
            f"{context_label} hostname '{hostname}' is not in the approved official publisher registry {approved_domains}."
        )
    return hostname


def _resolve_issuer_registry_key(item: Dict[str, Any]) -> str:
    notes = item.get("notes")
    if not isinstance(notes, dict):
        try:
            notes = json.loads(item.get("notes_json") or "{}")
        except Exception as exc:
            logger.debug("Notes JSON parse notice in _resolve_issuer_registry_key: %s", exc)
            notes = {}
    ticker = str(item.get("issuer_ticker") or "").strip().upper()
    if ticker in ISSUER_OFFICIAL_DOMAINS:
        return ticker
    charter = str(notes.get("bank_charter_key") or "").strip().upper()
    if charter in ISSUER_OFFICIAL_DOMAINS:
        return charter
    return ticker or charter


def validate_savings_provenance(item: Dict[str, Any]) -> None:
    """Enforces HTTPS scheme, approved official authority/issuer hostname whitelist, and source identity."""
    inst_id = str(item.get("instrument_id") or "").strip().upper()
    if not inst_id:
        raise ValueError("Savings instrument requires a non-empty instrument_id.")
    category = str(item.get("category") or "").strip().upper()
    if category not in SAVINGS_CATEGORIES:
        raise ValueError(f"Unsupported savings category '{category}' for {inst_id}.")
    try:
        rate = float(item["base_rate_pct"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"Invalid base_rate_pct for {inst_id}.") from exc
    if not (0.0 <= rate <= 25.0):
        raise ValueError(f"Out-of-bounds base_rate_pct ({rate}%) for {inst_id}; expected 0.0..25.0%.")
    eff_dt = _parse_iso_date(item.get("effective_from"))
    if eff_dt is None:
        raise ValueError(f"Savings instrument {inst_id} requires a valid YYYY-MM-DD effective_from date.")
    auth = str(item.get("source_authority") or "").strip()
    if len(auth) < 3:
        raise ValueError(f"Savings instrument {inst_id} requires a non-empty official source_authority.")
    url = str(item.get("source_url") or "").strip()
    if _has_forbidden_vendor_token(f"{auth} {url}"):
        raise ValueError(
            f"Savings instrument {inst_id} cites a forbidden retail/aggregator source ('{auth}' / '{url}')."
        )

    if category in CATEGORY_OFFICIAL_DOMAINS:
        approved_domains = CATEGORY_OFFICIAL_DOMAINS[category]
        _validate_https_official_url(url, approved_domains, f"Savings instrument {inst_id} ({category})")
        auth_pat = _STATUTORY_AUTHORITY_PATTERNS[category]
        if not auth_pat.search(auth):
            raise ValueError(
                f"Savings instrument {inst_id} source_authority '{auth}' does not match an approved statutory authority for {category}."
            )
    else:
        issuer_key = _resolve_issuer_registry_key(item)
        if not issuer_key or issuer_key not in ISSUER_OFFICIAL_DOMAINS:
            raise ValueError(
                f"Savings instrument {inst_id} issuer '{issuer_key or item.get('issuer_name')}' is not registered in ISSUER_OFFICIAL_DOMAINS."
            )
        approved_domains = ISSUER_OFFICIAL_DOMAINS[issuer_key]
        _validate_https_official_url(url, approved_domains, f"Savings instrument {inst_id} ({issuer_key})")
        expected_tokens = _ISSUER_AUTHORITY_TOKENS.get(issuer_key, ())
        auth_lower = auth.lower()
        if expected_tokens and not any(tok in auth_lower for tok in expected_tokens):
            raise ValueError(
                f"Savings instrument {inst_id} source_authority '{auth}' does not match registered issuer '{issuer_key}'."
            )


def validate_tax_rule_provenance(tv: Dict[str, Any]) -> None:
    """Enforces HTTPS official CBDT/Ministry of Finance provenance on tax_rule_registry rows."""
    rule_ver = str(tv.get("rule_version") or "").strip()
    if not rule_ver:
        raise ValueError("Tax rule entry requires a non-empty rule_version.")
    if _parse_iso_date(tv.get("effective_from")) is None:
        raise ValueError(f"Tax rule {rule_ver} requires a valid YYYY-MM-DD effective_from date.")
    auth = str(tv.get("source_authority") or "").strip()
    url = str(tv.get("source_url") or "").strip()
    if _has_forbidden_vendor_token(f"{auth} {url}"):
        raise ValueError(f"Tax rule {rule_ver} cites a forbidden vendor token.")
    _validate_https_official_url(url, TAX_RULE_OFFICIAL_DOMAINS, f"Tax rule {rule_ver}")
    if not _STATUTORY_AUTHORITY_PATTERNS["TAX_RULE"].search(auth):
        raise ValueError(f"Tax rule {rule_ver} source_authority '{auth}' is not an official tax authority.")


ALL_APPROVED_SAVINGS_DOMAINS: Tuple[str, ...] = tuple(
    sorted(
        {
            dom
            for doms in (*CATEGORY_OFFICIAL_DOMAINS.values(), *ISSUER_OFFICIAL_DOMAINS.values())
            for dom in doms
        }
    )
)


def validate_observation_provenance(obs: Dict[str, Any]) -> None:
    """Enforces HTTPS official publisher domain & valid date/rate fields on savings_rate_observations."""
    inst_id = str(obs.get("instrument_id") or "").strip().upper()
    if not inst_id:
        raise ValueError("Rate observation requires a non-empty instrument_id.")
    if _parse_iso_date(obs.get("effective_from")) is None:
        raise ValueError(f"Rate observation for {inst_id} requires a valid YYYY-MM-DD effective_from date.")
    try:
        rate = float(obs["base_rate_pct"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"Invalid base_rate_pct on rate observation for {inst_id}.") from exc
    if not (0.0 <= rate <= 25.0):
        raise ValueError(f"Out-of-bounds base_rate_pct ({rate}%) on rate observation for {inst_id}.")
    auth = str(obs.get("source_authority") or "").strip()
    url = str(obs.get("source_url") or "").strip()
    if len(auth) < 3 or _has_forbidden_vendor_token(f"{auth} {url}"):
        raise ValueError(f"Rate observation for {inst_id} has invalid/vendor source_authority.")
    _validate_https_official_url(url, ALL_APPROVED_SAVINGS_DOMAINS, f"Rate observation {inst_id}")


def is_valid_savings_provenance(item: Dict[str, Any]) -> bool:
    """Boolean wrapper around validate_savings_provenance for read/staleness paths."""
    try:
        validate_savings_provenance(item)
        return True
    except ValueError:
        return False


_BASE_36_COLS: Tuple[str, ...] = (
    "instrument_id",
    "scheme_name",
    "category",
    "issuer_name",
    "issuer_ticker",
    "issuer_type",
    "sovereign_backed",
    "dicgc_insured",
    "dicgc_limit_inr",
    "credit_rating",
    "base_rate_pct",
    "senior_citizen_bonus_bps",
    "rate_type",
    "floating_benchmark",
    "floating_spread_bps",
    "compounding_freq",
    "payout_options_json",
    "tenure_min_months",
    "tenure_max_months",
    "lock_in_months",
    "premature_exit_rule",
    "min_investment_inr",
    "max_investment_inr",
    "tax_section_80c_eligible",
    "interest_taxability",
    "maturity_taxability",
    "tds_applicable",
    "tds_threshold_regular_inr",
    "tds_threshold_senior_inr",
    "effective_from",
    "next_review_date",
    "source_authority",
    "source_url",
    "notes_json",
    "is_active",
    "updated_at",
)

_EPHEMERAL_NOTES_KEYS = frozenset({"last_tariff_verified_on", "unverified_portal_rate_candidate"})


def _normalize_payout_json(item: Dict[str, Any]) -> str:
    payout_options = item.get("payout_options")
    if payout_options is None:
        raw = str(item.get("payout_options_json") or '["CUMULATIVE"]')
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, list):
                return json.dumps([str(x) for x in parsed])
        except Exception as exc:
            logger.debug("Payout JSON normalize notice: %s", exc)
        return raw
    if isinstance(payout_options, str):
        try:
            parsed = json.loads(payout_options)
            if isinstance(parsed, list):
                return json.dumps([str(x) for x in parsed])
        except Exception as exc:
            logger.debug("Payout string normalize notice: %s", exc)
        return payout_options
    return json.dumps([str(x) for x in list(payout_options)])


def _normalize_notes_json(item: Dict[str, Any]) -> Tuple[str, Dict[str, Any]]:
    notes_obj = item.get("notes")
    if notes_obj is None:
        raw = str(item.get("notes_json") or "{}")
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                return json.dumps(parsed, sort_keys=True), parsed
        except Exception as exc:
            logger.debug("Notes JSON normalize notice: %s", exc)
        return raw, {}
    if isinstance(notes_obj, str):
        try:
            parsed = json.loads(notes_obj)
            if isinstance(parsed, dict):
                return json.dumps(parsed, sort_keys=True), parsed
        except Exception as exc:
            logger.debug("Notes string normalize notice: %s", exc)
        return notes_obj, {}
    clean_dict = dict(notes_obj)
    return json.dumps(clean_dict, sort_keys=True), clean_dict


def compute_material_terms_snapshot(
    item: Dict[str, Any],
    *,
    rate_circular_ref: Optional[str] = None,
) -> Tuple[str, str]:
    """Serializes all material non-rate instrument terms and computes a deterministic SHA-256 hash.

    Preserves full 36-column reconstruction fidelity in terms_snapshot_json while excluding
    ephemeral verification stamps (last_tariff_verified_on, unverified_portal_rate_candidate)
    from material_terms_hash so routine liveness checks do not spawn spurious revisions.
    """
    payout_json = _normalize_payout_json(item)
    notes_json, notes_dict = _normalize_notes_json(item)
    source_auth = str(item.get("source_authority") or "").strip()
    circ_ref = (
        str(rate_circular_ref).strip()
        if rate_circular_ref is not None
        else str(
            item.get("rate_circular_ref")
            or notes_dict.get("rate_circular_ref")
            or notes_dict.get("circular_ref")
            or source_auth
        ).strip()
    )
    material_notes = {k: v for k, v in notes_dict.items() if k not in _EPHEMERAL_NOTES_KEYS}

    snapshot_obj: Dict[str, Any] = {
        "scheme_name": str(item.get("scheme_name") or "").strip(),
        "category": str(item.get("category") or "").strip().upper(),
        "issuer_name": str(item.get("issuer_name") or "").strip(),
        "issuer_ticker": (
            str(item["issuer_ticker"]).strip().upper() if item.get("issuer_ticker") else None
        ),
        "issuer_type": str(item.get("issuer_type") or "").strip().upper(),
        "sovereign_backed": 1 if item.get("sovereign_backed") else 0,
        "dicgc_insured": 1 if item.get("dicgc_insured") else 0,
        "dicgc_limit_inr": round(float(item.get("dicgc_limit_inr") or 0.0), 2),
        "credit_rating": str(item.get("credit_rating") or "UNRATED").strip(),
        "rate_type": str(item.get("rate_type") or "FIXED").strip().upper(),
        "floating_benchmark": (
            str(item["floating_benchmark"]).strip() if item.get("floating_benchmark") else None
        ),
        "floating_spread_bps": round(float(item.get("floating_spread_bps") or 0.0), 2),
        "compounding_freq": str(item.get("compounding_freq") or "QUARTERLY").strip().upper(),
        "payout_options_json": payout_json,
        "tenure_min_months": int(item.get("tenure_min_months") or 0),
        "tenure_max_months": int(item.get("tenure_max_months") or 0),
        "lock_in_months": int(item.get("lock_in_months") or 0),
        "premature_exit_rule": str(item.get("premature_exit_rule") or "").strip(),
        "min_investment_inr": round(float(item.get("min_investment_inr") or 0.0), 2),
        "max_investment_inr": (
            round(float(item["max_investment_inr"]), 2)
            if item.get("max_investment_inr") is not None
            else None
        ),
        "tax_section_80c_eligible": 1 if item.get("tax_section_80c_eligible") else 0,
        "interest_taxability": str(item.get("interest_taxability") or "SLAB_TAXABLE").strip().upper(),
        "maturity_taxability": str(item.get("maturity_taxability") or "EXEMPT").strip().upper(),
        "tds_applicable": 1 if item.get("tds_applicable") else 0,
        "tds_threshold_regular_inr": round(float(item.get("tds_threshold_regular_inr") or 0.0), 2),
        "tds_threshold_senior_inr": round(float(item.get("tds_threshold_senior_inr") or 0.0), 2),
        "next_review_date": (
            str(item["next_review_date"]).strip()[:10] if item.get("next_review_date") else None
        ),
        "source_authority": source_auth,
        "source_url": str(item.get("source_url") or "").strip(),
        "notes_json": notes_json,
        "is_active": 1 if item.get("is_active", 1) else 0,
        "rate_circular_ref": circ_ref,
    }
    hash_basis = dict(snapshot_obj)
    hash_basis.pop("notes_json", None)
    hash_basis["material_notes"] = material_notes
    terms_snapshot_json = json.dumps(snapshot_obj, sort_keys=True, separators=(",", ":"))
    material_hash = hashlib.sha256(
        json.dumps(hash_basis, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()[:32]
    return terms_snapshot_json, material_hash


def compute_observation_id(
    *,
    instrument_id: str,
    effective_from: str,
    base_rate_pct: float,
    senior_citizen_bonus_bps: float,
    rate_circular_ref: str,
    source_authority: str,
    source_url: str,
    material_terms_hash: str = "",
    override_epoch: int = 0,
) -> str:
    """Computes a globally deterministic content-addressed observation_id across SQLite & PostgreSQL."""
    basis = {
        "instrument_id": str(instrument_id or "").strip().upper(),
        "effective_from": str(effective_from or "").strip()[:10],
        "base_rate_pct": round(float(base_rate_pct or 0.0), 4),
        "senior_citizen_bonus_bps": round(float(senior_citizen_bonus_bps or 0.0), 2),
        "rate_circular_ref": str(rate_circular_ref or "").strip(),
        "source_authority": str(source_authority or "").strip(),
        "source_url": str(source_url or "").strip(),
        "material_terms_hash": str(material_terms_hash or "").strip(),
        "override_epoch": int(override_epoch or 0),
    }
    digest = hashlib.sha256(
        json.dumps(basis, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()[:28]
    return f"obs_{digest}"


def _table_exists_on_cursor(cursor: Any, table_name: str, *, is_pg: bool) -> bool:
    if is_pg:
        cursor.execute(
            "SELECT 1 FROM information_schema.tables WHERE table_schema = 'public' AND table_name = %s;",
            (table_name,),
        )
    else:
        cursor.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?;",
            (table_name,),
        )
    return cursor.fetchone() is not None


def _table_columns_on_cursor(cursor: Any, table_name: str, *, is_pg: bool) -> List[str]:
    if not _table_exists_on_cursor(cursor, table_name, is_pg=is_pg):
        return []
    if is_pg:
        cursor.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema = 'public' AND table_name = %s ORDER BY ordinal_position;",
            (table_name,),
        )
        return [str(r[0]) for r in cursor.fetchall()]
    cursor.execute(f"PRAGMA table_info({table_name});")
    return [str(r[1]) for r in cursor.fetchall()]


def _row36_to_dict(row: Any) -> Dict[str, Any]:
    return {col: row[idx] for idx, col in enumerate(_BASE_36_COLS)}


def _mirror_legacy_v049_tables_on_cursor(
    cursor: Any,
    *,
    is_pg: bool,
    instrument_row_dict: Optional[Dict[str, Any]] = None,
    observation_row_dict: Optional[Dict[str, Any]] = None,
    tax_rule_dict: Optional[Dict[str, Any]] = None,
) -> None:
    """Maintains live rollback compatibility with retained v049 draft tables when present."""
    p = "%s" if is_pg else "?"
    excl = "EXCLUDED" if is_pg else "excluded"

    if instrument_row_dict is not None and _table_exists_on_cursor(
        cursor, "fixed_savings_instruments", is_pg=is_pg
    ):
        cols_sql = ", ".join(_BASE_36_COLS)
        ph_sql = ", ".join([p] * len(_BASE_36_COLS))
        upd_sql = ", ".join(
            [f"{c} = {excl}.{c}" for c in _BASE_36_COLS if c != "instrument_id"]
        )
        cursor.execute(
            f"INSERT INTO fixed_savings_instruments ({cols_sql}) VALUES ({ph_sql}) "
            f"ON CONFLICT (instrument_id) DO UPDATE SET {upd_sql};",
            tuple(instrument_row_dict.get(c) for c in _BASE_36_COLS),
        )

    if observation_row_dict is not None and _table_exists_on_cursor(
        cursor, "savings_rate_history", is_pg=is_pg
    ):
        cursor.execute(
            f"SELECT id FROM savings_rate_history "
            f"WHERE instrument_id = {p} AND effective_from = {p} AND ABS(base_rate_pct - {p}) < 1e-6 LIMIT 1;",
            (
                observation_row_dict["instrument_id"],
                observation_row_dict["effective_from"],
                float(observation_row_dict["base_rate_pct"]),
            ),
        )
        if cursor.fetchone() is None:
            cursor.execute(
                f"""
                INSERT INTO savings_rate_history (
                    instrument_id, base_rate_pct, senior_citizen_bonus_bps,
                    effective_from, effective_to, source_authority, source_url, recorded_at
                ) VALUES ({p}, {p}, {p}, {p}, {p}, {p}, {p}, {p});
                """,
                (
                    observation_row_dict["instrument_id"],
                    float(observation_row_dict["base_rate_pct"]),
                    float(observation_row_dict.get("senior_citizen_bonus_bps") or 0.0),
                    observation_row_dict["effective_from"],
                    observation_row_dict.get("effective_to"),
                    observation_row_dict["source_authority"],
                    observation_row_dict["source_url"],
                    observation_row_dict["observed_at"],
                ),
            )

    if tax_rule_dict is not None and _table_exists_on_cursor(
        cursor, "regulatory_tax_rule_versions", is_pg=is_pg
    ):
        cursor.execute(
            f"""
            INSERT INTO regulatory_tax_rule_versions (
                rule_version, finance_act_label, effective_from, effective_to,
                rules_json, source_authority, source_url, updated_at
            ) VALUES ({p}, {p}, {p}, {p}, {p}, {p}, {p}, {p})
            ON CONFLICT (rule_version) DO UPDATE SET
                finance_act_label = {excl}.finance_act_label,
                effective_from = {excl}.effective_from,
                effective_to = {excl}.effective_to,
                rules_json = {excl}.rules_json,
                source_authority = {excl}.source_authority,
                source_url = {excl}.source_url,
                updated_at = {excl}.updated_at;
            """,
            (
                tax_rule_dict["rule_version"],
                tax_rule_dict["finance_act_label"],
                tax_rule_dict["effective_from"],
                tax_rule_dict.get("effective_to"),
                tax_rule_dict["rules_json"],
                tax_rule_dict["source_authority"],
                tax_rule_dict["source_url"],
                tax_rule_dict["updated_at"],
            ),
        )


def reconcile_savings_schema_and_legacy_tables(
    cursor: Any,
    *,
    is_pg: bool,
    reference_date_iso: Optional[str] = None,
) -> Dict[str, Any]:
    """Idempotent v050/v051 schema upgrade, dual-table conflict reconciliation, and preservation verifier.

    Guarantees:
    1. Canonical tables exist with globally unique `observation_id TEXT PRIMARY KEY`, `override_epoch`,
       `active_observation_id`, and `savings_override_audit_log`.
    2. Upgrades any pre-v051 `savings_rate_observations` table (integer id + composite UNIQUE) cleanly
       into `observation_id TEXT PRIMARY KEY` with zero row loss.
    3. Reconciles when BOTH legacy (`fixed_savings_instruments`, `savings_rate_history`,
       `regulatory_tax_rule_versions`) and canonical tables contain data (including conflicting rates/terms):
       - Preserves 100% of rows and 36-column snapshots from BOTH tables in `savings_rate_observations`.
       - Selects the deterministic active winner (`effective_from <= ref_date`, newest `effective_from`,
         newest `updated_at`), keeping future-dated candidates as `SCHEDULED_FUTURE`.
       - Verifies 100% row/field preservation in-transaction (raising RuntimeError on any mismatch)
         and RETAINS legacy tables mirrored to the reconciled active state for rollback compatibility.
    """
    p = "%s" if is_pg else "?"
    excl = "EXCLUDED" if is_pg else "excluded"
    ref_iso = (_parse_iso_date(reference_date_iso) or datetime.now(IST).date()).isoformat()
    now_iso = _now_ist_iso()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS savings_instruments (
            instrument_id TEXT PRIMARY KEY,
            scheme_name TEXT NOT NULL,
            category TEXT NOT NULL,
            issuer_name TEXT NOT NULL,
            issuer_ticker TEXT,
            issuer_type TEXT NOT NULL,
            sovereign_backed INTEGER NOT NULL DEFAULT 0,
            dicgc_insured INTEGER NOT NULL DEFAULT 0,
            dicgc_limit_inr REAL NOT NULL DEFAULT 0.0,
            credit_rating TEXT NOT NULL DEFAULT 'UNRATED',
            base_rate_pct REAL NOT NULL,
            senior_citizen_bonus_bps REAL NOT NULL DEFAULT 0.0,
            rate_type TEXT NOT NULL DEFAULT 'FIXED',
            floating_benchmark TEXT,
            floating_spread_bps REAL NOT NULL DEFAULT 0.0,
            compounding_freq TEXT NOT NULL DEFAULT 'QUARTERLY',
            payout_options_json TEXT NOT NULL DEFAULT '["CUMULATIVE"]',
            tenure_min_months INTEGER NOT NULL DEFAULT 0,
            tenure_max_months INTEGER NOT NULL DEFAULT 0,
            lock_in_months INTEGER NOT NULL DEFAULT 0,
            premature_exit_rule TEXT,
            min_investment_inr REAL NOT NULL DEFAULT 500.0,
            max_investment_inr REAL,
            tax_section_80c_eligible INTEGER NOT NULL DEFAULT 0,
            interest_taxability TEXT NOT NULL DEFAULT 'SLAB_TAXABLE',
            maturity_taxability TEXT NOT NULL DEFAULT 'EXEMPT',
            tds_applicable INTEGER NOT NULL DEFAULT 0,
            tds_threshold_regular_inr REAL NOT NULL DEFAULT 0.0,
            tds_threshold_senior_inr REAL NOT NULL DEFAULT 0.0,
            effective_from TEXT NOT NULL,
            next_review_date TEXT,
            source_authority TEXT NOT NULL,
            source_url TEXT NOT NULL,
            notes_json TEXT NOT NULL DEFAULT '{}',
            is_active INTEGER NOT NULL DEFAULT 1,
            updated_at TEXT NOT NULL,
            override_epoch INTEGER NOT NULL DEFAULT 0,
            active_observation_id TEXT
        );
    """)
    inst_cols = set(_table_columns_on_cursor(cursor, "savings_instruments", is_pg=is_pg))
    if "override_epoch" not in inst_cols:
        cursor.execute(
            "ALTER TABLE savings_instruments ADD COLUMN override_epoch INTEGER NOT NULL DEFAULT 0;"
        )
    if "active_observation_id" not in inst_cols:
        cursor.execute(
            "ALTER TABLE savings_instruments ADD COLUMN active_observation_id TEXT;"
        )
    cursor.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_savings_instruments_pk_uniq ON savings_instruments(instrument_id);"
    )

    obs_cols = _table_columns_on_cursor(cursor, "savings_rate_observations", is_pg=is_pg)
    if not obs_cols:
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS savings_rate_observations (
                observation_id TEXT PRIMARY KEY,
                instrument_id TEXT NOT NULL,
                base_rate_pct REAL NOT NULL,
                senior_citizen_bonus_bps REAL NOT NULL DEFAULT 0.0,
                effective_from TEXT NOT NULL,
                effective_to TEXT,
                revision_seq INTEGER NOT NULL DEFAULT 1,
                rate_circular_ref TEXT NOT NULL DEFAULT '',
                source_authority TEXT NOT NULL,
                source_url TEXT NOT NULL,
                material_terms_hash TEXT NOT NULL DEFAULT '',
                terms_snapshot_json TEXT NOT NULL DEFAULT '{}',
                change_reason TEXT NOT NULL DEFAULT 'INITIAL_SEED',
                observation_status TEXT NOT NULL DEFAULT 'ACTIVE',
                origin_db TEXT NOT NULL DEFAULT 'local',
                observed_at TEXT NOT NULL,
                superseded_at TEXT,
                superseded_by_observation_id TEXT,
                evidence_sha256 TEXT
            );
        """)
    elif "observation_id" not in obs_cols:
        cols36_sql = ", ".join(_BASE_36_COLS)
        cursor.execute(f"SELECT {cols36_sql} FROM savings_instruments;")
        inst_snap_by_id = {str(r[0]): _row36_to_dict(r) for r in cursor.fetchall()}

        cursor.execute("""
            SELECT instrument_id, base_rate_pct, senior_citizen_bonus_bps,
                   effective_from, effective_to, revision_seq, rate_circular_ref,
                   source_authority, source_url, observed_at, superseded_at
            FROM savings_rate_observations
            ORDER BY instrument_id ASC, effective_from ASC, revision_seq ASC;
        """)
        old_obs_rows = cursor.fetchall()

        cursor.execute("DROP TABLE IF EXISTS savings_rate_observations_v2;")
        cursor.execute("""
            CREATE TABLE savings_rate_observations_v2 (
                observation_id TEXT PRIMARY KEY,
                instrument_id TEXT NOT NULL,
                base_rate_pct REAL NOT NULL,
                senior_citizen_bonus_bps REAL NOT NULL DEFAULT 0.0,
                effective_from TEXT NOT NULL,
                effective_to TEXT,
                revision_seq INTEGER NOT NULL DEFAULT 1,
                rate_circular_ref TEXT NOT NULL DEFAULT '',
                source_authority TEXT NOT NULL,
                source_url TEXT NOT NULL,
                material_terms_hash TEXT NOT NULL DEFAULT '',
                terms_snapshot_json TEXT NOT NULL DEFAULT '{}',
                change_reason TEXT NOT NULL DEFAULT 'MIGRATED_OBSERVATION',
                observation_status TEXT NOT NULL DEFAULT 'ACTIVE',
                origin_db TEXT NOT NULL DEFAULT 'local',
                observed_at TEXT NOT NULL,
                superseded_at TEXT,
                superseded_by_observation_id TEXT,
                evidence_sha256 TEXT
            );
        """)
        prepared_v2: List[Dict[str, Any]] = []
        active_obs_by_inst_date: Dict[Tuple[str, str], str] = {}
        seen_obs_ids: Dict[str, int] = {}

        for r in old_obs_rows:
            oid_inst = str(r[0])
            oid_rate = round(float(r[1] or 0.0), 4)
            oid_bonus = round(float(r[2] or 0.0), 2)
            oid_eff = str(r[3])[:10]
            oid_eff_to = str(r[4])[:10] if r[4] else None
            oid_rev = int(r[5] or 1)
            oid_circ = str(r[6] or r[7] or "")
            oid_auth = str(r[7] or "")
            oid_url = str(r[8] or "")
            oid_obs_at = str(r[9] or now_iso)
            oid_sup_at = str(r[10]) if r[10] else None

            base_dict = dict(inst_snap_by_id.get(oid_inst) or {})
            base_dict.update(
                {
                    "instrument_id": oid_inst,
                    "base_rate_pct": oid_rate,
                    "senior_citizen_bonus_bps": oid_bonus,
                    "effective_from": oid_eff,
                    "source_authority": oid_auth,
                    "source_url": oid_url,
                }
            )
            snap_json, mat_hash = compute_material_terms_snapshot(
                base_dict, rate_circular_ref=oid_circ
            )
            obs_id = compute_observation_id(
                instrument_id=oid_inst,
                effective_from=oid_eff,
                base_rate_pct=oid_rate,
                senior_citizen_bonus_bps=oid_bonus,
                rate_circular_ref=oid_circ,
                source_authority=oid_auth,
                source_url=oid_url,
                material_terms_hash=mat_hash,
                override_epoch=0,
            )
            if obs_id in seen_obs_ids:
                seen_obs_ids[obs_id] += 1
                obs_id = compute_observation_id(
                    instrument_id=oid_inst,
                    effective_from=oid_eff,
                    base_rate_pct=oid_rate,
                    senior_citizen_bonus_bps=oid_bonus,
                    rate_circular_ref=f"{oid_circ}#rev{oid_rev}_{seen_obs_ids[obs_id]}",
                    source_authority=oid_auth,
                    source_url=oid_url,
                    material_terms_hash=mat_hash,
                    override_epoch=0,
                )
            else:
                seen_obs_ids[obs_id] = 1

            if oid_sup_at:
                obs_status = "SUPERSEDED"
            elif oid_eff > ref_iso:
                obs_status = "SCHEDULED_FUTURE"
            elif oid_eff_to:
                obs_status = "HISTORICAL"
            else:
                obs_status = "ACTIVE"
                active_obs_by_inst_date[(oid_inst, oid_eff)] = obs_id

            prepared_v2.append(
                {
                    "observation_id": obs_id,
                    "instrument_id": oid_inst,
                    "base_rate_pct": oid_rate,
                    "senior_citizen_bonus_bps": oid_bonus,
                    "effective_from": oid_eff,
                    "effective_to": oid_eff_to,
                    "revision_seq": oid_rev,
                    "rate_circular_ref": oid_circ,
                    "source_authority": oid_auth,
                    "source_url": oid_url,
                    "material_terms_hash": mat_hash,
                    "terms_snapshot_json": snap_json,
                    "change_reason": "INITIAL_SEED" if oid_rev == 1 else "SAME_DATE_REVISION",
                    "observation_status": obs_status,
                    "origin_db": "postgres" if is_pg else "local",
                    "observed_at": oid_obs_at,
                    "superseded_at": oid_sup_at,
                }
            )

        for item_v2 in prepared_v2:
            sup_by = (
                active_obs_by_inst_date.get((item_v2["instrument_id"], item_v2["effective_from"]))
                if item_v2["superseded_at"]
                else None
            )
            if sup_by == item_v2["observation_id"]:
                sup_by = None
            cursor.execute(
                f"""
                INSERT INTO savings_rate_observations_v2 (
                    observation_id, instrument_id, base_rate_pct, senior_citizen_bonus_bps,
                    effective_from, effective_to, revision_seq, rate_circular_ref,
                    source_authority, source_url, material_terms_hash, terms_snapshot_json,
                    change_reason, observation_status, origin_db, observed_at,
                    superseded_at, superseded_by_observation_id, evidence_sha256
                ) VALUES ({", ".join([p] * 19)});
                """,
                (
                    item_v2["observation_id"],
                    item_v2["instrument_id"],
                    item_v2["base_rate_pct"],
                    item_v2["senior_citizen_bonus_bps"],
                    item_v2["effective_from"],
                    item_v2["effective_to"],
                    item_v2["revision_seq"],
                    item_v2["rate_circular_ref"],
                    item_v2["source_authority"],
                    item_v2["source_url"],
                    item_v2["material_terms_hash"],
                    item_v2["terms_snapshot_json"],
                    item_v2["change_reason"],
                    item_v2["observation_status"],
                    item_v2["origin_db"],
                    item_v2["observed_at"],
                    item_v2["superseded_at"],
                    sup_by,
                    None,
                ),
            )

        cursor.execute("SELECT COUNT(*) FROM savings_rate_observations_v2;")
        migrated_cnt = int(cursor.fetchone()[0] or 0)
        if migrated_cnt != len(old_obs_rows):
            raise RuntimeError(
                f"Observation migration row-count mismatch: expected {len(old_obs_rows)}, got {migrated_cnt}."
            )
        cursor.execute("DROP TABLE savings_rate_observations;")
        cursor.execute(
            "ALTER TABLE savings_rate_observations_v2 RENAME TO savings_rate_observations;"
        )

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS tax_rule_registry (
            rule_version TEXT PRIMARY KEY,
            finance_act_label TEXT NOT NULL,
            effective_from TEXT NOT NULL,
            effective_to TEXT,
            rules_json TEXT NOT NULL,
            source_authority TEXT NOT NULL,
            source_url TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS savings_override_audit_log (
            override_id TEXT PRIMARY KEY,
            instrument_id TEXT NOT NULL,
            operator_id TEXT NOT NULL,
            override_reason TEXT NOT NULL,
            override_epoch INTEGER NOT NULL,
            prior_observation_id TEXT,
            prior_effective_from TEXT,
            prior_rate_pct REAL,
            replacement_observation_id TEXT NOT NULL,
            replacement_effective_from TEXT NOT NULL,
            replacement_rate_pct REAL NOT NULL,
            dependent_updates_json TEXT NOT NULL DEFAULT '[]',
            created_at TEXT NOT NULL
        );
    """)

    # Reconcile legacy tables when present (including dual-populated legacy + canonical conflict cases)
    has_leg_inst = _table_exists_on_cursor(cursor, "fixed_savings_instruments", is_pg=is_pg)
    has_leg_hist = _table_exists_on_cursor(cursor, "savings_rate_history", is_pg=is_pg)
    has_leg_tax = _table_exists_on_cursor(cursor, "regulatory_tax_rule_versions", is_pg=is_pg)
    reconciled_conflicts = 0

    def _ensure_obs_for_row(
        row_d: Dict[str, Any],
        *,
        origin_tag: str,
        change_reason: str,
        status_tag: str,
        eff_to: Optional[str] = None,
        sup_at: Optional[str] = None,
        sup_by: Optional[str] = None,
        rev_seq: int = 1,
    ) -> str:
        circ = _extract_circular_ref(
            row_d,
            str(row_d.get("notes_json") or "{}"),
            str(row_d.get("source_authority") or ""),
        )
        snap_j, mat_h = compute_material_terms_snapshot(row_d, rate_circular_ref=circ)
        obs_id_val = compute_observation_id(
            instrument_id=str(row_d["instrument_id"]),
            effective_from=str(row_d["effective_from"])[:10],
            base_rate_pct=float(row_d["base_rate_pct"]),
            senior_citizen_bonus_bps=float(row_d.get("senior_citizen_bonus_bps") or 0.0),
            rate_circular_ref=circ,
            source_authority=str(row_d["source_authority"]),
            source_url=str(row_d["source_url"]),
            material_terms_hash=mat_h,
            override_epoch=int(row_d.get("override_epoch") or 0),
        )
        cursor.execute(
            f"""
            INSERT INTO savings_rate_observations (
                observation_id, instrument_id, base_rate_pct, senior_citizen_bonus_bps,
                effective_from, effective_to, revision_seq, rate_circular_ref,
                source_authority, source_url, material_terms_hash, terms_snapshot_json,
                change_reason, observation_status, origin_db, observed_at,
                superseded_at, superseded_by_observation_id, evidence_sha256
            ) VALUES ({", ".join([p] * 19)})
            ON CONFLICT (observation_id) DO UPDATE SET
                effective_to = COALESCE(savings_rate_observations.effective_to, {excl}.effective_to),
                superseded_at = COALESCE(savings_rate_observations.superseded_at, {excl}.superseded_at),
                superseded_by_observation_id = COALESCE(
                    savings_rate_observations.superseded_by_observation_id,
                    {excl}.superseded_by_observation_id
                ),
                observation_status = CASE
                    WHEN {excl}.superseded_at IS NOT NULL THEN {excl}.observation_status
                    ELSE savings_rate_observations.observation_status
                END;
            """,
            (
                obs_id_val,
                str(row_d["instrument_id"]),
                round(float(row_d["base_rate_pct"]), 4),
                round(float(row_d.get("senior_citizen_bonus_bps") or 0.0), 2),
                str(row_d["effective_from"])[:10],
                eff_to,
                rev_seq,
                circ,
                str(row_d["source_authority"]),
                str(row_d["source_url"]),
                mat_h,
                snap_j,
                change_reason,
                status_tag,
                origin_tag,
                str(row_d.get("updated_at") or now_iso),
                sup_at,
                sup_by,
                None,
            ),
        )
        return obs_id_val

    cols36_sql = ", ".join(_BASE_36_COLS)
    if has_leg_inst:
        cursor.execute(f"SELECT {cols36_sql} FROM fixed_savings_instruments;")
        leg_map = {str(r[0]): _row36_to_dict(r) for r in cursor.fetchall()}
        cursor.execute(f"SELECT {cols36_sql}, override_epoch FROM savings_instruments;")
        can_map: Dict[str, Dict[str, Any]] = {}
        for r in cursor.fetchall():
            d = _row36_to_dict(r[:36])
            d["override_epoch"] = int(r[36] or 0)
            can_map[str(r[0])] = d

        for inst_id in sorted(set(leg_map) | set(can_map)):
            leg_d = leg_map.get(inst_id)
            can_d = can_map.get(inst_id)
            if leg_d and not can_d:
                leg_eff = str(leg_d["effective_from"])[:10]
                st_tag = "SCHEDULED_FUTURE" if leg_eff > ref_iso else "ACTIVE"
                winner = dict(leg_d)
                winner["override_epoch"] = 0
                win_obs = _ensure_obs_for_row(
                    winner,
                    origin_tag="legacy_v049",
                    change_reason="MIGRATED_FROM_LEGACY_V049",
                    status_tag=st_tag,
                )
            elif can_d and not leg_d:
                can_eff = str(can_d["effective_from"])[:10]
                st_tag = "SCHEDULED_FUTURE" if can_eff > ref_iso else "ACTIVE"
                winner = dict(can_d)
                win_obs = _ensure_obs_for_row(
                    winner,
                    origin_tag="canonical",
                    change_reason="CANONICAL_EXISTING",
                    status_tag=st_tag,
                )
            else:
                assert leg_d is not None and can_d is not None
                leg_eff = str(leg_d["effective_from"])[:10]
                can_eff = str(can_d["effective_from"])[:10]
                leg_obs = _ensure_obs_for_row(
                    leg_d,
                    origin_tag="legacy_v049",
                    change_reason="MIGRATED_FROM_LEGACY_V049",
                    status_tag="SCHEDULED_FUTURE" if leg_eff > ref_iso else "ACTIVE",
                )
                can_obs = _ensure_obs_for_row(
                    can_d,
                    origin_tag="canonical",
                    change_reason="CANONICAL_EXISTING",
                    status_tag="SCHEDULED_FUTURE" if can_eff > ref_iso else "ACTIVE",
                    rev_seq=2 if leg_eff == can_eff else 1,
                )

                # Choose active winner deterministically among candidates effective <= ref_iso
                cands = [
                    (leg_d, leg_obs, 0),
                    (can_d, can_obs, 1),
                ]
                due_cands = [c for c in cands if str(c[0]["effective_from"])[:10] <= ref_iso]
                pool = due_cands if due_cands else cands
                pool.sort(
                    key=lambda x: (
                        str(x[0]["effective_from"])[:10],
                        str(x[0].get("updated_at") or ""),
                        x[2],
                    )
                )
                winner_raw, win_obs, _ = pool[-1]
                loser_raw, lose_obs, _ = pool[0]
                winner = dict(winner_raw)
                winner.setdefault("override_epoch", int(can_d.get("override_epoch") or 0))

                if lose_obs != win_obs:
                    reconciled_conflicts += 1
                    lose_eff = str(loser_raw["effective_from"])[:10]
                    win_eff = str(winner["effective_from"])[:10]
                    if lose_eff == win_eff:
                        cursor.execute(
                            f"""
                            UPDATE savings_rate_observations
                            SET superseded_at = {p},
                                superseded_by_observation_id = {p},
                                observation_status = 'SUPERSEDED_CONFLICT'
                            WHERE observation_id = {p};
                            """,
                            (now_iso, win_obs, lose_obs),
                        )
                    elif lose_eff < win_eff and win_eff <= ref_iso:
                        cursor.execute(
                            f"""
                            UPDATE savings_rate_observations
                            SET effective_to = COALESCE(effective_to, {p}),
                                observation_status = 'HISTORICAL'
                            WHERE observation_id = {p};
                            """,
                            (win_eff, lose_obs),
                        )

            all_38_cols = (*_BASE_36_COLS, "override_epoch", "active_observation_id")
            ph_38 = ", ".join([p] * len(all_38_cols))
            upd_38 = ", ".join(
                [f"{c} = {excl}.{c}" for c in all_38_cols if c != "instrument_id"]
            )
            vals_38 = tuple(winner.get(c) for c in _BASE_36_COLS) + (
                int(winner.get("override_epoch") or 0),
                win_obs,
            )
            cursor.execute(
                f"INSERT INTO savings_instruments ({', '.join(all_38_cols)}) VALUES ({ph_38}) "
                f"ON CONFLICT (instrument_id) DO UPDATE SET {upd_38};",
                vals_38,
            )

    if has_leg_hist:
        cursor.execute(f"SELECT {cols36_sql}, active_observation_id FROM savings_instruments;")
        cur_inst_by_id: Dict[str, Tuple[Dict[str, Any], Optional[str]]] = {
            str(r[0]): (_row36_to_dict(r[:36]), str(r[36]) if r[36] else None)
            for r in cursor.fetchall()
        }
        cursor.execute("""
            SELECT instrument_id, base_rate_pct, senior_citizen_bonus_bps,
                   effective_from, effective_to, source_authority, source_url, recorded_at
            FROM savings_rate_history
            ORDER BY id ASC;
        """)
        for hr in cursor.fetchall():
            h_inst = str(hr[0])
            h_rate = round(float(hr[1] or 0.0), 4)
            h_bonus = round(float(hr[2] or 0.0), 2)
            h_eff = str(hr[3])[:10]
            h_eff_to = str(hr[4])[:10] if hr[4] else None
            h_auth = str(hr[5] or "")
            h_url = str(hr[6] or "")
            h_rec = str(hr[7] or now_iso)

            inst_base, active_oid = cur_inst_by_id.get(h_inst, ({}, None))
            synth = dict(inst_base)
            synth.update(
                {
                    "instrument_id": h_inst,
                    "base_rate_pct": h_rate,
                    "senior_citizen_bonus_bps": h_bonus,
                    "effective_from": h_eff,
                    "source_authority": h_auth,
                    "source_url": h_url,
                    "updated_at": h_rec,
                }
            )
            snap_j, mat_h = compute_material_terms_snapshot(synth, rate_circular_ref=h_auth)
            h_obs_id = compute_observation_id(
                instrument_id=h_inst,
                effective_from=h_eff,
                base_rate_pct=h_rate,
                senior_citizen_bonus_bps=h_bonus,
                rate_circular_ref=h_auth,
                source_authority=h_auth,
                source_url=h_url,
                material_terms_hash=mat_h,
                override_epoch=0,
            )
            cur_eff = str(inst_base.get("effective_from") or "")[:10] if inst_base else ""
            if cur_eff and h_eff < cur_eff:
                h_eff_to = h_eff_to or cur_eff

            # If fixed_savings_instruments already created the exact (instrument_id, effective_from, rate, bonus, url)
            # observation, enrich effective_to rather than duplicating the same legacy history point.
            cursor.execute(
                f"""
                SELECT observation_id FROM savings_rate_observations
                WHERE instrument_id = {p}
                  AND effective_from = {p}
                  AND ABS(base_rate_pct - {p}) < 1e-6
                  AND ABS(senior_citizen_bonus_bps - {p}) < 1e-6
                  AND source_url = {p}
                LIMIT 1;
                """,
                (h_inst, h_eff, h_rate, h_bonus, h_url),
            )
            existing_hist_obs = cursor.fetchone()
            if existing_hist_obs:
                if h_eff_to:
                    cursor.execute(
                        f"UPDATE savings_rate_observations SET effective_to = COALESCE(effective_to, {p}) WHERE observation_id = {p};",
                        (h_eff_to, str(existing_hist_obs[0])),
                    )
                continue

            sup_at_val: Optional[str] = None
            sup_by_val: Optional[str] = None
            if h_eff > ref_iso:
                st_val = "SCHEDULED_FUTURE"
            elif cur_eff and h_eff < cur_eff:
                st_val = "HISTORICAL"
            elif cur_eff and h_eff == cur_eff and active_oid and active_oid != h_obs_id:
                sup_at_val = now_iso
                sup_by_val = active_oid
                st_val = "SUPERSEDED_CONFLICT"
            elif h_eff_to:
                st_val = "HISTORICAL"
            else:
                st_val = "ACTIVE"

            cursor.execute(
                f"""
                INSERT INTO savings_rate_observations (
                    observation_id, instrument_id, base_rate_pct, senior_citizen_bonus_bps,
                    effective_from, effective_to, revision_seq, rate_circular_ref,
                    source_authority, source_url, material_terms_hash, terms_snapshot_json,
                    change_reason, observation_status, origin_db, observed_at,
                    superseded_at, superseded_by_observation_id, evidence_sha256
                ) VALUES ({", ".join([p] * 19)})
                ON CONFLICT (observation_id) DO NOTHING;
                """,
                (
                    h_obs_id,
                    h_inst,
                    h_rate,
                    h_bonus,
                    h_eff,
                    h_eff_to,
                    1,
                    h_auth,
                    h_auth,
                    h_url,
                    mat_h,
                    snap_j,
                    "MIGRATED_FROM_LEGACY_HISTORY",
                    st_val,
                    "legacy_v049",
                    h_rec,
                    sup_at_val,
                    sup_by_val,
                    None,
                ),
            )

    if has_leg_tax:
        cursor.execute("""
            SELECT rule_version, finance_act_label, effective_from, effective_to,
                   rules_json, source_authority, source_url, updated_at
            FROM regulatory_tax_rule_versions;
        """)
        leg_tax_rows = cursor.fetchall()
        cursor.execute("SELECT rule_version, updated_at FROM tax_rule_registry;")
        can_tax_ts = {str(r[0]): str(r[1] or "") for r in cursor.fetchall()}
        for tr in leg_tax_rows:
            rv = str(tr[0])
            leg_ts = str(tr[7] or "")
            if rv not in can_tax_ts or leg_ts > can_tax_ts[rv]:
                cursor.execute(
                    f"""
                    INSERT INTO tax_rule_registry (
                        rule_version, finance_act_label, effective_from, effective_to,
                        rules_json, source_authority, source_url, updated_at
                    ) VALUES ({", ".join([p] * 8)})
                    ON CONFLICT (rule_version) DO UPDATE SET
                        finance_act_label = {excl}.finance_act_label,
                        effective_from = {excl}.effective_from,
                        effective_to = {excl}.effective_to,
                        rules_json = {excl}.rules_json,
                        source_authority = {excl}.source_authority,
                        source_url = {excl}.source_url,
                        updated_at = {excl}.updated_at;
                    """,
                    tuple(tr),
                )

    # Backfill active_observation_id on any savings_instruments row missing one
    cursor.execute(f"SELECT {cols36_sql}, override_epoch, active_observation_id FROM savings_instruments;")
    for r in cursor.fetchall():
        inst_id_b = str(r[0])
        cur_act_obs = r[37]
        if cur_act_obs:
            continue
        cursor.execute(
            f"""
            SELECT observation_id
            FROM savings_rate_observations
            WHERE instrument_id = {p} AND superseded_at IS NULL AND effective_from <= {p}
            ORDER BY effective_from DESC, revision_seq DESC
            LIMIT 1;
            """,
            (inst_id_b, ref_iso),
        )
        found = cursor.fetchone()
        if found and found[0]:
            obs_to_link = str(found[0])
        else:
            d_b = _row36_to_dict(r[:36])
            d_b["override_epoch"] = int(r[36] or 0)
            obs_to_link = _ensure_obs_for_row(
                d_b,
                origin_tag="postgres" if is_pg else "local",
                change_reason="BACKFILLED_ACTIVE_OBSERVATION",
                status_tag="SCHEDULED_FUTURE" if str(d_b["effective_from"])[:10] > ref_iso else "ACTIVE",
            )
        cursor.execute(
            f"UPDATE savings_instruments SET active_observation_id = {p} WHERE instrument_id = {p};",
            (obs_to_link, inst_id_b),
        )

    # Create canonical indexes
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_savings_instruments_cat ON savings_instruments(category, is_active);"
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_savings_instruments_ticker ON savings_instruments(issuer_ticker);"
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_savings_rate_obs_inst ON savings_rate_observations(instrument_id, effective_from DESC, revision_seq DESC);"
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_savings_rate_obs_sched ON savings_rate_observations(observation_status, effective_from);"
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_savings_override_audit_inst ON savings_override_audit_log(instrument_id, override_epoch DESC);"
    )

    # In-transaction preservation verification + legacy mirror sync (retains legacy tables for rollback)
    preservation = _verify_legacy_preservation_on_cursor(cursor, is_pg=is_pg)
    if not preservation["valid"]:
        raise RuntimeError(
            f"Savings migration preservation check failed; rolling back without dropping tables: {preservation['errors']}"
        )

    if has_leg_inst:
        cursor.execute(f"SELECT {cols36_sql} FROM savings_instruments;")
        for r in cursor.fetchall():
            _mirror_legacy_v049_tables_on_cursor(
                cursor,
                is_pg=is_pg,
                instrument_row_dict=_row36_to_dict(r),
            )
    if has_leg_tax:
        cursor.execute("""
            SELECT rule_version, finance_act_label, effective_from, effective_to,
                   rules_json, source_authority, source_url, updated_at
            FROM tax_rule_registry;
        """)
        for tr in cursor.fetchall():
            _mirror_legacy_v049_tables_on_cursor(
                cursor,
                is_pg=is_pg,
                tax_rule_dict={
                    "rule_version": tr[0],
                    "finance_act_label": tr[1],
                    "effective_from": tr[2],
                    "effective_to": tr[3],
                    "rules_json": tr[4],
                    "source_authority": tr[5],
                    "source_url": tr[6],
                    "updated_at": tr[7],
                },
            )

    return {
        "reconciled_conflicts": reconciled_conflicts,
        "legacy_tables_retained": [
            t
            for t, flag in (
                ("fixed_savings_instruments", has_leg_inst),
                ("savings_rate_history", has_leg_hist),
                ("regulatory_tax_rule_versions", has_leg_tax),
            )
            if flag
        ],
        "preservation": preservation,
    }


def _verify_legacy_preservation_on_cursor(cursor: Any, *, is_pg: bool) -> Dict[str, Any]:
    """Verifies 100% row and field preservation between retained legacy v049 tables and canonical v051 tables."""
    p = "%s" if is_pg else "?"
    errors: List[str] = []
    cols36_sql = ", ".join(_BASE_36_COLS)

    if _table_exists_on_cursor(cursor, "fixed_savings_instruments", is_pg=is_pg):
        cursor.execute(f"SELECT {cols36_sql} FROM fixed_savings_instruments;")
        leg_rows = [_row36_to_dict(r) for r in cursor.fetchall()]
        cursor.execute(f"SELECT {cols36_sql} FROM savings_instruments;")
        can_by_id = {str(r[0]): _row36_to_dict(r) for r in cursor.fetchall()}

        for leg in leg_rows:
            iid = str(leg["instrument_id"])
            if iid not in can_by_id:
                errors.append(f"Missing instrument_id {iid} in savings_instruments.")
                continue
            _, leg_hash = compute_material_terms_snapshot(leg)
            _, can_hash = compute_material_terms_snapshot(can_by_id[iid])
            same_active = (
                leg_hash == can_hash
                and abs(float(leg["base_rate_pct"]) - float(can_by_id[iid]["base_rate_pct"])) < 1e-6
                and str(leg["effective_from"])[:10] == str(can_by_id[iid]["effective_from"])[:10]
            )
            if not same_active:
                cursor.execute(
                    f"""
                    SELECT COUNT(*) FROM savings_rate_observations
                    WHERE instrument_id = {p}
                      AND effective_from = {p}
                      AND ABS(base_rate_pct - {p}) < 1e-6
                      AND material_terms_hash = {p};
                    """,
                    (iid, str(leg["effective_from"])[:10], float(leg["base_rate_pct"]), leg_hash),
                )
                if int(cursor.fetchone()[0] or 0) == 0:
                    errors.append(
                        f"Legacy row {iid} ({leg['effective_from']} @ {leg['base_rate_pct']}%) not preserved in observations."
                    )

    if _table_exists_on_cursor(cursor, "savings_rate_history", is_pg=is_pg):
        cursor.execute(
            "SELECT instrument_id, effective_from, base_rate_pct FROM savings_rate_history;"
        )
        for hr in cursor.fetchall():
            cursor.execute(
                f"""
                SELECT COUNT(*) FROM savings_rate_observations
                WHERE instrument_id = {p}
                  AND effective_from = {p}
                  AND ABS(base_rate_pct - {p}) < 1e-6;
                """,
                (str(hr[0]), str(hr[1])[:10], float(hr[2] or 0.0)),
            )
            if int(cursor.fetchone()[0] or 0) == 0:
                errors.append(
                    f"Legacy rate history row {hr[0]} ({hr[1]} @ {hr[2]}%) missing from savings_rate_observations."
                )

    if _table_exists_on_cursor(cursor, "regulatory_tax_rule_versions", is_pg=is_pg):
        cursor.execute("SELECT rule_version FROM regulatory_tax_rule_versions;")
        leg_vers = {str(r[0]) for r in cursor.fetchall()}
        cursor.execute("SELECT rule_version FROM tax_rule_registry;")
        can_vers = {str(r[0]) for r in cursor.fetchall()}
        missing_tax = sorted(leg_vers - can_vers)
        if missing_tax:
            errors.append(f"Missing tax rule versions in tax_rule_registry: {missing_tax}")

    return {"valid": len(errors) == 0, "errors": errors}


def validate_legacy_savings_migration_preservation(conn: Optional[Any] = None) -> Dict[str, Any]:
    """Public verifier proving 100% row/field preservation before any post-soak legacy table drop."""
    owns = conn is None
    active = conn or get_db_connection()
    cursor = active.cursor()
    is_pg = bool(get_supabase_url()) or is_postgres_connection(active)
    try:
        return _verify_legacy_preservation_on_cursor(cursor, is_pg=is_pg)
    finally:
        cursor.close()
        if owns:
            active.close()


def acquire_savings_write_locks(
    active_conn: Any,
    cursor: Any,
    *,
    lock_universe: bool = False,
    instrument_ids: Optional[List[str]] = None,
    is_pg: bool,
    owns_conn: bool,
) -> List[str]:
    """Serializes a multi-instrument writer against per-instrument writers.

    PostgreSQL: takes the same per-instrument advisory xact locks used by
    `_acquire_instrument_write_locks`, in ascending key order, so it can never
    AB/BA-deadlock with a single-instrument writer. `lock_universe=True` locks
    every canonical and legacy instrument id (used by destructive cutovers that
    must verify-then-mutate the whole savings universe atomically).
    SQLite: opens a `BEGIN IMMEDIATE` write transaction when this call owns the
    connection (database-level write lock already covers the universe).
    Returns the sorted list of advisory keys taken (empty on SQLite).
    """
    if not is_pg:
        if owns_conn and not getattr(active_conn, "in_transaction", False):
            cursor.execute("BEGIN IMMEDIATE;")
        return []

    keys = {str(i) for i in (instrument_ids or []) if i}
    if lock_universe:
        for tbl in ("savings_instruments", "fixed_savings_instruments"):
            if _table_exists_on_cursor(cursor, tbl, is_pg=is_pg):
                cursor.execute(f"SELECT instrument_id FROM {tbl};")
                keys.update(str(r[0]) for r in cursor.fetchall() if r and r[0])
    ordered = sorted(keys)
    for lock_key in ordered:
        cursor.execute(
            "SELECT pg_advisory_xact_lock(%s, hashtext(%s));",
            (SAVINGS_ADVISORY_LOCK_NS, lock_key),
        )
    return ordered


def drop_retired_v049_savings_tables(
    *,
    confirm: bool = False,
    conn: Optional[Any] = None,
) -> Dict[str, Any]:
    """Explicit post-soak cutover helper: drops retained v049 legacy tables ONLY after confirm=True and validation."""
    if not confirm:
        raise ValueError("Refusing to drop retained v049 tables without explicit confirm=True.")
    owns = conn is None
    active = conn or get_db_connection()
    cursor = active.cursor()
    is_pg = bool(get_supabase_url()) or is_postgres_connection(active)
    try:
        acquire_savings_write_locks(
            active,
            cursor,
            lock_universe=True,
            is_pg=is_pg,
            owns_conn=owns,
        )
        check = _verify_legacy_preservation_on_cursor(cursor, is_pg=is_pg)
        if not check["valid"]:
            raise RuntimeError(
                f"Cannot drop retained v049 tables; preservation check failed: {check['errors']}"
            )
        dropped: List[str] = []
        for tbl in (
            "fixed_savings_instruments",
            "savings_rate_history",
            "regulatory_tax_rule_versions",
        ):
            if _table_exists_on_cursor(cursor, tbl, is_pg=is_pg):
                cursor.execute(f"DROP TABLE {tbl};")
                dropped.append(tbl)
        if owns:
            active.commit()
        return {"status": "DROPPED", "dropped_tables": dropped}
    except Exception:
        if owns:
            active.rollback()
        raise
    finally:
        cursor.close()
        if owns:
            active.close()


def _ensure_tables_ready(conn: Any) -> None:
    """Guarantees v049/v050/v051 canonical tables exist before write/seeded-read paths run."""
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT override_epoch, active_observation_id FROM savings_instruments LIMIT 1;")
        cursor.execute("SELECT observation_id, observation_status FROM savings_rate_observations LIMIT 1;")
        cursor.execute("SELECT 1 FROM tax_rule_registry LIMIT 1;")
        cursor.execute("SELECT 1 FROM savings_override_audit_log LIMIT 1;")
    except Exception as probe_err:
        logger.debug("savings_instruments schema probe triggered init_db: %s", probe_err)
        try:
            conn.rollback()
        except Exception as rb_err:
            logger.debug("Rollback before init_db notice: %s", rb_err)
        init_db(force=True)
    finally:
        cursor.close()


def load_baseline_savings_payload(file_path: Optional[Path] = None) -> Dict[str, Any]:
    """Loads curated baseline JSON payload from disk."""
    target = Path(file_path) if file_path else BASELINE_SAVINGS_JSON_PATH
    if not target.exists():
        logger.error("Savings baseline file missing at %s", target)
        return {"instruments": [], "tax_rule_versions": []}
    try:
        return json.loads(target.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.error("Failed reading savings baseline JSON %s: %s", target, exc)
        return {"instruments": [], "tax_rule_versions": []}


def compute_staleness_badge(
    instrument: Dict[str, Any],
    reference_date: Optional[str] = None,
) -> Dict[str, Any]:
    """Computes provenance & freshness status without mutating effective_from.

    Enforced policy:
    - Any unapproved publisher hostname, authority mismatch, non-HTTPS URL, or missing/future
      (>366d) effective_from immediately escalates to UNVERIFIED_PROVENANCE.
    - Any instrument with next_review_date in the past: >0..45d -> REVIEW_DUE, >45d -> STALE_TARIFF.
    - SMALL_SAVINGS / SOVEREIGN_DIRECT: FRESH while within active <=100d future next_review_date
      window; otherwise >95d -> REVIEW_DUE, >180d -> STALE_TARIFF.
    - RETIREMENT_PENSION: MARKET_LINKED_NAV uses >45d -> REVIEW_DUE, >120d -> STALE_TARIFF;
      statutory EPF uses active <=370d future next_review_date window (up to <=420d max age),
      otherwise >365d -> REVIEW_DUE, >420d -> STALE_TARIFF.
    - SCHEDULED_BANK_FD / SFB_FD / CORPORATE_FD / HIGH_YIELD_SAVINGS: anchored on
      max(effective_from, last_tariff_verified_on), >45d -> REVIEW_DUE, >120d -> STALE_TARIFF.
    """
    ref_dt = _parse_iso_date(reference_date) or datetime.now(IST).date()
    eff_dt = _parse_iso_date(instrument.get("effective_from"))
    rev_dt = _parse_iso_date(instrument.get("next_review_date"))

    if eff_dt is None or (eff_dt - ref_dt).days > 366 or not is_valid_savings_provenance(instrument):
        return {
            "status": "UNVERIFIED_PROVENANCE",
            "badge_label": "Provenance Unverified (Withheld)",
            "age_days": max(0, (ref_dt - eff_dt).days) if eff_dt else 9999,
            "days_since_verified": 9999,
            "review_overdue": True,
        }

    notes = instrument.get("notes")
    if not isinstance(notes, dict):
        try:
            notes = json.loads(instrument.get("notes_json") or "{}")
        except Exception as exc:
            logger.debug("Notes JSON parse fallback in compute_staleness_badge: %s", exc)
            notes = {}

    raw_verified_dt = _parse_iso_date(notes.get("last_tariff_verified_on"))
    verified_dt = raw_verified_dt if (raw_verified_dt and raw_verified_dt <= ref_dt) else None
    anchor_dt = max(filter(None, [eff_dt, verified_dt]), default=eff_dt)
    age_days = max(0, (ref_dt - eff_dt).days)
    since_verified_days = max(0, (ref_dt - anchor_dt).days) if anchor_dt else age_days
    category = str(instrument.get("category") or "").upper()
    rate_type = str(instrument.get("rate_type") or "").upper()

    if rev_dt and ref_dt > rev_dt:
        overdue_days = (ref_dt - rev_dt).days
        if overdue_days > 45:
            return {
                "status": "STALE_TARIFF",
                "badge_label": f"Reset Overdue >45d ({overdue_days}d past {rev_dt.isoformat()})",
                "age_days": age_days,
                "days_since_verified": since_verified_days,
                "review_overdue": True,
            }
        return {
            "status": "REVIEW_DUE",
            "badge_label": f"Reset Review Due ({overdue_days}d past {rev_dt.isoformat()})",
            "age_days": age_days,
            "days_since_verified": since_verified_days,
            "review_overdue": True,
        }

    if category in STATUTORY_QUARTERLY_CATEGORIES:
        has_active_quarter_window = bool(rev_dt and 0 <= (rev_dt - ref_dt).days <= 100)
        if not has_active_quarter_window:
            if since_verified_days > 180:
                return {
                    "status": "STALE_TARIFF",
                    "badge_label": f"Statutory Tariff Unverified ({since_verified_days}d since check)",
                    "age_days": age_days,
                    "days_since_verified": since_verified_days,
                    "review_overdue": True,
                }
            if since_verified_days > 95:
                return {
                    "status": "REVIEW_DUE",
                    "badge_label": f"Quarterly Review Check Due ({since_verified_days}d)",
                    "age_days": age_days,
                    "days_since_verified": since_verified_days,
                    "review_overdue": True,
                }
        return {
            "status": "FRESH",
            "badge_label": f"Statutory Notification ({instrument.get('effective_from') or 'Verified'})",
            "age_days": age_days,
            "days_since_verified": since_verified_days,
            "review_overdue": False,
        }

    if category == "RETIREMENT_PENSION":
        if rate_type == "MARKET_LINKED_NAV":
            stale_limit, review_limit = 120, 45
        else:
            has_active_annual_window = bool(rev_dt and 0 <= (rev_dt - ref_dt).days <= 370)
            if has_active_annual_window and since_verified_days <= 420:
                return {
                    "status": "FRESH",
                    "badge_label": f"Statutory Notification ({instrument.get('effective_from') or 'Verified'})",
                    "age_days": age_days,
                    "days_since_verified": since_verified_days,
                    "review_overdue": False,
                }
            stale_limit, review_limit = 420, 365
        if since_verified_days > stale_limit:
            return {
                "status": "STALE_TARIFF",
                "badge_label": f"Retirement Benchmark Stale ({since_verified_days}d since check)",
                "age_days": age_days,
                "days_since_verified": since_verified_days,
                "review_overdue": True,
            }
        if since_verified_days > review_limit:
            return {
                "status": "REVIEW_DUE",
                "badge_label": f"Retirement Benchmark Check Due ({since_verified_days}d)",
                "age_days": age_days,
                "days_since_verified": since_verified_days,
                "review_overdue": True,
            }
        return {
            "status": "FRESH",
            "badge_label": f"Statutory Notification ({instrument.get('effective_from') or 'Verified'})",
            "age_days": age_days,
            "days_since_verified": since_verified_days,
            "review_overdue": False,
        }

    if since_verified_days > 120:
        return {
            "status": "STALE_TARIFF",
            "badge_label": f"Tariff Unverified ({since_verified_days}d since check)",
            "age_days": age_days,
            "days_since_verified": since_verified_days,
            "review_overdue": True,
        }

    if since_verified_days > 45:
        return {
            "status": "REVIEW_DUE",
            "badge_label": f"Tariff Check >45d ({since_verified_days}d)",
            "age_days": age_days,
            "days_since_verified": since_verified_days,
            "review_overdue": True,
        }

    return {
        "status": "FRESH",
        "badge_label": f"Verified Tariff (eff. {instrument.get('effective_from') or 'Current'})",
        "age_days": age_days,
        "days_since_verified": since_verified_days,
        "review_overdue": False,
    }


def _hydrate_instrument_row(
    row: Any,
    *,
    reference_date: Optional[str] = None,
) -> Dict[str, Any]:
    payout_raw = row[16] or '["CUMULATIVE"]'
    notes_raw = row[33] or "{}"
    try:
        payout_options = json.loads(payout_raw) if isinstance(payout_raw, str) else list(payout_raw)
    except Exception as exc:
        logger.warning("Malformed payout_options_json for %s: %s", row[0], exc)
        payout_options = ["CUMULATIVE"]
    try:
        notes = json.loads(notes_raw) if isinstance(notes_raw, str) else dict(notes_raw)
    except Exception as exc:
        logger.warning("Malformed notes_json for %s: %s", row[0], exc)
        notes = {}

    category = str(row[2])
    override_epoch_val = int(row[36] or 0) if len(row) > 36 and row[36] is not None else 0
    active_obs_id_val = str(row[37]) if len(row) > 37 and row[37] else None

    item: Dict[str, Any] = {
        "instrument_id": str(row[0]),
        "scheme_name": str(row[1]),
        "category": category,
        "category_label": SAVINGS_CATEGORY_LABELS.get(category, category.replace("_", " ").title()),
        "issuer_name": str(row[3]),
        "issuer_ticker": str(row[4]).strip().upper() if row[4] else None,
        "issuer_type": str(row[5]),
        "sovereign_backed": bool(int(row[6] or 0)),
        "dicgc_insured": bool(int(row[7] or 0)),
        "dicgc_limit_inr": float(row[8] or 0.0),
        "credit_rating": str(row[9] or "UNRATED"),
        "base_rate_pct": float(row[10] or 0.0),
        "senior_citizen_bonus_bps": float(row[11] or 0.0),
        "senior_rate_pct": round(float(row[10] or 0.0) + (float(row[11] or 0.0) / 100.0), 4),
        "rate_type": str(row[12] or "FIXED"),
        "floating_benchmark": str(row[13]) if row[13] else None,
        "floating_spread_bps": float(row[14] or 0.0),
        "compounding_freq": str(row[15] or "QUARTERLY"),
        "payout_options_json": payout_raw if isinstance(payout_raw, str) else json.dumps(payout_options),
        "payout_options": payout_options,
        "tenure_min_months": int(row[17] or 0),
        "tenure_max_months": int(row[18] or 0),
        "lock_in_months": int(row[19] or 0),
        "premature_exit_rule": str(row[20] or ""),
        "min_investment_inr": float(row[21] or 0.0),
        "max_investment_inr": float(row[22]) if row[22] is not None else None,
        "tax_section_80c_eligible": bool(int(row[23] or 0)),
        "interest_taxability": str(row[24] or "SLAB_TAXABLE"),
        "maturity_taxability": str(row[25] or "EXEMPT"),
        "tds_applicable": bool(int(row[26] or 0)),
        "tds_threshold_regular_inr": float(row[27] or 0.0),
        "tds_threshold_senior_inr": float(row[28] or 0.0),
        "effective_from": str(row[29]),
        "next_review_date": str(row[30]) if row[30] else None,
        "source_authority": str(row[31]),
        "source_url": str(row[32]),
        "notes_json": notes_raw if isinstance(notes_raw, str) else json.dumps(notes),
        "notes": notes,
        "is_active": bool(int(row[34] if row[34] is not None else 1)),
        "updated_at": str(row[35] or ""),
        "override_epoch": override_epoch_val,
        "active_observation_id": active_obs_id_val,
    }
    item["bank_charter_key"] = str(
        notes.get("bank_charter_key")
        or item["issuer_ticker"]
        or re.sub(r"[^A-Z0-9]+", "_", item["issuer_name"].upper()).strip("_")
    )
    item["staleness"] = compute_staleness_badge(item, reference_date=reference_date)
    return item


_SELECT_COLS_36 = """
    instrument_id, scheme_name, category, issuer_name, issuer_ticker, issuer_type,
    sovereign_backed, dicgc_insured, dicgc_limit_inr, credit_rating,
    base_rate_pct, senior_citizen_bonus_bps, rate_type, floating_benchmark,
    floating_spread_bps, compounding_freq, payout_options_json,
    tenure_min_months, tenure_max_months, lock_in_months, premature_exit_rule,
    min_investment_inr, max_investment_inr, tax_section_80c_eligible,
    interest_taxability, maturity_taxability, tds_applicable,
    tds_threshold_regular_inr, tds_threshold_senior_inr,
    effective_from, next_review_date, source_authority, source_url,
    notes_json, is_active, updated_at
"""

_SELECT_COLS = """
    instrument_id, scheme_name, category, issuer_name, issuer_ticker, issuer_type,
    sovereign_backed, dicgc_insured, dicgc_limit_inr, credit_rating,
    base_rate_pct, senior_citizen_bonus_bps, rate_type, floating_benchmark,
    floating_spread_bps, compounding_freq, payout_options_json,
    tenure_min_months, tenure_max_months, lock_in_months, premature_exit_rule,
    min_investment_inr, max_investment_inr, tax_section_80c_eligible,
    interest_taxability, maturity_taxability, tds_applicable,
    tds_threshold_regular_inr, tds_threshold_senior_inr,
    effective_from, next_review_date, source_authority, source_url,
    notes_json, is_active, updated_at, override_epoch, active_observation_id
"""


def _extract_circular_ref(item: Dict[str, Any], notes_json: str, source_authority: str) -> str:
    explicit = str(item.get("rate_circular_ref") or "").strip()
    if explicit:
        return explicit
    try:
        notes = json.loads(notes_json or "{}")
        from_notes = str(notes.get("rate_circular_ref") or notes.get("circular_ref") or "").strip()
        if from_notes:
            return from_notes
    except Exception as exc:
        logger.debug("Circular ref parse notice: %s", exc)
    return source_authority


def _acquire_instrument_write_locks(
    cursor: Any,
    active_conn: Any,
    inst_id: str,
    *,
    is_pg: bool,
    owns_conn: bool,
) -> None:
    """Serializes concurrent writers per instrument (and pegged dependents) without AB/BA deadlocks."""
    if is_pg:
        cursor.execute(
            "SELECT instrument_id FROM savings_instruments WHERE rate_type = 'FLOATING_PEGGED' AND floating_benchmark = %s;",
            (inst_id,),
        )
        dep_ids = [str(r[0]) for r in cursor.fetchall() if r and r[0]]
        # SAV-NSC may be inserted before SAV-FRSB-2020 exists; pre-lock known statutory peg pair deterministically
        if inst_id == "SAV-NSC" and "SAV-FRSB-2020" not in dep_ids:
            dep_ids.append("SAV-FRSB-2020")
        for lock_key in sorted(set([inst_id, *dep_ids])):
            cursor.execute(
                "SELECT pg_advisory_xact_lock(%s, hashtext(%s));",
                (SAVINGS_ADVISORY_LOCK_NS, lock_key),
            )
    elif owns_conn and not getattr(active_conn, "in_transaction", False):
        cursor.execute("BEGIN IMMEDIATE;")


def _append_rate_observation_on_cursor(
    cursor: Any,
    *,
    p: str,
    is_pg: bool,
    inst_id: str,
    base_rate_pct: float,
    senior_citizen_bonus_bps: float,
    effective_from: str,
    effective_to: Optional[str],
    rate_circular_ref: str,
    source_authority: str,
    source_url: str,
    material_terms_hash: str,
    terms_snapshot_json: str,
    change_reason: str,
    observation_status: str,
    origin_db: str,
    observed_at: str,
    override_epoch: int = 0,
    evidence_sha256: Optional[str] = None,
    close_prior_dates: bool = True,
    supersede_newer_dates: bool = False,
) -> Tuple[str, int]:
    """Appends an immutable observation with globally unique observation_id PK."""
    obs_id = compute_observation_id(
        instrument_id=inst_id,
        effective_from=effective_from,
        base_rate_pct=base_rate_pct,
        senior_citizen_bonus_bps=senior_citizen_bonus_bps,
        rate_circular_ref=rate_circular_ref,
        source_authority=source_authority,
        source_url=source_url,
        material_terms_hash=material_terms_hash,
        override_epoch=override_epoch,
    )

    # Check if this exact un-superseded observation_id already exists (idempotent replay)
    cursor.execute(
        f"SELECT revision_seq, superseded_at FROM savings_rate_observations WHERE observation_id = {p};",
        (obs_id,),
    )
    exact_existing = cursor.fetchone()
    if exact_existing and exact_existing[1] is None:
        return obs_id, int(exact_existing[0] or 1)

    if close_prior_dates:
        cursor.execute(
            f"""
            UPDATE savings_rate_observations
            SET effective_to = {p},
                observation_status = CASE
                    WHEN observation_status = 'ACTIVE' THEN 'HISTORICAL'
                    ELSE observation_status
                END
            WHERE instrument_id = {p}
              AND effective_to IS NULL
              AND superseded_at IS NULL
              AND effective_from < {p};
            """,
            (effective_from, inst_id, effective_from),
        )

    if supersede_newer_dates:
        cursor.execute(
            f"""
            UPDATE savings_rate_observations
            SET superseded_at = {p},
                superseded_by_observation_id = {p},
                observation_status = 'SUPERSEDED'
            WHERE instrument_id = {p}
              AND superseded_at IS NULL
              AND effective_from > {p};
            """,
            (observed_at, obs_id, inst_id, effective_from),
        )

    cursor.execute(
        f"""
        SELECT observation_id, revision_seq, base_rate_pct, senior_citizen_bonus_bps,
               material_terms_hash, superseded_at, effective_to, observation_status
        FROM savings_rate_observations
        WHERE instrument_id = {p} AND effective_from = {p}
        ORDER BY revision_seq DESC;
        """,
        (inst_id, effective_from),
    )
    existing_revs = cursor.fetchall()
    if existing_revs:
        max_rev = int(existing_revs[0][1] or 1)
        active_revs = [r for r in existing_revs if r[5] is None]
        if active_revs:
            cur_active = active_revs[0]
            cur_obs_id = str(cur_active[0])
            cur_rate = round(float(cur_active[2] or 0.0), 4)
            cur_bonus = round(float(cur_active[3] or 0.0), 2)
            cur_hash = str(cur_active[4] or "")
            cur_eff_to = cur_active[6]
            cur_status = str(cur_active[7] or "ACTIVE")
            if (
                abs(cur_rate - base_rate_pct) < 1e-6
                and abs(cur_bonus - senior_citizen_bonus_bps) < 1e-6
                and (not cur_hash or cur_hash == material_terms_hash)
                and cur_eff_to == effective_to
                and cur_status == observation_status
                and override_epoch == 0
            ):
                return cur_obs_id, int(cur_active[1] or 1)
            cursor.execute(
                f"""
                UPDATE savings_rate_observations
                SET superseded_at = {p},
                    superseded_by_observation_id = {p},
                    observation_status = 'SUPERSEDED'
                WHERE instrument_id = {p}
                  AND effective_from = {p}
                  AND superseded_at IS NULL;
                """,
                (observed_at, obs_id, inst_id, effective_from),
            )
        next_rev = max_rev + 1
    else:
        next_rev = 1

    # If a previously-superseded observation had the exact same hash (e.g. rollback back to an older rate
    # within the same epoch), salt circular ref with revision_seq so observation_id stays strictly immutable.
    if exact_existing and exact_existing[1] is not None:
        obs_id = compute_observation_id(
            instrument_id=inst_id,
            effective_from=effective_from,
            base_rate_pct=base_rate_pct,
            senior_citizen_bonus_bps=senior_citizen_bonus_bps,
            rate_circular_ref=f"{rate_circular_ref}#rev{next_rev}",
            source_authority=source_authority,
            source_url=source_url,
            material_terms_hash=material_terms_hash,
            override_epoch=override_epoch,
        )

    cursor.execute(
        f"""
        INSERT INTO savings_rate_observations (
            observation_id, instrument_id, base_rate_pct, senior_citizen_bonus_bps,
            effective_from, effective_to, revision_seq, rate_circular_ref,
            source_authority, source_url, material_terms_hash, terms_snapshot_json,
            change_reason, observation_status, origin_db, observed_at,
            superseded_at, superseded_by_observation_id, evidence_sha256
        ) VALUES ({", ".join([p] * 19)});
        """,
        (
            obs_id,
            inst_id,
            base_rate_pct,
            senior_citizen_bonus_bps,
            effective_from,
            effective_to,
            next_rev,
            rate_circular_ref,
            source_authority,
            source_url,
            material_terms_hash,
            terms_snapshot_json,
            change_reason,
            observation_status,
            origin_db,
            observed_at,
            None,
            None,
            evidence_sha256,
        ),
    )
    _mirror_legacy_v049_tables_on_cursor(
        cursor,
        is_pg=is_pg,
        observation_row_dict={
            "instrument_id": inst_id,
            "base_rate_pct": base_rate_pct,
            "senior_citizen_bonus_bps": senior_citizen_bonus_bps,
            "effective_from": effective_from,
            "effective_to": effective_to,
            "source_authority": source_authority,
            "source_url": source_url,
            "observed_at": observed_at,
        },
    )
    return obs_id, next_rev


def _schedule_future_pegged_dependents_on_cursor(
    cursor: Any,
    *,
    p: str,
    is_pg: bool,
    benchmark_id: str,
    future_bench_rate: float,
    future_effective_from: str,
    origin_db: str,
    now_iso: str,
) -> List[Dict[str, Any]]:
    """Appends SCHEDULED_FUTURE observations for pegged dependents without mutating active rows today."""
    cols36_sql = ", ".join([f"p.{c}" for c in _BASE_36_COLS])
    cursor.execute(
        f"""
        SELECT {cols36_sql}, p.override_epoch
        FROM savings_instruments p
        WHERE p.rate_type = 'FLOATING_PEGGED'
          AND p.is_active = 1
          AND p.floating_benchmark = {p};
        """,
        (benchmark_id,),
    )
    scheduled: List[Dict[str, Any]] = []
    for row in cursor.fetchall():
        peg_dict = _row36_to_dict(row[:36])
        peg_epoch = int(row[36] or 0)
        peg_id = str(peg_dict["instrument_id"])
        spread_bps = float(peg_dict.get("floating_spread_bps") or 0.0)
        peg_bonus = round(float(peg_dict.get("senior_citizen_bonus_bps") or 0.0), 2)
        expected_rate = round(float(future_bench_rate) + (spread_bps / 100.0), 4)
        peg_auth = str(peg_dict.get("source_authority") or "Reserve Bank of India (RBI Retail Direct)")
        peg_url = str(peg_dict.get("source_url") or "https://rbiretaildirect.org.in")
        circ_ref = _extract_circular_ref(
            {},
            str(peg_dict.get("notes_json") or "{}"),
            f"{peg_auth} (Scheduled +{int(round(spread_bps))} bps to {benchmark_id} eff. {future_effective_from})",
        )
        fut_snap_dict = dict(peg_dict)
        fut_snap_dict["base_rate_pct"] = expected_rate
        fut_snap_dict["effective_from"] = future_effective_from
        snap_json, mat_hash = compute_material_terms_snapshot(
            fut_snap_dict, rate_circular_ref=circ_ref
        )
        obs_id, rev_seq = _append_rate_observation_on_cursor(
            cursor,
            p=p,
            is_pg=is_pg,
            inst_id=peg_id,
            base_rate_pct=expected_rate,
            senior_citizen_bonus_bps=peg_bonus,
            effective_from=future_effective_from,
            effective_to=None,
            rate_circular_ref=circ_ref,
            source_authority=peg_auth,
            source_url=peg_url,
            material_terms_hash=mat_hash,
            terms_snapshot_json=snap_json,
            change_reason=f"SCHEDULED_PEGGED_TO_{benchmark_id}",
            observation_status="SCHEDULED_FUTURE",
            origin_db=origin_db,
            observed_at=now_iso,
            override_epoch=peg_epoch,
            close_prior_dates=False,
            supersede_newer_dates=False,
        )
        scheduled.append(
            {
                "instrument_id": peg_id,
                "scheduled_rate_pct": expected_rate,
                "effective_from": future_effective_from,
                "observation_id": obs_id,
                "revision_seq": rev_seq,
            }
        )
    return scheduled


def _cascade_pegged_dependents_on_cursor(
    cursor: Any,
    *,
    p: str,
    is_pg: bool,
    benchmark_id: Optional[str] = None,
    force_overwrite: bool = False,
    bump_override_epoch: bool = False,
    origin_db: str = "local",
    now_iso: str,
) -> List[Dict[str, Any]]:
    """Propagates FLOATING_PEGGED spreads (e.g. SAV-NSC + 35 bps -> SAV-FRSB-2020) without moving dates backwards."""
    where_bench = f"AND p.floating_benchmark = {p}" if benchmark_id else ""
    params: Tuple[Any, ...] = (benchmark_id,) if benchmark_id else ()
    cols36_p = ", ".join([f"p.{c}" for c in _BASE_36_COLS])
    cursor.execute(
        f"""
        SELECT {cols36_p}, p.override_epoch, p.active_observation_id,
               b.instrument_id, b.base_rate_pct, b.effective_from
        FROM savings_instruments p
        JOIN savings_instruments b ON b.instrument_id = p.floating_benchmark
        WHERE p.rate_type = 'FLOATING_PEGGED' AND p.is_active = 1 AND b.is_active = 1 {where_bench};
        """,
        params,
    )
    dependent_updates: List[Dict[str, Any]] = []
    for row in cursor.fetchall():
        peg_dict = _row36_to_dict(row[:36])
        cur_peg_epoch = int(row[36] or 0)
        prior_peg_obs_id = str(row[37]) if row[37] else None
        bench_id_val = str(row[38])
        bench_rate = float(row[39] or 0.0)
        bench_eff = str(row[40] or "")[:10]

        peg_id = str(peg_dict["instrument_id"])
        cur_peg_rate = round(float(peg_dict["base_rate_pct"] or 0.0), 4)
        spread_bps = float(peg_dict.get("floating_spread_bps") or 0.0)
        peg_bonus = round(float(peg_dict.get("senior_citizen_bonus_bps") or 0.0), 2)
        cur_peg_eff = str(peg_dict["effective_from"] or "")[:10]
        peg_auth = str(peg_dict.get("source_authority") or "Reserve Bank of India (RBI Retail Direct)")
        peg_url = str(peg_dict.get("source_url") or "https://rbiretaildirect.org.in")
        peg_notes_raw = str(peg_dict.get("notes_json") or "{}")

        peg_eff_dt = _parse_iso_date(cur_peg_eff)
        bench_eff_dt = _parse_iso_date(bench_eff)
        if bench_eff_dt is None:
            continue

        # Monotonicity guard: never move a newer pegged row backwards to an older benchmark date unless forced
        if not force_overwrite and peg_eff_dt is not None and peg_eff_dt > bench_eff_dt:
            continue

        target_eff = bench_eff if force_overwrite else max(filter(None, [cur_peg_eff, bench_eff]))
        expected_rate = round(bench_rate + (spread_bps / 100.0), 4)
        if abs(cur_peg_rate - expected_rate) < 1e-6 and target_eff == cur_peg_eff and not bump_override_epoch:
            continue

        new_peg_epoch = (cur_peg_epoch + 1) if bump_override_epoch else cur_peg_epoch
        circ_ref = _extract_circular_ref(
            {},
            peg_notes_raw,
            f"{peg_auth} (Pegged +{int(round(spread_bps))} bps to {bench_id_val} eff. {target_eff})",
        )
        updated_peg_dict = dict(peg_dict)
        updated_peg_dict["base_rate_pct"] = expected_rate
        updated_peg_dict["effective_from"] = target_eff
        updated_peg_dict["updated_at"] = now_iso
        snap_json, mat_hash = compute_material_terms_snapshot(
            updated_peg_dict, rate_circular_ref=circ_ref
        )
        new_peg_obs_id, _ = _append_rate_observation_on_cursor(
            cursor,
            p=p,
            is_pg=is_pg,
            inst_id=peg_id,
            base_rate_pct=expected_rate,
            senior_citizen_bonus_bps=peg_bonus,
            effective_from=target_eff,
            effective_to=None,
            rate_circular_ref=circ_ref,
            source_authority=peg_auth,
            source_url=peg_url,
            material_terms_hash=mat_hash,
            terms_snapshot_json=snap_json,
            change_reason=(
                f"FORCED_PEG_CASCADE_FROM_{bench_id_val}"
                if force_overwrite
                else f"PEGGED_CASCADE_FROM_{bench_id_val}"
            ),
            observation_status="ACTIVE",
            origin_db=origin_db,
            observed_at=now_iso,
            override_epoch=new_peg_epoch,
            close_prior_dates=True,
            supersede_newer_dates=bool(force_overwrite and peg_eff_dt and bench_eff_dt < peg_eff_dt),
        )

        if force_overwrite:
            cursor.execute(
                f"""
                UPDATE savings_instruments
                SET base_rate_pct = {p},
                    effective_from = {p},
                    updated_at = {p},
                    override_epoch = {p},
                    active_observation_id = {p}
                WHERE instrument_id = {p};
                """,
                (expected_rate, target_eff, now_iso, new_peg_epoch, new_peg_obs_id, peg_id),
            )
        else:
            cursor.execute(
                f"""
                UPDATE savings_instruments
                SET base_rate_pct = {p},
                    effective_from = {p},
                    updated_at = {p},
                    active_observation_id = {p}
                WHERE instrument_id = {p}
                  AND (effective_from IS NULL OR effective_from <= {p});
                """,
                (expected_rate, target_eff, now_iso, new_peg_obs_id, peg_id, target_eff),
            )
            if cursor.rowcount == 0:
                continue

        _mirror_legacy_v049_tables_on_cursor(
            cursor,
            is_pg=is_pg,
            instrument_row_dict=updated_peg_dict,
        )
        dependent_updates.append(
            {
                "instrument_id": peg_id,
                "prior_observation_id": prior_peg_obs_id,
                "prior_effective_from": cur_peg_eff,
                "prior_rate_pct": cur_peg_rate,
                "replacement_observation_id": new_peg_obs_id,
                "effective_from": target_eff,
                "new_rate_pct": expected_rate,
                "override_epoch": new_peg_epoch,
            }
        )
    return dependent_updates


def upsert_savings_instrument(
    item: Dict[str, Any],
    force_effective_from: bool = False,
    *,
    force_overwrite: bool = False,
    override_reason: Optional[str] = None,
    override_operator: Optional[str] = None,
    baseline_seed: bool = False,
    allow_older_effective_date: bool = False,
    reference_date: Optional[str] = None,
    origin_db: Optional[str] = None,
    evidence_sha256: Optional[str] = None,
    conn: Optional[Any] = None,
) -> Dict[str, Any]:
    """Upserts a single savings instrument and appends immutable savings_rate_observations.

    Invariants:
    1. Official Publisher Whitelist: Rejects missing/malformed effective_from, non-HTTPS URLs,
       retail aggregator links, or unapproved publisher/issuer hostnames.
    2. Material Non-Rate & Evidence Revisions: When rate and senior bonus are unchanged on a
       direct upsert (`baseline_seed=False`), changes to circular references, source URLs,
       payout options, or contractual terms append a `TERMS_OR_EVIDENCE_AMENDMENT` observation
       without erasing the prior observation's supporting evidence.
    3. Future-Dated Rate Scheduling: Rates with `effective_from > reference_date` are stored
       in `savings_rate_observations` with `observation_status = 'SCHEDULED_FUTURE'` without
       overwriting the currently active tariff until `reference_date >= effective_from`.
    4. Forced Override Audit Trail: `force_overwrite=True` (or `force_effective_from=True` /
       `allow_older_effective_date=True`) requires an explicit `override_reason` (>= 8 chars)
       and `override_operator`, increments `override_epoch`, and writes an immutable entry to
       `savings_override_audit_log`.
    """
    validate_savings_provenance(item)
    is_force = bool(force_overwrite or force_effective_from or allow_older_effective_date)
    clean_reason = str(override_reason or item.get("override_reason") or "").strip()
    clean_operator = str(override_operator or item.get("override_operator") or "").strip()
    if is_force:
        if len(clean_reason) < 8:
            raise ValueError(
                "Forced savings rate override requires an explicit override_reason (>= 8 characters)."
            )
        if not clean_operator:
            raise ValueError(
                "Forced savings rate override requires a non-empty override_operator identity."
            )

    ref_dt = _parse_iso_date(reference_date) or datetime.now(IST).date()
    ref_iso = ref_dt.isoformat()
    requested_eff_from = str(item["effective_from"]).strip()[:10]
    req_eff_dt = _parse_iso_date(requested_eff_from)
    if req_eff_dt is None:
        raise ValueError("Savings instrument requires a valid YYYY-MM-DD effective_from date.")
    if (req_eff_dt - ref_dt).days > 366:
        raise ValueError(
            f"Savings instrument {item.get('instrument_id')} effective_from {requested_eff_from} "
            f"exceeds 366-day future scheduling horizon relative to {ref_iso}."
        )

    owns_conn = conn is None
    active_conn = conn or get_db_connection()
    if owns_conn:
        _ensure_tables_ready(active_conn)
    cursor = active_conn.cursor()
    p = get_placeholder()
    is_pg = bool(get_supabase_url()) or is_postgres_connection(active_conn)
    excl = "EXCLUDED" if is_pg else "excluded"
    origin_tag = str(origin_db or ("postgres" if is_pg else "local"))

    inst_id = str(item["instrument_id"]).strip().upper()
    new_rate = round(float(item["base_rate_pct"]), 4)
    new_bonus = round(float(item.get("senior_citizen_bonus_bps", 0.0)), 2)
    now_iso = _now_ist_iso()
    payout_json = _normalize_payout_json(item)
    notes_json, _ = _normalize_notes_json(item)
    source_auth_to_save = str(item["source_authority"]).strip()
    source_url_to_save = str(item["source_url"]).strip()
    next_rev_to_save = str(item["next_review_date"]).strip()[:10] if item.get("next_review_date") else None
    ev_hash = str(evidence_sha256 or item.get("evidence_sha256") or "").strip() or None

    def _merge_preserved_notes(existing_notes_raw: Any, incoming_notes_raw: str) -> str:
        try:
            old_notes = json.loads(existing_notes_raw or "{}")
            cur_notes = json.loads(incoming_notes_raw or "{}")
            merged_notes = dict(cur_notes)
            old_ver = _parse_iso_date(old_notes.get("last_tariff_verified_on"))
            cur_ver = _parse_iso_date(cur_notes.get("last_tariff_verified_on"))
            if old_ver and (cur_ver is None or old_ver > cur_ver):
                merged_notes["last_tariff_verified_on"] = old_ver.isoformat()
            for k, v in old_notes.items():
                if k not in merged_notes:
                    merged_notes[k] = v
            return json.dumps(merged_notes, sort_keys=True)
        except Exception as merge_err:
            logger.debug("Notes merge skipped for %s: %s", inst_id, merge_err)
            return incoming_notes_raw

    try:
        _acquire_instrument_write_locks(
            cursor,
            active_conn,
            inst_id,
            is_pg=is_pg,
            owns_conn=owns_conn,
        )

        select_for_update = " FOR UPDATE" if is_pg else ""
        cols36_sql = ", ".join(_BASE_36_COLS)
        cursor.execute(
            f"SELECT {cols36_sql}, override_epoch, active_observation_id "
            f"FROM savings_instruments WHERE instrument_id = {p}{select_for_update};",
            (inst_id,),
        )
        existing_full = cursor.fetchone()
        existing_dict = _row36_to_dict(existing_full[:36]) if existing_full else None
        prior_epoch = int(existing_full[36] or 0) if existing_full and existing_full[36] is not None else 0
        prior_active_obs_id = (
            str(existing_full[37]) if existing_full and existing_full[37] else None
        )

        cursor.execute(
            f"SELECT MAX(effective_from) FROM savings_rate_observations "
            f"WHERE instrument_id = {p} AND superseded_at IS NULL AND effective_from <= {p};",
            (inst_id, ref_iso),
        )
        hist_max_row = cursor.fetchone()
        max_hist_dt = _parse_iso_date(hist_max_row[0]) if hist_max_row and hist_max_row[0] else None

        # Check active observation's circular ref and revision_seq for non-rate change detection
        prior_circ_ref = ""
        active_rev_seq_on_old = 1
        if existing_dict:
            cursor.execute(
                f"""
                SELECT observation_id, revision_seq, rate_circular_ref, material_terms_hash
                FROM savings_rate_observations
                WHERE instrument_id = {p}
                  AND effective_from = {p}
                  AND superseded_at IS NULL
                ORDER BY revision_seq DESC
                LIMIT 1;
                """,
                (inst_id, str(existing_dict["effective_from"])[:10]),
            )
            act_obs_row = cursor.fetchone()
            if act_obs_row:
                if not prior_active_obs_id:
                    prior_active_obs_id = str(act_obs_row[0])
                active_rev_seq_on_old = int(act_obs_row[1] or 1)
                prior_circ_ref = str(act_obs_row[2] or "")

        # Future-dated announcement handling (Gap 4): store as SCHEDULED_FUTURE without making active today
        if req_eff_dt > ref_dt and not is_force:
            merged_for_future = dict(existing_dict or {})
            merged_for_future.update(item)
            merged_for_future["payout_options_json"] = payout_json
            merged_for_future["notes_json"] = (
                _merge_preserved_notes(existing_dict["notes_json"], notes_json)
                if existing_dict
                else notes_json
            )
            fut_circ = _extract_circular_ref(
                item, merged_for_future["notes_json"], source_auth_to_save
            )
            fut_snap_json, fut_mat_hash = compute_material_terms_snapshot(
                merged_for_future, rate_circular_ref=fut_circ
            )

            # If instrument has no prior row at all, insert inactive placeholder row until activation date
            if existing_dict is None:
                placeholder_cols = (*_BASE_36_COLS, "override_epoch", "active_observation_id")
                ph_vals = (
                    inst_id,
                    str(item["scheme_name"]).strip(),
                    str(item["category"]).strip().upper(),
                    str(item["issuer_name"]).strip(),
                    str(item["issuer_ticker"]).strip().upper() if item.get("issuer_ticker") else None,
                    str(item["issuer_type"]).strip().upper(),
                    1 if item.get("sovereign_backed") else 0,
                    1 if item.get("dicgc_insured") else 0,
                    float(item.get("dicgc_limit_inr", 0.0)),
                    str(item.get("credit_rating") or "UNRATED").strip(),
                    new_rate,
                    new_bonus,
                    str(item.get("rate_type") or "FIXED").strip().upper(),
                    str(item["floating_benchmark"]).strip() if item.get("floating_benchmark") else None,
                    float(item.get("floating_spread_bps", 0.0)),
                    str(item.get("compounding_freq") or "QUARTERLY").strip().upper(),
                    payout_json,
                    int(item.get("tenure_min_months", 0)),
                    int(item.get("tenure_max_months", 0)),
                    int(item.get("lock_in_months", 0)),
                    str(item.get("premature_exit_rule") or "").strip(),
                    float(item.get("min_investment_inr", 500.0)),
                    float(item["max_investment_inr"]) if item.get("max_investment_inr") is not None else None,
                    1 if item.get("tax_section_80c_eligible") else 0,
                    str(item.get("interest_taxability") or "SLAB_TAXABLE").strip().upper(),
                    str(item.get("maturity_taxability") or "EXEMPT").strip().upper(),
                    1 if item.get("tds_applicable") else 0,
                    float(item.get("tds_threshold_regular_inr", 0.0)),
                    float(item.get("tds_threshold_senior_inr", 0.0)),
                    requested_eff_from,
                    next_rev_to_save,
                    source_auth_to_save,
                    source_url_to_save,
                    notes_json,
                    0,  # inactive until activation date arrives
                    now_iso,
                    0,
                    None,
                )
                cursor.execute(
                    f"INSERT INTO savings_instruments ({', '.join(placeholder_cols)}) "
                    f"VALUES ({', '.join([p] * len(placeholder_cols))});",
                    ph_vals,
                )

            fut_obs_id, fut_rev_seq = _append_rate_observation_on_cursor(
                cursor,
                p=p,
                is_pg=is_pg,
                inst_id=inst_id,
                base_rate_pct=new_rate,
                senior_citizen_bonus_bps=new_bonus,
                effective_from=requested_eff_from,
                effective_to=None,
                rate_circular_ref=fut_circ,
                source_authority=source_auth_to_save,
                source_url=source_url_to_save,
                material_terms_hash=fut_mat_hash,
                terms_snapshot_json=fut_snap_json,
                change_reason="ANNOUNCED_FUTURE_RATE",
                observation_status="SCHEDULED_FUTURE",
                origin_db=origin_tag,
                observed_at=now_iso,
                override_epoch=prior_epoch,
                evidence_sha256=ev_hash,
                close_prior_dates=False,
                supersede_newer_dates=False,
            )
            scheduled_deps = _schedule_future_pegged_dependents_on_cursor(
                cursor,
                p=p,
                is_pg=is_pg,
                benchmark_id=inst_id,
                future_bench_rate=new_rate,
                future_effective_from=requested_eff_from,
                origin_db=origin_tag,
                now_iso=now_iso,
            )
            if owns_conn:
                active_conn.commit()
            return {
                "instrument_id": inst_id,
                "status": "SCHEDULED_FUTURE_RATE",
                "rate_changed": False,
                "scheduled_for": requested_eff_from,
                "scheduled_rate_pct": new_rate,
                "scheduled_dependents": scheduled_deps,
                "effective_from": str(existing_dict["effective_from"])[:10] if existing_dict else requested_eff_from,
                "base_rate_pct": round(float(existing_dict["base_rate_pct"]), 4) if existing_dict else new_rate,
                "observation_id": fut_obs_id,
                "revision_seq": fut_rev_seq,
            }

        rate_changed = False
        terms_changed = False
        status = "INSERTED"
        effective_from_to_save = requested_eff_from
        rate_to_save = new_rate
        bonus_to_save = new_bonus
        observation_rev_seq: Optional[int] = None
        observation_id_saved: Optional[str] = prior_active_obs_id
        new_epoch = (prior_epoch + 1) if (is_force and existing_dict is not None) else prior_epoch

        if existing_dict:
            old_rate = round(float(existing_dict["base_rate_pct"] or 0.0), 4)
            old_bonus = round(float(existing_dict["senior_citizen_bonus_bps"] or 0.0), 2)
            old_eff = str(existing_dict["effective_from"] or requested_eff_from)[:10]
            old_eff_dt = _parse_iso_date(old_eff)
            newest_known_dt = max(filter(None, [old_eff_dt, max_hist_dt]), default=old_eff_dt)

            _, old_mat_hash = compute_material_terms_snapshot(
                existing_dict,
                rate_circular_ref=prior_circ_ref or str(existing_dict.get("source_authority") or ""),
            )
            merged_candidate = dict(existing_dict)
            merged_candidate.update(item)
            merged_candidate["payout_options_json"] = payout_json
            merged_candidate["notes_json"] = _merge_preserved_notes(
                existing_dict["notes_json"], notes_json
            )
            incoming_circ = _extract_circular_ref(
                item, merged_candidate["notes_json"], source_auth_to_save
            )
            _, new_mat_hash = compute_material_terms_snapshot(
                merged_candidate, rate_circular_ref=incoming_circ
            )

            if (
                baseline_seed
                and not is_force
                and newest_known_dt is not None
                and (
                    req_eff_dt < newest_known_dt
                    or (
                        req_eff_dt == newest_known_dt
                        and (
                            abs(old_rate - new_rate) >= 1e-6
                            or abs(old_bonus - new_bonus) >= 1e-6
                            or active_rev_seq_on_old > 1
                        )
                    )
                )
            ):
                # Baseline sync MUST NOT revert updated rates OR operator-amended circular/terms revisions
                notes_merged = _merge_preserved_notes(existing_dict["notes_json"], notes_json)
                if notes_merged != existing_dict["notes_json"]:
                    cursor.execute(
                        f"UPDATE savings_instruments SET notes_json = {p}, updated_at = {p} WHERE instrument_id = {p};",
                        (notes_merged, now_iso, inst_id),
                    )
                st_ret = (
                    "PRESERVED_EXISTING_RATE"
                    if (abs(old_rate - new_rate) >= 1e-6 or abs(old_bonus - new_bonus) >= 1e-6)
                    else "METADATA_SYNCED"
                )
                if owns_conn:
                    active_conn.commit()
                return {
                    "instrument_id": inst_id,
                    "status": st_ret,
                    "rate_changed": False,
                    "effective_from": old_eff,
                    "base_rate_pct": old_rate,
                    "observation_id": prior_active_obs_id,
                    "revision_seq": active_rev_seq_on_old,
                }

            if (
                not baseline_seed
                and not is_force
                and old_eff_dt is not None
                and req_eff_dt < old_eff_dt
            ):
                # Out-of-order older bulletin: archive into observations without reverting active row
                hist_snap_json, hist_mat_hash = compute_material_terms_snapshot(
                    merged_candidate, rate_circular_ref=incoming_circ
                )
                hist_obs_id, observation_rev_seq = _append_rate_observation_on_cursor(
                    cursor,
                    p=p,
                    is_pg=is_pg,
                    inst_id=inst_id,
                    base_rate_pct=new_rate,
                    senior_citizen_bonus_bps=new_bonus,
                    effective_from=requested_eff_from,
                    effective_to=old_eff,
                    rate_circular_ref=incoming_circ,
                    source_authority=source_auth_to_save,
                    source_url=source_url_to_save,
                    material_terms_hash=hist_mat_hash,
                    terms_snapshot_json=hist_snap_json,
                    change_reason="OUT_OF_ORDER_HISTORICAL_BULLETIN",
                    observation_status="HISTORICAL",
                    origin_db=origin_tag,
                    observed_at=now_iso,
                    override_epoch=prior_epoch,
                    evidence_sha256=ev_hash,
                    close_prior_dates=False,
                    supersede_newer_dates=False,
                )
                if owns_conn:
                    active_conn.commit()
                return {
                    "instrument_id": inst_id,
                    "status": "SKIPPED_OLDER_EFFECTIVE_DATE",
                    "rate_changed": False,
                    "effective_from": old_eff,
                    "base_rate_pct": old_rate,
                    "observation_id": hist_obs_id,
                    "revision_seq": observation_rev_seq,
                }

            if abs(old_rate - new_rate) < 1e-6 and abs(old_bonus - new_bonus) < 1e-6 and not is_force:
                notes_json = _merge_preserved_notes(existing_dict["notes_json"], notes_json)
                if old_mat_hash == new_mat_hash:
                    status = "METADATA_SYNCED"
                    effective_from_to_save = old_eff
                else:
                    # Gap 3: Material non-rate / evidence amendment creates a new observation revision!
                    status = "TERMS_OR_EVIDENCE_UPDATED"
                    terms_changed = True
                    effective_from_to_save = (
                        requested_eff_from
                        if (old_eff_dt is not None and req_eff_dt > old_eff_dt)
                        else old_eff
                    )
            else:
                rate_changed = (
                    abs(old_rate - new_rate) >= 1e-6
                    or abs(old_bonus - new_bonus) >= 1e-6
                    or is_force
                )
                status = "RATE_UPDATED"
                effective_from_to_save = requested_eff_from
                notes_json = _merge_preserved_notes(existing_dict["notes_json"], notes_json)

        issuer_ticker_val = str(item["issuer_ticker"]).strip().upper() if item.get("issuer_ticker") else None
        max_inv_val = float(item["max_investment_inr"]) if item.get("max_investment_inr") is not None else None
        row36_to_write: Dict[str, Any] = {
            "instrument_id": inst_id,
            "scheme_name": str(item["scheme_name"]).strip(),
            "category": str(item["category"]).strip().upper(),
            "issuer_name": str(item["issuer_name"]).strip(),
            "issuer_ticker": issuer_ticker_val,
            "issuer_type": str(item["issuer_type"]).strip().upper(),
            "sovereign_backed": 1 if item.get("sovereign_backed") else 0,
            "dicgc_insured": 1 if item.get("dicgc_insured") else 0,
            "dicgc_limit_inr": float(item.get("dicgc_limit_inr", 0.0)),
            "credit_rating": str(item.get("credit_rating") or "UNRATED").strip(),
            "base_rate_pct": rate_to_save,
            "senior_citizen_bonus_bps": bonus_to_save,
            "rate_type": str(item.get("rate_type") or "FIXED").strip().upper(),
            "floating_benchmark": str(item["floating_benchmark"]).strip() if item.get("floating_benchmark") else None,
            "floating_spread_bps": float(item.get("floating_spread_bps", 0.0)),
            "compounding_freq": str(item.get("compounding_freq") or "QUARTERLY").strip().upper(),
            "payout_options_json": payout_json,
            "tenure_min_months": int(item.get("tenure_min_months", 0)),
            "tenure_max_months": int(item.get("tenure_max_months", 0)),
            "lock_in_months": int(item.get("lock_in_months", 0)),
            "premature_exit_rule": str(item.get("premature_exit_rule") or "").strip(),
            "min_investment_inr": float(item.get("min_investment_inr", 500.0)),
            "max_investment_inr": max_inv_val,
            "tax_section_80c_eligible": 1 if item.get("tax_section_80c_eligible") else 0,
            "interest_taxability": str(item.get("interest_taxability") or "SLAB_TAXABLE").strip().upper(),
            "maturity_taxability": str(item.get("maturity_taxability") or "EXEMPT").strip().upper(),
            "tds_applicable": 1 if item.get("tds_applicable") else 0,
            "tds_threshold_regular_inr": float(item.get("tds_threshold_regular_inr", 0.0)),
            "tds_threshold_senior_inr": float(item.get("tds_threshold_senior_inr", 0.0)),
            "effective_from": effective_from_to_save,
            "next_review_date": next_rev_to_save,
            "source_authority": source_auth_to_save,
            "source_url": source_url_to_save,
            "notes_json": notes_json,
            "is_active": 1 if item.get("is_active", 1) else 0,
            "updated_at": now_iso,
        }

        if status in ("INSERTED", "RATE_UPDATED", "TERMS_OR_EVIDENCE_UPDATED"):
            old_eff_for_rollback = (
                _parse_iso_date(str(existing_dict["effective_from"])[:10])
                if existing_dict and existing_dict.get("effective_from")
                else None
            )
            is_forced_rollback = bool(
                is_force
                and old_eff_for_rollback is not None
                and req_eff_dt <= old_eff_for_rollback
            )
            circ_ref = _extract_circular_ref(item, notes_json, source_auth_to_save)
            snap_json_to_save, mat_hash_to_save = compute_material_terms_snapshot(
                row36_to_write, rate_circular_ref=circ_ref
            )
            if is_force:
                reason_tag = f"FORCED_OVERRIDE: {clean_reason}"
            elif status == "INSERTED":
                reason_tag = "INITIAL_SEED" if baseline_seed else "DIRECT_INSERT"
            elif status == "TERMS_OR_EVIDENCE_UPDATED":
                reason_tag = "TERMS_OR_EVIDENCE_AMENDMENT"
            else:
                reason_tag = "RATE_UPDATE"

            observation_id_saved, observation_rev_seq = _append_rate_observation_on_cursor(
                cursor,
                p=p,
                is_pg=is_pg,
                inst_id=inst_id,
                base_rate_pct=rate_to_save,
                senior_citizen_bonus_bps=bonus_to_save,
                effective_from=effective_from_to_save,
                effective_to=None,
                rate_circular_ref=circ_ref,
                source_authority=source_auth_to_save,
                source_url=source_url_to_save,
                material_terms_hash=mat_hash_to_save,
                terms_snapshot_json=snap_json_to_save,
                change_reason=reason_tag,
                observation_status="ACTIVE",
                origin_db=origin_tag,
                observed_at=now_iso,
                override_epoch=new_epoch,
                evidence_sha256=ev_hash,
                close_prior_dates=True,
                supersede_newer_dates=bool(is_force),
            )

        where_monotonic = (
            ""
            if is_force
            else f" WHERE savings_instruments.effective_from IS NULL OR {excl}.effective_from >= savings_instruments.effective_from"
        )
        all_38_cols = (*_BASE_36_COLS, "override_epoch", "active_observation_id")
        placeholders = ", ".join([p] * len(all_38_cols))
        upd_clauses = ", ".join(
            [f"{c} = {excl}.{c}" for c in all_38_cols if c != "instrument_id"]
        )
        upsert_sql = (
            f"INSERT INTO savings_instruments ({', '.join(all_38_cols)}) "
            f"VALUES ({placeholders}) "
            f"ON CONFLICT (instrument_id) DO UPDATE SET {upd_clauses}{where_monotonic};"
        )
        params = tuple(row36_to_write[c] for c in _BASE_36_COLS) + (
            new_epoch,
            observation_id_saved,
        )
        cursor.execute(upsert_sql, params)
        _mirror_legacy_v049_tables_on_cursor(
            cursor,
            is_pg=is_pg,
            instrument_row_dict=row36_to_write,
        )

        dependent_updates: List[Dict[str, Any]] = []
        if rate_changed:
            dependent_updates = _cascade_pegged_dependents_on_cursor(
                cursor,
                p=p,
                is_pg=is_pg,
                benchmark_id=inst_id,
                force_overwrite=is_force,
                bump_override_epoch=bool(is_force and existing_dict is not None),
                origin_db=origin_tag,
                now_iso=now_iso,
            )

        override_id_logged: Optional[str] = None
        if is_force and existing_dict is not None and observation_id_saved is not None:
            ovr_payload = json.dumps(
                {
                    "instrument_id": inst_id,
                    "override_epoch": new_epoch,
                    "operator_id": clean_operator,
                    "prior_observation_id": prior_active_obs_id,
                    "replacement_observation_id": observation_id_saved,
                    "created_at": now_iso,
                },
                sort_keys=True,
            )
            override_id_logged = (
                "ovr_" + hashlib.sha256(ovr_payload.encode("utf-8")).hexdigest()[:28]
            )
            cursor.execute(
                f"""
                INSERT INTO savings_override_audit_log (
                    override_id, instrument_id, operator_id, override_reason, override_epoch,
                    prior_observation_id, prior_effective_from, prior_rate_pct,
                    replacement_observation_id, replacement_effective_from, replacement_rate_pct,
                    dependent_updates_json, created_at
                ) VALUES ({", ".join([p] * 13)});
                """,
                (
                    override_id_logged,
                    inst_id,
                    clean_operator,
                    clean_reason,
                    new_epoch,
                    prior_active_obs_id,
                    str(existing_dict["effective_from"])[:10],
                    round(float(existing_dict["base_rate_pct"] or 0.0), 4),
                    observation_id_saved,
                    effective_from_to_save,
                    rate_to_save,
                    json.dumps(dependent_updates, sort_keys=True),
                    now_iso,
                ),
            )

        if owns_conn:
            active_conn.commit()
        return {
            "instrument_id": inst_id,
            "status": status,
            "rate_changed": rate_changed,
            "terms_changed": terms_changed,
            "effective_from": effective_from_to_save,
            "base_rate_pct": rate_to_save,
            "observation_id": observation_id_saved,
            "revision_seq": observation_rev_seq,
            "override_epoch": new_epoch,
            "override_id": override_id_logged,
            "dependent_updates": dependent_updates,
        }
    except Exception as exc:
        logger.error("Error upserting savings instrument %s: %s", inst_id, exc)
        if owns_conn:
            active_conn.rollback()
        raise
    finally:
        cursor.close()
        if owns_conn:
            active_conn.close()


def activate_due_future_savings_rates(
    reference_date: Optional[str] = None,
    *,
    conn: Optional[Any] = None,
) -> Dict[str, Any]:
    """Promotes matured SCHEDULED_FUTURE observations (effective_from <= reference_date) to ACTIVE."""
    ref_iso = (_parse_iso_date(reference_date) or datetime.now(IST).date()).isoformat()
    owns_conn = conn is None
    active_conn = conn or get_db_connection()
    if owns_conn:
        _ensure_tables_ready(active_conn)
    cursor = active_conn.cursor()
    p = get_placeholder()
    is_pg = bool(get_supabase_url()) or is_postgres_connection(active_conn)
    now_iso = _now_ist_iso()

    try:
        cursor.execute(
            f"""
            SELECT observation_id, instrument_id, base_rate_pct, senior_citizen_bonus_bps,
                   effective_from, revision_seq, source_authority, source_url,
                   terms_snapshot_json, origin_db
            FROM savings_rate_observations
            WHERE observation_status = 'SCHEDULED_FUTURE'
              AND superseded_at IS NULL
              AND effective_from <= {p}
            ORDER BY instrument_id ASC, effective_from ASC, revision_seq ASC;
            """,
            (ref_iso,),
        )
        due_rows = cursor.fetchall()
        if not due_rows:
            return {"activated_count": 0, "activated_ids": [], "reference_date": ref_iso}

        if not is_pg and owns_conn and not getattr(active_conn, "in_transaction", False):
            cursor.execute("BEGIN IMMEDIATE;")

        # Group by instrument_id; promote chronologically and pick latest <= ref_iso as current active
        by_inst: Dict[str, List[Any]] = {}
        for dr in due_rows:
            by_inst.setdefault(str(dr[1]), []).append(dr)

        activated_ids: List[str] = []
        cols36_sql = ", ".join(_BASE_36_COLS)
        for inst_id, obs_list in by_inst.items():
            if is_pg:
                cursor.execute(
                    "SELECT pg_advisory_xact_lock(%s, hashtext(%s));",
                    (SAVINGS_ADVISORY_LOCK_NS, inst_id),
                )
            cursor.execute(
                f"SELECT {cols36_sql}, override_epoch FROM savings_instruments WHERE instrument_id = {p};",
                (inst_id,),
            )
            cur_row = cursor.fetchone()
            cur_dict = _row36_to_dict(cur_row[:36]) if cur_row else {}
            cur_epoch = int(cur_row[36] or 0) if cur_row else 0

            winner_obs = obs_list[-1]
            win_obs_id = str(winner_obs[0])
            win_rate = round(float(winner_obs[2] or 0.0), 4)
            win_bonus = round(float(winner_obs[3] or 0.0), 2)
            win_eff = str(winner_obs[4])[:10]
            win_auth = str(winner_obs[6])
            win_url = str(winner_obs[7])
            win_origin = str(winner_obs[9] or ("postgres" if is_pg else "local"))
            try:
                snap_obj = json.loads(winner_obs[8] or "{}")
            except Exception as snap_err:
                logger.debug("Scheduled snapshot parse notice for %s: %s", inst_id, snap_err)
                snap_obj = {}

            # Mark earlier due scheduled observations historical and winner ACTIVE
            for earlier in obs_list[:-1]:
                e_id = str(earlier[0])
                cursor.execute(
                    f"""
                    UPDATE savings_rate_observations
                    SET effective_to = {p}, observation_status = 'HISTORICAL'
                    WHERE observation_id = {p};
                    """,
                    (win_eff, e_id),
                )
            cursor.execute(
                f"""
                UPDATE savings_rate_observations
                SET effective_to = {p},
                    observation_status = CASE
                        WHEN observation_status = 'ACTIVE' THEN 'HISTORICAL'
                        ELSE observation_status
                    END
                WHERE instrument_id = {p}
                  AND effective_to IS NULL
                  AND superseded_at IS NULL
                  AND effective_from < {p};
                """,
                (win_eff, inst_id, win_eff),
            )
            cursor.execute(
                f"UPDATE savings_rate_observations SET observation_status = 'ACTIVE' WHERE observation_id = {p};",
                (win_obs_id,),
            )

            merged_36 = dict(cur_dict)
            for k in _BASE_36_COLS:
                if k in snap_obj and snap_obj[k] is not None:
                    merged_36[k] = snap_obj[k]
            merged_36["instrument_id"] = inst_id
            merged_36["base_rate_pct"] = win_rate
            merged_36["senior_citizen_bonus_bps"] = win_bonus
            merged_36["effective_from"] = win_eff
            merged_36["source_authority"] = win_auth
            merged_36["source_url"] = win_url
            merged_36["is_active"] = int(snap_obj.get("is_active", 1) or 1)
            merged_36["updated_at"] = now_iso

            excl = "EXCLUDED" if is_pg else "excluded"
            all_38_cols = (*_BASE_36_COLS, "override_epoch", "active_observation_id")
            upd_38 = ", ".join(
                [f"{c} = {excl}.{c}" for c in all_38_cols if c != "instrument_id"]
            )
            cursor.execute(
                f"INSERT INTO savings_instruments ({', '.join(all_38_cols)}) "
                f"VALUES ({', '.join([p] * len(all_38_cols))}) "
                f"ON CONFLICT (instrument_id) DO UPDATE SET {upd_38};",
                tuple(merged_36.get(c) for c in _BASE_36_COLS) + (cur_epoch, win_obs_id),
            )
            _mirror_legacy_v049_tables_on_cursor(
                cursor,
                is_pg=is_pg,
                instrument_row_dict=merged_36,
            )
            _cascade_pegged_dependents_on_cursor(
                cursor,
                p=p,
                is_pg=is_pg,
                benchmark_id=inst_id,
                force_overwrite=False,
                origin_db=win_origin,
                now_iso=now_iso,
            )
            activated_ids.append(inst_id)

        if owns_conn:
            active_conn.commit()
        return {
            "activated_count": len(activated_ids),
            "activated_ids": activated_ids,
            "reference_date": ref_iso,
        }
    except Exception as exc:
        logger.error("Error activating due future savings rates: %s", exc)
        if owns_conn:
            active_conn.rollback()
        raise
    finally:
        cursor.close()
        if owns_conn:
            active_conn.close()


def get_savings_override_audit_log(instrument_id: Optional[str] = None) -> List[Dict[str, Any]]:
    """Returns immutable forced-override audit entries ordered newest first."""
    conn = get_db_connection()
    _ensure_tables_ready(conn)
    cursor = conn.cursor()
    p = get_placeholder()
    try:
        if instrument_id:
            cursor.execute(
                f"""
                SELECT override_id, instrument_id, operator_id, override_reason, override_epoch,
                       prior_observation_id, prior_effective_from, prior_rate_pct,
                       replacement_observation_id, replacement_effective_from, replacement_rate_pct,
                       dependent_updates_json, created_at
                FROM savings_override_audit_log
                WHERE UPPER(instrument_id) = {p}
                ORDER BY override_epoch DESC, created_at DESC;
                """,
                (instrument_id.strip().upper(),),
            )
        else:
            cursor.execute(
                """
                SELECT override_id, instrument_id, operator_id, override_reason, override_epoch,
                       prior_observation_id, prior_effective_from, prior_rate_pct,
                       replacement_observation_id, replacement_effective_from, replacement_rate_pct,
                       dependent_updates_json, created_at
                FROM savings_override_audit_log
                ORDER BY created_at DESC, override_epoch DESC;
                """
            )
        out: List[Dict[str, Any]] = []
        for r in cursor.fetchall():
            try:
                deps = json.loads(r[11] or "[]")
            except Exception as exc:
                logger.debug("Dependent updates JSON parse notice: %s", exc)
                deps = []
            out.append(
                {
                    "override_id": str(r[0]),
                    "instrument_id": str(r[1]),
                    "operator_id": str(r[2]),
                    "override_reason": str(r[3]),
                    "override_epoch": int(r[4] or 0),
                    "prior_observation_id": str(r[5]) if r[5] else None,
                    "prior_effective_from": str(r[6]) if r[6] else None,
                    "prior_rate_pct": float(r[7]) if r[7] is not None else None,
                    "replacement_observation_id": str(r[8]),
                    "replacement_effective_from": str(r[9]),
                    "replacement_rate_pct": float(r[10]),
                    "dependent_updates": deps,
                    "created_at": str(r[12]),
                }
            )
        return out
    finally:
        cursor.close()
        conn.close()


def seed_tax_rule_versions(
    tax_versions: Optional[List[Dict[str, Any]]] = None,
    conn: Optional[Any] = None,
) -> int:
    """Seeds dated Finance Act tax rule versions into tax_rule_registry."""
    if tax_versions is None:
        payload = load_baseline_savings_payload()
        tax_versions = payload.get("tax_rule_versions", [])
    if not tax_versions:
        return 0

    owns_conn = conn is None
    active_conn = conn or get_db_connection()
    if owns_conn:
        _ensure_tables_ready(active_conn)
    cursor = active_conn.cursor()
    p = get_placeholder()
    is_pg = bool(get_supabase_url()) or is_postgres_connection(active_conn)
    excl = "EXCLUDED" if is_pg else "excluded"
    now_iso = _now_ist_iso()
    saved = 0

    try:
        for tv in tax_versions:
            validate_tax_rule_provenance(tv)
            rules_raw = tv.get("rules")
            rules_json = json.dumps(rules_raw, sort_keys=True) if isinstance(rules_raw, dict) else str(rules_raw or "{}")
            tv_row = {
                "rule_version": str(tv["rule_version"]).strip(),
                "finance_act_label": str(tv["finance_act_label"]).strip(),
                "effective_from": str(tv["effective_from"]).strip()[:10],
                "effective_to": str(tv["effective_to"]).strip()[:10] if tv.get("effective_to") else None,
                "rules_json": rules_json,
                "source_authority": str(tv["source_authority"]).strip(),
                "source_url": str(tv["source_url"]).strip(),
                "updated_at": now_iso,
            }
            sql = f"""
                INSERT INTO tax_rule_registry (
                    rule_version, finance_act_label, effective_from, effective_to,
                    rules_json, source_authority, source_url, updated_at
                ) VALUES ({p}, {p}, {p}, {p}, {p}, {p}, {p}, {p})
                ON CONFLICT (rule_version) DO UPDATE SET
                    finance_act_label = {excl}.finance_act_label,
                    effective_from = {excl}.effective_from,
                    effective_to = {excl}.effective_to,
                    rules_json = {excl}.rules_json,
                    source_authority = {excl}.source_authority,
                    source_url = {excl}.source_url,
                    updated_at = {excl}.updated_at;
            """
            cursor.execute(
                sql,
                (
                    tv_row["rule_version"],
                    tv_row["finance_act_label"],
                    tv_row["effective_from"],
                    tv_row["effective_to"],
                    tv_row["rules_json"],
                    tv_row["source_authority"],
                    tv_row["source_url"],
                    tv_row["updated_at"],
                ),
            )
            _mirror_legacy_v049_tables_on_cursor(cursor, is_pg=is_pg, tax_rule_dict=tv_row)
            saved += 1
        if owns_conn:
            active_conn.commit()
        return saved
    except Exception as exc:
        logger.error("Error seeding tax_rule_registry: %s", exc)
        if owns_conn:
            active_conn.rollback()
        raise
    finally:
        cursor.close()
        if owns_conn:
            active_conn.close()


def get_active_tax_rule_version(reference_date: Optional[str] = None) -> Dict[str, Any]:
    """Returns the active Finance Act tax rule version for a given reference date."""
    ref_iso = (_parse_iso_date(reference_date) or datetime.now(IST).date()).isoformat()
    conn = get_db_connection()
    _ensure_tables_ready(conn)
    cursor = conn.cursor()
    p = get_placeholder()
    try:
        cursor.execute(
            f"""
            SELECT rule_version, finance_act_label, effective_from, effective_to,
                   rules_json, source_authority, source_url, updated_at
            FROM tax_rule_registry
            WHERE effective_from <= {p}
              AND (effective_to IS NULL OR effective_to >= {p})
            ORDER BY effective_from DESC
            LIMIT 1;
            """,
            (ref_iso, ref_iso),
        )
        row = cursor.fetchone()
        if not row:
            cursor.close()
            conn.close()
            seed_tax_rule_versions()
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT rule_version, finance_act_label, effective_from, effective_to,
                       rules_json, source_authority, source_url, updated_at
                FROM tax_rule_registry
                ORDER BY effective_from DESC
                LIMIT 1;
                """
            )
            row = cursor.fetchone()
        if row:
            return {
                "rule_version": str(row[0]),
                "finance_act_label": str(row[1]),
                "effective_from": str(row[2]),
                "effective_to": str(row[3]) if row[3] else None,
                "rules": json.loads(row[4] or "{}"),
                "source_authority": str(row[5]),
                "source_url": str(row[6]),
                "updated_at": str(row[7] or ""),
            }
    except Exception as exc:
        logger.warning("Fallback to JSON baseline in get_active_tax_rule_version: %s", exc)
    finally:
        cursor.close()
        conn.close()

    payload = load_baseline_savings_payload()
    versions = payload.get("tax_rule_versions", [])
    if versions:
        tv = versions[0]
        return {
            "rule_version": tv["rule_version"],
            "finance_act_label": tv["finance_act_label"],
            "effective_from": tv["effective_from"],
            "effective_to": tv.get("effective_to"),
            "rules": tv.get("rules", {}),
            "source_authority": tv["source_authority"],
            "source_url": tv["source_url"],
            "updated_at": "",
        }
    return {
        "rule_version": "FY2025_26_FA2025",
        "finance_act_label": "Finance Act 2025 (AY 2026-27 / FY 2025-26)",
        "effective_from": "2025-04-01",
        "effective_to": None,
        "rules": {},
        "source_authority": "Central Board of Direct Taxes (CBDT), Ministry of Finance, Govt of India",
        "source_url": "https://incometaxindia.gov.in",
        "updated_at": "",
    }


def _reconcile_pegged_instruments(conn: Any, *, force_overwrite: bool = False) -> int:
    """Ensures FLOATING_PEGGED instruments match their live benchmark + spread without moving dates backwards."""
    cursor = conn.cursor()
    p = get_placeholder()
    is_pg = bool(get_supabase_url()) or is_postgres_connection(conn)
    now_iso = _now_ist_iso()
    try:
        deps = _cascade_pegged_dependents_on_cursor(
            cursor,
            p=p,
            is_pg=is_pg,
            benchmark_id=None,
            force_overwrite=force_overwrite,
            origin_db="postgres" if is_pg else "local",
            now_iso=now_iso,
        )
        return len(deps)
    finally:
        cursor.close()


def seed_baseline_savings_universe(
    file_path: Optional[Path] = None,
    force_effective_from: bool = False,
    *,
    force_overwrite: bool = False,
    override_reason: Optional[str] = None,
    override_operator: Optional[str] = None,
    reference_date: Optional[str] = None,
) -> Dict[str, Any]:
    """Seeds or synchronizes the curated baseline savings universe idempotently.

    Unless force_overwrite=True (with explicit override_reason + override_operator),
    existing rows that have already received rate or evidence updates are NEVER reverted.
    """
    is_force = bool(force_overwrite or force_effective_from)
    if is_force:
        if len(str(override_reason or "").strip()) < 8 or not str(override_operator or "").strip():
            raise ValueError(
                "Forced baseline savings reseed requires explicit override_reason (>= 8 chars) and override_operator."
            )

    payload = load_baseline_savings_payload(file_path=file_path)
    instruments = payload.get("instruments", [])
    tax_versions = payload.get("tax_rule_versions", [])
    is_baseline_seed = not is_force

    conn = get_db_connection()
    _ensure_tables_ready(conn)
    inserted = 0
    rate_updated = 0
    metadata_synced = 0
    preserved_existing = 0

    try:
        is_pg = bool(get_supabase_url()) or is_postgres_connection(conn)
        if not is_pg and not getattr(conn, "in_transaction", False):
            cur_tx = conn.cursor()
            cur_tx.execute("BEGIN IMMEDIATE;")
            cur_tx.close()

        tax_saved = seed_tax_rule_versions(tax_versions=tax_versions, conn=conn)
        for item in instruments:
            res = upsert_savings_instrument(
                item,
                force_effective_from=force_effective_from,
                force_overwrite=is_force,
                override_reason=override_reason,
                override_operator=override_operator,
                baseline_seed=is_baseline_seed,
                allow_older_effective_date=is_force,
                reference_date=reference_date,
                conn=conn,
            )
            st = res["status"]
            if st == "INSERTED":
                inserted += 1
            elif st == "RATE_UPDATED":
                rate_updated += 1
            elif st == "PRESERVED_EXISTING_RATE":
                preserved_existing += 1
            else:
                metadata_synced += 1
        pegged_reconciled = _reconcile_pegged_instruments(conn, force_overwrite=is_force)
        conn.commit()
        return {
            "status": "SUCCESS",
            "total_processed": len(instruments),
            "inserted": inserted,
            "rate_updated": rate_updated,
            "preserved_existing": preserved_existing,
            "pegged_reconciled": pegged_reconciled,
            "metadata_synced": metadata_synced,
            "tax_versions_saved": tax_saved,
        }
    except Exception as exc:
        logger.error("Failed seeding baseline savings universe: %s", exc)
        conn.rollback()
        return {
            "status": "ERROR",
            "error": str(exc),
            "total_processed": 0,
            "inserted": inserted,
            "rate_updated": rate_updated,
            "preserved_existing": preserved_existing,
            "metadata_synced": metadata_synced,
        }
    finally:
        conn.close()


def inspect_savings_universe_readonly() -> List[Dict[str, Any]]:
    """Strictly read-only active-universe inspector for CLI --check previews.

    Performs ZERO schema initialization, ZERO file creation, and ZERO baseline seeding.
    """
    raw_pg = get_configured_supabase_url()
    if is_hosted_production_runtime() or bool(raw_pg):
        conn = _get_raw_connection()
        cursor = conn.cursor()
        try:
            cursor.execute("SET TRANSACTION READ ONLY;")
            cursor.execute(
                """
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = 'public'
                   AND table_name IN ('savings_instruments', 'fixed_savings_instruments')
                ORDER BY CASE WHEN table_name = 'savings_instruments' THEN 0 ELSE 1 END
                LIMIT 1;
                """
            )
            tbl_row = cursor.fetchone()
            if not tbl_row:
                return []
            tbl = str(tbl_row[0])
            cols_present = set(_table_columns_on_cursor(cursor, tbl, is_pg=True))
            sel_cols = (
                _SELECT_COLS
                if ("override_epoch" in cols_present and "active_observation_id" in cols_present)
                else _SELECT_COLS_36
            )
            cursor.execute(
                f"SELECT {sel_cols} FROM {tbl} WHERE is_active = 1 "
                f"ORDER BY sovereign_backed DESC, dicgc_insured DESC, base_rate_pct DESC, scheme_name ASC;"
            )
            return [_hydrate_instrument_row(r) for r in cursor.fetchall()]
        finally:
            try:
                conn.rollback()
            except Exception as rb_err:
                logger.debug("Read-only PG rollback notice: %s", rb_err)
            cursor.close()
            conn.close()

    db_file = Path(get_db_path())
    if not db_file.is_file() or db_file.stat().st_size == 0:
        return []

    ro_conn = sqlite3.connect(f"file:{db_file}?mode=ro", uri=True)
    cursor = ro_conn.cursor()
    try:
        cursor.execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE type = 'table'
              AND name IN ('savings_instruments', 'fixed_savings_instruments')
            ORDER BY CASE WHEN name = 'savings_instruments' THEN 0 ELSE 1 END
            LIMIT 1;
            """
        )
        tbl_row = cursor.fetchone()
        if not tbl_row:
            return []
        tbl = str(tbl_row[0])
        cols_present = set(_table_columns_on_cursor(cursor, tbl, is_pg=False))
        sel_cols = (
            _SELECT_COLS
            if ("override_epoch" in cols_present and "active_observation_id" in cols_present)
            else _SELECT_COLS_36
        )
        cursor.execute(
            f"SELECT {sel_cols} FROM {tbl} WHERE is_active = 1 "
            f"ORDER BY sovereign_backed DESC, dicgc_insured DESC, base_rate_pct DESC, scheme_name ASC;"
        )
        return [_hydrate_instrument_row(r) for r in cursor.fetchall()]
    finally:
        cursor.close()
        ro_conn.close()


def get_savings_count() -> int:
    """Returns count of active fixed savings & deposit instruments."""
    conn = get_db_connection()
    _ensure_tables_ready(conn)
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT COUNT(*) FROM savings_instruments WHERE is_active = 1;")
        row = cursor.fetchone()
        cnt = int(row[0]) if row and row[0] is not None else 0
        if cnt == 0:
            cursor.close()
            conn.close()
            seed_baseline_savings_universe()
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM savings_instruments WHERE is_active = 1;")
            row2 = cursor.fetchone()
            return int(row2[0]) if row2 and row2[0] is not None else 0
        return cnt
    except Exception as exc:
        logger.warning("Error querying savings_instruments count: %s", exc)
        return 0
    finally:
        cursor.close()
        conn.close()


def ensure_savings_universe_seeded() -> None:
    """Ensures baseline instruments exist before application read queries run."""
    conn = get_db_connection()
    _ensure_tables_ready(conn)
    cursor = conn.cursor()
    needs_seed = False
    try:
        cursor.execute("SELECT COUNT(*) FROM savings_instruments;")
        row = cursor.fetchone()
        if not row or int(row[0] or 0) == 0:
            needs_seed = True
    except Exception as exc:
        logger.warning("Savings seed check notice: %s", exc)
        needs_seed = True
    finally:
        cursor.close()
        conn.close()

    if needs_seed:
        seed_baseline_savings_universe()


def _promote_matured_scheduled_if_wallclock_due() -> None:
    """Zero-write fast check that activates matured SCHEDULED_FUTURE observations when wall-clock date arrives."""
    today_iso = datetime.now(IST).date().isoformat()
    conn = get_db_connection()
    cursor = conn.cursor()
    p = get_placeholder()
    has_due = False
    try:
        cursor.execute(
            f"""
            SELECT 1 FROM savings_rate_observations
            WHERE observation_status = 'SCHEDULED_FUTURE'
              AND superseded_at IS NULL
              AND effective_from <= {p}
            LIMIT 1;
            """,
            (today_iso,),
        )
        has_due = cursor.fetchone() is not None
    except Exception as exc:
        logger.debug("Scheduled future probe notice: %s", exc)
    finally:
        cursor.close()
        conn.close()

    if has_due:
        activate_due_future_savings_rates(reference_date=today_iso)


def _overlay_point_in_time_and_scheduled_metadata(
    cursor: Any,
    items: List[Dict[str, Any]],
    *,
    p: str,
    ref_iso: str,
    point_in_time_mode: bool,
) -> List[Dict[str, Any]]:
    """Attaches scheduled_future_rate metadata and resolves point-in-time observation state without mutating DB."""
    if not items:
        return []

    out: List[Dict[str, Any]] = []
    for base_item in items:
        item = dict(base_item)
        inst_id = item["instrument_id"]

        if point_in_time_mode:
            cursor.execute(
                f"""
                SELECT observation_id, base_rate_pct, senior_citizen_bonus_bps,
                       effective_from, rate_circular_ref, source_authority,
                       source_url, terms_snapshot_json
                FROM savings_rate_observations
                WHERE instrument_id = {p}
                  AND superseded_at IS NULL
                  AND effective_from <= {p}
                ORDER BY effective_from DESC, revision_seq DESC
                LIMIT 1;
                """,
                (inst_id, ref_iso),
            )
            pit_obs = cursor.fetchone()
            if pit_obs is None:
                if str(item.get("effective_from") or "")[:10] > ref_iso or not item.get("is_active"):
                    continue
            else:
                try:
                    snap = json.loads(pit_obs[7] or "{}")
                except Exception as exc:
                    logger.debug("Point-in-time snapshot parse notice for %s: %s", inst_id, exc)
                    snap = {}
                for k, v in snap.items():
                    if v is not None and k in item:
                        item[k] = v
                if "payout_options_json" in snap:
                    try:
                        item["payout_options"] = json.loads(snap["payout_options_json"])
                    except Exception as p_err:
                        logger.debug("Payout parse notice: %s", p_err)
                if "notes_json" in snap:
                    try:
                        item["notes"] = json.loads(snap["notes_json"])
                    except Exception as n_err:
                        logger.debug("Notes parse notice: %s", n_err)
                item["active_observation_id"] = str(pit_obs[0])
                item["base_rate_pct"] = float(pit_obs[1] or 0.0)
                item["senior_citizen_bonus_bps"] = float(pit_obs[2] or 0.0)
                item["senior_rate_pct"] = round(
                    item["base_rate_pct"] + (item["senior_citizen_bonus_bps"] / 100.0), 4
                )
                item["effective_from"] = str(pit_obs[3])[:10]
                item["rate_circular_ref"] = str(pit_obs[4] or "")
                item["source_authority"] = str(pit_obs[5])
                item["source_url"] = str(pit_obs[6])
                item["is_active"] = bool(int(snap.get("is_active", 1) if snap else 1))
                if not item["is_active"]:
                    continue
                item["staleness"] = compute_staleness_badge(item, reference_date=ref_iso)
        else:
            if not item.get("is_active") or str(item.get("effective_from") or "")[:10] > ref_iso:
                continue

        cursor.execute(
            f"""
            SELECT observation_id, base_rate_pct, senior_citizen_bonus_bps,
                   effective_from, revision_seq, rate_circular_ref,
                   source_authority, source_url
            FROM savings_rate_observations
            WHERE instrument_id = {p}
              AND superseded_at IS NULL
              AND effective_from > {p}
            ORDER BY effective_from ASC, revision_seq DESC
            LIMIT 1;
            """,
            (inst_id, ref_iso),
        )
        sched_row = cursor.fetchone()
        if sched_row:
            item["scheduled_future_rate"] = {
                "observation_id": str(sched_row[0]),
                "base_rate_pct": float(sched_row[1] or 0.0),
                "senior_citizen_bonus_bps": float(sched_row[2] or 0.0),
                "senior_rate_pct": round(
                    float(sched_row[1] or 0.0) + (float(sched_row[2] or 0.0) / 100.0), 4
                ),
                "effective_from": str(sched_row[3])[:10],
                "revision_seq": int(sched_row[4] or 1),
                "rate_circular_ref": str(sched_row[5] or ""),
                "source_authority": str(sched_row[6]),
                "source_url": str(sched_row[7]),
            }
        else:
            item["scheduled_future_rate"] = None
        out.append(item)

    # If point-in-time mode resolved a newer benchmark rate (e.g. SAV-NSC on future reference_date),
    # ensure FLOATING_PEGGED instruments in the returned view reflect their benchmark + spread as of ref_iso
    if point_in_time_mode:
        by_id_pit = {x["instrument_id"]: x for x in out}
        for x in out:
            if str(x.get("rate_type") or "").upper() == "FLOATING_PEGGED":
                bench_id = str(x.get("floating_benchmark") or "")
                bench_item = by_id_pit.get(bench_id)
                if bench_item and str(bench_item["effective_from"])[:10] >= str(x["effective_from"])[:10]:
                    expected_peg = round(
                        float(bench_item["base_rate_pct"])
                        + (float(x.get("floating_spread_bps") or 0.0) / 100.0),
                        4,
                    )
                    x["base_rate_pct"] = expected_peg
                    x["senior_rate_pct"] = round(
                        expected_peg + (float(x.get("senior_citizen_bonus_bps") or 0.0) / 100.0), 4
                    )
                    x["effective_from"] = bench_item["effective_from"]
                    x["staleness"] = compute_staleness_badge(x, reference_date=ref_iso)

    out.sort(
        key=lambda r: (
            -int(bool(r.get("sovereign_backed"))),
            -int(bool(r.get("dicgc_insured"))),
            -float(r.get("base_rate_pct") or 0.0),
            str(r.get("scheme_name") or ""),
        )
    )
    return out


def get_active_savings_instruments(
    category: Optional[str] = None,
    query: Optional[str] = None,
    dicgc_only: bool = False,
    sovereign_only: bool = False,
    tax_80c_only: bool = False,
    *,
    reference_date: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Retrieves active fixed savings instruments with optional filters and point-in-time reference_date."""
    ensure_savings_universe_seeded()
    today_iso = datetime.now(IST).date().isoformat()
    ref_dt = _parse_iso_date(reference_date)
    ref_iso = ref_dt.isoformat() if ref_dt else today_iso
    point_in_time_mode = ref_dt is not None and ref_iso != today_iso

    if not point_in_time_mode:
        _promote_matured_scheduled_if_wallclock_due()

    conn = get_db_connection()
    cursor = conn.cursor()
    p = get_placeholder()

    where_clauses = ["1 = 1"] if point_in_time_mode else ["is_active = 1"]
    params: List[Any] = []

    if category and category.strip().upper() not in ("", "ALL"):
        where_clauses.append(f"category = {p}")
        params.append(category.strip().upper())

    if dicgc_only:
        where_clauses.append("dicgc_insured = 1")

    if sovereign_only:
        where_clauses.append("sovereign_backed = 1")

    if tax_80c_only:
        where_clauses.append("tax_section_80c_eligible = 1")

    if query and query.strip():
        like_pat = f"%{query.strip().upper()}%"
        where_clauses.append(
            f"(UPPER(instrument_id) LIKE {p} OR UPPER(scheme_name) LIKE {p} "
            f"OR UPPER(issuer_name) LIKE {p} OR UPPER(COALESCE(issuer_ticker, '')) LIKE {p} "
            f"OR UPPER(category) LIKE {p})"
        )
        params.extend([like_pat, like_pat, like_pat, like_pat, like_pat])

    sql = f"""
        SELECT {_SELECT_COLS}
        FROM savings_instruments
        WHERE {' AND '.join(where_clauses)}
        ORDER BY sovereign_backed DESC, dicgc_insured DESC, base_rate_pct DESC, scheme_name ASC;
    """
    try:
        cursor.execute(sql, tuple(params))
        rows = cursor.fetchall()
        hydrated = [_hydrate_instrument_row(r, reference_date=ref_iso) for r in rows]
        return _overlay_point_in_time_and_scheduled_metadata(
            cursor,
            hydrated,
            p=p,
            ref_iso=ref_iso,
            point_in_time_mode=point_in_time_mode,
        )
    except Exception as exc:
        logger.error("Error fetching active savings instruments: %s", exc)
        return []
    finally:
        cursor.close()
        conn.close()


def get_savings_instrument_by_id(
    instrument_id: str,
    *,
    reference_date: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """Retrieves a single fixed savings instrument by canonical instrument_id (as of reference_date)."""
    if not instrument_id:
        return None
    ensure_savings_universe_seeded()
    today_iso = datetime.now(IST).date().isoformat()
    ref_dt = _parse_iso_date(reference_date)
    ref_iso = ref_dt.isoformat() if ref_dt else today_iso
    point_in_time_mode = ref_dt is not None and ref_iso != today_iso

    if not point_in_time_mode:
        _promote_matured_scheduled_if_wallclock_due()

    conn = get_db_connection()
    cursor = conn.cursor()
    p = get_placeholder()
    try:
        cursor.execute(
            f"SELECT {_SELECT_COLS} FROM savings_instruments WHERE UPPER(instrument_id) = {p} LIMIT 1;",
            (instrument_id.strip().upper(),),
        )
        row = cursor.fetchone()
        if not row:
            return None
        base_item = _hydrate_instrument_row(row, reference_date=ref_iso)
        # If this instrument is FLOATING_PEGGED and point_in_time_mode is True, also include its benchmark
        items_to_resolve = [base_item]
        if point_in_time_mode and str(base_item.get("rate_type") or "").upper() == "FLOATING_PEGGED":
            bench_id = str(base_item.get("floating_benchmark") or "")
            if bench_id:
                cursor.execute(
                    f"SELECT {_SELECT_COLS} FROM savings_instruments WHERE UPPER(instrument_id) = {p} LIMIT 1;",
                    (bench_id.strip().upper(),),
                )
                b_row = cursor.fetchone()
                if b_row:
                    items_to_resolve.append(_hydrate_instrument_row(b_row, reference_date=ref_iso))
        resolved = _overlay_point_in_time_and_scheduled_metadata(
            cursor,
            items_to_resolve,
            p=p,
            ref_iso=ref_iso,
            point_in_time_mode=point_in_time_mode,
        )
        for cand in resolved:
            if cand["instrument_id"].upper() == instrument_id.strip().upper():
                return cand
        return None
    except Exception as exc:
        logger.error("Error fetching savings instrument %s: %s", instrument_id, exc)
        return None
    finally:
        cursor.close()
        conn.close()


def get_savings_rate_observations(
    instrument_id: str,
    *,
    include_superseded: bool = True,
) -> List[Dict[str, Any]]:
    """Returns chronological append-only rate observations (including same-date & future revisions)."""
    if not instrument_id:
        return []
    ensure_savings_universe_seeded()
    conn = get_db_connection()
    cursor = conn.cursor()
    p = get_placeholder()
    superseded_filter = "" if include_superseded else " AND superseded_at IS NULL"
    try:
        cursor.execute(
            f"""
            SELECT observation_id, instrument_id, base_rate_pct, senior_citizen_bonus_bps,
                   effective_from, effective_to, revision_seq, rate_circular_ref,
                   source_authority, source_url, material_terms_hash, terms_snapshot_json,
                   change_reason, observation_status, origin_db, observed_at,
                   superseded_at, superseded_by_observation_id, evidence_sha256
            FROM savings_rate_observations
            WHERE UPPER(instrument_id) = {p}{superseded_filter}
            ORDER BY effective_from DESC, revision_seq DESC, observed_at DESC;
            """,
            (instrument_id.strip().upper(),),
        )
        rows = cursor.fetchall()
        out: List[Dict[str, Any]] = []
        for r in rows:
            try:
                terms_snap = json.loads(r[11] or "{}")
            except Exception as exc:
                logger.debug("Observation terms_snapshot_json parse notice: %s", exc)
                terms_snap = {}
            out.append(
                {
                    "id": str(r[0]),
                    "observation_id": str(r[0]),
                    "instrument_id": str(r[1]),
                    "base_rate_pct": float(r[2]),
                    "senior_citizen_bonus_bps": float(r[3] or 0.0),
                    "senior_rate_pct": round(float(r[2]) + (float(r[3] or 0.0) / 100.0), 4),
                    "effective_from": str(r[4]),
                    "effective_to": str(r[5]) if r[5] else None,
                    "revision_seq": int(r[6] or 1),
                    "rate_circular_ref": str(r[7] or ""),
                    "source_authority": str(r[8]),
                    "source_url": str(r[9]),
                    "material_terms_hash": str(r[10] or ""),
                    "terms_snapshot_json": str(r[11] or "{}"),
                    "terms_snapshot": terms_snap,
                    "change_reason": str(r[12] or ""),
                    "observation_status": str(r[13] or "ACTIVE"),
                    "origin_db": str(r[14] or "local"),
                    "observed_at": str(r[15]),
                    "recorded_at": str(r[15]),
                    "superseded_at": str(r[16]) if r[16] else None,
                    "superseded_by_observation_id": str(r[17]) if r[17] else None,
                    "evidence_sha256": str(r[18]) if r[18] else None,
                }
            )
        return out
    except Exception as exc:
        logger.error("Error fetching rate observations for %s: %s", instrument_id, exc)
        return []
    finally:
        cursor.close()
        conn.close()


def get_savings_rate_history(
    instrument_id: str,
    *,
    include_superseded: bool = True,
) -> List[Dict[str, Any]]:
    """Backward-compatible alias for get_savings_rate_observations."""
    return get_savings_rate_observations(instrument_id, include_superseded=include_superseded)


def get_savings_instruments_by_issuer_ticker(ticker: str) -> List[Dict[str, Any]]:
    """Returns active deposit/savings instruments issued by a listed bank/SFB/NBFC ticker."""
    if not ticker:
        return []
    ensure_savings_universe_seeded()
    _promote_matured_scheduled_if_wallclock_due()
    today_iso = datetime.now(IST).date().isoformat()
    conn = get_db_connection()
    cursor = conn.cursor()
    p = get_placeholder()
    try:
        cursor.execute(
            f"""
            SELECT {_SELECT_COLS}
            FROM savings_instruments
            WHERE is_active = 1 AND effective_from <= {p} AND UPPER(issuer_ticker) = {p}
            ORDER BY base_rate_pct DESC;
            """,
            (today_iso, ticker.strip().upper()),
        )
        return [_hydrate_instrument_row(r) for r in cursor.fetchall()]
    except Exception as exc:
        logger.error("Error querying savings instruments for issuer %s: %s", ticker, exc)
        return []
    finally:
        cursor.close()
        conn.close()


# Automated public rate-card verification patterns (scoped per single-scheme notification block)
_PUBLIC_RATE_PROBES: List[Dict[str, Any]] = [
    {
        "instrument_id": "SAV-PPF",
        "url": "https://www.indiapost.gov.in/Financial/Pages/Content/Post-Office-Saving-Schemes.aspx",
        "scheme_anchor_pattern": r"\bPublic\s+Provident\s+Fund\b",
        "rival_scheme_pattern": (
            r"\b(?:Senior\s+Citizen[s']?\s+Savings\s+Scheme|National\s+Savings\s+Certificates?|"
            r"Sukanya\s+Samriddhi|Kisan\s+Vikas\s+Patra|Monthly\s+Income\s+Account|"
            r"Time\s+Deposit|Recurring\s+Deposit)\b"
        ),
        "pattern": r"Public\s+Provident\s+Fund[^0-9]{1,120}([6-9]\.\d{1,2})\s*%",
        "min_pct": 6.0,
        "max_pct": 9.5,
    },
    {
        "instrument_id": "SAV-SCSS",
        "url": "https://www.indiapost.gov.in/Financial/Pages/Content/Post-Office-Saving-Schemes.aspx",
        "scheme_anchor_pattern": r"\bSenior\s+Citizen[s']?\s+Savings\s+Scheme\b",
        "rival_scheme_pattern": (
            r"\b(?:Public\s+Provident\s+Fund|National\s+Savings\s+Certificates?|"
            r"Sukanya\s+Samriddhi|Kisan\s+Vikas\s+Patra|Monthly\s+Income\s+Account|"
            r"Time\s+Deposit|Recurring\s+Deposit)\b"
        ),
        "pattern": r"Senior\s+Citizen[s']?\s+Savings\s+Scheme[^0-9]{1,120}([7-9]\.\d{1,2})\s*%",
        "min_pct": 7.0,
        "max_pct": 10.0,
    },
    {
        "instrument_id": "SAV-NSC",
        "url": "https://www.indiapost.gov.in/Financial/Pages/Content/Post-Office-Saving-Schemes.aspx",
        "scheme_anchor_pattern": r"\bNational\s+Savings\s+Certificates?\b",
        "rival_scheme_pattern": (
            r"\b(?:Public\s+Provident\s+Fund|Senior\s+Citizen[s']?\s+Savings\s+Scheme|"
            r"Sukanya\s+Samriddhi|Kisan\s+Vikas\s+Patra|Monthly\s+Income\s+Account|"
            r"Time\s+Deposit|Recurring\s+Deposit)\b"
        ),
        "pattern": r"National\s+Savings\s+Certificates?[^0-9]{1,120}([6-9]\.\d{1,2})\s*%",
        "min_pct": 6.0,
        "max_pct": 9.5,
    },
]


def _strip_html_to_text(raw_html: str) -> str:
    no_tags = re.sub(r"<[^>]+>", " ", raw_html or "")
    unescaped = html_lib.unescape(no_tags)
    return re.sub(r"\s+", " ", unescaped).strip()


def _extract_effective_dates_in_text(text: str) -> List[str]:
    """Extracts all explicit w.e.f. / effective from dates inside a bounded text snippet."""
    found: List[str] = []
    for m_iso in re.finditer(
        r"(?:w\.?e\.?f\.?|effective(?:\s+from)?)\s*[:\-]?\s*(20\d{2}-\d{2}-\d{2})",
        text or "",
        re.IGNORECASE,
    ):
        dt = _parse_iso_date(m_iso.group(1))
        if dt and dt.isoformat() not in found:
            found.append(dt.isoformat())

    for m_dmy in re.finditer(
        r"(?:w\.?e\.?f\.?|effective(?:\s+from)?)\s*[:\-]?\s*(\d{2})[./\-](\d{2})[./\-](20\d{2})",
        text or "",
        re.IGNORECASE,
    ):
        day_s, mon_s, yr_s = m_dmy.groups()
        dt = _parse_iso_date(f"{yr_s}-{mon_s}-{day_s}")
        if dt and dt.isoformat() not in found:
            found.append(dt.isoformat())
    return found


def extract_scoped_portal_rate_evidence(
    html_text: str,
    probe: Dict[str, Any],
) -> Dict[str, Any]:
    """Verifies page-level notification co-location (Gap 6).

    Requires the scheme title, bounded interest rate, and unambiguous `w.e.f.` effective date
    to reside inside the SAME single-instrument notification container (`<tr>`, `<li>`,
    `<article>`, `<section>`, `<div>`, `<p>`) or enclosing single-notification `<table>`
    header without rival scheme names or conflicting effective dates. Never combines a rate
    from one section with an unrelated banner/footer/sibling `w.e.f.` date elsewhere on the page.
    """
    scheme_re = re.compile(
        probe.get("scheme_anchor_pattern") or probe["pattern"],
        re.IGNORECASE | re.DOTALL,
    )
    rival_re = (
        re.compile(probe["rival_scheme_pattern"], re.IGNORECASE | re.DOTALL)
        if probe.get("rival_scheme_pattern")
        else None
    )
    min_pct = float(probe.get("min_pct", 0.0))
    max_pct = float(probe.get("max_pct", 25.0))

    def _extract_single_bounded_rate(snippet_text: str) -> Tuple[Optional[float], Optional[str]]:
        m_anchor = scheme_re.search(snippet_text)
        if not m_anchor:
            return None, "NO_SCHEME_MATCH"
        if rival_re and rival_re.search(snippet_text):
            return None, "RIVAL_SCHEME_IN_SAME_BLOCK"
        tail = snippet_text[m_anchor.start() :]
        raw_rates = [
            round(float(m.group(1)), 2)
            for m in re.finditer(r"(\d{1,2}\.\d{1,2})\s*%", tail)
        ]
        if not raw_rates:
            return None, "NO_RATE_IN_BLOCK"
        unique_rates = sorted(set(raw_rates))
        if len(unique_rates) > 1:
            return None, "AMBIGUOUS_MULTIPLE_RATES_IN_BLOCK"
        rate_val = unique_rates[0]
        if not (min_pct <= rate_val <= max_pct):
            return rate_val, "OUT_OF_BOUNDS_RATE"
        return rate_val, None

    # 1. Inspect structured <table> -> <tr> rows first
    first_unscoped_rate: Optional[float] = None
    first_rejection_reason: str = "NO_SCHEME_MATCH"

    for tbl_match in re.finditer(
        r"<table\b[^>]*>(.*?)</table>", html_text or "", re.IGNORECASE | re.DOTALL
    ):
        tbl_html = tbl_match.group(1)
        header_parts = [
            _strip_html_to_text(m.group(1))
            for m in re.finditer(
                r"<(?:caption|thead)\b[^>]*>(.*?)</(?:caption|thead)>",
                tbl_html,
                re.IGNORECASE | re.DOTALL,
            )
        ]
        header_text = " ".join(p for p in header_parts if p)
        header_dates = _extract_effective_dates_in_text(header_text)
        all_tbl_dates = _extract_effective_dates_in_text(_strip_html_to_text(tbl_html))

        for tr_match in re.finditer(
            r"<tr\b[^>]*>(.*?)</tr>", tbl_html, re.IGNORECASE | re.DOTALL
        ):
            row_text = _strip_html_to_text(tr_match.group(1))
            if not scheme_re.search(row_text):
                continue
            rate_val, err = _extract_single_bounded_rate(row_text)
            if err:
                first_rejection_reason = err
                if rate_val is not None and first_unscoped_rate is None:
                    first_unscoped_rate = rate_val
                continue
            assert rate_val is not None
            row_dates = _extract_effective_dates_in_text(row_text)
            if len(row_dates) > 1:
                first_unscoped_rate = rate_val
                first_rejection_reason = "CONFLICTING_EFFECTIVE_DATES_IN_ROW"
                continue
            if len(row_dates) == 1:
                excerpt = row_text
                eff_iso = row_dates[0]
                return {
                    "valid": True,
                    "parsed_rate": rate_val,
                    "effective_from": eff_iso,
                    "scoped_excerpt": excerpt,
                    "evidence_sha256": hashlib.sha256(excerpt.encode("utf-8")).hexdigest(),
                }
            # Fallback to enclosing <table>'s own <caption>/<thead> ONLY if unambiguous across the table
            if len(header_dates) == 1 and set(all_tbl_dates) == {header_dates[0]}:
                excerpt = f"{header_text} | {row_text}"
                eff_iso = header_dates[0]
                return {
                    "valid": True,
                    "parsed_rate": rate_val,
                    "effective_from": eff_iso,
                    "scoped_excerpt": excerpt,
                    "evidence_sha256": hashlib.sha256(excerpt.encode("utf-8")).hexdigest(),
                }
            first_unscoped_rate = rate_val
            first_rejection_reason = (
                "CONFLICTING_EFFECTIVE_DATES_IN_TABLE"
                if len(all_tbl_dates) > 1
                else "MISSING_OR_UNSCOPED_EFFECTIVE_DATE"
            )

    # 2. Inspect non-table leaf notification blocks (<li>, <article>, <section>, <div>, <p>)
    for blk_match in re.finditer(
        r"<(li|article|section|div|p)\b[^>]*>((?:(?!</?\1\b).)*?)</\1>",
        html_text or "",
        re.IGNORECASE | re.DOTALL,
    ):
        blk_text = _strip_html_to_text(blk_match.group(2))
        if not scheme_re.search(blk_text):
            continue
        rate_val, err = _extract_single_bounded_rate(blk_text)
        if err:
            first_rejection_reason = err
            if rate_val is not None and first_unscoped_rate is None:
                first_unscoped_rate = rate_val
            continue
        assert rate_val is not None
        blk_dates = _extract_effective_dates_in_text(blk_text)
        if len(blk_dates) == 1:
            return {
                "valid": True,
                "parsed_rate": rate_val,
                "effective_from": blk_dates[0],
                "scoped_excerpt": blk_text,
                "evidence_sha256": hashlib.sha256(blk_text.encode("utf-8")).hexdigest(),
            }
        first_unscoped_rate = rate_val
        first_rejection_reason = (
            "CONFLICTING_EFFECTIVE_DATES_IN_BLOCK"
            if len(blk_dates) > 1
            else "MISSING_OR_UNSCOPED_EFFECTIVE_DATE"
        )

    # 3. Fallback for plain-text or minimal snippets without block tags
    if "<" not in (html_text or ""):
        plain_text = _strip_html_to_text(html_text)
        rate_val, err = _extract_single_bounded_rate(plain_text)
        if err is None and rate_val is not None:
            p_dates = _extract_effective_dates_in_text(plain_text)
            if len(p_dates) == 1:
                return {
                    "valid": True,
                    "parsed_rate": rate_val,
                    "effective_from": p_dates[0],
                    "scoped_excerpt": plain_text,
                    "evidence_sha256": hashlib.sha256(plain_text.encode("utf-8")).hexdigest(),
                }
            first_unscoped_rate = rate_val
            first_rejection_reason = (
                "CONFLICTING_EFFECTIVE_DATES_IN_BLOCK"
                if len(p_dates) > 1
                else "MISSING_OR_UNSCOPED_EFFECTIVE_DATE"
            )

    return {
        "valid": False,
        "reason": first_rejection_reason,
        "parsed_rate": first_unscoped_rate,
        "effective_from": None,
        "scoped_excerpt": None,
        "evidence_sha256": None,
    }


def _stamp_tariff_verification(instrument_id: str, verified_date: str) -> bool:
    """Records last_tariff_verified_on in notes_json WITHOUT touching effective_from."""
    conn = get_db_connection()
    cursor = conn.cursor()
    p = get_placeholder()
    now_iso = _now_ist_iso()
    try:
        cursor.execute(
            f"SELECT notes_json FROM savings_instruments WHERE instrument_id = {p};",
            (instrument_id,),
        )
        row = cursor.fetchone()
        if not row:
            return False
        notes = json.loads(row[0] or "{}")
        notes["last_tariff_verified_on"] = verified_date
        cursor.execute(
            f"UPDATE savings_instruments SET notes_json = {p}, updated_at = {p} WHERE instrument_id = {p};",
            (json.dumps(notes, sort_keys=True), now_iso, instrument_id),
        )
        conn.commit()
        return True
    except Exception as exc:
        logger.warning("Could not stamp tariff verification for %s: %s", instrument_id, exc)
        conn.rollback()
        return False
    finally:
        cursor.close()
        conn.close()


def _extract_portal_effective_date(html_text: str) -> Optional[str]:
    """Backward-compatible helper returning a date ONLY if the snippet has a single unambiguous date."""
    dates = _extract_effective_dates_in_text(_strip_html_to_text(html_text))
    return dates[0] if len(dates) == 1 else None


def _record_unverified_portal_drift(
    instrument_id: str,
    parsed_rate: Optional[float],
    detected_date: str,
    url: str,
    *,
    reason: str = "MISSING_OR_UNSCOPED_EFFECTIVE_DATE",
) -> None:
    """Logs an unscoped/undated portal rate discrepancy in notes_json without mutating base_rate_pct or effective_from."""
    conn = get_db_connection()
    cursor = conn.cursor()
    p = get_placeholder()
    now_iso = _now_ist_iso()
    try:
        cursor.execute(
            f"SELECT notes_json FROM savings_instruments WHERE instrument_id = {p};",
            (instrument_id,),
        )
        row = cursor.fetchone()
        if not row:
            return
        notes = json.loads(row[0] or "{}")
        notes["unverified_portal_rate_candidate"] = {
            "parsed_rate_pct": parsed_rate,
            "detected_on": detected_date,
            "source_url": url,
            "rejection_reason": reason,
        }
        cursor.execute(
            f"UPDATE savings_instruments SET notes_json = {p}, updated_at = {p} WHERE instrument_id = {p};",
            (json.dumps(notes, sort_keys=True), now_iso, instrument_id),
        )
        conn.commit()
    except Exception as exc:
        logger.warning("Could not record portal rate drift notice for %s: %s", instrument_id, exc)
        conn.rollback()
    finally:
        cursor.close()
        conn.close()


def verify_and_sync_automated_savings_rates(
    edition_date: Optional[str] = None,
    allow_network: bool = True,
) -> Dict[str, Any]:
    """Automated rate importer & live tariff verifier for scheduled pipelines.

    1. Ensures baseline universe + tax rules are seeded WITHOUT reverting any newer rates.
    2. Promotes any scheduled future rates whose effective_from <= edition_date.
    3. Atomically ingests structured JSON bulletins dropped into data/savings_rates/inbox/*.json
       (rolling back the entire file transaction and retaining the file in inbox/ if any item fails).
    4. Probes official public statutory endpoints using certifi.where() TLS verification and
       `extract_scoped_portal_rate_evidence()` (requiring scheme title, rate, and `w.e.f.` date
       to belong to the same scoped notification block).
    """
    check_date = (edition_date or datetime.now(IST).strftime("%Y-%m-%d"))[:10]
    seed_summary = seed_baseline_savings_universe(
        force_overwrite=False,
        reference_date=check_date,
    )
    activated_summary = activate_due_future_savings_rates(reference_date=check_date)

    inbox_files_processed = 0
    inbox_files_failed = 0
    inbox_rate_updates = 0
    inbox_scheduled_future = 0
    if SAVINGS_INBOX_DIR.exists():
        processed_dir = SAVINGS_INBOX_DIR / "processed"
        for json_file in sorted(SAVINGS_INBOX_DIR.glob("*.json")):
            file_conn = get_db_connection()
            try:
                is_pg = bool(get_supabase_url()) or is_postgres_connection(file_conn)
                if not is_pg and not getattr(file_conn, "in_transaction", False):
                    cur_tx = file_conn.cursor()
                    cur_tx.execute("BEGIN IMMEDIATE;")
                    cur_tx.close()

                bulletin = json.loads(json_file.read_text(encoding="utf-8"))
                items = bulletin.get("instruments", bulletin if isinstance(bulletin, list) else [])
                force_bulletin = (
                    bool(bulletin.get("force_overwrite", False))
                    if isinstance(bulletin, dict)
                    else False
                )
                bulletin_reason = (
                    str(bulletin.get("override_reason") or "").strip()
                    if isinstance(bulletin, dict)
                    else ""
                )
                bulletin_operator = (
                    str(bulletin.get("override_operator") or "").strip()
                    if isinstance(bulletin, dict)
                    else ""
                )
                file_updates = 0
                file_scheduled = 0
                for entry in items:
                    existing = get_savings_instrument_by_id(
                        str(entry.get("instrument_id", "")),
                        reference_date=check_date,
                    )
                    merged = dict(existing or {})
                    merged.update(entry)
                    force_entry = bool(
                        force_bulletin or entry.get("force_overwrite") or entry.get("force")
                    )
                    res = upsert_savings_instrument(
                        merged,
                        force_overwrite=force_entry,
                        override_reason=entry.get("override_reason") or bulletin_reason or None,
                        override_operator=entry.get("override_operator") or bulletin_operator or None,
                        baseline_seed=False,
                        reference_date=check_date,
                        conn=file_conn,
                    )
                    if res.get("rate_changed"):
                        file_updates += 1
                    elif res.get("status") == "SCHEDULED_FUTURE_RATE":
                        file_scheduled += 1
                file_conn.commit()
                processed_dir.mkdir(parents=True, exist_ok=True)
                target_archive = processed_dir / f"{check_date}_{json_file.name}"
                json_file.replace(target_archive)
                inbox_files_processed += 1
                inbox_rate_updates += file_updates
                inbox_scheduled_future += file_scheduled
            except Exception as exc:
                file_conn.rollback()
                inbox_files_failed += 1
                logger.error(
                    "Rolled back savings rate inbox file %s (retained in inbox for retry): %s",
                    json_file,
                    exc,
                )
            finally:
                file_conn.close()

    live_probes_attempted = 0
    live_probes_verified = 0
    live_rate_changes = 0
    rate_drift_alerts: List[str] = []

    if allow_network:
        ssl_ctx = ssl.create_default_context(cafile=certifi.where())
        headers = {
            "User-Agent": "Mozilla/5.0 (compatible; MoatnomicsRateVerifier/1.0)",
            "Accept": "text/html,application/xhtml+xml,application/json;q=0.9,*/*;q=0.8",
        }
        url_cache: Dict[str, str] = {}
        for probe in _PUBLIC_RATE_PROBES:
            live_probes_attempted += 1
            url = probe["url"]
            try:
                if url not in url_cache:
                    req = urllib.request.Request(url, headers=headers)
                    with urllib.request.urlopen(req, timeout=4, context=ssl_ctx) as resp:
                        if resp.status == 200:
                            url_cache[url] = resp.read(262144).decode("utf-8", errors="ignore")
                html_text = url_cache.get(url, "")
                if not html_text:
                    continue
                current = get_savings_instrument_by_id(
                    probe["instrument_id"], reference_date=check_date
                )
                if not current:
                    continue

                scoped = extract_scoped_portal_rate_evidence(html_text, probe)
                parsed_rate = scoped.get("parsed_rate")
                if parsed_rate is not None and not (
                    probe["min_pct"] <= float(parsed_rate) <= probe["max_pct"]
                ):
                    logger.warning(
                        "Rejected out-of-bounds parsed rate %.2f%% for %s",
                        float(parsed_rate),
                        probe["instrument_id"],
                    )
                    continue

                if scoped["valid"]:
                    assert parsed_rate is not None
                    live_probes_verified += 1
                    if abs(float(current["base_rate_pct"]) - float(parsed_rate)) >= 0.01:
                        portal_eff = str(scoped["effective_from"])
                        cur_eff_dt = _parse_iso_date(current.get("effective_from"))
                        portal_eff_dt = _parse_iso_date(portal_eff)
                        if portal_eff_dt and (cur_eff_dt is None or portal_eff_dt >= cur_eff_dt):
                            updated_payload = dict(current)
                            updated_payload["base_rate_pct"] = float(parsed_rate)
                            updated_payload["effective_from"] = portal_eff
                            notes = dict(updated_payload.get("notes") or {})
                            notes["last_tariff_verified_on"] = check_date
                            notes.pop("unverified_portal_rate_candidate", None)
                            updated_payload["notes"] = notes
                            upsert_res = upsert_savings_instrument(
                                updated_payload,
                                baseline_seed=False,
                                reference_date=check_date,
                                evidence_sha256=scoped.get("evidence_sha256"),
                            )
                            if upsert_res.get("rate_changed"):
                                live_rate_changes += 1
                        else:
                            _record_unverified_portal_drift(
                                probe["instrument_id"],
                                float(parsed_rate),
                                check_date,
                                url,
                                reason="OLDER_EFFECTIVE_DATE_ON_PORTAL",
                            )
                            rate_drift_alerts.append(probe["instrument_id"])
                    else:
                        _stamp_tariff_verification(probe["instrument_id"], check_date)
                elif parsed_rate is not None:
                    live_probes_verified += 1
                    if abs(float(current["base_rate_pct"]) - float(parsed_rate)) >= 0.01:
                        _record_unverified_portal_drift(
                            probe["instrument_id"],
                            float(parsed_rate),
                            check_date,
                            url,
                            reason=str(scoped.get("reason") or "UNSCOPED_OR_AMBIGUOUS_PAGE_EVIDENCE"),
                        )
                        rate_drift_alerts.append(probe["instrument_id"])
                    else:
                        _stamp_tariff_verification(probe["instrument_id"], check_date)
            except Exception as probe_err:
                logger.warning(
                    "Automated savings probe notice (%s): %s. Retaining verified statutory rate.",
                    probe["instrument_id"],
                    probe_err,
                )

    all_active = get_active_savings_instruments(reference_date=check_date)
    stale_items = sorted(
        {
            inst["instrument_id"]
            for inst in all_active
            if inst.get("staleness", {}).get("status")
            in ("REVIEW_DUE", "STALE_TARIFF", "UNVERIFIED_PROVENANCE")
        }
        | set(rate_drift_alerts)
    )

    return {
        "status": "SUCCESS" if seed_summary.get("status") == "SUCCESS" else "DEGRADED",
        "edition_date": check_date,
        "total_active": len(all_active),
        "baseline_sync": seed_summary,
        "future_rates_activated": activated_summary.get("activated_count", 0),
        "inbox_files_processed": inbox_files_processed,
        "inbox_files_failed": inbox_files_failed,
        "inbox_rate_updates": inbox_rate_updates,
        "inbox_scheduled_future": inbox_scheduled_future,
        "live_probes_attempted": live_probes_attempted,
        "live_probes_verified": live_probes_verified,
        "live_rate_changes": live_rate_changes,
        "rate_drift_alerts": rate_drift_alerts,
        "review_due_count": len(stale_items),
        "review_due_ids": stale_items,
    }
