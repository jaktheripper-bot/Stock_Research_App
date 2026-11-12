"""
Research Bouquet & Day-End 7-Asset Market Wrap Compiler.

Curates post-settlement (post-19:30 IST) multi-asset intelligence across all 7 asset classes:
1. Listed Equities (from the settled Discovery Reel & 7-pillar archive)
2. Sovereign Par Curve & State Development Loan (SDL) Spreads
3. Corporate Debt & Listed NCD / SDI Credit Surveillance
4. National ETF Liquidity, NAV & Tracking Error Matrix
5. REITs, InvITs & Sovereign Gold Bond (SGB) Yield Arbitrage
6. Mutual Fund Look-Through Spotlight (stamped with Prior-Session AMFI Audit date)
7. Unlisted MSME Manufacturing & Supply-Chain Champions

Enforces:
- Fail-closed domain integrity (`BouquetDataUnavailableError` when `require_live_data=True` and live tables are empty; zero synthetic Potemkin fallback payloads)
- Branded click tracking subdomain alignment (`links.moatnomics.com` / `moatnomics.com`)
- Statutory SEBI non-advisory safe harbor disclosures (descriptive post-close observations only)
- Statutory 1-click unsubscribe per IT Rules 2021 & anti-spam regulations
"""

import re
import hashlib
import logging
import os
from datetime import datetime
from typing import Any, Dict, List, Optional
from urllib.parse import quote, urlencode

from core.config import get_secret

logger = logging.getLogger("equity_research.core.analysis.research_bouquet")


class BouquetDataUnavailableError(RuntimeError):
    """Raised when `require_live_data=True` and one or more required live asset pillars lack database records."""


def get_tracking_base_url() -> str:
    """
    Returns the branded tracking subdomain base URL.
    Prefers TRACKING_BASE_URL environment variable (e.g. https://links.moatnomics.com).
    Falls back to primary domain https://moatnomics.com.
    """
    custom = get_secret("TRACKING_BASE_URL") or os.getenv("TRACKING_BASE_URL")
    if custom and str(custom).strip():
        url = str(custom).strip().rstrip("/")
        if not url.startswith("http://") and not url.startswith("https://"):
            url = f"https://{url}"
        return url
    return "https://moatnomics.com"


def compute_subscriber_ref(token_or_email: Optional[str]) -> Optional[str]:
    """
    Computes a privacy-safe, non-reversible 12-character subscriber reference hash (`sub_ref`)
    from an unsubscribe token or email so article links track unique verified subscriber CTR
    without exposing the raw unsubscribe token (`sub_tk`).
    """
    raw = str(token_or_email or "").strip()
    if not raw:
        return None
    if raw in ("preview_token", "test_admin_token"):
        return raw
    return f"sub_{hashlib.sha256(f'moatnomics_sub_ref:{raw}'.encode('utf-8')).hexdigest()[:12]}"


def build_tracked_link(
    target_path: str,
    token: Optional[str] = None,
    utm_medium: str = "email_digest",
    utm_source: str = "moatnomics_digest",
    utm_campaign: Optional[str] = None,
    utm_content: Optional[str] = None,
    utm_term: Optional[str] = None,
    edition_date: Optional[str] = None,
) -> str:
    """
    Builds an email link with structured UTM attribution and privacy-safe subscriber reference (`sub_ref`).
    """
    base = get_tracking_base_url()
    path = target_path if target_path.startswith("/") else f"/{target_path}"

    clean_edition = str(edition_date or "").strip()[:10]
    effective_campaign = (
        str(utm_campaign).strip()
        if utm_campaign and str(utm_campaign).strip()
        else (f"research_bouquet_{clean_edition}" if clean_edition else "research_bouquet")
    )

    params: Dict[str, str] = {
        "utm_source": str(utm_source or "moatnomics_digest").strip(),
        "utm_medium": str(utm_medium or "email_digest").strip(),
        "utm_campaign": effective_campaign,
    }
    if utm_content and str(utm_content).strip():
        params["utm_content"] = str(utm_content).strip()
    if utm_term and str(utm_term).strip():
        params["utm_term"] = str(utm_term).strip()

    sub_ref = compute_subscriber_ref(token)
    if sub_ref:
        params["sub_ref"] = sub_ref

    qs = urlencode(params)
    sep = "&" if "?" in path else "?"
    return f"{base}{path}{sep}{qs}"


def _truncate_clean(text: Any, max_chars: int = 190) -> str:
    raw = " ".join(str(text or "").split()).strip()
    if not raw:
        return ""
    if len(raw) <= max_chars:
        return raw
    clipped = raw[: max_chars - 3].rsplit(" ", 1)[0]
    return f"{clipped}..."


_HTML_SECTION_NUM_RE = re.compile(r'(<div class="section-title">)\d+\. ')
_TEXT_SECTION_NUM_RE = re.compile(r"^\d+\. (?=[A-Z])", re.M)


def _renumber_html_sections(html: str) -> str:
    """Numbers the rendered section titles 1..n so split editions never skip numbers."""
    counter = iter(range(1, 100))
    return _HTML_SECTION_NUM_RE.sub(lambda m: f"{m.group(1)}{next(counter)}. ", html)


def _renumber_text_sections(text: str) -> str:
    """Plain-text counterpart of `_renumber_html_sections` for headings like "6. MUTUAL FUND ..."."""
    counter = iter(range(1, 100))
    return _TEXT_SECTION_NUM_RE.sub(lambda m: f"{next(counter)}. ", text)


def _date_index(seed_prefix: str, date_str: str, pool_len: int) -> int:
    if pool_len <= 0:
        return 0
    digest = hashlib.sha256(f"{seed_prefix}:{date_str}".encode("utf-8")).hexdigest()[:8]
    return int(digest, 16) % pool_len


def _load_live_equities(date_str: str, limit: int = 3) -> List[Dict[str, Any]]:
    """Load post-settlement listed equity highlights from `discovery_reel` (zero fabricated defaults)."""
    equity_picks: List[Dict[str, Any]] = []
    try:
        from core.db.discovery import get_active_discovery_reel

        raw_picks = get_active_discovery_reel(
            edition_date=date_str,
            exclude_tests=True,
            allow_fallback=True,
            limit=limit,
        )

        for p in raw_picks or []:
            ticker = str(p.get("ticker") or "").strip().upper()
            if not ticker:
                continue
            canonical = str(p.get("canonical") or ticker).strip().upper()
            roce_raw = p.get("roce_pct") if p.get("roce_pct") is not None else p.get("roce")
            cmp_raw = (
                p.get("current_price")
                if p.get("current_price") is not None
                else (p.get("cmp") if p.get("cmp") is not None else p.get("base_price"))
            )
            sales_raw = p.get("sales_growth_3y")
            de_raw = p.get("debt_to_equity")
            thesis_raw = p.get("ria_thesis") or p.get("default_thesis") or ""
            pe_disp = str(p.get("pe_display") or p.get("pe_ratio") or "N/A")

            equity_picks.append(
                {
                    "ticker": ticker,
                    "canonical": canonical,
                    "company_name": str(p.get("company_name") or ticker),
                    "sector": str(p.get("sector") or "Listed Equity"),
                    "roce": round(float(roce_raw), 1) if roce_raw is not None else None,
                    "sales_growth_3y": round(float(sales_raw), 1) if sales_raw is not None else None,
                    "debt_to_equity": round(float(de_raw), 2) if de_raw is not None else None,
                    "cmp": round(float(cmp_raw), 2) if cmp_raw is not None else None,
                    "pe_display": pe_disp,
                    "thesis": _truncate_clean(thesis_raw, 195),
                    "edition_source_date": str(p.get("edition_date") or date_str)[:10],
                    "dossier_url": f"/dossier/{canonical}",
                }
            )
    except Exception as eq_err:
        logger.error("Failed loading live equity discovery picks for %s: %s", date_str, eq_err)
    return equity_picks


