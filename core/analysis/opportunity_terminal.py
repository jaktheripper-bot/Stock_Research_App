"""
Opportunity Terminal Normalization & Multi-Modal Consumption Engine.

Aggregates, normalizes, and scores investment opportunities across all six active asset classes:
1. Corporate Debt & SDIs (core.db.debt)
2. Alternative Real Assets: Commercial REITs, InvITs, SEBI SM REITs (core.db.reits)
3. Sovereign Gold Bonds (SGBs) (core.db.reits)
4. Sovereign Yield Benchmarks & T-Bills (core.db.sovereign)
5. Mutual Funds (core.db.mutual_funds)
6. National ETFs (core.db.sovereign etf_matrix)
7. Fundamental Equities (core.db.reports)

Applies statutory Indian tax waterfalls (Sec 47(viic), Sec 115UA, Sec 50AA, Sec 112A),
calculates real in-hand return net of MOSPI CPI inflation, and ranks opportunities
across the 6-tier capital hierarchy seniority ladder (Sovereign -> Equity).
"""

import logging
from typing import List, Dict, Any, Optional

from core.db.debt import get_active_debt_securities, get_debt_security_by_isin
from core.db.reits import get_all_reits_and_invits, get_all_sgb_tranches, get_reit_by_symbol, get_sgb_by_symbol
from core.db.sovereign import get_sovereign_yield_curve, get_etf_matrix
from core.db.mutual_funds import get_active_mutual_funds, get_mutual_fund_scheme
from core.db.reports import get_archived_reports

logger = logging.getLogger(__name__)

# Statutory 10Y Benchmark Anchor Yield
BENCHMARK_10Y_GSEC_YIELD: float = 7.10
DEFAULT_MOSPI_CPI_INFLATION: float = 4.50
DEFAULT_TAX_SLAB_PCT: float = 30.0

# Capital Hierarchy Seniority Hierarchy (0: Safest Sovereign to 5: Residual Equity)
SENIORITY_RANKS = {
    "SOVEREIGN": 0,
    "AAA_PSU": 1,
    "SENIOR_SECURED": 2,
    "SUBORDINATED": 3,
    "SDI": 3,
    "REAL_ASSET": 4,
    "EQUITY": 5
}


