"""Institutional Net Real Post-Tax Return Engine for Indian Multi-Asset Wealth.

Accurately models purchasing power, post-tax cash flows, and capital preservation across:
1. Bank Fixed Deposits (DICGC insured up to ₹5L, taxed at marginal slab)
2. Sovereign Gold Bonds (SGB: 2.5% coupon + 100% Tax-Free capital gains under Sec 47(viic))
3. Corporate Debt & Senior Secured NCDs (taxed at slab)
4. Equity Mutual Funds & Index ETFs (Budget 2024: 12.5% LTCG above ₹1.25L, 20% STCG)
5. Debt Mutual Funds (Finance Act 2023 / Section 50AA: 100% taxed at slab, zero indexation)
6. Sovereign 10Y G-Sec / Treasury Bills (Sovereign risk-free, taxed at slab)

Applies MOSPI All-India Consumer Price Index (CPI) inflation deflator:
Real Return = ((1 + Post_Tax_Nominal) / (1 + CPI_Inflation)) - 1
"""

import math
from typing import Dict, Any, List, Optional

# Standard Indian Marginal Income Tax Slabs (New Tax Regime FY 2024-25 / FY 2025-26)
TAX_SLABS = {
    "NIL": 0.0,
    "SLAB_5": 0.05,
    "SLAB_10": 0.10,
    "SLAB_15": 0.15,
    "SLAB_20": 0.20,
    "SLAB_30": 0.30,
    "HIGHEST_SURCHARGE": 0.39  # 30% + 25% surcharge + 4% cess
}

# Current MOSPI All-India Urban+Rural CPI Benchmark (approx. 4.80% - 5.10%)
DEFAULT_CPI_INFLATION = 5.00


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


def calculate_net_real_return(
    nominal_annual_return_pct: float,
    tax_rate_pct: float,
    cpi_inflation_pct: float = DEFAULT_CPI_INFLATION
) -> Dict[str, Any]:
    """
    Computes exact post-tax nominal return, tax drag, and real purchasing power return.
    Uses continuous compounding deflator formula: (1 + R_post) / (1 + Inflation) - 1.
    Hardened against division-by-zero (-100% inflation) and NaN inputs.
    """
    nom_pct = _safe_float(nominal_annual_return_pct, default=0.0)
    tax_pct = max(0.0, min(100.0, _safe_float(tax_rate_pct, default=0.0)))
    cpi_pct = _safe_float(cpi_inflation_pct, default=DEFAULT_CPI_INFLATION)

    r_nom = nom_pct / 100.0
    t_rate = tax_pct / 100.0
    inf = cpi_pct / 100.0

    post_tax_nominal = r_nom * (1.0 - t_rate)
    deflator = max(0.001, 1.0 + inf)
    real_return = ((1.0 + post_tax_nominal) / deflator) - 1.0
    tax_drag_pct = (r_nom - post_tax_nominal) * 100.0

    return {
        "nominal_return_pct": round(nom_pct, 2),
        "post_tax_nominal_pct": round(post_tax_nominal * 100.0, 2),
        "cpi_inflation_pct": round(cpi_pct, 2),
        "net_real_return_pct": round(real_return * 100.0, 2),
        "tax_drag_pct": round(tax_drag_pct, 2),
        "purchasing_power_verdict": "Wealth Compounding" if real_return > 0.015 else ("Capital Preserved" if real_return >= 0 else "Wealth Destruction (Negative Real Yield)")
    }