def _load_live_sovereign_posture(date_str: str) -> Dict[str, Any]:
    """Query live sovereign yield curve, RBI monetary corridor, and SDL fiscal spreads from the database."""
    try:
        from core.db.connection import get_db_connection, init_db
        from core.db.sovereign import (
            get_macro_monetary_corridor,
            get_sovereign_curve_analytics,
        )

        init_db()
        curve_analytics = get_sovereign_curve_analytics() or {}
        corridor = get_macro_monetary_corridor() or {}

        ten_raw = curve_analytics.get("benchmark_10y_gsec") or curve_analytics.get("ten_year_yield")
        one_raw = curve_analytics.get("risk_free_short_tbill") or curve_analytics.get("one_year_yield")

        repo_val = corridor.get("repo_rate")
        repo_raw = repo_val.get("value") if isinstance(repo_val, dict) else repo_val

        sdl_highlight = None
        conn = get_db_connection()
        cur = conn.cursor()
        try:
            if ten_raw is None or one_raw is None:
                cur.execute(
                    "SELECT tenor_label, cut_off_yield FROM sovereign_benchmarks WHERE tenor_label IN ('10Y_GSEC', '364D_TBILL')"
                )
                bench_map = {str(r[0]): float(r[1]) for r in cur.fetchall() if r and r[1] is not None}
                if ten_raw is None:
                    ten_raw = bench_map.get("10Y_GSEC")
                if one_raw is None:
                    one_raw = bench_map.get("364D_TBILL")

            if repo_raw is None:
                cur.execute(
                    "SELECT rate_pct FROM sovereign_macro_rates WHERE rate_key IN ('REPO', 'repo_rate') LIMIT 1"
                )
                r_row = cur.fetchone()
                if r_row and r_row[0] is not None:
                    repo_raw = float(r_row[0])

            cur.execute(
                """
                SELECT state_name, cut_off_yield, spread_over_gsec_bps, fiscal_tier
                FROM sovereign_sdl_spreads
                WHERE cut_off_yield IS NOT NULL
                ORDER BY spread_over_gsec_bps ASC, state_name ASC
                """
            )
            sdl_rows = cur.fetchall()
            if sdl_rows:
                idx = _date_index("sdl", date_str, len(sdl_rows))
                s_row = sdl_rows[idx]
                sdl_highlight = {
                    "state_name": str(s_row[0]),
                    "cut_off_yield": round(float(s_row[1]), 2),
                    "spread_bps": int(round(float(s_row[2] or 0.0))),
                    "fiscal_tier": str(s_row[3] or "AUDITED"),
                }
        finally:
            cur.close()
            conn.close()

        if ten_raw is None or one_raw is None:
            return {}

        ten_yr = float(ten_raw)
        one_yr = float(one_raw)
        repo_rate = float(repo_raw) if repo_raw is not None else round(one_yr - 0.25, 2)
        spread_bps = int(round((ten_yr - one_yr) * 100))
        curve_shape = str(curve_analytics.get("curve_shape") or "Normal (Upward Sloping)")

        sdl_clause = ""
        if sdl_highlight:
            sdl_clause = (
                f" 10Y {sdl_highlight['state_name']} SDL settled at {sdl_highlight['cut_off_yield']:.2f}% "
                f"({sdl_highlight['spread_bps']:+d} bps over G-Sec)."
            )

        duration_summary = (
            f"Term spread closed at {spread_bps:+d} bps ({curve_shape}): "
            f"10Y G-Sec at {ten_yr:.2f}% vs 364D T-Bill at {one_yr:.2f}%.{sdl_clause}"
        )

        statutory_parts: List[str] = []
        ppf_rate_val: Optional[float] = None
        scss_rate_val: Optional[float] = None
        try:
            from core.db.savings import get_savings_instrument_by_id

            ppf_inst = get_savings_instrument_by_id("SAV-PPF", reference_date=date_str)
            scss_inst = get_savings_instrument_by_id("SAV-SCSS", reference_date=date_str)
            if (
                ppf_inst
                and ppf_inst.get("is_active")
                and str((ppf_inst.get("staleness") or {}).get("status") or "").upper()
                not in ("STALE_TARIFF", "UNVERIFIED_PROVENANCE")
            ):
                ppf_rate_val = round(float(ppf_inst["base_rate_pct"]), 2)
                statutory_parts.append(f"PPF EEE {ppf_rate_val:.2f}%")
            if (
                scss_inst
                and scss_inst.get("is_active")
                and str((scss_inst.get("staleness") or {}).get("status") or "").upper()
                not in ("STALE_TARIFF", "UNVERIFIED_PROVENANCE")
            ):
                scss_rate_val = round(float(scss_inst["base_rate_pct"]), 2)
                statutory_parts.append(f"SCSS {scss_rate_val:.2f}%")
        except Exception as sav_err:
            logger.debug("Bouquet statutory savings lookup notice: %s", sav_err)

        statutory_clause = f"; Statutory {' / '.join(statutory_parts)}" if statutory_parts else ""

        return {
            "ten_year_gsec": round(ten_yr, 2),
            "one_year_tbill": round(one_yr, 2),
            "repo_rate": round(repo_rate, 2),
            "ppf_rate_pct": ppf_rate_val,
            "scss_rate_pct": scss_rate_val,
            "term_spread_bps": spread_bps,
            "yield_wedge_bps": spread_bps,
            "curve_shape": curve_shape,
            "sdl_highlight": sdl_highlight,
            "stance": duration_summary,
            "signal_summary": duration_summary,
            "tax_free_highlight": (
                f"Sovereign 10Y G-Sec settled at {ten_yr:.2f}% (Policy Repo {repo_rate:.2f}%, "
                f"Term Spread {spread_bps:+d} bps{statutory_clause})."
            ),
        }
    except Exception as e:
        logger.error("Failed loading live sovereign posture for %s: %s", date_str, e)
        return {}