def calculate_tax_waterfall(
    gross_yield: float,
    asset_class: str,
    tax_slab: float = 30.0,
    details: Optional[Dict[str, Any]] = None
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
            "effective_tax_rate_pct": 0.0
        }

    # 1. Sovereign Gold Bonds: Section 47(viic)
    # Capital gains on redemption are 100% tax-free. Only 2.50% annual coupon is taxed at slab.
    if asset_class == "SGB":
        annual_coupon = float(details.get("coupon_rate_pct", 2.50))
        # Coupon yield component vs capital appreciation component
        coupon_yield = min(annual_coupon, gross_yield)
        capital_yield = max(0.0, gross_yield - coupon_yield)
        taxed_coupon = coupon_yield * (1.0 - (tax_slab / 100.0))
        net_yield = capital_yield + taxed_coupon
        eff_tax_rate = ((gross_yield - net_yield) / gross_yield * 100.0) if gross_yield > 0 else 0.0
        return {
            "net_yield_pct": round(net_yield, 2),
            "tax_drag_pct": round(gross_yield - net_yield, 2),
            "tax_statute": "Sec 47(viic) 100% Tax-Free Capital Gains (Coupon at Slab)",
            "effective_tax_rate_pct": round(eff_tax_rate, 1)
        }

    # 2. REITs & InvITs: Section 115UA Pass-Through Waterfall
    # Typical statutory distribution split: 40% Interest (slab), 35% Dividend (exempt), 25% Return of Capital (tax-free capital reduction)
    elif asset_class in ("REIT", "INVIT", "SM_REIT"):
        interest_pct = float(details.get("interest_component_pct", 40.0))
        dividend_pct = float(details.get("dividend_component_pct", 35.0))
        roc_pct = float(details.get("roc_component_pct", 25.0))
        
        # Interest taxed at slab
        interest_yield = gross_yield * (interest_pct / 100.0)
        net_interest = interest_yield * (1.0 - (tax_slab / 100.0))
        # Dividend under SPV old regime is 100% exempt
        net_dividend = gross_yield * (dividend_pct / 100.0)
        # RoC is tax-free up to acquisition cost
        net_roc = gross_yield * (roc_pct / 100.0)
        
        net_yield = net_interest + net_dividend + net_roc
        eff_tax_rate = ((gross_yield - net_yield) / gross_yield * 100.0) if gross_yield > 0 else 0.0
        return {
            "net_yield_pct": round(net_yield, 2),
            "tax_drag_pct": round(gross_yield - net_yield, 2),
            "tax_statute": "Sec 115UA Hybrid Pass-Through (Interest at Slab, Dividend/RoC Tax-Sheltered)",
            "effective_tax_rate_pct": round(eff_tax_rate, 1)
        }

    # 3. Equities & Equity Mutual Funds: Section 112A (12.5% Long-Term Capital Gains)
    elif asset_class in ("EQUITY", "MF_EQUITY", "ETF_EQUITY"):
        ltcg_rate = 12.5
        net_yield = gross_yield * (1.0 - (ltcg_rate / 100.0))
        return {
            "net_yield_pct": round(net_yield, 2),
            "tax_drag_pct": round(gross_yield - net_yield, 2),
            "tax_statute": "Sec 112A Long-Term Capital Gains (Flat 12.5% above ₹1.25L)",
            "effective_tax_rate_pct": ltcg_rate
        }

    # 4. Standard Fixed Income & Debt: Section 50AA / Marginal Slab Tax
    # Corporate bonds, SDIs, T-Bills, and G-Secs taxed at marginal slab rate
    else:
        net_yield = gross_yield * (1.0 - (tax_slab / 100.0))
        return {
            "net_yield_pct": round(net_yield, 2),
            "tax_drag_pct": round(gross_yield - net_yield, 2),
            "tax_statute": "Sec 50AA / General Marginal Income Slab",
            "effective_tax_rate_pct": tax_slab
        }


def assign_tenure_bucket(years: float) -> str:
    """Categorizes maturity or duration into institutional tenure buckets."""
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


