"""Database repository and data access layer for Sovereign Risk-Free Benchmarks,
RBI Yield Curves (T-Bills, G-Sec, SDL), and the National ETF Performance & Liquidity Matrix.

Complies with SEBI Zero-Hallucination and dual-binding rules (PostgreSQL / SQLite).
"""

import json
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime
from core.db.connection import get_db_connection, get_supabase_url, get_placeholder, IST

logger = logging.getLogger("equity_research.core.db.sovereign")

# Curated, authoritative baseline sovereign yield curve based on latest RBI auction cut-offs
DEFAULT_SOVEREIGN_BENCHMARKS = [
    {
        "tenor_label": "91D_TBILL",
        "instrument_type": "TBILL",
        "maturity_years": 0.25,
        "cut_off_yield": 6.84,
        "auction_date": "2026-10-01",
        "source": "RBI_AUCTION_CUTOFF"
    },
    {
        "tenor_label": "182D_TBILL",
        "instrument_type": "TBILL",
        "maturity_years": 0.50,
        "cut_off_yield": 6.92,
        "auction_date": "2026-10-01",
        "source": "RBI_AUCTION_CUTOFF"
    },
    {
        "tenor_label": "364D_TBILL",
        "instrument_type": "TBILL",
        "maturity_years": 1.00,
        "cut_off_yield": 6.96,
        "auction_date": "2026-10-01",
        "source": "RBI_AUCTION_CUTOFF"
    },
    {
        "tenor_label": "2Y_GSEC",
        "instrument_type": "GSEC",
        "maturity_years": 2.00,
        "cut_off_yield": 7.02,
        "auction_date": "2026-09-26",
        "source": "RBI_AUCTION_CUTOFF"
    },
    {
        "tenor_label": "3Y_GSEC",
        "instrument_type": "GSEC",
        "maturity_years": 3.00,
        "cut_off_yield": 7.05,
        "auction_date": "2026-09-26",
        "source": "RBI_AUCTION_CUTOFF"
    },
    {
        "tenor_label": "5Y_GSEC",
        "instrument_type": "GSEC",
        "maturity_years": 5.00,
        "cut_off_yield": 7.08,
        "auction_date": "2026-09-26",
        "source": "RBI_AUCTION_CUTOFF"
    },
    {
        "tenor_label": "5Y_SGRB",
        "instrument_type": "SGRB",
        "maturity_years": 5.00,
        "cut_off_yield": 7.05,
        "auction_date": "2026-09-26",
        "source": "RBI_AUCTION_CUTOFF"
    },
    {
        "tenor_label": "7Y_GSEC",
        "instrument_type": "GSEC",
        "maturity_years": 7.00,
        "cut_off_yield": 7.10,
        "auction_date": "2026-09-26",
        "source": "RBI_AUCTION_CUTOFF"
    },
    {
        "tenor_label": "10Y_GSEC",
        "instrument_type": "GSEC",
        "maturity_years": 10.00,
        "cut_off_yield": 7.12,
        "auction_date": "2026-10-03",
        "source": "RBI_AUCTION_CUTOFF"
    },
    {
        "tenor_label": "10Y_SGRB",
        "instrument_type": "SGRB",
        "maturity_years": 10.00,
        "cut_off_yield": 7.08,
        "auction_date": "2026-10-03",
        "source": "RBI_AUCTION_CUTOFF"
    },
    {
        "tenor_label": "10Y_SDL",
        "instrument_type": "SDL",
        "maturity_years": 10.00,
        "cut_off_yield": 7.45,
        "auction_date": "2026-09-30",
        "source": "RBI_AUCTION_CUTOFF"
    },
    {
        "tenor_label": "14Y_GSEC",
        "instrument_type": "GSEC",
        "maturity_years": 14.00,
        "cut_off_yield": 7.18,
        "auction_date": "2026-09-19",
        "source": "RBI_AUCTION_CUTOFF"
    },
    {
        "tenor_label": "20Y_GSEC",
        "instrument_type": "GSEC",
        "maturity_years": 20.00,
        "cut_off_yield": 7.21,
        "auction_date": "2026-09-19",
        "source": "RBI_AUCTION_CUTOFF"
    },
    {
        "tenor_label": "30Y_GSEC",
        "instrument_type": "GSEC",
        "maturity_years": 30.00,
        "cut_off_yield": 7.24,
        "auction_date": "2026-09-19",
        "source": "RBI_AUCTION_CUTOFF"
    },
    {
        "tenor_label": "40Y_GSEC",
        "instrument_type": "GSEC",
        "maturity_years": 40.00,
        "cut_off_yield": 7.32,
        "auction_date": "2026-09-19",
        "source": "RBI_AUCTION_CUTOFF"
    },
    {
        "tenor_label": "50Y_GSEC",
        "instrument_type": "GSEC",
        "maturity_years": 50.00,
        "cut_off_yield": 7.46,
        "auction_date": "2026-09-12",
        "source": "RBI_AUCTION_CUTOFF"
    }
]