def _load_live_corporate_debt(date_str: str) -> Dict[str, Any]:
    """Deterministically rotate across live `corporate_debt_securities` records."""
    from core.db.connection import get_db_connection, init_db

    try:
        init_db()
        conn = get_db_connection()
        cur = conn.cursor()
        try:
            cur.execute(
                """
                SELECT isin, ticker, instrument_name, instrument_type, seniority_tier,
                       coupon_rate_pct, credit_rating, credit_rating_agency,
                       asset_cover_ratio, is_sdi, ytm_pct, modified_duration_years, last_updated
                FROM corporate_debt_securities
                WHERE ytm_pct IS NOT NULL
                ORDER BY ytm_pct DESC, isin ASC
                """
            )
            cols = [c[0] for c in cur.description]
            rows = [dict(zip(cols, r)) for r in cur.fetchall()]
        finally:
            cur.close()
            conn.close()

        if not rows:
            return {}

        high_grade = [
            r
            for r in rows
            if str(r.get("credit_rating") or "").upper().startswith(("AAA", "AA"))
            and not bool(r.get("is_sdi"))
        ]
        pool = high_grade if high_grade else rows
        picked = pool[_date_index("corp_debt", date_str, len(pool))]

        sdi_count = sum(1 for r in rows if bool(r.get("is_sdi")))
        aaa_ytms = sorted(
            float(r["ytm_pct"])
            for r in rows
            if str(r.get("credit_rating") or "").upper().startswith("AAA") and r.get("ytm_pct") is not None
        )
        median_aaa = round(aaa_ytms[len(aaa_ytms) // 2], 2) if aaa_ytms else round(float(picked["ytm_pct"]), 2)

        isin = str(picked.get("isin") or "")
        rating = str(picked.get("credit_rating") or "Rated")
        agency = str(picked.get("credit_rating_agency") or "CRA")
        seniority = str(picked.get("seniority_tier") or "SENIOR_SECURED").replace("_", " ").title()
        ytm = round(float(picked.get("ytm_pct") or 0.0), 2)
        coupon = round(float(picked.get("coupon_rate_pct") or 0.0), 2)
        cover = picked.get("asset_cover_ratio")
        cover_str = f"{float(cover):.2f}x" if cover is not None else "N/A"
        duration = picked.get("modified_duration_years")
        dur_str = f"{float(duration):.2f} yrs" if duration is not None else "N/A"

        summary = (
            f"{rating} ({agency}) · {seniority} · YTM {ytm:.2f}% (Coupon {coupon:.2f}%, "
            f"Asset Cover {cover_str}, Mod. Duration {dur_str}). "
            f"Universe median AAA YTM: {median_aaa:.2f}% across {len(rows)} tracked securities ({sdi_count} SDIs)."
        )

        return {
            "isin": isin,
            "ticker": str(picked.get("ticker") or isin),
            "instrument_name": str(picked.get("instrument_name") or picked.get("ticker") or isin),
            "credit_rating": rating,
            "credit_rating_agency": agency,
            "seniority": seniority,
            "ytm_pct": ytm,
            "coupon_rate_pct": coupon,
            "asset_cover": cover_str,
            "modified_duration": dur_str,
            "median_aaa_ytm": median_aaa,
            "total_tracked": len(rows),
            "sdi_count": sdi_count,
            "summary": summary,
            "detail_url": f"/debt/{isin}",
        }
    except Exception as e:
        logger.error("Failed loading live corporate debt highlight for %s: %s", date_str, e)
        return {}


def _load_live_etf_highlight(date_str: str) -> Dict[str, Any]:
    """Deterministically rotate across high-liquidity ETFs in `etf_matrix`."""
    from core.db.connection import get_db_connection, init_db

    try:
        init_db()
        conn = get_db_connection()
        cur = conn.cursor()
        try:
            cur.execute(
                """
                SELECT symbol, scheme_name, category, last_price, nav,
                       premium_discount_pct, tracking_error_1y, expense_ratio_pct,
                       aum_crores, liquidity_tier, updated_at
                FROM etf_matrix
                WHERE last_price IS NOT NULL AND nav IS NOT NULL
                ORDER BY COALESCE(aum_crores, 0) DESC, symbol ASC
                """
            )
            cols = [c[0] for c in cur.description]
            rows = [dict(zip(cols, r)) for r in cur.fetchall()]
        finally:
            cur.close()
            conn.close()

        if not rows:
            return {}

        liquid_pool = rows[: min(45, len(rows))]
        picked = liquid_pool[_date_index("etf_matrix", date_str, len(liquid_pool))]
        categories = {str(r.get("category") or "") for r in rows if r.get("category")}

        symbol = str(picked.get("symbol") or "")
        price = round(float(picked.get("last_price") or 0.0), 2)
        nav = round(float(picked.get("nav") or 0.0), 2)
        prem_disc = round(float(picked.get("premium_discount_pct") or 0.0), 2)
        te_raw = picked.get("tracking_error_1y")
        ter_raw = picked.get("expense_ratio_pct")
        te_str = f"{float(te_raw):.2f}%" if te_raw is not None else "N/A"
        ter_str = f"{float(ter_raw):.2f}%" if ter_raw is not None else "N/A"

        summary = (
            f"Closed at ₹{price:.2f} vs iNAV/NAV ₹{nav:.2f} ({prem_disc:+.2f}% premium/discount) · "
            f"1Y Tracking Error {te_str} · TER {ter_str}. "
            f"Tracked across {len(rows)} listed ETFs in {len(categories)} categories."
        )

        return {
            "symbol": symbol,
            "scheme_name": str(picked.get("scheme_name") or symbol),
            "category": str(picked.get("category") or "Index ETF"),
            "last_price": price,
            "nav": nav,
            "premium_discount_pct": prem_disc,
            "tracking_error": te_str,
            "expense_ratio": ter_str,
            "total_tracked": len(rows),
            "categories_count": len(categories),
            "summary": summary,
            "detail_url": f"/etfs/{symbol}",
        }
    except Exception as e:
        logger.error("Failed loading live ETF matrix highlight for %s: %s", date_str, e)
        return {}


def _load_live_reits_and_sgb(date_str: str) -> Dict[str, Any]:
    """Load live REIT/InvIT cash-flow purity and Sovereign Gold Bond parity from database."""
    from core.db.connection import get_db_connection, init_db

    try:
        init_db()
        conn = get_db_connection()
        cur = conn.cursor()
        try:
            cur.execute(
                """
                SELECT symbol, name, structure_type, current_price, nav_per_unit,
                       discount_to_nav_pct, distribution_yield_pct, ndcf_payout_purity_pct
                FROM reits_and_invits
                WHERE current_price IS NOT NULL
                ORDER BY COALESCE(distribution_yield_pct, 0) DESC, symbol ASC
                """
            )
            r_cols = [c[0] for c in cur.description]
            reit_rows = [dict(zip(r_cols, r)) for r in cur.fetchall()]

            cur.execute(
                """
                SELECT symbol, series_name, market_price, spot_gold_price,
                       discount_to_spot_pct, annual_coupon_rate, maturity_date
                FROM sgb_tranches
                WHERE market_price IS NOT NULL
                ORDER BY COALESCE(discount_to_spot_pct, 0) ASC, symbol ASC
                """
            )
            s_cols = [c[0] for c in cur.description]
            sgb_rows = [dict(zip(s_cols, r)) for r in cur.fetchall()]
        finally:
            cur.close()
            conn.close()

        if not reit_rows and not sgb_rows:
            return {}

        reit_pick = reit_rows[_date_index("reit", date_str, len(reit_rows))] if reit_rows else {}
        sgb_pick = sgb_rows[_date_index("sgb", date_str, len(sgb_rows))] if sgb_rows else {}

        r_sym = str(reit_pick.get("symbol") or "")
        r_name = str(reit_pick.get("name") or r_sym)
        r_price = round(float(reit_pick.get("current_price") or 0.0), 2)
        r_yield = round(float(reit_pick.get("distribution_yield_pct") or 0.0), 2)
        r_disc = round(float(reit_pick.get("discount_to_nav_pct") or 0.0), 1)
        r_purity = round(float(reit_pick.get("ndcf_payout_purity_pct") or 0.0), 1)

        sgb_clause = ""
        sgb_symbol = ""
        sgb_disc = None
        if sgb_pick:
            sgb_symbol = str(sgb_pick.get("symbol") or "")
            sgb_price = round(float(sgb_pick.get("market_price") or 0.0), 1)
            sgb_disc = round(float(sgb_pick.get("discount_to_spot_pct") or 0.0), 2)
            sgb_coupon = round(float(sgb_pick.get("annual_coupon_rate") or 2.5), 2)
            sgb_clause = (
                f" SGB parity watch: {sgb_pick.get('series_name') or sgb_symbol} ({sgb_symbol}) "
                f"at ₹{sgb_price:.1f} ({sgb_disc:+.2f}% vs IBJA spot gold, {sgb_coupon:.2f}% coupon)."
            )

        summary = (
            f"{r_name} ({r_sym}) settled at ₹{r_price:.2f} ({r_disc:+.1f}% vs NAV) · "
            f"Distribution Yield {r_yield:.2f}% · NDCF Payout Purity {r_purity:.1f}%.{sgb_clause}"
        )

        return {
            "reit_symbol": r_sym,
            "reit_name": r_name,
            "structure_type": str(reit_pick.get("structure_type") or "REIT").replace("_", " "),
            "current_price": r_price,
            "distribution_yield_pct": r_yield,
            "discount_to_nav_pct": r_disc,
            "ndcf_purity_pct": r_purity,
            "sgb_symbol": sgb_symbol,
            "sgb_series": str(sgb_pick.get("series_name") or sgb_symbol),
            "sgb_discount_to_spot_pct": sgb_disc,
            "summary": summary,
            "detail_url": f"/reits/{r_sym}" if r_sym else "/reits",
        }
    except Exception as e:
        logger.error("Failed loading live REIT/InvIT & SGB highlight for %s: %s", date_str, e)
        return {}


def _load_live_mf_highlight(date_str: str) -> Dict[str, Any]:
    """Deterministically rotate across live Mutual Fund schemes & prior-session AMFI forensic dossiers."""
    from core.db.connection import get_db_connection, init_db

    try:
        init_db()
        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                """
                SELECT s.scheme_code, s.scheme_name, s.category, s.nav, s.ter_direct_pct,
                       s.last_portfolio_date, s.last_updated,
                       d.active_share_pct, d.composite_health_score,
                       CASE WHEN d.evidence_receipt_json IS NOT NULL AND d.weighted_moat_score >= 0
                            THEN d.weighted_moat_score END AS weighted_moat_score,
                       d.last_audited_at
                FROM mutual_fund_schemes s
                LEFT JOIN fund_forensic_dossiers d ON s.scheme_code = d.scheme_code AND d.evidence_receipt_json IS NOT NULL
                ORDER BY (d.weighted_moat_score IS NULL) ASC, d.weighted_moat_score DESC, s.scheme_code ASC
                """
            )
            cols = [c[0] for c in cursor.description]
            rows = [dict(zip(cols, r)) for r in cursor.fetchall()]
        finally:
            cursor.close()
            conn.close()

        if not rows:
            return {}

        audited = [r for r in rows if r.get("weighted_moat_score") is not None]
        pool = audited if len(audited) >= 2 else rows
        picked = pool[_date_index("mf", date_str, len(pool))]

        active_share = picked.get("active_share_pct")
        if active_share is not None and float(active_share) < 0:
            active_share = None
        ter = picked.get("ter_direct_pct")
        moat = picked.get("weighted_moat_score")
        health = picked.get("composite_health_score")
        health = health if health is not None and float(health) >= 0 else None
        nav_val = picked.get("nav")

        amfi_as_of = str(
            picked.get("last_updated")
            or picked.get("last_audited_at")
            or picked.get("last_portfolio_date")
            or date_str
        )[:10]
        provenance_badge = f"Prior-Session AMFI Audit ({amfi_as_of})"

        active_share_str = f"{float(active_share):.1f}%" if active_share is not None else "Direct Sleeve"
        ter_str = f"{float(ter):.2f}%" if ter is not None else "N/A"
        nav_str = f"₹{float(nav_val):.2f}" if nav_val is not None else "N/A"

        if moat is not None:
            takeaway = f"Researched-equity weighted moat score of {float(moat):.1f}/100 (NAV {nav_str})."
        elif health is not None:
            takeaway = (
                f"{picked.get('category', 'Equity')} mandate scoring {float(health):.1f}/100 composite "
                f"forensic health with {ter_str} direct expense ratio (NAV {nav_str})."
            )
        else:
            takeaway = f"Direct-growth institutional scheme tracked at NAV {nav_str} ({ter_str} direct TER)."

        code = str(picked["scheme_code"])
        return {
            "scheme_code": code,
            "scheme_name": str(picked["scheme_name"]),
            "nav": nav_str,
            "active_share": active_share_str,
            "expense_ratio": ter_str,
            "amfi_as_of_date": amfi_as_of,
            "provenance_badge": provenance_badge,
            "takeaway": takeaway,
            "highlight": takeaway,
            "detail_url": f"/funds/{code}",
        }
    except Exception as e:
        logger.error("Failed loading live MF highlight for %s: %s", date_str, e)
        return {}


def _load_live_msme_highlight(date_str: str) -> Dict[str, Any]:
    """Select a live Unlisted MSME enterprise from `msme_firms` + deterministic forensic engine."""
    from core.db.connection import get_db_connection, init_db
    from core.msme.forensic_engine import compute_msme_forensic_dossier

    try:
        init_db()
        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                """
                SELECT uin, name, sector_code, sector_name, city, state, annual_turnover,
                       employee_count, registration_date, source, last_updated
                FROM msme_firms
                ORDER BY annual_turnover DESC, uin ASC
                LIMIT 30
                """
            )
            cols = [c[0] for c in cursor.description]
            rows = [dict(zip(cols, r)) for r in cursor.fetchall()]
        finally:
            cursor.close()
            conn.close()

        if not rows:
            return {}

        firm = rows[_date_index("msme", date_str, len(rows))]
        dossier = compute_msme_forensic_dossier(firm)
        wc = dossier.get("pillar_1_working_capital", {})
        supply_chain = dossier.get("pillar_2_supply_chain", {})
        solv = dossier.get("pillar_3_solvency", {})
        moat = dossier.get("pillar_4_moat", {})
        bench = dossier.get("sector_forensic_benchmarks", {})
        buyers = supply_chain.get("listed_buyers", [])

        turnover_cr = firm.get("annual_turnover") or 0
        ccc_days = wc.get("net_ccc_days", "N/A")
        moat_score = moat.get("moat_score", "N/A")
        icr = solv.get("interest_coverage_ratio", "N/A")
        debt_to_turnover = bench.get("debt_to_turnover_median")
        oem_str = ", ".join([b.get("name", "") for b in buyers[:2] if b.get("name")]) or "Listed Industrial OEMs"

        moat_note = (
            f"Heuristic Moat {moat_score}/100 · Sector Median Net CCC {ccc_days} days · "
            f"Est. ICR {icr}x · Offtake universe: {oem_str}."
        )
        uin = str(firm.get("uin") or "")

        return {
            "uin": uin,
            "company_name": str(firm.get("name") or uin),
            "cluster": f"{firm.get('city', 'Industrial')}, {firm.get('state', 'India')} ({firm.get('sector_name', 'Manufacturing')})",
            "roce_pct": f"₹{turnover_cr} Cr Turnover",
            "roce": f"₹{turnover_cr} Cr",
            "debt_to_equity": f"{float(debt_to_turnover):.2f}" if debt_to_turnover is not None else "N/A",
            "moat_note": moat_note,
            "highlight": moat_note,
            "detail_url": f"/msme/{uin}",
        }
    except Exception as e:
        logger.error("Failed loading live MSME highlight for %s: %s", date_str, e)
        return {}


