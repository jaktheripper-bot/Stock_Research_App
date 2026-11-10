"""Typed opportunity measures and comparable groups for the Opportunity Terminal."""

from datetime import date, datetime
import logging
import math
import re
from typing import Any, Dict, List, Optional, Tuple
from zoneinfo import ZoneInfo

from core.analysis.metric_contract import has_forbidden_vendor_token
from core.analysis.savings_engine import compute_fisher_real_yield_pct, is_pure_sec_112a_arbitrage_fund
from core.db.connection import get_db_connection
from core.db.debt import get_active_debt_securities
from core.db.mutual_funds import get_active_mutual_funds
from core.db.reits import get_all_reits_and_invits, get_all_sgb_tranches
from core.db.reports import get_archived_reports
from core.db.savings import get_active_savings_instruments
from core.db.sovereign import get_etf_matrix, get_live_macro_anchors, get_sovereign_yield_curve

logger = logging.getLogger(__name__)

DEFAULT_MOSPI_CPI_INFLATION: float = 3.65
DEFAULT_TAX_SLAB_PCT: float = 30.0

_MF_DEBT_CATEGORY_RE = re.compile(
    r"\b(?:debt|liquid|gilt|overnight|money\s+market|banking\s+and\s+psu|corporate\s+bond|credit\s+risk)\b",
    re.IGNORECASE,
)
_MF_GILT_PSU_RE = re.compile(r"\b(?:gilt|psu)\b", re.IGNORECASE)

# Capital Hierarchy Seniority Hierarchy (0: Safest Sovereign to 5: Residual Equity)
SENIORITY_RANKS = {
    "SOVEREIGN": 0,
    "AAA_PSU": 1,
    "SENIOR_SECURED": 2,
    "COMMODITY_BACKED_TRUST": 2,
    "SUBORDINATED": 3,
    "SDI": 3,
    "REAL_ASSET": 4,
    "EQUITY": 5,
}