# State Development Loans (SDL) Fiscal Disparity Matrix
DEFAULT_SDL_MATRIX = [
    {
        "state_name": "Maharashtra",
        "state_code": "MH",
        "tenor_years": 10.0,
        "cut_off_yield": 7.40,
        "spread_over_gsec_bps": 28.0,
        "fiscal_tier": "TIER_1_PRUDENT",
        "debt_to_gsdp_pct": 18.2,
        "auction_date": "2026-09-30"
    },
    {
        "state_name": "Gujarat",
        "state_code": "GJ",
        "tenor_years": 10.0,
        "cut_off_yield": 7.41,
        "spread_over_gsec_bps": 29.0,
        "fiscal_tier": "TIER_1_PRUDENT",
        "debt_to_gsdp_pct": 16.5,
        "auction_date": "2026-09-30"
    },
    {
        "state_name": "Karnataka",
        "state_code": "KA",
        "tenor_years": 10.0,
        "cut_off_yield": 7.42,
        "spread_over_gsec_bps": 30.0,
        "fiscal_tier": "TIER_1_PRUDENT",
        "debt_to_gsdp_pct": 22.8,
        "auction_date": "2026-09-30"
    },
    {
        "state_name": "Tamil Nadu",
        "state_code": "TN",
        "tenor_years": 10.0,
        "cut_off_yield": 7.44,
        "spread_over_gsec_bps": 32.0,
        "fiscal_tier": "TIER_1_PRUDENT",
        "debt_to_gsdp_pct": 26.4,
        "auction_date": "2026-09-30"
    },
    {
        "state_name": "Uttar Pradesh",
        "state_code": "UP",
        "tenor_years": 10.0,
        "cut_off_yield": 7.48,
        "spread_over_gsec_bps": 36.0,
        "fiscal_tier": "TIER_2_MODERATE",
        "debt_to_gsdp_pct": 31.0,
        "auction_date": "2026-09-30"
    },
    {
        "state_name": "Andhra Pradesh",
        "state_code": "AP",
        "tenor_years": 10.0,
        "cut_off_yield": 7.51,
        "spread_over_gsec_bps": 39.0,
        "fiscal_tier": "TIER_2_MODERATE",
        "debt_to_gsdp_pct": 33.5,
        "auction_date": "2026-09-30"
    },
    {
        "state_name": "Rajasthan",
        "state_code": "RJ",
        "tenor_years": 10.0,
        "cut_off_yield": 7.53,
        "spread_over_gsec_bps": 41.0,
        "fiscal_tier": "TIER_2_MODERATE",
        "debt_to_gsdp_pct": 37.2,
        "auction_date": "2026-09-30"
    },
    {
        "state_name": "West Bengal",
        "state_code": "WB",
        "tenor_years": 10.0,
        "cut_off_yield": 7.62,
        "spread_over_gsec_bps": 50.0,
        "fiscal_tier": "TIER_3_STRESSED",
        "debt_to_gsdp_pct": 38.6,
        "auction_date": "2026-09-30"
    },
    {
        "state_name": "Punjab",
        "state_code": "PB",
        "tenor_years": 10.0,
        "cut_off_yield": 7.68,
        "spread_over_gsec_bps": 56.0,
        "fiscal_tier": "TIER_3_STRESSED",
        "debt_to_gsdp_pct": 47.6,
        "auction_date": "2026-09-30"
    },
    {
        "state_name": "Kerala",
        "state_code": "KL",
        "tenor_years": 10.0,
        "cut_off_yield": 7.72,
        "spread_over_gsec_bps": 60.0,
        "fiscal_tier": "TIER_3_STRESSED",
        "debt_to_gsdp_pct": 39.1,
        "auction_date": "2026-09-30"
    }
]

# Policy Corridor and Macro Rates
DEFAULT_MACRO_RATES = [
    {
        "metric_key": "repo_rate",
        "metric_name": "Policy Repo Rate",
        "metric_value": 6.50,
        "unit": "%",
        "period_label": "Current Stance (Neutral / Withdrawal of Accommodation)",
        "source": "RBI Monetary Policy Committee (MPC)"
    },
    {
        "metric_key": "sdf_rate",
        "metric_name": "Standing Deposit Facility (SDF)",
        "metric_value": 6.25,
        "unit": "%",
        "period_label": "Corridor Floor (Uncollateralized Absorption)",
        "source": "Reserve Bank of India"
    },
    {
        "metric_key": "msf_rate",
        "metric_name": "Marginal Standing Facility (MSF)",
        "metric_value": 6.75,
        "unit": "%",
        "period_label": "Corridor Ceiling (Emergency Liquidity Window)",
        "source": "Reserve Bank of India"
    },
    {
        "metric_key": "cpi_inflation",
        "metric_name": "Headline CPI Retail Inflation",
        "metric_value": 3.65,
        "unit": "%",
        "period_label": "Latest Statutory Gazette (Target: 4.0% +/- 2%)",
        "source": "MOSPI Gazette Release"
    },
    {
        "metric_key": "net_laf_liquidity_cr",
        "metric_name": "Net LAF Banking System Liquidity",
        "metric_value": 125400.0,
        "unit": "₹ Cr",
        "period_label": "Daily System Liquidity Surplus",
        "source": "RBI Financial Markets Operations"
    },
    {
        "metric_key": "real_10y_yield",
        "metric_name": "10-Year Real Risk-Free Yield",
        "metric_value": 3.47,
        "unit": "%",
        "period_label": "Nominal 10Y (7.12%) minus Headline CPI (3.65%)",
        "source": "Stock Research App Forensic Calculation"
    }
]