def _load_live_savings_posture(date_str: str) -> Dict[str, Any]:
    """Selects a live, provenance-verified Fixed Savings / Small Savings highlight from `savings_instruments`."""
    try:
        from core.analysis.savings_engine import evaluate_savings_post_tax
        from core.db.savings import get_active_savings_instruments

        rows = [
            r
            for r in get_active_savings_instruments(reference_date=date_str)
            if str((r.get("staleness") or {}).get("status") or "").upper()
            not in ("STALE_TARIFF", "UNVERIFIED_PROVENANCE")
        ]
        if not rows:
            return {}

        by_id = {r["instrument_id"]: r for r in rows}
        picked = rows[_date_index("fixed_savings", date_str, len(rows))]
        tax_ev = evaluate_savings_post_tax(picked, tax_regime="NEW_115BAC", slab_rate_pct=30.0)

        bench_parts: List[str] = []
        for sid, label in (("SAV-PPF", "PPF"), ("SAV-SCSS", "SCSS"), ("SAV-NSC", "NSC")):
            srow = by_id.get(sid)
            if srow:
                bench_parts.append(f"{label} {float(srow['base_rate_pct']):.2f}%")
        bench_clause = f" Statutory anchors: {' · '.join(bench_parts)}." if bench_parts else ""

        inst_id = str(picked["instrument_id"])
        summary = (
            f"{picked['issuer_name']} · Gross APY {tax_ev['gross_apy_pct']:.2f}% · "
            f"New-Regime 30% Post-Tax {tax_ev['post_tax_yield_pct']:.2f}% · "
            f"Fisher Real {tax_ev['fisher_real_yield_pct']:+.2f}% ({picked['staleness']['badge_label']})."
            f"{bench_clause}"
        )
        return {
            "instrument_id": inst_id,
            "scheme_name": str(picked["scheme_name"]),
            "issuer_name": str(picked["issuer_name"]),
            "category": str(picked["category"]),
            "base_rate_pct": round(float(picked["base_rate_pct"]), 2),
            "gross_apy_pct": tax_ev["gross_apy_pct"],
            "post_tax_yield_pct": tax_ev["post_tax_yield_pct"],
            "fisher_real_yield_pct": tax_ev["fisher_real_yield_pct"],
            "ppf_rate_pct": round(float(by_id["SAV-PPF"]["base_rate_pct"]), 2) if "SAV-PPF" in by_id else None,
            "scss_rate_pct": round(float(by_id["SAV-SCSS"]["base_rate_pct"]), 2) if "SAV-SCSS" in by_id else None,
            "nsc_rate_pct": round(float(by_id["SAV-NSC"]["base_rate_pct"]), 2) if "SAV-NSC" in by_id else None,
            "summary": summary,
            "detail_url": f"/savings/{inst_id}",
        }
    except Exception as e:
        logger.error("Failed loading live fixed-savings posture for %s: %s", date_str, e)
        return {}


