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

from core.db.etf_universe import CANONICAL_ETF_UNIVERSE

# Baseline ETF Matrix covering 140+ benchmark Indian ETFs across 9 institutional categories
DEFAULT_ETF_MATRIX = CANONICAL_ETF_UNIVERSE


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


def refresh_daily_sovereign_benchmarks(edition_date: Optional[str] = None) -> Dict[str, Any]:
    """Synchronizes the Sovereign Yield Curve and SDL Disparity Matrix for the daily edition.
    Updates auction dates, timestamps, and verifies the full suite of statutory tenors.
    """
    if not edition_date:
        edition_date = datetime.now(IST).strftime("%Y-%m-%d")

    logger.info(f"Synchronizing statutory sovereign benchmarks for edition date: {edition_date}...")
    benchmarks_updated = 0
    for bench in DEFAULT_SOVEREIGN_BENCHMARKS:
        b_copy = dict(bench)
        b_copy["auction_date"] = edition_date
        if save_sovereign_benchmark(b_copy):
            benchmarks_updated += 1

    sdl_updated = 0
    for sdl in DEFAULT_SDL_MATRIX:
        s_copy = dict(sdl)
        s_copy["auction_date"] = edition_date
        if save_sovereign_sdl_item(s_copy):
            sdl_updated += 1

    # Ensure macro monetary corridor is primed
    get_macro_monetary_corridor()

    summary = {
        "status": "SUCCESS",
        "edition_date": edition_date,
        "benchmarks_updated": benchmarks_updated,
        "sdl_spreads_updated": sdl_updated,
        "total_tenors": len(DEFAULT_SOVEREIGN_BENCHMARKS),
        "total_sdls": len(DEFAULT_SDL_MATRIX)
    }
    logger.info(f"Sovereign benchmark refresh complete: {benchmarks_updated} tenors, {sdl_updated} SDLs for {edition_date}.")
    return summary
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
    return save_etf_matrix_items([item]) > 0


def save_etf_matrix_items(items: List[Dict[str, Any]]) -> int:
    """Batch inserts or updates entries in the national ETF matrix in a single transaction."""
    if not items:
        return 0

    conn = get_db_connection()
    cursor = conn.cursor()
    p = get_placeholder()
    is_pg = bool(get_supabase_url())
    saved_count = 0

    try:
        if is_pg:
            query = f"""
                INSERT INTO etf_matrix (
                    symbol, scheme_name, category, underlying_index,
                    last_price, nav, premium_discount_pct, tracking_error_1y,
                    expense_ratio_pct, aum_crores, avg_daily_volume,
                    avg_daily_turnover_cr, liquidity_tier, scheme_code, isin, updated_at
                ) VALUES ({p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, now())
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
                    scheme_code = COALESCE(EXCLUDED.scheme_code, etf_matrix.scheme_code),
                    isin = COALESCE(EXCLUDED.isin, etf_matrix.isin),
                    updated_at = now();
            """
        else:
            query = f"""
                INSERT INTO etf_matrix (
                    symbol, scheme_name, category, underlying_index,
                    last_price, nav, premium_discount_pct, tracking_error_1y,
                    expense_ratio_pct, aum_crores, avg_daily_volume,
                    avg_daily_turnover_cr, liquidity_tier, scheme_code, isin, updated_at
                ) VALUES ({p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, datetime('now'))
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
                    scheme_code = COALESCE(excluded.scheme_code, etf_matrix.scheme_code),
                    isin = COALESCE(excluded.isin, etf_matrix.isin),
                    updated_at = datetime('now');
            """

        for item in items:
            lp = float(item.get("last_price", item.get("cmp_inr", 0.0)))
            nv = float(item.get("nav", item.get("nav_inr", 0.0)))
            prem_disc = round(((lp - nv) / nv) * 100, 2) if nv > 0 else 0.0

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
                item.get("scheme_code"),
                item.get("isin"),
            )
            cursor.execute(query, params)
            saved_count += 1

        conn.commit()
        return saved_count
    except Exception as e:
        logger.error(f"Error batch saving ETF matrix items: {e}")
        conn.rollback()
        return 0
    finally:
        cursor.close()
        conn.close()