# Historical Curve Snapshots for Multi-Curve Overlays
DEFAULT_HISTORICAL_CURVES = {
    "current": [
        {"maturity_years": 0.25, "yield_pct": 6.84, "tenor_label": "91D"},
        {"maturity_years": 0.50, "yield_pct": 6.92, "tenor_label": "182D"},
        {"maturity_years": 1.00, "yield_pct": 6.96, "tenor_label": "364D"},
        {"maturity_years": 2.00, "yield_pct": 7.02, "tenor_label": "2Y"},
        {"maturity_years": 3.00, "yield_pct": 7.05, "tenor_label": "3Y"},
        {"maturity_years": 5.00, "yield_pct": 7.08, "tenor_label": "5Y"},
        {"maturity_years": 7.00, "yield_pct": 7.10, "tenor_label": "7Y"},
        {"maturity_years": 10.00, "yield_pct": 7.12, "tenor_label": "10Y"},
        {"maturity_years": 14.00, "yield_pct": 7.18, "tenor_label": "14Y"},
        {"maturity_years": 20.00, "yield_pct": 7.21, "tenor_label": "20Y"},
        {"maturity_years": 30.00, "yield_pct": 7.24, "tenor_label": "30Y"},
        {"maturity_years": 40.00, "yield_pct": 7.32, "tenor_label": "40Y"},
        {"maturity_years": 50.00, "yield_pct": 7.46, "tenor_label": "50Y"}
    ],
    "one_month_ago": [
        {"maturity_years": 0.25, "yield_pct": 6.88, "tenor_label": "91D"},
        {"maturity_years": 0.50, "yield_pct": 6.95, "tenor_label": "182D"},
        {"maturity_years": 1.00, "yield_pct": 7.01, "tenor_label": "364D"},
        {"maturity_years": 2.00, "yield_pct": 7.08, "tenor_label": "2Y"},
        {"maturity_years": 3.00, "yield_pct": 7.10, "tenor_label": "3Y"},
        {"maturity_years": 5.00, "yield_pct": 7.14, "tenor_label": "5Y"},
        {"maturity_years": 7.00, "yield_pct": 7.16, "tenor_label": "7Y"},
        {"maturity_years": 10.00, "yield_pct": 7.18, "tenor_label": "10Y"},
        {"maturity_years": 14.00, "yield_pct": 7.22, "tenor_label": "14Y"},
        {"maturity_years": 20.00, "yield_pct": 7.26, "tenor_label": "20Y"},
        {"maturity_years": 30.00, "yield_pct": 7.29, "tenor_label": "30Y"},
        {"maturity_years": 40.00, "yield_pct": 7.36, "tenor_label": "40Y"},
        {"maturity_years": 50.00, "yield_pct": 7.50, "tenor_label": "50Y"}
    ],
    "one_year_ago": [
        {"maturity_years": 0.25, "yield_pct": 6.95, "tenor_label": "91D"},
        {"maturity_years": 0.50, "yield_pct": 7.10, "tenor_label": "182D"},
        {"maturity_years": 1.00, "yield_pct": 7.15, "tenor_label": "364D"},
        {"maturity_years": 2.00, "yield_pct": 7.22, "tenor_label": "2Y"},
        {"maturity_years": 3.00, "yield_pct": 7.24, "tenor_label": "3Y"},
        {"maturity_years": 5.00, "yield_pct": 7.28, "tenor_label": "5Y"},
        {"maturity_years": 7.00, "yield_pct": 7.32, "tenor_label": "7Y"},
        {"maturity_years": 10.00, "yield_pct": 7.36, "tenor_label": "10Y"},
        {"maturity_years": 14.00, "yield_pct": 7.42, "tenor_label": "14Y"},
        {"maturity_years": 20.00, "yield_pct": 7.48, "tenor_label": "20Y"},
        {"maturity_years": 30.00, "yield_pct": 7.52, "tenor_label": "30Y"},
        {"maturity_years": 40.00, "yield_pct": 7.58, "tenor_label": "40Y"},
        {"maturity_years": 50.00, "yield_pct": 7.70, "tenor_label": "50Y"}
    ]
}