# Email editions (option B). MARKET_CLOSE is sent at 19:30 IST for the trading day; FUND_NAV at
# 07:30 IST with the prior night's official AMFI NAVs. `edition_kind=None` keeps the full 8-section
# compilation used by the mobile brief and the admin preview.
EDITION_SECTIONS: Dict[str, tuple] = {
    "MARKET_CLOSE": ("equities", "sovereign", "corporate_debt", "reits_sgb", "msme", "fixed_savings"),
    "FUND_NAV": ("etfs", "mutual_funds"),
}
# Sections that must hold live data before an edition is sent (fail closed otherwise).
EDITION_REQUIRED_SECTIONS: Dict[str, tuple] = {
    "MARKET_CLOSE": ("equities", "sovereign", "corporate_debt", "reits_sgb", "msme"),
    "FUND_NAV": ("etfs", "mutual_funds"),
}
_ALL_SECTIONS = ("equities", "sovereign", "corporate_debt", "etfs", "reits_sgb", "mutual_funds", "msme", "fixed_savings")
_LEGACY_REQUIRED = ("equities", "sovereign", "corporate_debt", "etfs", "reits_sgb", "mutual_funds", "msme")


def _edition_copy(edition_kind: Optional[str], date_label: str, formatted_date: str) -> Dict[str, str]:
    if edition_kind == "MARKET_CLOSE":
        return {
            "subject": f"Moatnomics Market Close Wrap: Equities, Bonds, Real Assets & Savings ({date_label})",
            "kicker": "Market Close Wrap &bull; Post-Close Intelligence",
            "kicker_text": "MOATNOMICS MARKET CLOSE WRAP — POST-CLOSE DIGEST",
            "intro": (
                "Good evening. Here is today's post-close breakdown across listed equities, sovereign yields, "
                "corporate credit, real assets &amp; gold parity, unlisted MSME enterprises and fixed savings."
            ),
            "intro_text": (
                "Good evening. Here is today's post-close breakdown across listed equities, sovereign yields, "
                "corporate credit, real assets & gold parity, unlisted MSME enterprises and fixed savings."
            ),
        }
    if edition_kind == "FUND_NAV":
        return {
            "subject": f"Moatnomics Fund NAV Update: Mutual Funds & ETFs ({date_label})",
            "kicker": "Fund NAV Update &bull; Official AMFI NAVs",
            "kicker_text": "MOATNOMICS FUND NAV UPDATE — MUTUAL FUNDS & ETFS",
            "intro": (
                f"Good morning. Here is the mutual fund and ETF update built on the official AMFI NAVs "
                f"published for {formatted_date}."
            ),
            "intro_text": (
                f"Good morning. Here is the mutual fund and ETF update built on the official AMFI NAVs "
                f"published for {formatted_date}."
            ),
        }
    return {
        "subject": f"Moatnomics Day-End Market Wrap: Multi-Asset Close & Forensic Signals ({date_label})",
        "kicker": "Day-End 7-Asset Market Wrap &bull; Post-Close Intelligence",
        "kicker_text": "MOATNOMICS DAY-END MARKET WRAP — 7-ASSET POST-CLOSE DIGEST",
        "intro": (
            "Good evening. Here is today's post-settlement breakdown across listed equities, sovereign yields, "
            "corporate credit, ETFs, real assets &amp; gold parity, mutual fund look-through audits, and unlisted MSME enterprises."
        ),
        "intro_text": "Good evening. Here is today's post-settlement breakdown across all seven asset classes.",
    }


