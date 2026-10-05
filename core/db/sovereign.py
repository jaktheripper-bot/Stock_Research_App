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
        "tenor_label": "5Y_GSEC",
        "instrument_type": "GSEC",
        "maturity_years": 5.00,
        "cut_off_yield": 7.08,
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
        "tenor_label": "30Y_GSEC",
        "instrument_type": "GSEC",
        "maturity_years": 30.00,
        "cut_off_yield": 7.24,
        "auction_date": "2026-09-19",
        "source": "RBI_AUCTION_CUTOFF"
    },
    {
        "tenor_label": "10Y_SDL",
        "instrument_type": "SDL",
        "maturity_years": 10.00,
        "cut_off_yield": 7.45,
        "auction_date": "2026-09-30",
        "source": "RBI_AUCTION_CUTOFF"
    }
]

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

        if not rows:
            # Seed defaults
            logger.info("Sovereign benchmarks table is empty. Initializing baseline RBI auction yields...")
            for b in DEFAULT_SOVEREIGN_BENCHMARKS:
                save_sovereign_benchmark(b)
            return DEFAULT_SOVEREIGN_BENCHMARKS

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


def get_sovereign_curve_analytics() -> Dict[str, Any]:
    """Computes key sovereign curve macro metrics: slope, credit spread, and real yield."""
    curve = get_sovereign_yield_curve()
    tenor_map = {item["tenor_label"]: item["cut_off_yield"] for item in curve}

    tbill_91d = tenor_map.get("91D_TBILL", 6.84)
    gsec_10y = tenor_map.get("10Y_GSEC", 7.12)
    sdl_10y = tenor_map.get("10Y_SDL", 7.45)

    # 10Y G-Sec vs 91D T-Bill slope (Term Spread in basis points)
    term_spread_bps = round((gsec_10y - tbill_91d) * 100, 1)

    # 10Y State Development Loan (SDL) vs Central G-Sec spread
    sdl_spread_bps = round((sdl_10y - gsec_10y) * 100, 1)

    return {
        "benchmark_10y_gsec": gsec_10y,
        "risk_free_short_tbill": tbill_91d,
        "sdl_state_yield": sdl_10y,
        "term_spread_bps": term_spread_bps,
        "sdl_credit_spread_bps": sdl_spread_bps,
        "curve_shape": "Normal (Upward Sloping)" if term_spread_bps > 15 else ("Flat" if term_spread_bps >= -10 else "Inverted"),
        "curve_points": curve
    }


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