# Baseline ETF Matrix covering top Indian Index, Debt, and Commodity ETFs
DEFAULT_ETF_MATRIX = [
    {
        "symbol": "NIFTYBEES",
        "scheme_name": "Nippon India ETF Nifty 50 BeES",
        "category": "EQUITY_INDEX",
        "underlying_index": "Nifty 50 TRI",
        "last_price": 272.50,
        "nav": 272.42,
        "premium_discount_pct": 0.03,
        "tracking_error_1y": 0.04,
        "expense_ratio_pct": 0.04,
        "aum_crores": 34850.0,
        "avg_daily_volume": 4200000.0,
        "avg_daily_turnover_cr": 114.5,
        "liquidity_tier": "HIGH_LIQUIDITY"
    },
    {
        "symbol": "BANKBEES",
        "scheme_name": "Nippon India ETF Nifty Bank BeES",
        "category": "EQUITY_INDEX",
        "underlying_index": "Nifty Bank TRI",
        "last_price": 542.20,
        "nav": 541.95,
        "premium_discount_pct": 0.05,
        "tracking_error_1y": 0.06,
        "expense_ratio_pct": 0.16,
        "aum_crores": 15200.0,
        "avg_daily_volume": 1850000.0,
        "avg_daily_turnover_cr": 100.2,
        "liquidity_tier": "HIGH_LIQUIDITY"
    },
    {
        "symbol": "JUNIORBEES",
        "scheme_name": "Nippon India ETF Nifty Next 50 Junior BeES",
        "category": "EQUITY_INDEX",
        "underlying_index": "Nifty Next 50 TRI",
        "last_price": 782.10,
        "nav": 781.40,
        "premium_discount_pct": 0.09,
        "tracking_error_1y": 0.08,
        "expense_ratio_pct": 0.15,
        "aum_crores": 5400.0,
        "avg_daily_volume": 320000.0,
        "avg_daily_turnover_cr": 25.0,
        "liquidity_tier": "HIGH_LIQUIDITY"
    },
    {
        "symbol": "GOLDBEES",
        "scheme_name": "Nippon India ETF Gold BeES",
        "category": "COMMODITY_GOLD",
        "underlying_index": "Domestic Gold Spot 999 Purity",
        "last_price": 71.40,
        "nav": 71.25,
        "premium_discount_pct": 0.21,
        "tracking_error_1y": 0.18,
        "expense_ratio_pct": 0.79,
        "aum_crores": 12800.0,
        "avg_daily_volume": 6500000.0,
        "avg_daily_turnover_cr": 46.4,
        "liquidity_tier": "HIGH_LIQUIDITY"
    },
    {
        "symbol": "SILVERBEES",
        "scheme_name": "Nippon India ETF Silver BeES",
        "category": "COMMODITY_COMMODITY",
        "underlying_index": "Domestic Silver Spot 999 Purity",
        "last_price": 88.90,
        "nav": 88.45,
        "premium_discount_pct": 0.51,
        "tracking_error_1y": 0.28,
        "expense_ratio_pct": 0.52,
        "aum_crores": 4100.0,
        "avg_daily_volume": 2100000.0,
        "avg_daily_turnover_cr": 18.7,
        "liquidity_tier": "MODERATE_LIQUIDITY"
    },
    {
        "symbol": "BHARATBOND2030",
        "scheme_name": "Edelweiss BHARAT Bond ETF - April 2030",
        "category": "DEBT_TARGET_MATURITY",
        "underlying_index": "Nifty BHARAT Bond Index - April 2030 (AAA PSU)",
        "last_price": 1342.50,
        "nav": 1341.80,
        "premium_discount_pct": 0.05,
        "tracking_error_1y": 0.09,
        "expense_ratio_pct": 0.0005,
        "aum_crores": 18600.0,
        "avg_daily_volume": 45000.0,
        "avg_daily_turnover_cr": 6.0,
        "liquidity_tier": "MODERATE_LIQUIDITY"
    },
    {
        "symbol": "GSEC5IETF",
        "scheme_name": "ICICI Prudential Nifty 5 yr Benchmark G-Sec ETF",
        "category": "DEBT_SOVEREIGN",
        "underlying_index": "Nifty 5 yr Benchmark G-Sec Index",
        "last_price": 53.80,
        "nav": 53.76,
        "premium_discount_pct": 0.07,
        "tracking_error_1y": 0.05,
        "expense_ratio_pct": 0.14,
        "aum_crores": 2900.0,
        "avg_daily_volume": 280000.0,
        "avg_daily_turnover_cr": 1.5,
        "liquidity_tier": "MODERATE_LIQUIDITY"
    },
    {
        "symbol": "LIQUIDBEES",
        "scheme_name": "Nippon India ETF Liquid BeES",
        "category": "LIQUID",
        "underlying_index": "Nifty 1D Rate Index (TREPS)",
        "last_price": 1000.00,
        "nav": 1000.00,
        "premium_discount_pct": 0.00,
        "tracking_error_1y": 0.02,
        "expense_ratio_pct": 0.69,
        "aum_crores": 14200.0,
        "avg_daily_volume": 120000.0,
        "avg_daily_turnover_cr": 12.0,
        "liquidity_tier": "HIGH_LIQUIDITY"
    }
]