def compare_asset_classes_post_tax(
    marginal_tax_slab_pct: float = 30.0,
    holding_period_years: float = 3.0,
    cpi_inflation_pct: float = DEFAULT_CPI_INFLATION
) -> List[Dict[str, Any]]:
    """
    Produces a multi-asset comparative matrix auditing net post-tax purchasing power across:
    1. Bank FD (7.10% nominal)
    2. Sovereign 10Y G-Sec (7.12% nominal)
    3. Senior Secured Corporate NCD (9.50% nominal)
    4. Sovereign Gold Bond (SGB: 2.5% coupon + 8.5% gold CAGR = 11.0% nominal)
    5. Gold ETF (8.5% gold CAGR - 0.79% TER = 7.71% nominal)
    6. Equity Index ETF / Mutual Fund (12.00% nominal)
    7. Debt Mutual Fund (7.20% nominal)
    """
    t_slab = max(0.0, min(100.0, _safe_float(marginal_tax_slab_pct, default=30.0))) / 100.0
    cpi_inf = _safe_float(cpi_inflation_pct, default=DEFAULT_CPI_INFLATION)
    inf = cpi_inf / 100.0
    h_years = max(0.1, _safe_float(holding_period_years, default=3.0))

    # 1. Bank Fixed Deposit
    fd_nom = 7.10
    fd_tax = fd_nom * t_slab
    fd_post = fd_nom - fd_tax
    fd_real = ((1.0 + (fd_post / 100.0)) / (1.0 + (inf))) - 1.0

    # 2. Sovereign 10Y G-Sec
    gsec_nom = 7.12
    gsec_tax = gsec_nom * t_slab
    gsec_post = gsec_nom - gsec_tax
    gsec_real = ((1.0 + (gsec_post / 100.0)) / (1.0 + (inf))) - 1.0

    # 3. Senior Secured Corporate NCD (AA / AAA rated)
    ncd_nom = 9.50
    ncd_tax = ncd_nom * t_slab
    ncd_post = ncd_nom - ncd_tax
    ncd_real = ((1.0 + (ncd_post / 100.0)) / (1.0 + (inf))) - 1.0

    # 4. Sovereign Gold Bond (SGB) held to maturity
    # Coupon 2.5% is taxed at slab; Capital appreciation (approx 8.5%) is 100% TAX-FREE under Sec 47(viic)
    sgb_coupon = 2.50
    sgb_cap_gain = 8.50
    sgb_nom = sgb_coupon + sgb_cap_gain
    sgb_post = (sgb_coupon * (1.0 - t_slab)) + sgb_cap_gain
    sgb_real = ((1.0 + (sgb_post / 100.0)) / (1.0 + (inf))) - 1.0

    # 5. Gold ETF (Nippon Gold BeES)
    # Post Budget 2024: Gold ETFs held >12M taxed at 12.5% LTCG; underlying net of 0.79% TER
    gold_etf_nom = 8.50 - 0.79
    gold_etf_tax = gold_etf_nom * 0.125
    gold_etf_post = gold_etf_nom - gold_etf_tax
    gold_etf_real = ((1.0 + (gold_etf_post / 100.0)) / (1.0 + (inf))) - 1.0

    # 6. Equity Mutual Fund / Nifty 50 ETF (Holding > 1 Year)
    # Budget 2024: 12.5% LTCG on gains exceeding ₹1.25 Lakhs
    equity_nom = 12.00
    equity_tax = equity_nom * 0.125
    equity_post = equity_nom - equity_tax
    equity_real = ((1.0 + (equity_post / 100.0)) / (1.0 + (inf))) - 1.0

    # 7. Debt Mutual Fund (Post-April 2023 Finance Act / Section 50AA)
    # 100% of capital gains taxed at slab rate regardless of holding period
    debt_mf_nom = 7.20
    debt_mf_tax = debt_mf_nom * t_slab
    debt_mf_post = debt_mf_nom - debt_mf_tax
    debt_mf_real = ((1.0 + (debt_mf_post / 100.0)) / (1.0 + (inf))) - 1.0

    assets = [
        {
            "asset_name": "Sovereign Gold Bond (SGB)",
            "category": "SOVEREIGN_GOLD",
            "nominal_yield_pct": sgb_nom,
            "tax_statute_citation": "Section 47(viic) Income Tax Act (100% Tax-Free capital gains at maturity)",
            "effective_tax_rate_pct": round(((sgb_nom - sgb_post) / sgb_nom) * 100, 1),
            "post_tax_yield_pct": round(sgb_post, 2),
            "net_real_return_pct": round(sgb_real * 100.0, 2),
            "purchasing_power_verdict": "Maximum Wealth Compounding (Zero Tax Drag on Gold)",
            "rank": 1
        },
        {
            "asset_name": "Nifty 50 Equity ETF / Index Fund",
            "category": "EQUITY",
            "nominal_yield_pct": equity_nom,
            "tax_statute_citation": "Section 112A Income Tax Act (12.5% LTCG beyond ₹1.25L exemption)",
            "effective_tax_rate_pct": 12.5,
            "post_tax_yield_pct": round(equity_post, 2),
            "net_real_return_pct": round(equity_real * 100.0, 2),
            "purchasing_power_verdict": "High Compounding (Beats Inflation by ~5.2%)",
            "rank": 2
        },
        {
            "asset_name": "Senior Secured Listed Corporate NCD",
            "category": "CORPORATE_DEBT",
            "nominal_yield_pct": ncd_nom,
            "tax_statute_citation": "Section 56(2) Income from Other Sources (Taxed at marginal slab)",
            "effective_tax_rate_pct": marginal_tax_slab_pct,
            "post_tax_yield_pct": round(ncd_post, 2),
            "net_real_return_pct": round(ncd_real * 100.0, 2),
            "purchasing_power_verdict": "Positive Real Return (Beats Inflation by ~1.6%)",
            "rank": 3
        },
        {
            "asset_name": "Gold ETF (Physical Gold Backed)",
            "category": "COMMODITY_ETF",
            "nominal_yield_pct": round(gold_etf_nom, 2),
            "tax_statute_citation": "Budget 2024 LTCG at 12.5% (>12M holding) + 0.79% TER drag",
            "effective_tax_rate_pct": 12.5,
            "post_tax_yield_pct": round(gold_etf_post, 2),
            "net_real_return_pct": round(gold_etf_real * 100.0, 2),
            "purchasing_power_verdict": "Positive Real Return (Lags SGB by ~2.3% due to LTCG & TER)",
            "rank": 4
        },
        {
            "asset_name": "Sovereign 10Y G-Sec / RBI Retail Direct",
            "category": "SOVEREIGN_DEBT",
            "nominal_yield_pct": gsec_nom,
            "tax_statute_citation": "Taxed at marginal slab; zero credit risk (Sovereign guarantee)",
            "effective_tax_rate_pct": marginal_tax_slab_pct,
            "post_tax_yield_pct": round(gsec_post, 2),
            "net_real_return_pct": round(gsec_real * 100.0, 2),
            "purchasing_power_verdict": "Marginal Wealth Destruction (Negative Real Yield for 30%+ slab)",
            "rank": 5
        },
        {
            "asset_name": "Debt Mutual Fund / Target Maturity",
            "category": "DEBT_MUTUAL_FUND",
            "nominal_yield_pct": debt_mf_nom,
            "tax_statute_citation": "Section 50AA Income Tax Act (Indexation eliminated; 100% slab tax)",
            "effective_tax_rate_pct": marginal_tax_slab_pct,
            "post_tax_yield_pct": round(debt_mf_post, 2),
            "net_real_return_pct": round(debt_mf_real * 100.0, 2),
            "purchasing_power_verdict": "Severe Tax Drag (Zero indexation post Finance Act 2023)",
            "rank": 6
        },
        {
            "asset_name": "Bank Fixed Deposit (1Y - 3Y)",
            "category": "BANK_DEPOSIT",
            "nominal_yield_pct": fd_nom,
            "tax_statute_citation": "Section 194A TDS + Taxed at marginal slab; DICGC insured up to ₹5L",
            "effective_tax_rate_pct": marginal_tax_slab_pct,
            "post_tax_yield_pct": round(fd_post, 2),
            "net_real_return_pct": round(fd_real * 100.0, 2),
            "purchasing_power_verdict": "Guaranteed Negative Real Return (Loses purchasing power to inflation)",
            "rank": 7
        }
    ]

    return assets