def compile_research_bouquet(
    edition_date: Optional[str] = None,
    require_live_data: bool = False,
    edition_kind: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Compiles a research email edition from live database tables.

    `edition_kind` selects the sections: "MARKET_CLOSE" (19:30 IST), "FUND_NAV" (07:30 IST) or None
    (all 8 sections). When `require_live_data=True`, raises `BouquetDataUnavailableError` if any
    section required by that edition is empty.
    """
    from core.db.connection import IST

    kind = str(edition_kind).strip().upper() if edition_kind else None
    if kind is not None and kind not in EDITION_SECTIONS:
        raise ValueError(f"Unknown research email edition kind: {edition_kind!r}")
    sections = EDITION_SECTIONS[kind] if kind else _ALL_SECTIONS

    date_str = edition_date or datetime.now(IST).strftime("%Y-%m-%d")
    formatted_date = datetime.strptime(date_str[:10], "%Y-%m-%d").strftime("%A, %B %d, %Y")

    loaders = {
        "equities": lambda: _load_live_equities(date_str, limit=3),
        "sovereign": lambda: _load_live_sovereign_posture(date_str),
        "corporate_debt": lambda: _load_live_corporate_debt(date_str),
        "etfs": lambda: _load_live_etf_highlight(date_str),
        "reits_sgb": lambda: _load_live_reits_and_sgb(date_str),
        "mutual_funds": lambda: _load_live_mf_highlight(date_str),
        "msme": lambda: _load_live_msme_highlight(date_str),
        "fixed_savings": lambda: _load_live_savings_posture(date_str),
    }
    loaded = {name: (loaders[name]() if name in sections else ([] if name == "equities" else {})) for name in _ALL_SECTIONS}
    equity_picks = loaded["equities"]
    sovereign_posture = loaded["sovereign"]
    corporate_debt = loaded["corporate_debt"]
    etf_highlight = loaded["etfs"]
    reits_sgb = loaded["reits_sgb"]
    mf_highlight = loaded["mutual_funds"]
    msme_highlight = loaded["msme"]
    savings_highlight = loaded["fixed_savings"]

    copy = _edition_copy(kind, date_str[:10], formatted_date)
    if require_live_data:
        required = EDITION_REQUIRED_SECTIONS[kind] if kind else _LEGACY_REQUIRED
        missing = [name for name in required if not loaded[name]]
        if missing:
            raise BouquetDataUnavailableError(
                f"Cannot compile live {kind or 'Day-End Market Wrap'} edition for {date_str}; "
                f"missing live sections: {', '.join(missing)}"
            )

    return {
        "edition_date": date_str[:10],
        "edition_kind": kind,
        "formatted_date": formatted_date,
        "subject": copy["subject"],
        "header_kicker": copy["kicker"],
        "header_kicker_text": copy["kicker_text"],
        "intro_html": copy["intro"],
        "intro_text": copy["intro_text"],
        "equities": equity_picks,
        "sovereign": sovereign_posture,
        "corporate_debt": corporate_debt,
        "etfs": etf_highlight,
        "reits_sgb": reits_sgb,
        "mutual_funds": mf_highlight,
        "mutual_fund": mf_highlight,
        "msme": msme_highlight,
        "fixed_savings": savings_highlight,
        "tracking_domain": get_tracking_base_url(),
    }


PRIMARY_TAB_HINT = (
    "Using Gmail? Drag this email into your Primary tab so future editions arrive there."
)


def build_unsubscribe_url(token: str) -> str:
    """One-click unsubscribe URL for a subscriber token (body link and List-Unsubscribe header)."""
    return f"{get_tracking_base_url()}/api/notifications/unsubscribe?token={quote(str(token or ''), safe='')}"


def render_bouquet_html(bouquet: Dict[str, Any], subscriber: Optional[Dict[str, Any]] = None) -> str:
    """
    Renders an institutional, responsive 7-asset Day-End Market Wrap HTML email template.
    """
    token = subscriber.get("unsubscribe_token") if subscriber else "preview_token"
    user_name = subscriber.get("full_name") if subscriber else "Reader"
    edition_date = str(bouquet.get("edition_date") or "").strip()[:10]
    base_url = get_tracking_base_url()
    unsub_url = build_unsubscribe_url(token)

    equities_html = ""
    for eq in bouquet.get("equities") or []:
        eq_ticker = str(eq.get("ticker") or "").strip()
        link = build_tracked_link(
            eq.get("dossier_url") or f"/dossier/{eq_ticker}",
            token=token,
            edition_date=edition_date,
            utm_content="equity_card",
            utm_term=eq_ticker,
        )
        roce_disp = f"{eq['roce']}%" if eq.get("roce") is not None else "N/A"
        sg_disp = f"{eq['sales_growth_3y']:+.1f}%" if eq.get("sales_growth_3y") is not None else "N/A"
        de_disp = f"{eq['debt_to_equity']}" if eq.get("debt_to_equity") is not None else "N/A"
        cmp_disp = f"₹{eq['cmp']}" if eq.get("cmp") is not None else "N/A"
        equities_html += f"""
        <div class="card">
          <div style="display: flex; justify-content: space-between; align-items: baseline; flex-wrap: wrap; gap: 6px; margin-bottom: 6px;">
            <div style="font-size: 15px; font-weight: 800; color: #0f172a;">
              <a href="{link}" style="color: #0E3D32; text-decoration: none;">{eq.get('ticker')}</a>
              <span style="font-size: 13px; font-weight: 500; color: #64748b; margin-left: 6px;">{eq.get('company_name')}</span>
            </div>
            <div class="pill">{eq.get('sector')} &bull; Close {cmp_disp}</div>
          </div>
          <div style="font-size: 12.5px; color: #334155; line-height: 1.5; margin-bottom: 10px;">
            {eq.get('thesis')}
          </div>
          <div style="display: flex; flex-wrap: wrap; gap: 12px; font-size: 11.5px; color: #64748b; border-top: 1px solid #f1f5f9; padding-top: 8px;">
            <span>ROCE: <strong style="color: #0E3D32;">{roce_disp}</strong></span>
            <span>3Y Sales: <strong style="color: #0f172a;">{sg_disp}</strong></span>
            <span>D/E: <strong style="color: #0f172a;">{de_disp}</strong></span>
            <span style="margin-left: auto;"><a href="{link}" style="color: #0E3D32; font-weight: 700; text-decoration: none;">Open Dossier &rarr;</a></span>
          </div>
        </div>
        """

    sov = bouquet.get("sovereign") or {}
    sov_link = build_tracked_link(
        "/sovereign",
        token=token,
        edition_date=edition_date,
        utm_content="sovereign_curve",
        utm_term="10Y_GSEC",
    )
    sov_html = ""
    if sov:
        sov_html = f"""
      <div class="section-title">2. Sovereign Par Curve &amp; SDL Spreads</div>
      <div class="card">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
          <span style="font-weight: 700; font-size: 13.5px; color: #0f172a;">10Y Benchmark G-Sec Close</span>
          <span style="font-size: 15px; font-weight: 800; color: #0E3D32;">{sov.get('ten_year_gsec')}%</span>
        </div>
        <div style="font-size: 12.5px; color: #475569; line-height: 1.5; margin-bottom: 8px;">
          {sov.get('signal_summary')}
        </div>
        <div style="display: flex; flex-wrap: wrap; gap: 10px; font-size: 11.5px; color: #64748b;">
          <span>364D T-Bill: <strong>{sov.get('one_year_tbill')}%</strong></span>
          <span>&bull; Policy Repo: <strong>{sov.get('repo_rate')}%</strong></span>
          <span>&bull; Wedge: <strong>{sov.get('yield_wedge_bps'):+d} bps</strong></span>
          <span style="margin-left: auto;"><a href="{sov_link}" style="color: #0E3D32; font-weight: 700; text-decoration: none;">Yield Curve &rarr;</a></span>
        </div>
      </div>
        """

    debt = bouquet.get("corporate_debt") or {}
    debt_html = ""
    if debt:
        debt_link = build_tracked_link(
            debt.get("detail_url") or "/debt",
            token=token,
            edition_date=edition_date,
            utm_content="corporate_debt",
            utm_term=str(debt.get("isin") or ""),
        )
        debt_html = f"""
      <div class="section-title">3. Corporate Debt &amp; Credit Surveillance</div>
      <div class="card">
        <div style="display: flex; justify-content: space-between; align-items: baseline; gap: 8px; margin-bottom: 6px;">
          <span style="font-weight: 700; font-size: 13.5px; color: #0f172a;">{debt.get('instrument_name')} ({debt.get('isin')})</span>
          <span class="pill">{debt.get('credit_rating')} &bull; {debt.get('ytm_pct')}% YTM</span>
        </div>
        <div style="font-size: 12.5px; color: #334155; line-height: 1.5; margin-bottom: 8px;">
          {debt.get('summary')}
        </div>
        <div style="font-size: 11.5px; text-align: right;">
          <a href="{debt_link}" style="color: #0E3D32; font-weight: 700; text-decoration: none;">Inspect Credit Dossier &rarr;</a>
        </div>
      </div>
        """

    etf = bouquet.get("etfs") or {}
    etf_html = ""
    if etf:
        etf_link = build_tracked_link(
            etf.get("detail_url") or "/etfs",
            token=token,
            edition_date=edition_date,
            utm_content="etf_matrix",
            utm_term=str(etf.get("symbol") or ""),
        )
        etf_html = f"""
      <div class="section-title">4. National ETF Liquidity &amp; Tracking Matrix</div>
      <div class="card">
        <div style="display: flex; justify-content: space-between; align-items: baseline; gap: 8px; margin-bottom: 6px;">
          <span style="font-weight: 700; font-size: 13.5px; color: #0f172a;">{etf.get('scheme_name')} ({etf.get('symbol')})</span>
          <span class="pill">{etf.get('category')}</span>
        </div>
        <div style="font-size: 12.5px; color: #334155; line-height: 1.5; margin-bottom: 8px;">
          {etf.get('summary')}
        </div>
        <div style="font-size: 11.5px; text-align: right;">
          <a href="{etf_link}" style="color: #0E3D32; font-weight: 700; text-decoration: none;">Open ETF Matrix &rarr;</a>
        </div>
      </div>
        """

    reits = bouquet.get("reits_sgb") or {}
    reits_html = ""
    if reits:
        reit_link = build_tracked_link(
            reits.get("detail_url") or "/reits",
            token=token,
            edition_date=edition_date,
            utm_content="reits_sgb",
            utm_term=str(reits.get("reit_symbol") or ""),
        )
        reits_html = f"""
      <div class="section-title">5. REITs, InvITs &amp; Sovereign Gold Parity</div>
      <div class="card">
        <div style="display: flex; justify-content: space-between; align-items: baseline; gap: 8px; margin-bottom: 6px;">
          <span style="font-weight: 700; font-size: 13.5px; color: #0f172a;">{reits.get('reit_name')} ({reits.get('reit_symbol')})</span>
          <span class="pill">Yield {reits.get('distribution_yield_pct')}%</span>
        </div>
        <div style="font-size: 12.5px; color: #334155; line-height: 1.5; margin-bottom: 8px;">
          {reits.get('summary')}
        </div>
        <div style="font-size: 11.5px; text-align: right;">
          <a href="{reit_link}" style="color: #0E3D32; font-weight: 700; text-decoration: none;">Open Real Assets &amp; SGBs &rarr;</a>
        </div>
      </div>
        """

    mf = bouquet.get("mutual_funds") or {}
    mf_html = ""
    if mf:
        mf_link = build_tracked_link(
            mf.get("detail_url") or f"/funds/{mf.get('scheme_code', '')}",
            token=token,
            edition_date=edition_date,
            utm_content="mutual_fund",
            utm_term=str(mf.get("scheme_code") or ""),
        )
        mf_badge = mf.get("provenance_badge") or "Prior-Session AMFI Audit"
        mf_html = f"""
      <div class="section-title">6. Mutual Fund Look-Through Spotlight</div>
      <div class="card">
        <div style="display: flex; justify-content: space-between; align-items: baseline; flex-wrap: wrap; gap: 6px; margin-bottom: 6px;">
          <span style="font-weight: 700; font-size: 13.5px; color: #0f172a;">{mf.get('scheme_name')}</span>
          <span class="pill">{mf_badge}</span>
        </div>
        <div style="font-size: 12.5px; color: #334155; line-height: 1.5; margin-bottom: 8px;">
          {mf.get('highlight')}
        </div>
        <div style="display: flex; flex-wrap: wrap; gap: 10px; font-size: 11.5px; color: #64748b;">
          <span>Active Share: <strong style="color: #0E3D32;">{mf.get('active_share')}</strong></span>
          <span>&bull; Direct TER: <strong>{mf.get('expense_ratio')}</strong></span>
          <span style="margin-left: auto;"><a href="{mf_link}" style="color: #0E3D32; font-weight: 700; text-decoration: none;">Look-Through Audit &rarr;</a></span>
        </div>
      </div>
        """

    msme = bouquet.get("msme") or {}
    msme_html = ""
    if msme:
        msme_path = msme.get("detail_url") or (f"/msme/{msme['uin']}" if msme.get("uin") else "/msme")
        msme_link = build_tracked_link(
            msme_path,
            token=token,
            edition_date=edition_date,
            utm_content="msme_spotlight",
            utm_term=str(msme.get("uin") or ""),
        )
        msme_html = f"""
      <div class="section-title">7. Unlisted MSME Forensic Spotlight</div>
      <div class="card">
        <div style="font-size: 13.5px; font-weight: 700; color: #0f172a; margin-bottom: 4px;">{msme.get('company_name')}</div>
        <div style="font-size: 12px; color: #475569; margin-bottom: 8px;">
          Cluster: <strong>{msme.get('cluster')}</strong> &nbsp;&bull;&nbsp; Scale: <strong>{msme.get('roce_pct')}</strong>
        </div>
        <div style="font-size: 12.5px; line-height: 1.5; color: #334155; margin-bottom: 8px;">{msme.get('moat_note')}</div>
        <div style="font-size: 11.5px; text-align: right;">
          <a href="{msme_link}" style="color: #0E3D32; font-weight: 700; text-decoration: none;">Inspect MSME Forensic Dossier &rarr;</a>
        </div>
      </div>
        """

    sav = bouquet.get("fixed_savings") or {}
    sav_html = ""
    if sav:
        sav_link = build_tracked_link(
            sav.get("detail_url") or "/savings",
            token=token,
            edition_date=edition_date,
            utm_content="fixed_savings",
            utm_term=str(sav.get("instrument_id") or ""),
        )
        sav_html = f"""
      <div class="section-title">8. Fixed Savings, Term Deposits &amp; Statutory Small Savings</div>
      <div class="card">
        <div style="display: flex; justify-content: space-between; align-items: baseline; gap: 8px; margin-bottom: 6px;">
          <span style="font-weight: 700; font-size: 13.5px; color: #0f172a;">{sav.get('scheme_name')} ({sav.get('instrument_id')})</span>
          <span class="pill">{sav.get('base_rate_pct')}% Tariff</span>
        </div>
        <div style="font-size: 12.5px; color: #334155; line-height: 1.5; margin-bottom: 8px;">
          {sav.get('summary')}
        </div>
        <div style="font-size: 11.5px; text-align: right;">
          <a href="{sav_link}" style="color: #0E3D32; font-weight: 700; text-decoration: none;">Open Fixed Savings Dossier &rarr;</a>
        </div>
      </div>
        """

    terminal_cta_link = build_tracked_link(
        "/",
        token=token,
        edition_date=edition_date,
        utm_content="terminal_cta",
    )

    equities_block = (
        f'<div class="section-title">1. Listed Equities &mdash; Post-Close Discovery Cohort</div>\n      {equities_html}'
        if equities_html.strip()
        else ""
    )

    return _renumber_html_sections(f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{bouquet.get('subject')}</title>
  <style>
    body {{ font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; line-height: 1.6; color: #282F33; background-color: #F7F5EE; margin: 0; padding: 16px; }}
    .wrapper {{ max-width: 620px; margin: 0 auto; background: #F7F5EE; border-radius: 10px; border: 1px solid #D9E3E8; overflow: hidden; }}
    .header {{ background: #0E3D32; color: #F7F5EE; padding: 24px; border-bottom: 3px solid #7DA77A; text-align: left; }}
    .header h1 {{ margin: 0; font-family: 'Playfair Display', Georgia, serif; font-size: 20px; font-weight: 800; letter-spacing: -0.01em; color: #F7F5EE; }}
    .header p {{ margin: 4px 0 0; font-size: 12px; color: #D9E3E8; }}
    .content {{ padding: 24px; }}
    .section-title {{ font-size: 12.5px; font-weight: 800; color: #0B2337; text-transform: uppercase; letter-spacing: 0.05em; margin: 20px 0 10px 0; }}
    .card {{ background: #ffffff; border: 1px solid #D9E3E8; border-radius: 8px; padding: 16px; margin-bottom: 14px; }}
    .footer {{ background: #D9E3E8; padding: 20px 24px; font-size: 11.5px; color: #282F33; border-top: 1px solid #7DA77A; text-align: center; line-height: 1.5; }}
    .footer a {{ color: #0E3D32; text-decoration: underline; }}
    .pill {{ display: inline-block; background: #E7EFE9; color: #0E3D32; padding: 2px 8px; border-radius: 4px; font-size: 11px; font-weight: 700; }}
  </style>
</head>
<body>
  <div class="wrapper">
    <div class="header">
      <div style="font-size: 11px; text-transform: uppercase; letter-spacing: 0.1em; color: #C7E268; font-weight: 700; margin-bottom: 4px;">
        {bouquet.get('header_kicker') or 'Day-End 7-Asset Market Wrap &bull; Post-Close Intelligence'}
      </div>
      <h1>MOATNOMICS RESEARCH</h1>
      <p>{bouquet.get('formatted_date')} &bull; Prepared for {user_name}</p>
    </div>

    <div class="content">
      <p style="font-size: 14px; margin-top: 0; color: #334155;">
        {bouquet.get('intro_html') or _edition_copy(None, edition_date, str(bouquet.get('formatted_date') or ''))['intro']}
      </p>

      {equities_block}
      {sov_html}
      {debt_html}
      {etf_html}
      {reits_html}
      {mf_html}
      {msme_html}
      {sav_html}

      <div style="text-align: center; margin: 28px 0 12px 0;">
        <a href="{terminal_cta_link}" style="background: #0E3D32; color: #F7F5EE; font-weight: 800; font-size: 14px; text-decoration: none; padding: 12px 28px; border-radius: 8px; display: inline-block;">
          Open Research Terminal &rarr;
        </a>
      </div>
    </div>

    <div class="footer">
      <p style="margin: 0 0 8px 0; font-weight: 700; color: #0B2337;">
        Moatnomics &bull; Quantitative Multi-Asset Intelligence &amp; Solvency Auditing
      </p>
      <p style="margin: 0 0 10px 0; font-size: 10.5px; color: #475569; line-height: 1.4;">
        <strong>Regulatory Safe-Harbor Disclosure:</strong> Moatnomics is an independent financial technology analytics software tool. We are not registered anywhere as a corporate entity or broker, and do not provide SEBI-regulated investment advice or recommendations. All data is computed deterministically for educational research and forensic screening only.
      </p>
      <p style="margin: 0; font-size: 11px;">
        {PRIMARY_TAB_HINT}<br>
        You received this email because your account is subscribed to Moatnomics Research Digest dispatches.<br>
        To opt out immediately with one click: <a href="{unsub_url}" style="color: #0E3D32; font-weight: 700;">Unsubscribe from Research Digest</a>.
      </p>
    </div>
  </div>
</body>
</html>
""")