def calculate_tax_waterfall(
    gross_yield: float,
    asset_class: str,
    tax_slab: float = 30.0,
    details: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Computes precise statutory post-tax yield under Indian Income Tax Act regimes.

    Returns a dict containing:
    - net_yield_pct: float
    - tax_drag_pct: float
    - tax_statute: str
    - effective_tax_rate_pct: float
    """
    tax_slab = max(0.0, min(float(tax_slab), 45.0))
    gross_yield = float(gross_yield)
    details = details or {}

    if gross_yield <= 0:
        return {
            "net_yield_pct": 0.0,
            "tax_drag_pct": 0.0,
            "tax_statute": "N/A",
            "effective_tax_rate_pct": 0.0,
        }

    # 1. Sovereign Gold Bonds: Section 47(viic)
    # Capital gains on redemption are 100% tax-free. Only 2.50% annual coupon is taxed at slab.
    if asset_class == "SGB":
        annual_coupon = float(details.get("coupon_rate_pct", 2.50))
        coupon_yield = min(annual_coupon, gross_yield)
        capital_yield = max(0.0, gross_yield - coupon_yield)
        taxed_coupon = coupon_yield * (1.0 - (tax_slab / 100.0))
        net_yield = capital_yield + taxed_coupon
        eff_tax_rate = ((gross_yield - net_yield) / gross_yield * 100.0) if gross_yield > 0 else 0.0
        return {
            "net_yield_pct": round(net_yield, 2),
            "tax_drag_pct": round(gross_yield - net_yield, 2),
            "tax_statute": "Sec 47(viic) 100% Tax-Free Capital Gains (Coupon at Slab)",
            "effective_tax_rate_pct": round(eff_tax_rate, 1),
        }

    # 2. REITs & InvITs: Section 115UA Pass-Through Waterfall
    elif asset_class in ("REIT", "INVIT", "SM_REIT"):
        interest_pct = float(details.get("interest_component_pct", 40.0))
        dividend_pct = float(details.get("dividend_component_pct", 35.0))
        roc_pct = float(details.get("roc_component_pct", 25.0))

        interest_yield = gross_yield * (interest_pct / 100.0)
        net_interest = interest_yield * (1.0 - (tax_slab / 100.0))
        net_dividend = gross_yield * (dividend_pct / 100.0)
        net_roc = gross_yield * (roc_pct / 100.0)

        net_yield = net_interest + net_dividend + net_roc
        eff_tax_rate = ((gross_yield - net_yield) / gross_yield * 100.0) if gross_yield > 0 else 0.0
        return {
            "net_yield_pct": round(net_yield, 2),
            "tax_drag_pct": round(gross_yield - net_yield, 2),
            "tax_statute": "Sec 115UA Hybrid Pass-Through (Interest at Slab, Dividend/RoC Tax-Sheltered)",
            "effective_tax_rate_pct": round(eff_tax_rate, 1),
        }

    # 3. Equities, Equity Mutual Funds & Pure Sec 112A Arbitrage Funds
    elif asset_class in ("EQUITY", "MF_EQUITY", "ETF_EQUITY", "ARBITRAGE_MF"):
        ltcg_rate = 12.5
        net_yield = gross_yield * (1.0 - (ltcg_rate / 100.0))
        return {
            "net_yield_pct": round(net_yield, 2),
            "tax_drag_pct": round(gross_yield - net_yield, 2),
            "tax_statute": "Sec 112A Long-Term Capital Gains (Flat 12.5% above ₹1.25L)",
            "effective_tax_rate_pct": ltcg_rate,
        }

    # 3B. Exempt-Exempt-Exempt Statutory Small Savings (PPF / SSY / EPF within ₹2.5L)
    elif asset_class == "SAVINGS_EEE":
        return {
            "net_yield_pct": round(gross_yield, 2),
            "tax_drag_pct": 0.0,
            "tax_statute": "Sec 10(11) / 10(11A) / 10(12) 100% Exempt-Exempt-Exempt",
            "effective_tax_rate_pct": 0.0,
        }

    # 4. Standard Fixed Income & Debt: Section 50AA / Marginal Slab Tax
    else:
        net_yield = gross_yield * (1.0 - (tax_slab / 100.0))
        return {
            "net_yield_pct": round(net_yield, 2),
            "tax_drag_pct": round(gross_yield - net_yield, 2),
            "tax_statute": "Sec 50AA / General Marginal Income Slab",
            "effective_tax_rate_pct": tax_slab,
        }


def assign_tenure_bucket(years: float) -> str:
    """Categorize a supplied maturity or duration into tenure bands."""
    if years <= 1.0:
        return "<1Y"
    elif years <= 3.0:
        return "1-3Y"
    elif years <= 5.0:
        return "3-5Y"
    elif years <= 10.0:
        return "5-10Y"
    else:
        return "10Y+"


# Maximum publication age in calendar days. These are display policies.
MEASURE_MAX_AGE = {
    "CONTRACTUAL_YTM": 7,
    "AUCTION_CUTOFF_YIELD": 45,
    "STATUTORY_OR_TARIFF_RATE": 365,
    "DISTRIBUTION_YIELD_TTM": 7,
    "HISTORICAL_CAGR_3Y": 45,
    "EARNINGS_YIELD_TTM": 7,
    "DIVIDEND_YIELD_TTM": 7,
}


def _number(value: Any) -> Optional[float]:
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (ValueError, TypeError, OverflowError):
        return None
    return number if math.isfinite(number) else None


def _observation(
    yield_type: Optional[str],
    value: Any = None,
    as_of: Any = None,
    source: Any = None,
) -> Dict[str, Any]:
    number = _number(value)
    try:
        source_date = date.fromisoformat(str(as_of))
    except ValueError:
        source_date = None
    source_name = source.strip() if isinstance(source, str) else ""
    vendor_blocked = has_forbidden_vendor_token(source_name) if source_name else False
    if vendor_blocked:
        source_name = ""
        source_date = None
    status = "unavailable"
    if yield_type and number is not None and source_date and source_name and not vendor_blocked:
        age = (datetime.now(ZoneInfo("Asia/Kolkata")).date() - source_date).days
        if age >= 0:
            status = "available" if age <= MEASURE_MAX_AGE[yield_type] else "stale"
    return {
        "yield_type": yield_type,
        "metric_status": status,
        "metric_as_of": source_date.isoformat() if source_date else None,
        "metric_source": source_name or None,
        "gross_yield_pct": number if status == "available" else None,
        "last_observed_pct": number if status == "stale" else None,
        # Retain legacy keys for API consumers during migration.
        "net_yield_pct": None,
        "post_tax_status": "not_calculated",
        "real_yield_pct": None,
        "spread_vs_10y_gsec_bps": None,
        "tax_statute": None,
        "effective_tax_rate_pct": None,
    }


def _source_metadata(row: Dict[str, Any]) -> Dict[str, Any]:
    meta = row.get("metadata")
    return meta if isinstance(meta, dict) else {}


def _load_latest_debt_quote_observations() -> Dict[str, Dict[str, Any]]:
    """Load latest reviewed debt quote observation per ISIN from dedicated table."""
    latest: Dict[str, Dict[str, Any]] = {}
    conn = None
    cur = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute(
            """
            SELECT isin, ytm_pct, as_of, source_url, years_to_maturity
            FROM debt_quote_observations
            ORDER BY as_of DESC, id DESC
            LIMIT 1000
            """
        )
        for row in cur.fetchall() or []:
            isin = str(row[0] or "").strip().upper()
            if not isin or isin in latest:
                continue
            latest[isin] = {
                "quoted_ytm_pct": row[1],
                "quoted_ytm_as_of": str(row[2]) if row[2] is not None else None,
                "quoted_ytm_source": row[3],
                "quoted_years_to_maturity": row[4],
            }
    except Exception as exc:
        logger.debug("Dedicated debt_quote_observations table lookup skipped: %s", exc)
    finally:
        if cur is not None:
            cur.close()
        if conn is not None:
            conn.close()
    return latest


def _load_latest_instrument_observations() -> Dict[Tuple[str, str, str], Dict[str, Any]]:
    """Load latest dated instrument metric observation by (instrument_id, asset_class, measure_type)."""
    latest: Dict[Tuple[str, str, str], Dict[str, Any]] = {}
    conn = None
    cur = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute(
            """
            SELECT instrument_id, asset_class, measure_type, value_pct, as_of, source_name, source_url
            FROM instrument_metric_observations
            ORDER BY as_of DESC, id DESC
            LIMIT 5000
            """
        )
        for row in cur.fetchall() or []:
            inst_id = str(row[0] or "").strip()
            asset_cls = str(row[1] or "").strip().upper()
            m_type = str(row[2] or "").strip().upper()
            key = (inst_id, asset_cls, m_type)
            if not inst_id or key in latest:
                continue
            latest[key] = {
                "value_pct": row[3],
                "as_of": str(row[4]) if row[4] is not None else None,
                "source": row[6] or row[5],
            }
    except Exception as exc:
        logger.debug("Dedicated instrument_metric_observations lookup skipped: %s", exc)
    finally:
        if cur is not None:
            cur.close()
        if conn is not None:
            conn.close()
    return latest


def _equity_observation(
    row: Dict[str, Any],
    inst_obs: Optional[Dict[Tuple[str, str, str], Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    ticker = str(row.get("ticker") or "").strip()
    if inst_obs and ticker:
        ey_obs = inst_obs.get((ticker, "EQUITY", "EARNINGS_YIELD_TTM"))
        if ey_obs:
            candidate = _observation("EARNINGS_YIELD_TTM", ey_obs["value_pct"], ey_obs["as_of"], ey_obs["source"])
            if candidate["metric_status"] != "unavailable":
                return candidate
        dy_obs = inst_obs.get((ticker, "EQUITY", "DIVIDEND_YIELD_TTM"))
        if dy_obs:
            candidate = _observation("DIVIDEND_YIELD_TTM", dy_obs["value_pct"], dy_obs["as_of"], dy_obs["source"])
            if candidate["metric_status"] != "unavailable":
                return candidate

    inputs = _source_metadata(row)
    price = _number(inputs.get("metric_close_price"))
    eps = _number(inputs.get("diluted_eps_ttm"))
    try:
        price_date = date.fromisoformat(str(inputs.get("metric_price_as_of")))
        earnings_end = date.fromisoformat(str(inputs.get("diluted_eps_ttm_period_end")))
        earnings_usable = 0 <= (price_date - earnings_end).days <= 180
    except ValueError:
        earnings_usable = False
    if price is not None and price > 0 and eps is not None and earnings_usable:
        return _observation(
            "EARNINGS_YIELD_TTM",
            eps / price * 100,
            inputs.get("metric_price_as_of"),
            inputs.get("metric_source"),
        )
    dividend = _observation(
        "DIVIDEND_YIELD_TTM",
        inputs.get("dividend_yield_ttm_pct"),
        inputs.get("dividend_yield_as_of"),
        inputs.get("dividend_yield_source"),
    )
    if dividend["metric_status"] != "unavailable":
        return dividend
    return _observation("EARNINGS_YIELD_TTM")


def _comparison_group(item: Dict[str, Any]) -> str:
    kind = item["yield_type"]
    if kind in {"CONTRACTUAL_YTM", "AUCTION_CUTOFF_YIELD", "STATUTORY_OR_TARIFF_RATE"}:
        # Duration and maturity are distinct. The collector uses a declared
        # years-to-maturity measure for these groups.
        tenure = item["tenure_bucket"]
        if tenure is None:
            return ""
        return f"{kind}:{item['asset_class']}:{tenure}"
    if kind == "HISTORICAL_CAGR_3Y":
        return f"{kind}:{item['asset_class']}:{item['seniority_tier']}"
    return kind or ""


def _opportunity_order(item: Dict[str, Any]) -> tuple:
    group = _comparison_group(item)
    value = item["gross_yield_pct"]
    ranked = bool(group) and value is not None
    return (not ranked, group, -value if ranked else 0, str(item["name"]), str(item["id"]))


def get_normalized_opportunity_universe(
    tax_slab: float = DEFAULT_TAX_SLAB_PCT,
    cpi_inflation: float = DEFAULT_MOSPI_CPI_INFLATION,
    persona_filter: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Keep the inventory visible even when the data needed for a measure is absent.
    """
    _ = (tax_slab, cpi_inflation)
    items: List[Dict[str, Any]] = []
    today_ist = datetime.now(ZoneInfo("Asia/Kolkata")).date()
    debt_obs_map = _load_latest_debt_quote_observations()
    inst_obs_map = _load_latest_instrument_observations()

    # ----------------------------------------------------
    # 1. Corporate Debt & Securitized Debt (SDIs)
    # ----------------------------------------------------
    try:
        debt_securities = get_active_debt_securities(limit=100)
        for d in debt_securities:
            isin_key = str(d.get("isin") or "").strip().upper()
            # Prefer dedicated debt_quote_observations table so metadata_json refreshes cannot wipe quotes;
            # fall back to row metadata when fresher or in unit-test mocks.
            inputs = dict(_source_metadata(d))
            dedicated_quote = debt_obs_map.get(isin_key)
            if dedicated_quote:
                meta_date = str(inputs.get("quoted_ytm_as_of") or "")
                ded_date = str(dedicated_quote.get("quoted_ytm_as_of") or "")
                if not meta_date or ded_date >= meta_date:
                    inputs.update(dedicated_quote)

            metric = _observation(
                "CONTRACTUAL_YTM",
                inputs.get("quoted_ytm_pct"),
                inputs.get("quoted_ytm_as_of"),
                inputs.get("quoted_ytm_source"),
            )
            maturity = _number(inputs.get("quoted_years_to_maturity"))
            duration = _number(d.get("macaulay_duration_years"))
            is_sdi = bool(d.get("is_sdi", False))
            seniority = (d.get("seniority_tier") or "SENIOR_SECURED").upper()

            if "PSU" in (d.get("instrument_type") or "").upper() or "SOVEREIGN" in seniority:
                s_tier = "AAA_PSU"
            elif is_sdi:
                s_tier = "SDI"
            elif "SUBORDINATED" in seniority or "PERPETUAL" in seniority or "AT1" in seniority:
                s_tier = "SUBORDINATED"
            else:
                s_tier = "SENIOR_SECURED"

            personas = []
            if s_tier == "AAA_PSU":
                personas.append("capital_preservation")

            items.append({
                "id": d.get("isin"),
                "symbol": d.get("ticker", "BOND"),
                "name": d.get("instrument_name", "Corporate Bond"),
                "asset_class": "SDI" if is_sdi else "BOND",
                "category_label": "Securitized Debt (SDI)" if is_sdi else f"{d.get('credit_rating', 'AAA')} Bond",
                **metric,
                "seniority_tier": s_tier,
                "seniority_rank": SENIORITY_RANKS.get(s_tier, 2),
                "credit_rating": d.get("credit_rating", "AAA"),
                "macaulay_duration_years": duration,
                "tenure_bucket": assign_tenure_bucket(maturity) if maturity is not None and maturity > 0 else None,
                "min_ticket_inr": float(d.get("face_value", 10000.0)),
                "liquidity_tier": "EXCHANGE_ACTIVE",
                "recovery_recourse": "1.25x First Pari-Passu Asset Charge" if s_tier == "SENIOR_SECURED" else "Subordinated Unsecured Claim",
                "primary_failure_mode": "Issuer Credit Downgrade / Refinancing Liquidity Shock",
                "detail_url": f"/debt/{d.get('isin')}",
                "persona_tags": personas,
            })
    except Exception as e:
        logger.error("Error aggregating corporate debt for Opportunity Terminal: %s", e)

    # ----------------------------------------------------
    # 2. Alternative Real Assets (SM REITs, REITs, InvITs)
    # ----------------------------------------------------
    try:
        reits = get_all_reits_and_invits()
        for r in reits:
            structure = r.get("structure_type", "PUBLIC_REIT")
            is_sm_reit = structure == "SM_REIT"
            is_invit = structure == "PUBLIC_INVIT"
            asset_type = "SM_REIT" if is_sm_reit else ("INVIT" if is_invit else "REIT")
            sym = str(r.get("symbol") or "").strip()

            inputs = dict(r.get("details") or {})
            ded_obs = inst_obs_map.get((sym, asset_type, "DISTRIBUTION_YIELD_TTM"))
            if ded_obs and not inputs.get("distribution_yield_as_of"):
                metric = _observation("DISTRIBUTION_YIELD_TTM", ded_obs["value_pct"], ded_obs["as_of"], ded_obs["source"])
            else:
                metric = _observation(
                    "DISTRIBUTION_YIELD_TTM",
                    inputs.get("distribution_yield_ttm_pct"),
                    inputs.get("distribution_yield_as_of"),
                    inputs.get("distribution_yield_source"),
                )

            label = "SEBI SM REIT Scheme" if is_sm_reit else ("Infrastructure InvIT" if is_invit else "Commercial REIT")
            min_ticket = 1000000.0 if is_sm_reit else 350.0

            personas = ["quarterly_cashflow"]
            if is_sm_reit:
                personas.append("hni_real_assets")

            items.append({
                "id": r.get("symbol"),
                "symbol": r.get("symbol"),
                "name": r.get("name", "Real Asset Offering"),
                "asset_class": asset_type,
                "category_label": label,
                **metric,
                "seniority_tier": "REAL_ASSET",
                "seniority_rank": SENIORITY_RANKS["REAL_ASSET"],
                "credit_rating": "AAA (Crisil)" if not is_sm_reit else "SEBI Registered Scheme",
                "macaulay_duration_years": None,
                "tenure_bucket": None,
                "min_ticket_inr": min_ticket,
                "liquidity_tier": "PERIODIC_WINDOW" if is_sm_reit else "EXCHANGE_ACTIVE",
                "recovery_recourse": f"Direct SPV Land/Asset Ownership (Occupancy: {r.get('occupancy_pct', 95)}%)",
                "primary_failure_mode": "Anchor Tenant Default / Regulatory Concession Cap Drift",
                "detail_url": f"/reits#{r.get('symbol')}",
                "persona_tags": personas,
            })
    except Exception as e:
        logger.error("Error aggregating REITs/InvITs for Opportunity Terminal: %s", e)

    # ----------------------------------------------------
    # 3. Sovereign Gold Bonds (SGBs) — exclude matured tranches
    # ----------------------------------------------------
    try:
        sgbs = get_all_sgb_tranches()
        for s in sgbs:
            raw_maturity = s.get("maturity_date")
            if raw_maturity:
                try:
                    if date.fromisoformat(str(raw_maturity)) <= today_ist:
                        continue
                except ValueError:
                    pass
            # A gold-linked redemption scenario is outside this observed-metric feed.
            metric = _observation(None)

            items.append({
                "id": s.get("symbol"),
                "symbol": s.get("symbol"),
                "name": f"SGB {s.get('series_code', '')} (Mat: {s.get('maturity_date', '2028')})",
                "asset_class": "SGB",
                "category_label": "Sovereign Gold Bond",
                **metric,
                "seniority_tier": "SOVEREIGN",
                "seniority_rank": SENIORITY_RANKS["SOVEREIGN"],
                "credit_rating": "SOVEREIGN",
                "macaulay_duration_years": None,
                "tenure_bucket": None,
                "min_ticket_inr": _number(s.get("current_price")),
                "liquidity_tier": "EXCHANGE_ACTIVE",
                "recovery_recourse": "Reserve Bank of India / Government of India Sovereign Guarantee",
                "primary_failure_mode": "Global Spot Gold Price Crash / Exchange Secondary Illiquidity",
                "detail_url": "/reits#sgbSection",
                "persona_tags": ["capital_preservation"],
            })
    except Exception as e:
        logger.error("Error aggregating SGBs for Opportunity Terminal: %s", e)

    # ----------------------------------------------------
    # 4. Sovereign Yield Benchmarks & T-Bills
    # ----------------------------------------------------
    try:
        sovereign_benchmarks = get_sovereign_yield_curve(auto_seed=False)
        canonical_tenors = ("91D", "364D", "5Y", "10Y", "10Y_SGRB", "30Y")
        for b in sovereign_benchmarks:
            tenor = b.get("tenor_label", "")
            is_canonical = (tenor in canonical_tenors) or any(
                tenor.startswith(f"{ct}_") or tenor == ct for ct in canonical_tenors
            )
            if is_canonical:
                inst_id = f"GOI_{tenor}"
                if b.get("source") in ("RBI_AUCTION_CUTOFF", "FBIL_LIVE") and not b.get("is_fallback"):
                    metric = _observation(
                        "AUCTION_CUTOFF_YIELD",
                        b.get("cut_off_yield"),
                        b.get("auction_date"),
                        b.get("source"),
                    )
                else:
                    ded_sov = inst_obs_map.get((inst_id, "SOVEREIGN", "AUCTION_CUTOFF_YIELD"))
                    if ded_sov:
                        metric = _observation("AUCTION_CUTOFF_YIELD", ded_sov["value_pct"], ded_sov["as_of"], ded_sov["source"])
                    else:
                        metric = _observation("AUCTION_CUTOFF_YIELD", None, b.get("auction_date"), b.get("source"))
                mat_years = _number(b.get("maturity_years"))

                clean_label = tenor.replace("_", " ").title()
                items.append({
                    "id": inst_id,
                    "symbol": f"GOI-{tenor}",
                    "name": f"Government of India {b.get('instrument_type', 'Benchmark')} ({clean_label})",
                    "asset_class": "SOVEREIGN",
                    "category_label": "Sovereign G-Sec / T-Bill",
                    **metric,
                    "seniority_tier": "SOVEREIGN",
                    "seniority_rank": SENIORITY_RANKS["SOVEREIGN"],
                    "credit_rating": "SOVEREIGN",
                    "macaulay_duration_years": None,
                    "tenure_bucket": assign_tenure_bucket(mat_years) if mat_years is not None and mat_years > 0 else None,
                    "min_ticket_inr": 10000.0,
                    "liquidity_tier": "INSTANT_T1",
                    "recovery_recourse": "Consolidated Fund of India Statutory Guarantee",
                    "primary_failure_mode": "Domestic Inflation Surge / Interest Rate Policy Hike",
                    "detail_url": "/sovereign",
                    "persona_tags": ["capital_preservation"],
                })
    except Exception as e:
        logger.error("Error aggregating sovereign curve for Opportunity Terminal: %s", e)

    # ----------------------------------------------------
    # 5. Mutual Funds (with strict Sec 112A Arbitrage vs FoF guard)
    # ----------------------------------------------------
    try:
        funds = get_active_mutual_funds(limit=20, audited_only=True)
        for f in funds:
            broad = (f.get("broad_category") or "EQUITY").upper()
            cat_name = f.get("category") or ""
            scheme_name = f.get("scheme_name") or "Mutual Fund Scheme"
            is_pure_arb = is_pure_sec_112a_arbitrage_fund(broad, cat_name, scheme_name)
            is_debt = (not is_pure_arb) and ((broad == "DEBT") or bool(_MF_DEBT_CATEGORY_RE.search(cat_name)))
            scheme_code = str(f.get("scheme_code") or "").strip()
            inputs = _source_metadata(f)
            ded_mf = inst_obs_map.get((scheme_code, "MF", "HISTORICAL_CAGR_3Y"))
            if ded_mf and not inputs.get("returns_3y_as_of"):
                metric = _observation("HISTORICAL_CAGR_3Y", ded_mf["value_pct"], ded_mf["as_of"], ded_mf["source"])
            else:
                metric = _observation(
                    "HISTORICAL_CAGR_3Y",
                    inputs.get("returns_3y_cagr"),
                    inputs.get("returns_3y_as_of"),
                    inputs.get("returns_3y_source"),
                )
            if is_pure_arb:
                seniority = "SENIOR_SECURED"
                personas = ["capital_preservation", "quarterly_cashflow"]
                recourse = "SEBI >=65% Hedged Cash-Futures Arbitrage + Sovereign T-Bill Margin"
                failure = "Cash-Futures Spread Compression in Bearish Derivatives Regime"
                resolved_cat_label = "Arbitrage Mutual Fund (Sec 112A)"
            elif is_debt:
                seniority = "AAA_PSU" if bool(_MF_GILT_PSU_RE.search(cat_name)) else "SENIOR_SECURED"
                personas = ["capital_preservation", "quarterly_cashflow"]
                recourse = "Regulated Underlying Debt Portfolio (AMFI Liquidations / Accrual)"
                failure = "Credit Rating Downgrade / RBI Repo Rate Shock"
                resolved_cat_label = cat_name or "Debt Mutual Fund"
            else:
                seniority = "EQUITY"
                personas = ["compounding", "asymmetric_upside"]
                recourse = "Diversified Underlying Equity Portfolio (AMFI NAV Liquidation)"
                failure = "Market-Wide Equity Drawdown / Active Fund Underperformance"
                resolved_cat_label = cat_name or "Equity Mutual Fund"

            items.append({
                "id": f.get("scheme_code"),
                "symbol": f.get("scheme_code"),
                "name": scheme_name,
                "asset_class": "MF",
                "category_label": resolved_cat_label,
                **metric,
                "seniority_tier": seniority,
                "seniority_rank": SENIORITY_RANKS.get(seniority, 5),
                "credit_rating": "SEBI Monitored Portfolio",
                "macaulay_duration_years": None,
                "tenure_bucket": None,
                "min_ticket_inr": 500.0,
                "liquidity_tier": "INSTANT_T1",
                "recovery_recourse": recourse,
                "primary_failure_mode": failure,
                "detail_url": f"/funds/{f.get('scheme_code')}",
                "persona_tags": personas,
            })
    except Exception as e:
        logger.error("Error aggregating mutual funds for Opportunity Terminal: %s", e)

    # ----------------------------------------------------
    # 6. National ETFs (Commodity ETFs classified as COMMODITY_BACKED_TRUST, never SOVEREIGN)
    # ----------------------------------------------------
    try:
        etfs = get_etf_matrix()
        for e in etfs:
            category = str(e.get("category") or "EQUITY_INDEX").upper()
            scheme_name = str(e.get("scheme_name") or e.get("fund_name") or e.get("name") or "National ETF")
            underlying_idx = str(e.get("underlying_index") or "")
            bullion_probe = f"{scheme_name} {underlying_idx}"
            is_commodity = (
                category in ("COMMODITY_GOLD", "COMMODITY_SILVER")
                or "GOLD" in category
                or "SILVER" in category
                or bool(
                    re.search(r"\b(gold(?!man)\b|silver\b)", bullion_probe, re.IGNORECASE)
                    and "miner" not in bullion_probe.lower()
                )
            )
            is_equity = category == "EQUITY_INDEX" and not is_commodity
            sym = str(e.get("symbol") or "").strip()

            inputs = _source_metadata(e)
            ded_etf = inst_obs_map.get((sym, "ETF", "HISTORICAL_CAGR_3Y"))
            if ded_etf and not inputs.get("returns_3y_as_of"):
                metric = _observation("HISTORICAL_CAGR_3Y", ded_etf["value_pct"], ded_etf["as_of"], ded_etf["source"])
            else:
                metric = _observation(
                    "HISTORICAL_CAGR_3Y",
                    inputs.get("returns_3y_cagr"),
                    inputs.get("returns_3y_as_of"),
                    inputs.get("returns_3y_source"),
                )

            if is_equity:
                s_tier = "EQUITY"
                personas = ["compounding"]
                recourse = "Index Basket Physical Settlement / Creation Units"
            elif is_commodity:
                s_tier = "COMMODITY_BACKED_TRUST"
                personas = ["capital_preservation"]
                recourse = "Custodial Physical Bullion / Authorised Participant Creation Units"
            else:
                s_tier = "SENIOR_SECURED"
                personas = []
                recourse = "Index Basket Physical Settlement / Creation Units"

            items.append({
                "id": e.get("symbol"),
                "symbol": e.get("symbol"),
                "name": scheme_name,
                "asset_class": "ETF",
                "category_label": f"ETF ({category.replace('_', ' ').title()})",
                **metric,
                "seniority_tier": s_tier,
                "seniority_rank": SENIORITY_RANKS[s_tier],
                "credit_rating": "Physical / Benchmark Replication",
                "macaulay_duration_years": None,
                "tenure_bucket": None,
                "min_ticket_inr": _number(e.get("last_price")),
                "liquidity_tier": "EXCHANGE_ACTIVE",
                "recovery_recourse": recourse,
                "primary_failure_mode": "Exchange Price vs NAV Divergence / Tracking Error Drag",
                "detail_url": f"/etfs/{sym}" if sym else "/etfs",
                "persona_tags": personas,
            })
    except Exception as e:
        logger.error("Error aggregating ETFs for Opportunity Terminal: %s", e)

    # ----------------------------------------------------
    # 7. Fundamental Equities (Top Tracked Dossiers)
    # ----------------------------------------------------
    try:
        equity_reports = get_archived_reports(include_text=False)
        for eq in equity_reports[:10]:
            ticker = eq.get("ticker")
            if not ticker:
                continue
            metric = _equity_observation(eq, inst_obs_map)

            items.append({
                "id": ticker,
                "symbol": ticker,
                "name": eq.get("short_name") or ticker,
                "asset_class": "EQUITY",
                "category_label": "High-Moat Listed Equity",
                **metric,
                "seniority_tier": "EQUITY",
                "seniority_rank": SENIORITY_RANKS["EQUITY"],
                "credit_rating": "Forensic 7-Pillar Scored",
                "macaulay_duration_years": None,
                "tenure_bucket": None,
                "min_ticket_inr": _number(eq.get("baseline_price")),
                "liquidity_tier": "INSTANT_T1",
                "recovery_recourse": "Residual Common Equity (Zero Recourse)",
                "primary_failure_mode": "Governance Failure / Competitive Moat Erosion / SUE Miss",
                "detail_url": f"/dossier/{ticker}",
                "persona_tags": ["compounding"],
            })
    except Exception as e:
        logger.error("Error aggregating equities for Opportunity Terminal: %s", e)

    # ----------------------------------------------------
    # 8. Statutory Small Savings, Term Deposits & Retirement Schemes
    # ----------------------------------------------------
    try:
        savings_items = get_active_savings_instruments()
        for sv in savings_items:
            stale_info = sv.get("staleness") or {}
            stale_status = str(stale_info.get("status") or "FRESH").upper()
            src_url = str(sv.get("source_url") or "").strip()
            src_auth = str(sv.get("source_authority") or "").strip()
            if (
                sv.get("rate_type") == "MARKET_LINKED_NAV"
                or stale_status == "UNVERIFIED_PROVENANCE"
                or not src_url.lower().startswith("https://")
                or has_forbidden_vendor_token(f"{src_auth} {src_url}")
            ):
                metric = _observation(None)
            elif stale_status == "STALE_TARIFF":
                raw_val = _number(sv.get("base_rate_pct"))
                metric = {
                    "yield_type": "STATUTORY_OR_TARIFF_RATE",
                    "metric_status": "stale",
                    "metric_as_of": str(sv.get("effective_from") or "")[:10] or None,
                    "metric_source": src_auth or None,
                    "gross_yield_pct": None,
                    "last_observed_pct": raw_val,
                    "net_yield_pct": None,
                    "post_tax_status": "not_calculated",
                    "real_yield_pct": None,
                    "spread_vs_10y_gsec_bps": None,
                    "tax_statute": None,
                    "effective_tax_rate_pct": None,
                }
            else:
                notes = sv.get("notes") if isinstance(sv.get("notes"), dict) else {}
                freshness_anchor = notes.get("last_tariff_verified_on") or sv.get("effective_from")
                metric = _observation(
                    "STATUTORY_OR_TARIFF_RATE",
                    sv.get("base_rate_pct"),
                    freshness_anchor,
                    src_auth,
                )
                if metric.get("metric_status") == "available" and sv.get("effective_from"):
                    metric["metric_as_of"] = str(sv.get("effective_from"))[:10]
            max_months = int(sv.get("tenure_max_months") or 0)
            mat_years = round(max_months / 12.0, 2) if max_months > 0 else 0.25
            if sv.get("sovereign_backed"):
                s_tier = "SOVEREIGN"
                recourse = "Government of India Statutory Sovereign Guarantee"
                failure = "Statutory Quarterly Reset Drift / Premature Closure Lock-In"
            elif sv.get("dicgc_insured"):
                s_tier = "AAA_PSU"
                recourse = "DICGC Act Sec 16(1) ₹5,00,000 Principal + Accrued Interest Insurance"
                failure = "Uninsured Balance Above ₹5L Per Bank Charter / Premature Exit Penalty"
            else:
                s_tier = "SUBORDINATED"
                recourse = "Unsecured Public Deposit Claim (0% DICGC Cover; Ranks Behind Secured NCDs)"
                failure = "NBFC Liquidity Freeze / Unsecured Creditor Haircut"

            personas = ["capital_preservation"]
            if "PAYOUT" in str(sv.get("compounding_freq") or ""):
                personas.append("quarterly_cashflow")

            items.append({
                "id": sv["instrument_id"],
                "symbol": sv["instrument_id"],
                "name": sv["scheme_name"],
                "asset_class": "SAVINGS_DEPOSIT",
                "category_label": sv.get("category_label", "Fixed Savings & Deposit"),
                **metric,
                "seniority_tier": s_tier,
                "seniority_rank": SENIORITY_RANKS[s_tier],
                "credit_rating": sv.get("credit_rating", "DICGC_INSURED"),
                "macaulay_duration_years": None,
                "tenure_bucket": assign_tenure_bucket(mat_years),
                "min_ticket_inr": _number(sv.get("min_investment_inr")),
                "liquidity_tier": "INSTANT_T1" if int(sv.get("lock_in_months") or 0) == 0 else "PERIODIC_WINDOW",
                "recovery_recourse": recourse,
                "primary_failure_mode": failure,
                "detail_url": f"/savings/{sv['instrument_id']}",
                "persona_tags": personas,
            })
    except Exception as e:
        logger.error("Error aggregating fixed savings universe for Opportunity Terminal: %s", e)

    # Research categories filter inventory without implying suitability.
    if persona_filter:
        p_clean = persona_filter.strip().lower()
        if p_clean in ("capital_preservation", "preservation"):
            items = [x for x in items if "capital_preservation" in [p.lower() for p in x.get("persona_tags", [])]]
        elif p_clean in ("quarterly_cashflow", "maximum_cashflow", "cashflow"):
            items = [x for x in items if "quarterly_cashflow" in [p.lower() for p in x.get("persona_tags", [])]]
        elif p_clean in ("hni_real_assets", "real_assets"):
            items = [x for x in items if "hni_real_assets" in [p.lower() for p in x.get("persona_tags", [])]]
        elif p_clean in ("compounding", "asymmetric_upside", "upside"):
            items = [x for x in items if "compounding" in [p.lower() for p in x.get("persona_tags", [])]]
        else:
            items = [x for x in items if p_clean in [p.lower() for p in x.get("persona_tags", [])]]

    for item in items:
        item["comparison_group"] = _comparison_group(item) or None
    items.sort(key=_opportunity_order)
    return items


def get_heatmap_matrix(universe: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    """Show only dated debt observations, separated by measure and maturity band."""
    if universe is None:
        universe = get_normalized_opportunity_universe()

    buckets = ["<1Y", "1-3Y", "3-5Y", "5-10Y", "10Y+"]
    row_specs = [
        ("SOVEREIGN", "AUCTION_CUTOFF_YIELD", "Sovereign auction cut-off"),
        ("BOND", "CONTRACTUAL_YTM", "Corporate bond quoted YTM"),
        ("SDI", "CONTRACTUAL_YTM", "Securitised debt quoted YTM"),
        ("SAVINGS_DEPOSIT", "STATUTORY_OR_TARIFF_RATE", "Statutory & DICGC deposit rate"),
    ]
    rows = []
    for asset_class, kind, label in row_specs:
        cells = {}
        for bucket in buckets:
            matches = [
                item
                for item in universe
                if item["asset_class"] == asset_class
                and item["yield_type"] == kind
                and item["tenure_bucket"] == bucket
                and item["metric_status"] == "available"
            ]
            best = min(matches, key=_opportunity_order) if matches else None
            cells[bucket] = {"has_data": best is not None}
            if best:
                cells[bucket].update({
                    key: best[key]
                    for key in (
                        "id",
                        "symbol",
                        "name",
                        "gross_yield_pct",
                        "yield_type",
                        "metric_as_of",
                        "metric_status",
                        "metric_source",
                        "detail_url",
                    )
                })
        rows.append({"category_label": label, "cells": cells})
    return {"tenure_buckets": buckets, "rows": rows, "benchmark_10y_yield": None}


def get_arbitrage_comparison(
    item_ids: List[str],
    tax_slab: float = DEFAULT_TAX_SLAB_PCT,
    cpi_inflation: float = DEFAULT_MOSPI_CPI_INFLATION,
) -> Dict[str, Any]:
    """
    Builds the normalized side-by-side comparison scorecard for pinned items.
    """
    universe = get_normalized_opportunity_universe(tax_slab=tax_slab, cpi_inflation=cpi_inflation)
    id_map = {item["id"]: item for item in universe}

    selected_items = [id_map[item_id] for item_id in dict.fromkeys(item_ids) if item_id in id_map]

    return {
        "count": len(selected_items),
        "tax_slab_applied": None,
        "cpi_inflation_applied": None,
        "benchmark_10y_yield": None,
        "same_comparison_group": len(selected_items) >= 2
        and selected_items[0]["comparison_group"] is not None
        and all(
            item["comparison_group"] == selected_items[0]["comparison_group"]
            and item["metric_status"] == "available"
            for item in selected_items
        ),
        "items": selected_items,
    }