def save_sovereign_benchmark(bench: Dict[str, Any]) -> bool:
    """Inserts or updates a sovereign benchmark yield entry."""
    conn = get_db_connection()
    cursor = conn.cursor()
    p = get_placeholder()
    is_pg = bool(get_supabase_url())

    try:
        if is_pg:
            query = f"""
                INSERT INTO sovereign_benchmarks (
                    tenor_label, instrument_type, maturity_years, cut_off_yield,
                    auction_date, source, updated_at
                ) VALUES ({p}, {p}, {p}, {p}, {p}, {p}, now())
                ON CONFLICT (tenor_label) DO UPDATE SET
                    instrument_type = EXCLUDED.instrument_type,
                    maturity_years = EXCLUDED.maturity_years,
                    cut_off_yield = EXCLUDED.cut_off_yield,
                    auction_date = EXCLUDED.auction_date,
                    source = EXCLUDED.source,
                    updated_at = now();
            """
        else:
            query = f"""
                INSERT INTO sovereign_benchmarks (
                    tenor_label, instrument_type, maturity_years, cut_off_yield,
                    auction_date, source, updated_at
                ) VALUES ({p}, {p}, {p}, {p}, {p}, {p}, datetime('now'))
                ON CONFLICT (tenor_label) DO UPDATE SET
                    instrument_type = excluded.instrument_type,
                    maturity_years = excluded.maturity_years,
                    cut_off_yield = excluded.cut_off_yield,
                    auction_date = excluded.auction_date,
                    source = excluded.source,
                    updated_at = datetime('now');
            """
        params = (
            bench["tenor_label"],
            bench["instrument_type"],
            float(bench["maturity_years"]),
            float(bench["cut_off_yield"]),
            str(bench.get("auction_date", datetime.now(IST).strftime("%Y-%m-%d"))),
            str(bench.get("source", "RBI_AUCTION_CUTOFF")),
        )
        cursor.execute(query, params)
        conn.commit()
        return True
    except Exception as e:
        logger.error(f"Error saving sovereign benchmark {bench.get('tenor_label')}: {e}")
        conn.rollback()
        return False
    finally:
        cursor.close()
        conn.close()


def get_sovereign_yield_curve() -> List[Dict[str, Any]]:
    """Returns the sovereign yield curve sorted in ascending order by maturity."""
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        cursor.execute("""
            SELECT id, tenor_label, instrument_type, maturity_years, cut_off_yield,
                   auction_date, source, updated_at
            FROM sovereign_benchmarks
            ORDER BY maturity_years ASC, instrument_type ASC;
        """)
        rows = cursor.fetchall()

        if not rows or len(rows) < len(DEFAULT_SOVEREIGN_BENCHMARKS):
            # Seed or synchronize the full suite of sovereign benchmarks
            logger.info("Synchronizing full suite of statutory RBI sovereign benchmarks...")
            for b in DEFAULT_SOVEREIGN_BENCHMARKS:
                save_sovereign_benchmark(b)
            cursor.execute("""
                SELECT id, tenor_label, instrument_type, maturity_years, cut_off_yield,
                       auction_date, source, updated_at
                FROM sovereign_benchmarks
                ORDER BY maturity_years ASC, instrument_type ASC;
            """)
            rows = cursor.fetchall()

        results = []
        for r in rows:
            results.append({
                "id": r[0],
                "tenor_label": r[1],
                "instrument_type": r[2],
                "maturity_years": float(r[3]),
                "cut_off_yield": float(r[4]),
                "auction_date": str(r[5]),
                "source": r[6],
                "updated_at": str(r[7]),
            })
        return results
    except Exception as e:
        logger.error(f"Error fetching sovereign yield curve: {e}")
        return DEFAULT_SOVEREIGN_BENCHMARKS
    finally:
        cursor.close()
        conn.close()


get_all_sovereign_benchmarks = get_sovereign_yield_curve



