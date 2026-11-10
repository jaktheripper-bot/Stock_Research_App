"""Net Real Post-Tax Return Engine for Indian Multi-Asset Wealth.

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

import logging
import math
from typing import Dict, Any, List, Optional

from core.db.sovereign import get_live_macro_anchors

logger = logging.getLogger("equity_research.core.analysis.net_real_tax_calculator")

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

# Baseline MOSPI All-India CPI Benchmark (dynamically resolved via get_live_macro_anchors())
DEFAULT_CPI_INFLATION = 3.65


def get_default_cpi_inflation() -> float:
    """Resolves live MOSPI CPI inflation from get_live_macro_anchors() for cross-surface parity."""
    try:
        return float(get_live_macro_anchors().get("cpi_inflation_pct", DEFAULT_CPI_INFLATION))
    except Exception as exc:
        logger.warning("CPI anchor fallback in net_real_tax_calculator: %s", exc)
        return DEFAULT_CPI_INFLATION


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
    cpi_inflation_pct: Optional[float] = None
) -> Dict[str, Any]:
    """
    Computes exact post-tax nominal return, tax drag, and real purchasing power return.
    Uses continuous compounding deflator formula: (1 + R_post) / (1 + Inflation) - 1.
    Hardened against division-by-zero (-100% inflation) and NaN inputs.
    """
    live_cpi = get_default_cpi_inflation()
    nom_pct = _safe_float(nominal_annual_return_pct, default=0.0)
    tax_pct = max(0.0, min(100.0, _safe_float(tax_rate_pct, default=0.0)))
    cpi_pct = _safe_float(cpi_inflation_pct, default=live_cpi) if cpi_inflation_pct is not None else live_cpi

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
        "purchasing_power_verdict": "Real Growth" if real_return > 0.015 else ("Capital Preserved" if real_return >= 0 else "Negative Real Return")
    }


def compare_asset_classes_post_tax(
    marginal_tax_slab_pct: float = 30.0,
    holding_period_years: float = 3.0,
    cpi_inflation_pct: Optional[float] = None,
    inflation_pct: Optional[float] = None,
    **kwargs
) -> List[Dict[str, Any]]:
    """
    Produces a multi-asset comparative matrix auditing net post-tax purchasing power across:
    1. Bank FD (7.10% nominal)
    2. Sovereign 10Y G-Sec (live 10Y G-Sec nominal)
    3. Senior Secured Corporate NCD (9.50% nominal)
    4. Sovereign Gold Bond (SGB: 2.5% coupon + 8.5% gold CAGR = 11.0% nominal)
    5. Gold ETF (8.5% gold CAGR - 0.79% TER = 7.71% nominal)
    6. Equity Index ETF / Mutual Fund (12.00% nominal)
    7. Debt Mutual Fund (7.20% nominal)
    8. Public Provident Fund (PPF: 7.10% EEE Tax-Exempt)
    9. Pure Arbitrage Mutual Fund (Sec 112A: 7.15% nominal, 12.5% LTCG)
    """
    live_anchors = get_live_macro_anchors()
    live_cpi = float(live_anchors.get("cpi_inflation_pct", 3.65))
    if inflation_pct is not None:
        cpi_inflation_pct = inflation_pct
    t_slab = max(0.0, min(100.0, _safe_float(marginal_tax_slab_pct, default=30.0))) / 100.0
    cpi_inf = _safe_float(cpi_inflation_pct, default=live_cpi) if cpi_inflation_pct is not None else live_cpi
    inf = cpi_inf / 100.0
    h_years = max(0.1, _safe_float(holding_period_years, default=3.0))
    _ = h_years

    # Resolve live Fixed Deposit, PPF & 10Y G-Sec nominal yields from DB where verified
    fd_nom = 7.10
    ppf_nom = 7.10
    gsec_nom = round(float(live_anchors.get("gsec_10y_pct", 7.12)), 2)
    tbill_91d = round(float(live_anchors.get("tbill_91d_pct", 6.84)), 2)
    try:
        from core.db.savings import get_active_savings_instruments, get_savings_instrument_by_id

        ppf_row = get_savings_instrument_by_id("SAV-PPF")
        if ppf_row and str((ppf_row.get("staleness") or {}).get("status") or "").upper() not in (
            "STALE_TARIFF",
            "UNVERIFIED_PROVENANCE",
        ):
            ppf_nom = round(float(ppf_row["base_rate_pct"]), 2)
        bank_fds = [
            b
            for b in get_active_savings_instruments(category="SCHEDULED_BANK_FD")
            if str((b.get("staleness") or {}).get("status") or "").upper()
            not in ("STALE_TARIFF", "UNVERIFIED_PROVENANCE")
        ]
        if bank_fds:
            fd_nom = round(max(float(b["base_rate_pct"]) for b in bank_fds), 2)
    except Exception as lookup_err:
        logger.debug("Fallback to baseline nominal rates in compare_asset_classes_post_tax: %s", lookup_err)

    # 1. Bank Fixed Deposit
    fd_tax = fd_nom * t_slab
    fd_post = fd_nom - fd_tax
    fd_real = ((1.0 + (fd_post / 100.0)) / (1.0 + (inf))) - 1.0

    # 2. Sovereign 10Y G-Sec
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

    # 8. Public Provident Fund (PPF — EEE Statutory)
    ppf_real = ((1.0 + (ppf_nom / 100.0)) / (1.0 + (inf))) - 1.0

    # 9. Pure Arbitrage Mutual Fund (Sec 112A: 91D T-Bill + 30 bps net spread proxy, 12.5% LTCG)
    arb_nom = round(max(0.0, tbill_91d + 0.30), 2)
    arb_post = arb_nom * 0.875
    arb_real = ((1.0 + (arb_post / 100.0)) / (1.0 + (inf))) - 1.0

    assets = [
        {
            "asset_name": "Sovereign Gold Bond (SGB)",
            "category": "SOVEREIGN_GOLD",
            "nominal_yield_pct": sgb_nom,
            "tax_statute_citation": "Section 47(viic) Income Tax Act (100% Tax-Free capital gains at maturity)",
            "effective_tax_rate_pct": round(((sgb_nom - sgb_post) / sgb_nom) * 100, 1),
            "post_tax_yield_pct": round(sgb_post, 2),
            "net_real_return_pct": round(sgb_real * 100.0, 2),
            "purchasing_power_verdict": "Strongest Real Return (No Tax Drag on Gold)",
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
            "purchasing_power_verdict": "High Compounding (Beats Inflation Over Full Cycles)",
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
            "purchasing_power_verdict": "Positive Real Return" if ncd_real >= 0 else "Negative Real Return After Slab Tax",
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
            "purchasing_power_verdict": "Positive Real Return (Lags SGB due to LTCG & TER)",
            "rank": 4
        },
        {
            "asset_name": "Public Provident Fund (PPF — EEE Statutory)",
            "category": "STATUTORY_SAVINGS",
            "nominal_yield_pct": ppf_nom,
            "tax_statute_citation": "Section 10(11) Income Tax Act (100% EEE Tax-Exempt across New & Old Regimes)",
            "effective_tax_rate_pct": 0.0,
            "post_tax_yield_pct": ppf_nom,
            "net_real_return_pct": round(ppf_real * 100.0, 2),
            "purchasing_power_verdict": "Sovereign Tax-Free Real Yield (Outperforms slab-taxed deposits in 30%+ brackets)",
            "rank": 5
        },
        {
            "asset_name": "Pure Arbitrage Mutual Fund (>12M Holding)",
            "category": "ARBITRAGE_MUTUAL_FUND",
            "nominal_yield_pct": arb_nom,
            "tax_statute_citation": "Section 112A Equity Taxation (12.5% LTCG above ₹1.25L; excludes Arbitrage FoFs)",
            "effective_tax_rate_pct": 12.5,
            "post_tax_yield_pct": round(arb_post, 2),
            "net_real_return_pct": round(arb_real * 100.0, 2),
            "purchasing_power_verdict": "Tax-Efficient Treasury Alternative vs Slab-Taxed Liquid/FD",
            "rank": 6
        },
        {
            "asset_name": "Sovereign 10Y G-Sec / RBI Retail Direct",
            "category": "SOVEREIGN_DEBT",
            "nominal_yield_pct": gsec_nom,
            "tax_statute_citation": "Taxed at marginal slab; zero credit risk (Sovereign guarantee)",
            "effective_tax_rate_pct": marginal_tax_slab_pct,
            "post_tax_yield_pct": round(gsec_post, 2),
            "net_real_return_pct": round(gsec_real * 100.0, 2),
            "purchasing_power_verdict": f"Positive Real Return at {cpi_inf:.2f}% CPI" if gsec_real >= 0 else "Negative Real Return for the 30%+ slab",
            "rank": 7
        },
        {
            "asset_name": "Debt Mutual Fund / Target Maturity",
            "category": "DEBT_MUTUAL_FUND",
            "nominal_yield_pct": debt_mf_nom,
            "tax_statute_citation": "Section 50AA Income Tax Act (Indexation eliminated; 100% slab tax)",
            "effective_tax_rate_pct": marginal_tax_slab_pct,
            "post_tax_yield_pct": round(debt_mf_post, 2),
            "net_real_return_pct": round(debt_mf_real * 100.0, 2),
            "purchasing_power_verdict": "Tax Deferral Until Redemption (Zero indexation post Finance Act 2023)",
            "rank": 8
        },
        {
            "asset_name": "Bank Fixed Deposit (1Y - 3Y)",
            "category": "BANK_DEPOSIT",
            "nominal_yield_pct": fd_nom,
            "tax_statute_citation": "Section 194A TDS + Taxed at marginal slab; DICGC insured up to ₹5L",
            "effective_tax_rate_pct": marginal_tax_slab_pct,
            "post_tax_yield_pct": round(fd_post, 2),
            "net_real_return_pct": round(fd_real * 100.0, 2),
            "purchasing_power_verdict": "Modest Real Return" if fd_real >= 0 else "Negative Real Return (Loses purchasing power to inflation)",
            "rank": 9
        }
    ]
    assets.sort(key=lambda item: float(item.get("net_real_return_pct", 0.0)), reverse=True)
    for idx, item in enumerate(assets, start=1):
        item["rank"] = idx

    return assets


def calculate_post_tax_matrix(
    marginal_tax_slab_pct: float = 30.0,
    inflation_pct: Optional[float] = None,
    holding_period_years: float = 3.0,
    **kwargs
) -> List[Dict[str, Any]]:
    """
    Computes comparative post-tax matrix across asset classes.
    Standardized entry point for the Post-Tax Real Return Engine.
    """
    cpi = kwargs.get("cpi_inflation_pct", inflation_pct)
    return compare_asset_classes_post_tax(
        marginal_tax_slab_pct=marginal_tax_slab_pct,
        holding_period_years=holding_period_years,
        cpi_inflation_pct=cpi,
        **kwargs
    )