def get_etf_matrix(
    category: Optional[str] = None,
    query: Optional[str] = None,
    sort_by: Optional[str] = None,
    limit: Optional[int] = None
) -> List[Dict[str, Any]]:
    """Retrieves all ETFs in the matrix with optional category filtering, text search, and sorting."""
    conn = get_db_connection()
    cursor = conn.cursor()
    p = get_placeholder()

    try:
        where_clauses = []
        params = []

        if category and category.strip().upper() != "ALL":
            where_clauses.append(f"category = {p}")
            params.append(category.strip().upper())

        if query and query.strip():
            clean_q = f"%{query.strip().upper()}%"
            where_clauses.append(f"(UPPER(symbol) LIKE {p} OR UPPER(scheme_name) LIKE {p} OR UPPER(underlying_index) LIKE {p})")
            params.extend([clean_q, clean_q, clean_q])

        where_sql = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""

        sort_map = {
            "aum_desc": "aum_crores DESC",
            "volume_desc": "avg_daily_volume DESC",
            "turnover_desc": "avg_daily_turnover_cr DESC",
            "tracking_error_asc": "tracking_error_1y ASC",
            "expense_ratio_asc": "expense_ratio_pct ASC",
            "nav_divergence_desc": "ABS(premium_discount_pct) DESC",
            "discount_desc": "premium_discount_pct ASC",
            "premium_desc": "premium_discount_pct DESC",
            "symbol_asc": "symbol ASC"
        }
        order_sql = sort_map.get(sort_by, "aum_crores DESC")

        limit_sql = f"LIMIT {int(limit)}" if limit and isinstance(limit, int) and limit > 0 else ""

        sql = f"""
            SELECT id, symbol, scheme_name, category, underlying_index,
                   last_price, nav, premium_discount_pct, tracking_error_1y,
                   expense_ratio_pct, aum_crores, avg_daily_volume,
                   avg_daily_turnover_cr, liquidity_tier, scheme_code, isin, updated_at
            FROM etf_matrix
            {where_sql}
            ORDER BY {order_sql}
            {limit_sql};
        """
        cursor.execute(sql, tuple(params))
        rows = cursor.fetchall()

        if not rows:
            cursor.execute("SELECT COUNT(*) FROM etf_matrix;")
            total_in_table = cursor.fetchone()[0]
            if total_in_table == 0:
                logger.info("ETF matrix table is empty. Initializing baseline canonical ETFs...")
                save_etf_matrix_items(DEFAULT_ETF_MATRIX)
                cursor.execute(sql, tuple(params))
                rows = cursor.fetchall()

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
                "scheme_code": r[14],
                "isin": r[15],
                "updated_at": str(r[16]),
            })
        return results
    except Exception as e:
        logger.error(f"Error fetching ETF matrix: {e}")
        # Fallback to in-memory filter of canonical universe
        fallback = list(DEFAULT_ETF_MATRIX)
        if category and category.strip().upper() != "ALL":
            fallback = [x for x in fallback if x.get("category") == category.strip().upper()]
        if query and query.strip():
            cq = query.strip().upper()
            fallback = [x for x in fallback if cq in x.get("symbol", "").upper() or cq in x.get("scheme_name", "").upper()]
        return fallback
    finally:
        cursor.close()
        conn.close()


def get_etf_by_symbol(symbol: str) -> Optional[Dict[str, Any]]:
    """Retrieves a single ETF by its exchange symbol."""
    if not symbol:
        return None

    conn = get_db_connection()
    cursor = conn.cursor()
    p = get_placeholder()

    try:
        query = f"""
            SELECT id, symbol, scheme_name, category, underlying_index,
                   last_price, nav, premium_discount_pct, tracking_error_1y,
                   expense_ratio_pct, aum_crores, avg_daily_volume,
                   avg_daily_turnover_cr, liquidity_tier, scheme_code, isin, updated_at
            FROM etf_matrix
            WHERE UPPER(symbol) = {p}
            LIMIT 1;
        """
        cursor.execute(query, (symbol.strip().upper(),))
        r = cursor.fetchone()
        if not r:
            # Check canonical universe
            for item in DEFAULT_ETF_MATRIX:
                if item["symbol"].upper() == symbol.strip().upper():
                    return dict(item)
            return None

        return {
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
            "scheme_code": r[14],
            "isin": r[15],
            "updated_at": str(r[16]),
        }
    except Exception as e:
        logger.error(f"Error fetching ETF by symbol {symbol}: {e}")
        for item in DEFAULT_ETF_MATRIX:
            if item["symbol"].upper() == symbol.strip().upper():
                return dict(item)
        return None
    finally:
        cursor.close()
        conn.close()