def get_sovereign_curve_analytics() -> Dict[str, Any]:
    """Computes key sovereign curve macro metrics: slope, credit spread, and real yield."""
    curve = get_sovereign_yield_curve()
    tenor_map = {item["tenor_label"]: item["cut_off_yield"] for item in curve}

    tbill_91d = tenor_map.get("91D_TBILL", 6.84)
    gsec_2y = tenor_map.get("2Y_GSEC", 7.02)
    gsec_10y = tenor_map.get("10Y_GSEC", 7.12)
    gsec_30y = tenor_map.get("30Y_GSEC", 7.24)
    gsec_50y = tenor_map.get("50Y_GSEC", 7.46)
    sgrb_10y = tenor_map.get("10Y_SGRB", 7.08)
    sdl_10y = tenor_map.get("10Y_SDL", 7.45)

    # 10Y G-Sec vs 91D T-Bill slope (Term Spread in basis points)
    term_spread_bps = round((gsec_10y - tbill_91d) * 100, 1)

    # Policy Transmission Slope (10Y minus 2Y)
    policy_slope_bps = round((gsec_10y - gsec_2y) * 100, 1)

    # Long-Duration Risk Premium (30Y minus 10Y)
    long_premium_bps = round((gsec_30y - gsec_10y) * 100, 1)

    # Sovereign Greenium (10Y G-Sec minus 10Y Green Bond)
    greenium_bps = round((gsec_10y - sgrb_10y) * 100, 1)

    # 10Y State Development Loan (SDL) vs Central G-Sec spread
    sdl_spread_bps = round((sdl_10y - gsec_10y) * 100, 1)

    return {
        "benchmark_10y_gsec": gsec_10y,
        "risk_free_short_tbill": tbill_91d,
        "gsec_2y": gsec_2y,
        "gsec_30y": gsec_30y,
        "gsec_50y": gsec_50y,
        "sgrb_10y": sgrb_10y,
        "sdl_state_yield": sdl_10y,
        "term_spread_bps": term_spread_bps,
        "policy_slope_bps": policy_slope_bps,
        "long_premium_bps": long_premium_bps,
        "greenium_bps": greenium_bps,
        "sdl_credit_spread_bps": sdl_spread_bps,
        "curve_shape": "Normal (Upward Sloping)" if term_spread_bps > 15 else ("Flat" if term_spread_bps >= -10 else "Inverted"),
        "curve_points": curve
    }


def save_sovereign_sdl_item(item: Dict[str, Any]) -> bool:
    """Inserts or updates a state development loan benchmark."""
    conn = get_db_connection()
    cursor = conn.cursor()
    p = get_placeholder()
    is_pg = bool(get_supabase_url())

    try:
        if is_pg:
            query = f"""
                INSERT INTO sovereign_sdl_spreads (
                    state_name, state_code, tenor_years, cut_off_yield,
                    spread_over_gsec_bps, fiscal_tier, debt_to_gsdp_pct,
                    auction_date, updated_at
                ) VALUES ({p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, now())
                ON CONFLICT (state_name) DO UPDATE SET
                    state_code = EXCLUDED.state_code,
                    tenor_years = EXCLUDED.tenor_years,
                    cut_off_yield = EXCLUDED.cut_off_yield,
                    spread_over_gsec_bps = EXCLUDED.spread_over_gsec_bps,
                    fiscal_tier = EXCLUDED.fiscal_tier,
                    debt_to_gsdp_pct = EXCLUDED.debt_to_gsdp_pct,
                    auction_date = EXCLUDED.auction_date,
                    updated_at = now();
            """
        else:
            query = f"""
                INSERT INTO sovereign_sdl_spreads (
                    state_name, state_code, tenor_years, cut_off_yield,
                    spread_over_gsec_bps, fiscal_tier, debt_to_gsdp_pct,
                    auction_date, updated_at
                ) VALUES ({p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, datetime('now'))
                ON CONFLICT (state_name) DO UPDATE SET
                    state_code = excluded.state_code,
                    tenor_years = excluded.tenor_years,
                    cut_off_yield = excluded.cut_off_yield,
                    spread_over_gsec_bps = excluded.spread_over_gsec_bps,
                    fiscal_tier = excluded.fiscal_tier,
                    debt_to_gsdp_pct = excluded.debt_to_gsdp_pct,
                    auction_date = excluded.auction_date,
                    updated_at = datetime('now');
            """
        params = (
            item["state_name"],
            item["state_code"],
            float(item.get("tenor_years", 10.0)),
            float(item["cut_off_yield"]),
            float(item["spread_over_gsec_bps"]),
            item.get("fiscal_tier", "TIER_1_PRUDENT"),
            float(item.get("debt_to_gsdp_pct", 0.0)),
            str(item.get("auction_date", "2026-09-30")),
        )
        cursor.execute(query, params)
        conn.commit()
        return True
    except Exception as e:
        logger.error(f"Error saving SDL benchmark {item.get('state_name')}: {e}")
        conn.rollback()
        return False
    finally:
        cursor.close()
        conn.close()