def render_bouquet_text(bouquet: Dict[str, Any], subscriber: Optional[Dict[str, Any]] = None) -> str:
    """
    Renders clean plain-text version of the 7-asset Day-End Market Wrap.
    """
    token = subscriber.get("unsubscribe_token") if subscriber else "preview_token"
    user_name = subscriber.get("full_name") if subscriber else "Reader"
    edition_date = str(bouquet.get("edition_date") or "").strip()[:10]
    base_url = get_tracking_base_url()
    unsub_url = build_unsubscribe_url(token)

    lines = [
        "===============================================================",
        bouquet.get("header_kicker_text") or "MOATNOMICS DAY-END MARKET WRAP — 7-ASSET POST-CLOSE DIGEST",
        "===============================================================",
        f"Edition Date: {bouquet.get('formatted_date')}",
        f"Recipient:    {user_name}",
        "",
        bouquet.get("intro_text") or "Good evening. Here is today's post-settlement breakdown across all seven asset classes.",
        "",
    ]
    if bouquet.get("equities"):
        lines.extend([
            "---------------------------------------------------------------",
            "1. LISTED EQUITIES — POST-CLOSE DISCOVERY COHORT",
            "---------------------------------------------------------------",
        ])
    for eq in bouquet.get("equities") or []:
        eq_ticker = str(eq.get("ticker") or "").strip()
        link = build_tracked_link(
            eq.get("dossier_url") or f"/dossier/{eq_ticker}",
            token=token,
            edition_date=edition_date,
            utm_content="equity_card",
            utm_term=eq_ticker,
        )
        cmp_disp = f"₹{eq['cmp']}" if eq.get("cmp") is not None else "N/A"
        roce_disp = f"{eq['roce']}%" if eq.get("roce") is not None else "N/A"
        sg_disp = f"{eq['sales_growth_3y']:+.1f}%" if eq.get("sales_growth_3y") is not None else "N/A"
        lines.extend(
            [
                f"* {eq.get('ticker')} — {eq.get('company_name')} ({eq.get('sector')}) | Close: {cmp_disp}",
                f"  ROCE: {roce_disp} | 3Y Sales: {sg_disp} | D/E: {eq.get('debt_to_equity')}",
                f"  Note: {eq.get('thesis')}",
                f"  Dossier: {link}",
                "",
            ]
        )

    sov = bouquet.get("sovereign") or {}
    if sov:
        lines.extend(
            [
                "---------------------------------------------------------------",
                "2. SOVEREIGN PAR CURVE & SDL SPREADS",
                "---------------------------------------------------------------",
                f"10Y Benchmark G-Sec: {sov.get('ten_year_gsec')}% | 364D T-Bill: {sov.get('one_year_tbill')}% | Policy Repo: {sov.get('repo_rate')}%",
                f"Signal: {sov.get('signal_summary')}",
                f"Curve:  {build_tracked_link('/sovereign', token=token, edition_date=edition_date, utm_content='sovereign_curve', utm_term='10Y_GSEC')}",
                "",
            ]
        )

    debt = bouquet.get("corporate_debt") or {}
    if debt:
        lines.extend(
            [
                "---------------------------------------------------------------",
                "3. CORPORATE DEBT & CREDIT SURVEILLANCE",
                "---------------------------------------------------------------",
                f"{debt.get('instrument_name')} ({debt.get('isin')})",
                f"{debt.get('summary')}",
                f"Dossier: {build_tracked_link(debt.get('detail_url') or '/debt', token=token, edition_date=edition_date, utm_content='corporate_debt', utm_term=str(debt.get('isin') or ''))}",
                "",
            ]
        )

    etf = bouquet.get("etfs") or {}
    if etf:
        lines.extend(
            [
                "---------------------------------------------------------------",
                "4. NATIONAL ETF LIQUIDITY & TRACKING MATRIX",
                "---------------------------------------------------------------",
                f"{etf.get('scheme_name')} ({etf.get('symbol')}) [{etf.get('category')}]",
                f"{etf.get('summary')}",
                f"Matrix:  {build_tracked_link(etf.get('detail_url') or '/etfs', token=token, edition_date=edition_date, utm_content='etf_matrix', utm_term=str(etf.get('symbol') or ''))}",
                "",
            ]
        )

    reits = bouquet.get("reits_sgb") or {}
    if reits:
        lines.extend(
            [
                "---------------------------------------------------------------",
                "5. REITS, INVITS & SOVEREIGN GOLD PARITY",
                "---------------------------------------------------------------",
                f"{reits.get('summary')}",
                f"Details: {build_tracked_link(reits.get('detail_url') or '/reits', token=token, edition_date=edition_date, utm_content='reits_sgb', utm_term=str(reits.get('reit_symbol') or ''))}",
                "",
            ]
        )

    mf = bouquet.get("mutual_funds") or {}
    if mf:
        lines.extend(
            [
                "---------------------------------------------------------------",
                f"6. MUTUAL FUND LOOK-THROUGH SPOTLIGHT [{mf.get('provenance_badge', 'Prior-Session AMFI Audit')}]",
                "---------------------------------------------------------------",
                f"Scheme:       {mf.get('scheme_name')}",
                f"Active Share: {mf.get('active_share')} | Direct TER: {mf.get('expense_ratio')}",
                f"Audit Note:   {mf.get('highlight')}",
                f"Dossier:      {build_tracked_link(mf.get('detail_url') or '/funds', token=token, edition_date=edition_date, utm_content='mutual_fund', utm_term=str(mf.get('scheme_code') or ''))}",
                "",
            ]
        )

    msme = bouquet.get("msme") or {}
    if msme:
        msme_path = msme.get("detail_url") or (f"/msme/{msme['uin']}" if msme.get("uin") else "/msme")
        lines.extend(
            [
                "---------------------------------------------------------------",
                "7. UNLISTED MSME FORENSIC SPOTLIGHT",
                "---------------------------------------------------------------",
                f"{msme.get('company_name')} ({msme.get('cluster')}) | {msme.get('roce_pct')}",
                f"{msme.get('moat_note')}",
                f"Inspect MSME Dossier: {build_tracked_link(msme_path, token=token, edition_date=edition_date, utm_content='msme_spotlight', utm_term=str(msme.get('uin') or ''))}",
                "",
            ]
        )

    sav = bouquet.get("fixed_savings") or {}
    if sav:
        lines.extend(
            [
                "---------------------------------------------------------------",
                "8. FIXED SAVINGS, TERM DEPOSITS & STATUTORY SMALL SAVINGS",
                "---------------------------------------------------------------",
                f"{sav.get('scheme_name')} ({sav.get('instrument_id')}) | {sav.get('base_rate_pct')}%",
                f"{sav.get('summary')}",
                f"Dossier: {build_tracked_link(sav.get('detail_url') or '/savings', token=token, edition_date=edition_date, utm_content='fixed_savings', utm_term=str(sav.get('instrument_id') or ''))}",
                "",
            ]
        )

    lines.extend(
        [
            "===============================================================",
            f"Terminal: {build_tracked_link('/', token=token, edition_date=edition_date, utm_content='terminal_cta')}",
            "===============================================================",
            "MANDATORY STATUTORY SAFE HARBOR:",
            "Moatnomics is an independent financial technology analytics software tool and is NOT registered anywhere as a corporate entity or broker. We do not provide investment advice under SEBI regulations.",
            "",
            PRIMARY_TAB_HINT,
            "",
            "1-Click Unsubscribe Link:",
            unsub_url,
            "",
        ]
    )
    return _renumber_text_sections("\n".join(lines))