def get_normalized_opportunity_universe(
    tax_slab: float = DEFAULT_TAX_SLAB_PCT,
    cpi_inflation: float = DEFAULT_MOSPI_CPI_INFLATION,
    persona_filter: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    Aggregates all active investment offerings across the 6 database repositories
    and standardizes them into the unified OpportunityItem structure.
    """
    items: List[Dict[str, Any]] = []

    # ----------------------------------------------------
    # 1. Corporate Debt & Securitized Debt (SDIs)
    # ----------------------------------------------------
    try:
        debt_securities = get_active_debt_securities(limit=100)
        for d in debt_securities:
            gross_ytm = float(d.get("ytm_pct") or d.get("coupon_rate_pct") or 7.0)
            duration = float(d.get("macaulay_duration_years") or 3.0)
            is_sdi = bool(d.get("is_sdi", False))
            seniority = d.get("seniority_tier", "SENIOR_SECURED").upper()
            
            # Seniority rank mapping
            if "PSU" in d.get("instrument_type", "").upper() or "SOVEREIGN" in seniority:
                s_tier = "AAA_PSU"
            elif is_sdi:
                s_tier = "SDI"
            elif "SUBORDINATED" in seniority or "PERPETUAL" in seniority or "AT1" in seniority:
                s_tier = "SUBORDINATED"
            else:
                s_tier = "SENIOR_SECURED"

            tax_info = calculate_tax_waterfall(gross_ytm, "BOND", tax_slab)
            net_yield = tax_info["net_yield_pct"]
            real_yield = round(net_yield - cpi_inflation, 2)
            spread_bps = round((gross_ytm - BENCHMARK_10Y_GSEC_YIELD) * 100)

            # Persona classification
            personas = []
            if s_tier in ("AAA_PSU", "SENIOR_SECURED") and gross_ytm >= 7.5:
                personas.append("quarterly_cashflow")
            if s_tier == "AAA_PSU":
                personas.append("capital_preservation")

            items.append({
                "id": d.get("isin"),
                "symbol": d.get("ticker", "BOND"),
                "name": d.get("instrument_name", "Corporate Bond"),
                "asset_class": "SDI" if is_sdi else "BOND",
                "category_label": "Securitized Debt (SDI)" if is_sdi else f"{d.get('credit_rating', 'AAA')} Bond",
                "gross_yield_pct": gross_ytm,
                "net_yield_pct": net_yield,
                "real_yield_pct": real_yield,
                "spread_vs_10y_gsec_bps": spread_bps,
                "seniority_tier": s_tier,
                "seniority_rank": SENIORITY_RANKS.get(s_tier, 2),
                "credit_rating": d.get("credit_rating", "AAA"),
                "macaulay_duration_years": duration,
                "tenure_bucket": assign_tenure_bucket(duration),
                "min_ticket_inr": float(d.get("face_value", 10000.0)),
                "liquidity_tier": "EXCHANGE_ACTIVE",
                "tax_statute": tax_info["tax_statute"],
                "effective_tax_rate_pct": tax_info["effective_tax_rate_pct"],
                "recovery_recourse": "1.25x First Pari-Passu Asset Charge" if s_tier == "SENIOR_SECURED" else "Subordinated Unsecured Claim",
                "primary_failure_mode": "Issuer Credit Downgrade / Refinancing Liquidity Shock",
                "detail_url": f"/debt/{d.get('isin')}",
                "persona_tags": personas
            })
    except Exception as e:
        logger.error(f"Error aggregating corporate debt for Opportunity Terminal: {e}")

    # ----------------------------------------------------
    # 2. Alternative Real Assets (SM REITs, REITs, InvITs)
    # ----------------------------------------------------
    try:
        reits = get_all_reits_and_invits()
        for r in reits:
            yield_pct = float(r.get("distribution_yield_pct", 7.5))
            structure = r.get("structure_type", "PUBLIC_REIT")
            is_sm_reit = (structure == "SM_REIT")
            is_invit = (structure == "PUBLIC_INVIT")
            
            asset_type = "SM_REIT" if is_sm_reit else ("INVIT" if is_invit else "REIT")
            label = "SEBI SM REIT Scheme" if is_sm_reit else ("Infrastructure InvIT" if is_invit else "Commercial REIT")
            min_ticket = 1000000.0 if is_sm_reit else 350.0

            tax_info = calculate_tax_waterfall(yield_pct, asset_type, tax_slab)
            net_yield = tax_info["net_yield_pct"]
            real_yield = round(net_yield - cpi_inflation, 2)
            spread_bps = round((yield_pct - BENCHMARK_10Y_GSEC_YIELD) * 100)
            wale = float(r.get("wale_years", 6.5))

            personas = ["quarterly_cashflow"]
            if is_sm_reit:
                personas.append("hni_real_assets")

            items.append({
                "id": r.get("symbol"),
                "symbol": r.get("symbol"),
                "name": r.get("name", "Real Asset Offering"),
                "asset_class": asset_type,
                "category_label": label,
                "gross_yield_pct": yield_pct,
                "net_yield_pct": net_yield,
                "real_yield_pct": real_yield,
                "spread_vs_10y_gsec_bps": spread_bps,
                "seniority_tier": "REAL_ASSET",
                "seniority_rank": SENIORITY_RANKS["REAL_ASSET"],
                "credit_rating": "AAA (Crisil)" if not is_sm_reit else "SEBI Registered Scheme",
                "macaulay_duration_years": wale,
                "tenure_bucket": assign_tenure_bucket(wale),
                "min_ticket_inr": min_ticket,
                "liquidity_tier": "PERIODIC_WINDOW" if is_sm_reit else "EXCHANGE_ACTIVE",
                "tax_statute": tax_info["tax_statute"],
                "effective_tax_rate_pct": tax_info["effective_tax_rate_pct"],
                "recovery_recourse": f"Direct SPV Land/Asset Ownership (Occupancy: {r.get('occupancy_pct', 95)}%)",
                "primary_failure_mode": "Anchor Tenant Default / Regulatory Concession Cap Drift",
                "detail_url": f"/reits#{r.get('symbol')}",
                "persona_tags": personas
            })
    except Exception as e:
        logger.error(f"Error aggregating REITs/InvITs for Opportunity Terminal: {e}")

    # ----------------------------------------------------
    # 3. Sovereign Gold Bonds (SGBs)
    # ----------------------------------------------------
    try:
        sgbs = get_all_sgb_tranches()
        for s in sgbs:
            ytm = float(s.get("ytm_annualized_pct", 8.0))
            years_left = float(s.get("years_to_maturity", 4.0))
            tax_info = calculate_tax_waterfall(ytm, "SGB", tax_slab, {"coupon_rate_pct": float(s.get("coupon_rate_pct", 2.50))})
            net_yield = tax_info["net_yield_pct"]
            real_yield = round(net_yield - cpi_inflation, 2)
            spread_bps = round((ytm - BENCHMARK_10Y_GSEC_YIELD) * 100)

            items.append({
                "id": s.get("symbol"),
                "symbol": s.get("symbol"),
                "name": f"SGB {s.get('series_code', '')} (Mat: {s.get('maturity_date', '2028')})",
                "asset_class": "SGB",
                "category_label": "Sovereign Gold Bond",
                "gross_yield_pct": ytm,
                "net_yield_pct": net_yield,
                "real_yield_pct": real_yield,
                "spread_vs_10y_gsec_bps": spread_bps,
                "seniority_tier": "SOVEREIGN",
                "seniority_rank": SENIORITY_RANKS["SOVEREIGN"],
                "credit_rating": "SOVEREIGN",
                "macaulay_duration_years": years_left,
                "tenure_bucket": assign_tenure_bucket(years_left),
                "min_ticket_inr": float(s.get("current_price", 7450.0)),
                "liquidity_tier": "EXCHANGE_ACTIVE",
                "tax_statute": tax_info["tax_statute"],
                "effective_tax_rate_pct": tax_info["effective_tax_rate_pct"],
                "recovery_recourse": "Reserve Bank of India / Government of India Sovereign Guarantee",
                "primary_failure_mode": "Global Spot Gold Price Crash / Exchange Secondary Illiquidity",
                "detail_url": "/reits#sgbSection",
                "persona_tags": ["capital_preservation"]
            })
    except Exception as e:
        logger.error(f"Error aggregating SGBs for Opportunity Terminal: {e}")

    # ----------------------------------------------------
    # 4. Sovereign Yield Benchmarks & T-Bills
    # ----------------------------------------------------
    try:
        sovereign_benchmarks = get_sovereign_yield_curve()
        for b in sovereign_benchmarks:
            # We select key canonical points: 91D, 364D, 5Y, 10Y, 30Y, and Sovereign Green Bond
            tenor = b.get("tenor_label", "")
            if tenor in ("91D", "364D", "5Y", "10Y", "10Y SGrB", "30Y"):
                yield_val = float(b.get("cut_off_yield", 7.0))
                mat_years = float(b.get("maturity_years", 5.0))
                tax_info = calculate_tax_waterfall(yield_val, "SOVEREIGN", tax_slab)
                net_yield = tax_info["net_yield_pct"]
                real_yield = round(net_yield - cpi_inflation, 2)
                spread_bps = round((yield_val - BENCHMARK_10Y_GSEC_YIELD) * 100)

                items.append({
                    "id": f"GOI_{tenor.replace(' ', '_')}",
                    "symbol": f"GOI-{tenor}",
                    "name": f"Government of India {b.get('instrument_type', 'Benchmark')} ({tenor})",
                    "asset_class": "SOVEREIGN",
                    "category_label": "Sovereign G-Sec / T-Bill",
                    "gross_yield_pct": yield_val,
                    "net_yield_pct": net_yield,
                    "real_yield_pct": real_yield,
                    "spread_vs_10y_gsec_bps": spread_bps,
                    "seniority_tier": "SOVEREIGN",
                    "seniority_rank": SENIORITY_RANKS["SOVEREIGN"],
                    "credit_rating": "SOVEREIGN",
                    "macaulay_duration_years": mat_years,
                    "tenure_bucket": assign_tenure_bucket(mat_years),
                    "min_ticket_inr": 10000.0,
                    "liquidity_tier": "INSTANT_T1",
                    "tax_statute": tax_info["tax_statute"],
                    "effective_tax_rate_pct": tax_info["effective_tax_rate_pct"],
                    "recovery_recourse": "Consolidated Fund of India Statutory Guarantee",
                    "primary_failure_mode": "Domestic Inflation Surge / Interest Rate Policy Hike",
                    "detail_url": "/sovereign",
                    "persona_tags": ["capital_preservation"]
                })
    except Exception as e:
        logger.error(f"Error aggregating sovereign curve for Opportunity Terminal: {e}")

    # ----------------------------------------------------
    # 5. Mutual Funds & ETFs
    # ----------------------------------------------------
    try:
        funds = get_active_mutual_funds(limit=20)
        for f in funds:
            cagr = float(f.get("returns_3y_cagr") or f.get("returns_5y_cagr") or 14.5)
            tax_info = calculate_tax_waterfall(cagr, "MF_EQUITY", tax_slab)
            net_yield = tax_info["net_yield_pct"]
            real_yield = round(net_yield - cpi_inflation, 2)
            spread_bps = round((cagr - BENCHMARK_10Y_GSEC_YIELD) * 100)

            items.append({
                "id": f.get("scheme_code"),
                "symbol": f.get("scheme_code"),
                "name": f.get("scheme_name", "Mutual Fund Scheme"),
                "asset_class": "MF",
                "category_label": f.get("category", "Equity Mutual Fund"),
                "gross_yield_pct": cagr,
                "net_yield_pct": net_yield,
                "real_yield_pct": real_yield,
                "spread_vs_10y_gsec_bps": spread_bps,
                "seniority_tier": "EQUITY",
                "seniority_rank": SENIORITY_RANKS["EQUITY"],
                "credit_rating": "SEBI Monitored Portfolio",
                "macaulay_duration_years": 5.0,
                "tenure_bucket": "3-5Y",
                "min_ticket_inr": 500.0,
                "liquidity_tier": "INSTANT_T1",
                "tax_statute": tax_info["tax_statute"],
                "effective_tax_rate_pct": tax_info["effective_tax_rate_pct"],
                "recovery_recourse": "Diversified Underlying Equity Portfolio (AMFI NAV Liquidation)",
                "primary_failure_mode": "Market-Wide Equity Drawdown / Active Fund Underperformance",
                "detail_url": f"/funds/{f.get('scheme_code')}",
                "persona_tags": ["compounding"]
            })
    except Exception as e:
        logger.error(f"Error aggregating mutual funds for Opportunity Terminal: {e}")

    # ----------------------------------------------------
    # 6. National ETFs
    # ----------------------------------------------------
    try:
        etfs = get_etf_matrix()
        for e in etfs:
            category = e.get("category", "EQUITY_INDEX")
            is_equity = (category == "EQUITY_INDEX")
            is_gold = (category == "COMMODITY_GOLD")
            exp_return = 12.8 if is_equity else (10.5 if is_gold else 7.1)
            tax_info = calculate_tax_waterfall(exp_return, "ETF_EQUITY" if is_equity else "BOND", tax_slab)
            net_yield = tax_info["net_yield_pct"]
            real_yield = round(net_yield - cpi_inflation, 2)
            spread_bps = round((exp_return - BENCHMARK_10Y_GSEC_YIELD) * 100)

            personas = ["compounding"] if is_equity else (["capital_preservation"] if is_gold else [])

            items.append({
                "id": e.get("symbol"),
                "symbol": e.get("symbol"),
                "name": e.get("scheme_name", "National ETF"),
                "asset_class": "ETF",
                "category_label": f"ETF ({category.replace('_', ' ').title()})",
                "gross_yield_pct": exp_return,
                "net_yield_pct": net_yield,
                "real_yield_pct": real_yield,
                "spread_vs_10y_gsec_bps": spread_bps,
                "seniority_tier": "EQUITY" if is_equity else ("SOVEREIGN" if is_gold else "SENIOR_SECURED"),
                "seniority_rank": 5 if is_equity else (0 if is_gold else 2),
                "credit_rating": "Physical / Benchmark Replication",
                "macaulay_duration_years": 3.0,
                "tenure_bucket": "1-3Y",
                "min_ticket_inr": float(e.get("last_price", 250.0)),
                "liquidity_tier": "EXCHANGE_ACTIVE",
                "tax_statute": tax_info["tax_statute"],
                "effective_tax_rate_pct": tax_info["effective_tax_rate_pct"],
                "recovery_recourse": "Index Basket Physical Settlement / Creation Units",
                "primary_failure_mode": "Exchange Price vs NAV Divergence / Tracking Error Drag",
                "detail_url": "/etfs",
                "persona_tags": personas
            })
    except Exception as e:
        logger.error(f"Error aggregating ETFs for Opportunity Terminal: {e}")

    # ----------------------------------------------------
    # 7. Fundamental Equities (Top Tracked Dossiers)
    # ----------------------------------------------------
    try:
        equity_reports = get_archived_reports(include_text=False)
        for eq in equity_reports[:10]:
            ticker = eq.get("ticker", "INFY")
            # Estimated long term equity cost of capital / expected CAGR: ~14.0%
            eq_return = 14.0
            tax_info = calculate_tax_waterfall(eq_return, "EQUITY", tax_slab)
            net_yield = tax_info["net_yield_pct"]
            real_yield = round(net_yield - cpi_inflation, 2)
            spread_bps = round((eq_return - BENCHMARK_10Y_GSEC_YIELD) * 100)

            items.append({
                "id": ticker,
                "symbol": ticker,
                "name": eq.get("short_name") or ticker,
                "asset_class": "EQUITY",
                "category_label": "High-Moat Listed Equity",
                "gross_yield_pct": eq_return,
                "net_yield_pct": net_yield,
                "real_yield_pct": real_yield,
                "spread_vs_10y_gsec_bps": spread_bps,
                "seniority_tier": "EQUITY",
                "seniority_rank": SENIORITY_RANKS["EQUITY"],
                "credit_rating": "Forensic 7-Pillar Scored",
                "macaulay_duration_years": 7.0,
                "tenure_bucket": "5-10Y",
                "min_ticket_inr": float(eq.get("baseline_price") or 1500.0),
                "liquidity_tier": "INSTANT_T1",
                "tax_statute": tax_info["tax_statute"],
                "effective_tax_rate_pct": tax_info["effective_tax_rate_pct"],
                "recovery_recourse": "Residual Common Equity (Zero Recourse)",
                "primary_failure_mode": "Governance Failure / Competitive Moat Erosion / SUE Miss",
                "detail_url": f"/dossier/{ticker}",
                "persona_tags": ["compounding"]
            })
    except Exception as e:
        logger.error(f"Error aggregating equities for Opportunity Terminal: {e}")

    # Filter by persona/scenario if specified
    if persona_filter:
        p_clean = persona_filter.strip().lower()
        if p_clean in ("capital_preservation", "preservation"):
            items = [x for x in items if "capital_preservation" in [p.lower() for p in x.get("persona_tags", [])] and x.get("real_yield_pct", 0) >= 0]
        elif p_clean in ("quarterly_cashflow", "maximum_cashflow", "cashflow"):
            items = [x for x in items if "quarterly_cashflow" in [p.lower() for p in x.get("persona_tags", [])]]
        elif p_clean in ("hni_real_assets", "real_assets"):
            items = [x for x in items if "hni_real_assets" in [p.lower() for p in x.get("persona_tags", [])]]
        elif p_clean in ("compounding", "asymmetric_upside", "upside"):
            items = [x for x in items if "compounding" in [p.lower() for p in x.get("persona_tags", [])]]
        else:
            items = [x for x in items if p_clean in [p.lower() for p in x.get("persona_tags", [])]]

    # Sort descending by Net Real Yield as primary institutional benchmark
    items.sort(key=lambda x: x["net_yield_pct"], reverse=True)
    return items


def get_heatmap_matrix(universe: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    """
    Constructs the 2D Heatmap Matrix spanning:
    Rows: Asset Subtypes (Sovereign, SGB, PSU AAA, Senior Corporate, SM REITs/InvITs, SDIs, Equities)
    Columns: Tenure Buckets (<1Y, 1-3Y, 3-5Y, 5-10Y, 10Y+)
    """
    if universe is None:
        universe = get_normalized_opportunity_universe()

    tenure_buckets = ["<1Y", "1-3Y", "3-5Y", "5-10Y", "10Y+"]
    row_categories = [
        {"key": "SOVEREIGN", "label": "Sovereign Benchmarks (RBI)"},
        {"key": "SGB", "label": "Sovereign Gold Bonds (SGB)"},
        {"key": "AAA_PSU", "label": "PSU & AAA Corporate Bonds"},
        {"key": "SENIOR_SECURED", "label": "Senior Secured Private Bonds"},
        {"key": "REAL_ASSET", "label": "SM REITs & Infrastructure InvITs"},
        {"key": "SDI", "label": "Securitized Debt (SDIs)"},
        {"key": "EQUITY", "label": "High-Moat Equities & ETFs"}
    ]

    matrix_rows = []
    for cat in row_categories:
        c_key = cat["key"]
        row_cells = {}
        for bucket in tenure_buckets:
            # Match items in this category and tenure bucket
            matching = [
                item for item in universe
                if (item.get("seniority_tier") == c_key or item.get("asset_class") == c_key)
                and item.get("tenure_bucket") == bucket
            ]
            if matching:
                # Pick the top offering by gross yield or highest liquidity
                top_item = max(matching, key=lambda x: x["gross_yield_pct"])
                row_cells[bucket] = {
                    "has_data": True,
                    "symbol": top_item["symbol"],
                    "name": top_item["name"],
                    "gross_yield_pct": top_item["gross_yield_pct"],
                    "net_yield_pct": top_item["net_yield_pct"],
                    "spread_bps": top_item["spread_vs_10y_gsec_bps"],
                    "detail_url": top_item["detail_url"],
                    "item_id": top_item["id"],
                    "rating": top_item.get("credit_rating", "")
                }
            else:
                row_cells[bucket] = {"has_data": False}

        matrix_rows.append({
            "category_key": c_key,
            "category_label": cat["label"],
            "cells": row_cells
        })

    return {
        "tenure_buckets": tenure_buckets,
        "rows": matrix_rows,
        "benchmark_10y_yield": BENCHMARK_10Y_GSEC_YIELD
    }


def get_arbitrage_comparison(
    item_ids: List[str],
    tax_slab: float = DEFAULT_TAX_SLAB_PCT,
    cpi_inflation: float = DEFAULT_MOSPI_CPI_INFLATION
) -> Dict[str, Any]:
    """
    Builds the normalized side-by-side comparison scorecard for 2 to 4 pinned items.
    """
    universe = get_normalized_opportunity_universe(tax_slab=tax_slab, cpi_inflation=cpi_inflation)
    id_map = {item["id"]: item for item in universe}
    
    selected_items = []
    for i_id in item_ids:
        if i_id in id_map:
            selected_items.append(id_map[i_id])
        else:
            # Fallback direct lookup
            pass

    return {
        "count": len(selected_items),
        "tax_slab_applied": tax_slab,
        "cpi_inflation_applied": cpi_inflation,
        "benchmark_10y_yield": BENCHMARK_10Y_GSEC_YIELD,
        "items": selected_items
    }