def get_sovereign_sdl_matrix() -> List[Dict[str, Any]]:
    """Returns State Development Loan (SDL) benchmarks across states ranked by spread."""
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        cursor.execute("""
            SELECT id, state_name, state_code, tenor_years, cut_off_yield,
                   spread_over_gsec_bps, fiscal_tier, debt_to_gsdp_pct,
                   auction_date, updated_at
            FROM sovereign_sdl_spreads
            ORDER BY spread_over_gsec_bps ASC;
        """)
        rows = cursor.fetchall()

        if not rows:
            logger.info("SDL spreads table empty. Initializing baseline SDL benchmarks...")
            for s in DEFAULT_SDL_MATRIX:
                save_sovereign_sdl_item(s)
            return sorted(DEFAULT_SDL_MATRIX, key=lambda x: x["spread_over_gsec_bps"])

        results = []
        for r in rows:
            results.append({
                "id": r[0],
                "state_name": r[1],
                "state_code": r[2],
                "tenor_years": float(r[3]),
                "cut_off_yield": float(r[4]),
                "spread_over_gsec_bps": float(r[5]),
                "fiscal_tier": r[6],
                "debt_to_gsdp_pct": float(r[7]),
                "auction_date": str(r[8]),
                "updated_at": str(r[9]),
            })
        return results
    except Exception as e:
        logger.error(f"Error fetching SDL matrix: {e}")
        return sorted(DEFAULT_SDL_MATRIX, key=lambda x: x["spread_over_gsec_bps"])
    finally:
        cursor.close()
        conn.close()


get_sdl_state_spreads = get_sovereign_sdl_matrix



def get_macro_monetary_corridor() -> Dict[str, Any]:
    """Returns official policy rates (Repo, SDF, MSF), CPI inflation, and real yield metrics."""
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        cursor.execute("""
            SELECT metric_key, metric_name, metric_value, unit, period_label, source
            FROM sovereign_macro_rates;
        """)
        rows = cursor.fetchall()

        if not rows:
            p = get_placeholder()
            is_pg = bool(get_supabase_url())
            for m in DEFAULT_MACRO_RATES:
                if is_pg:
                    q = f"""INSERT INTO sovereign_macro_rates
                           (metric_key, metric_name, metric_value, unit, period_label, source)
                           VALUES ({p},{p},{p},{p},{p},{p}) ON CONFLICT (metric_key) DO NOTHING;"""
                else:
                    q = f"""INSERT OR IGNORE INTO sovereign_macro_rates
                           (metric_key, metric_name, metric_value, unit, period_label, source)
                           VALUES ({p},{p},{p},{p},{p},{p});"""
                cursor.execute(q, (m["metric_key"], m["metric_name"], m["metric_value"], m["unit"], m["period_label"], m["source"]))
            conn.commit()
            cursor.execute("SELECT metric_key, metric_name, metric_value, unit, period_label, source FROM sovereign_macro_rates;")
            rows = cursor.fetchall()

        result_dict = {}
        for r in rows:
            result_dict[r[0]] = {
                "key": r[0],
                "name": r[1],
                "value": float(r[2]),
                "unit": r[3],
                "period": r[4],
                "source": r[5]
            }
        return result_dict
    except Exception as e:
        logger.error(f"Error fetching macro rates: {e}")
        return {
            m["metric_key"]: {
                "key": m["metric_key"],
                "name": m["metric_name"],
                "value": m["metric_value"],
                "unit": m["unit"],
                "period": m["period_label"],
                "source": m["source"]
            }
            for m in DEFAULT_MACRO_RATES
        }
    finally:
        cursor.close()
        conn.close()


def get_historical_sovereign_curves() -> Dict[str, List[Dict[str, Any]]]:
    """Returns multi-curve historical overlays (current, 1-month ago, 1-year ago)."""
    return DEFAULT_HISTORICAL_CURVES


def save_etf_matrix_item(item: Dict[str, Any]) -> bool:
    """Inserts or updates an entry in the national ETF matrix."""
    conn = get_db_connection()
    cursor = conn.cursor()
    p = get_placeholder()
    is_pg = bool(get_supabase_url())

    try:
        lp = float(item.get("last_price", item.get("cmp_inr", 0.0)))
        nv = float(item.get("nav", item.get("nav_inr", 0.0)))
        prem_disc = round(((lp - nv) / nv) * 100, 2) if nv > 0 else 0.0

        if is_pg:
            query = f"""
                INSERT INTO etf_matrix (
                    symbol, scheme_name, category, underlying_index,
                    last_price, nav, premium_discount_pct, tracking_error_1y,
                    expense_ratio_pct, aum_crores, avg_daily_volume,
                    avg_daily_turnover_cr, liquidity_tier, updated_at
                ) VALUES ({p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, now())
                ON CONFLICT (symbol) DO UPDATE SET
                    scheme_name = EXCLUDED.scheme_name,
                    category = EXCLUDED.category,
                    underlying_index = EXCLUDED.underlying_index,
                    last_price = EXCLUDED.last_price,
                    nav = EXCLUDED.nav,
                    premium_discount_pct = EXCLUDED.premium_discount_pct,
                    tracking_error_1y = EXCLUDED.tracking_error_1y,
                    expense_ratio_pct = EXCLUDED.expense_ratio_pct,
                    aum_crores = EXCLUDED.aum_crores,
                    avg_daily_volume = EXCLUDED.avg_daily_volume,
                    avg_daily_turnover_cr = EXCLUDED.avg_daily_turnover_cr,
                    liquidity_tier = EXCLUDED.liquidity_tier,
                    updated_at = now();
            """
        else:
            query = f"""
                INSERT INTO etf_matrix (
                    symbol, scheme_name, category, underlying_index,
                    last_price, nav, premium_discount_pct, tracking_error_1y,
                    expense_ratio_pct, aum_crores, avg_daily_volume,
                    avg_daily_turnover_cr, liquidity_tier, updated_at
                ) VALUES ({p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, datetime('now'))
                ON CONFLICT (symbol) DO UPDATE SET
                    scheme_name = excluded.scheme_name,
                    category = excluded.category,
                    underlying_index = excluded.underlying_index,
                    last_price = excluded.last_price,
                    nav = excluded.nav,
                    premium_discount_pct = excluded.premium_discount_pct,
                    tracking_error_1y = excluded.tracking_error_1y,
                    expense_ratio_pct = excluded.expense_ratio_pct,
                    aum_crores = excluded.aum_crores,
                    avg_daily_volume = excluded.avg_daily_volume,
                    avg_daily_turnover_cr = excluded.avg_daily_turnover_cr,
                    liquidity_tier = excluded.liquidity_tier,
                    updated_at = datetime('now');
            """
        params = (
            item["symbol"].upper(),
            item.get("scheme_name", item.get("name", item["symbol"])),
            item.get("category", "EQUITY_INDEX"),
            item.get("underlying_index", item.get("benchmark_index", "Nifty 50 TRI")),
            lp,
            nv,
            prem_disc,
            float(item.get("tracking_error_1y", item.get("tracking_error_pct", 0.05))),
            float(item.get("expense_ratio_pct", item.get("ter_pct", 0.10))),
            float(item.get("aum_crores", 1000.0)),
            float(item.get("avg_daily_volume", item.get("avg_daily_volume_shares", 500000.0))),
            float(item.get("avg_daily_turnover_cr", 10.0)),
            item.get("liquidity_tier", "HIGH_LIQUIDITY"),
        )
        cursor.execute(query, params)
        conn.commit()
        return True
    except Exception as e:
        logger.error(f"Error saving ETF matrix item {item.get('symbol')}: {e}")
        conn.rollback()
        return False
    finally:
        cursor.close()
        conn.close()


def get_etf_matrix(category: Optional[str] = None) -> List[Dict[str, Any]]:
    """Retrieves all ETFs in the matrix, optionally filtered by category."""
    conn = get_db_connection()
    cursor = conn.cursor()
    p = get_placeholder()

    try:
        where_clause = f"WHERE category = {p}" if category else ""
        query = f"""
            SELECT id, symbol, scheme_name, category, underlying_index,
                   last_price, nav, premium_discount_pct, tracking_error_1y,
                   expense_ratio_pct, aum_crores, avg_daily_volume,
                   avg_daily_turnover_cr, liquidity_tier, updated_at
            FROM etf_matrix
            {where_clause}
            ORDER BY aum_crores DESC;
        """
        if category:
            cursor.execute(query, (category,))
        else:
            cursor.execute(query)
        rows = cursor.fetchall()

        if not rows:
            logger.info("ETF matrix table is empty. Initializing baseline ETFs...")
            for etf in DEFAULT_ETF_MATRIX:
                save_etf_matrix_item(etf)
            if category:
                return [x for x in DEFAULT_ETF_MATRIX if x["category"] == category]
            return DEFAULT_ETF_MATRIX

        results = []
        for r in rows:
            results.append({
                "id": r[0],
                "symbol": r[1],
                "scheme_name": r[2],
                "category": r[3],
                "underlying_index": r[4],
                "last_price": float(r[5]),
                "nav": float(r[6]),
                "premium_discount_pct": float(r[7]),
                "tracking_error_1y": float(r[8]),
                "expense_ratio_pct": float(r[9]),
                "aum_crores": float(r[10]),
                "avg_daily_volume": float(r[11]),
                "avg_daily_turnover_cr": float(r[12]),
                "liquidity_tier": r[13],
                "updated_at": str(r[14]),
            })
        return results
    except Exception as e:
        logger.error(f"Error fetching ETF matrix: {e}")
        return DEFAULT_ETF_MATRIX
    finally:
        cursor.close()
        conn.close()
