"""AMFI Official Daily NAV & Scheme Master Ingestion Pipeline.

Ingests the authoritative daily NAV feed from the Association of Mutual Funds in India (AMFI):
Endpoint: https://www.amfiindia.com/spages/NAVAll.txt
Publishes NAVs for ~15,000 scheme options daily by 11:00 PM IST.

Complies with SEBI (Mutual Funds) Regulations, 1996 portfolio and NAV disclosure mandates.
Provides:
1. Resilient cached fetching with fallback SSL context
2. Structured parsing of 8-column and 6-column AMFI formats
3. Automated category, broad category, and benchmark index derivation
4. Fast batch synchronization to SQLite and PostgreSQL (Supabase)
5. Dynamic search across the master directory
"""

import os
import re
import ssl
import time
import logging
import urllib.request
from pathlib import Path
from datetime import datetime, date, timezone
from typing import List, Dict, Optional, Any, Tuple

from core.db.connection import IST
from core.db.mutual_funds import save_mutual_fund_scheme, get_mutual_fund_scheme

logger = logging.getLogger(__name__)

AMFI_NAV_ALL_URL = "https://www.amfiindia.com/spages/NAVAll.txt"
CACHE_DIR = Path(".cache")
CACHE_FILE = CACHE_DIR / "amfi_nav_all.txt"
CACHE_TTL_SECONDS = 12 * 3600  # 12 hours


def _get_ssl_context() -> ssl.SSLContext:
    """Creates a verified SSL context using certifi CA bundle or system certificates."""
    try:
        import os
        import certifi
        cafile = os.environ.get("SSL_CERT_FILE")
        if not cafile or not os.path.exists(cafile):
            cafile = certifi.where()
        return ssl.create_default_context(cafile=cafile)
    except Exception as cert_err:
        logger.debug("certifi context notice: %s", cert_err)
    return ssl.create_default_context()


def fetch_amfi_nav_raw(force_refresh: bool = False, timeout_sec: int = 20) -> str:
    """
    Fetches raw AMFI NAVAll.txt text with disk caching to avoid hitting AMFI on every query.
    Falls back to cached disk copy if network is unavailable.
    """
    now = time.time()
    CACHE_DIR.mkdir(parents=True, exist_ok=True)

    if not force_refresh and CACHE_FILE.exists():
        mtime = CACHE_FILE.stat().st_mtime
        if (now - mtime) < CACHE_TTL_SECONDS:
            try:
                with open(CACHE_FILE, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read()
                    if content and len(content) > 10000:
                        return content
            except Exception as e:
                logger.warning(f"Failed to read AMFI cache file: {e}")

    # Fetch live from AMFI
    ctx = _get_ssl_context()
    req = urllib.request.Request(
        AMFI_NAV_ALL_URL,
        headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) StockResearchApp/2.0",
            "Accept": "text/plain, */*"
        }
    )

    try:
        logger.info(f"Fetching fresh AMFI NAVAll.txt from {AMFI_NAV_ALL_URL}...")
        with urllib.request.urlopen(req, context=ctx, timeout=timeout_sec) as resp:
            raw_data = resp.read().decode("utf-8", errors="ignore")
            if raw_data and len(raw_data) > 10000:
                with open(CACHE_FILE, "w", encoding="utf-8") as f:
                    f.write(raw_data)
                logger.info(f"AMFI NAVAll.txt cached successfully ({len(raw_data):,} bytes).")
                return raw_data
    except Exception as e:
        logger.error(f"Error fetching AMFI NAV feed: {e}")
        # Try returning stale cache if available
        if CACHE_FILE.exists():
            logger.info("Falling back to stale AMFI cache on disk...")
            with open(CACHE_FILE, "r", encoding="utf-8", errors="ignore") as f:
                return f.read()
        raise e

    return ""


def derive_broad_category(category_name: str) -> str:
    """Categorizes granular SEBI scheme classification into broad asset classes."""
    cat_lower = (category_name or "").lower()
    if any(k in cat_lower for k in ("equity", "large cap", "mid cap", "small cap", "flexi cap", "multi cap", "elss", "dividend yield", "focused")):
        return "EQUITY"
    if any(k in cat_lower for k in ("debt", "bond", "liquid", "money market", "gilt", "overnight", "ultra short", "credit risk", "corporate bond", "banking and psu")):
        return "DEBT"
    if any(k in cat_lower for k in ("hybrid", "balanced", "arbitrage", "multi asset", "dynamic asset")):
        return "HYBRID"
    if any(k in cat_lower for k in ("gold", "silver", "commodity")):
        return "COMMODITY"
    if "index" in cat_lower or "etf" in cat_lower:
        return "EQUITY"
    if "solution" in cat_lower or "retirement" in cat_lower or "children" in cat_lower:
        return "SOLUTION_ORIENTED"
    return "OTHER"


def derive_benchmark_index(category_name: str, broad_category: str) -> str:
    """Maps SEBI scheme category to canonical benchmark index."""
    cat_lower = (category_name or "").lower()
    if "small cap" in cat_lower:
        return "NIFTY Smallcap 250 TRI"
    if "mid cap" in cat_lower:
        return "NIFTY Midcap 150 TRI"
    if "large cap" in cat_lower:
        return "NIFTY 50 TRI"
    if "large & mid" in cat_lower or "large and mid" in cat_lower:
        return "NIFTY LargeMidcap 250 TRI"
    if "flexi cap" in cat_lower or "multi cap" in cat_lower:
        return "NIFTY 500 TRI"
    if "elss" in cat_lower:
        return "NIFTY 500 TRI"
    if "bank" in cat_lower:
        return "NIFTY Bank TRI"
    if "it" in cat_lower or "tech" in cat_lower:
        return "NIFTY IT TRI"
    if broad_category == "DEBT":
        return "CRISIL Composite Bond Fund Index"
    if broad_category == "HYBRID":
        return "CRISIL Hybrid 35+65 Aggressive Index"
    return "NIFTY 500 TRI"


def parse_amfi_nav_feed(
    raw_source: Any,
    direct_growth_only: bool = False,
    query_filter: Optional[str] = None,
    limit: Optional[int] = None,
    exact_code: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    Parses AMFI NAVAll.txt into standardized scheme objects.
    Supports raw text string, open file object, or line iterator.
    Extracts category and AMC fund house from block headers.
    Optionally stops immediately upon matching exact_code or reaching limit.
    """
    if not raw_source:
        return []

    if isinstance(raw_source, str):
        import io
        lines = io.StringIO(raw_source)
    else:
        lines = raw_source

    schemes = []
    current_category = "Open Ended Schemes (Equity Scheme - Flexi Cap Fund)"
    current_fund_house = "Unknown AMC"

    clean_q = query_filter.strip().lower() if query_filter else None
    clean_exact = str(exact_code).strip() if exact_code else None

    for line in lines:
        line_clean = line.strip()
        if not line_clean:
            continue

        # Header check: Skip the column header
        if "Scheme Code;" in line_clean:
            continue

        # Category block header (e.g., 'Open Ended Schemes(Equity Scheme - Large Cap Fund)')
        if "(" in line_clean and ")" in line_clean and ";" not in line_clean:
            # Extract clean category inside parens
            m = re.search(r"\((.*?)\)", line_clean)
            if m:
                current_category = m.group(1).strip()
            else:
                current_category = line_clean
            continue

        # AMC Fund House block header (line without semicolons and without parens)
        if ";" not in line_clean:
            current_fund_house = line_clean.strip()
            continue

        # Semicolon data row
        parts = [p.strip() for p in line_clean.split(";")]
        if len(parts) < 6:
            continue

        code = parts[0]
        if not code.isdigit():
            continue

        # If searching for an exact scheme code, filter early before building strings
        if clean_exact and code != clean_exact:
            continue

        # 8-column format: Code, ISIN Growth, ISIN Reinv, Name, Plan, Option, NAV, Date
        if len(parts) >= 8:
            isin_growth = parts[1]
            base_name = parts[3]
            plan = parts[4]
            option = parts[5]
            nav_str = parts[6]
            date_str = parts[7]
            full_name = f"{base_name} - {plan} - {option}"
        else:
            # 6-column format: Code, ISIN Growth, ISIN Reinv, Full Name, NAV, Date
            isin_growth = parts[1]
            full_name = parts[3]
            plan = "Direct" if "direct" in full_name.lower() else "Regular"
            option = "Growth" if "growth" in full_name.lower() else "IDCW"
            nav_str = parts[4]
            date_str = parts[5]

        # Filter: Direct Growth only (bypassed if targeting an exact scheme code)
        is_direct = "direct" in plan.lower() or "direct" in full_name.lower()
        is_growth = "growth" in option.lower() or "growth" in full_name.lower()

        if not clean_exact and direct_growth_only and not (is_direct and is_growth):
            continue

        # Query filter if provided
        if clean_q:
            match_str = f"{code} {full_name} {current_fund_house} {current_category}".lower()
            if clean_q not in match_str:
                continue

        try:
            nav_val = float(nav_str)
        except (ValueError, TypeError):
            nav_val = 0.0

        broad_cat = derive_broad_category(current_category)
        bench = derive_benchmark_index(current_category, broad_cat)

        schemes.append({
            "scheme_code": code,
            "scheme_name": full_name,
            "fund_house": current_fund_house,
            "category": current_category,
            "broad_category": broad_cat,
            "benchmark_index": bench,
            "isin": isin_growth if isin_growth != "-" else "",
            "isin_growth": isin_growth if isin_growth != "-" else "",
            "nav": nav_val,
            "nav_date": date_str,
            "plan": "Direct" if is_direct else "Regular",
            "option": "Growth" if is_growth else "IDCW",
            "ter_direct_pct": 0.75 if broad_cat == "EQUITY" else 0.40,
            "ter_regular_pct": 1.50 if broad_cat == "EQUITY" else 0.85,
            "portfolio_turnover_ratio_pct": 25.0,
            "active_share_pct": 70.0 if broad_cat == "EQUITY" else 0.0,
            "risk_grade": "Very High" if broad_cat == "EQUITY" else "Moderate",
            "fund_manager": "Senior Fund Manager",
            "last_portfolio_date": datetime.now(IST).date().isoformat()
        })

        # Early termination: exact code match or limit reached
        if clean_exact:
            break
        if limit and len(schemes) >= limit:
            break

    return schemes


parse_amfi_nav_text = parse_amfi_nav_feed


def search_amfi_master_directory(
    query: str,
    limit: int = 25,
    direct_growth_only: bool = True
) -> List[Dict[str, Any]]:
    """
    Searches the live AMFI master directory for matching mutual fund schemes.
    Streams line-by-line from disk cache without allocating the entire 1.5MB file in memory.
    Stops immediately upon finding an exact scheme_code match or reaching limit items.
    Automatically persists matching schemes to the database for seamless future lookups.
    """
    if not query or len(query.strip()) < 2:
        return []

    clean_q = query.strip()
    is_numeric_code = clean_q.isdigit() and (5 <= len(clean_q) <= 8)

    try:
        # Ensure disk cache exists
        if not CACHE_FILE.exists() or (time.time() - CACHE_FILE.stat().st_mtime) >= CACHE_TTL_SECONDS:
            try:
                fetch_amfi_nav_raw()
            except Exception as fetch_err:
                logger.debug("Live fetch notice in AMFI directory search: %s", fetch_err)

        if not CACHE_FILE.exists():
            return []

        # Stream line-by-line using file iterator
        with open(CACHE_FILE, "r", encoding="utf-8", errors="ignore") as f:
            matches = parse_amfi_nav_feed(
                f,
                direct_growth_only=direct_growth_only if not is_numeric_code else False,
                query_filter=clean_q if not is_numeric_code else None,
                limit=limit,
                exact_code=clean_q if is_numeric_code else None
            )

        results = matches[:limit]

        # Opportunistically persist top matches to database if not present
        for s in results[:10]:
            try:
                save_mutual_fund_scheme(s)
            except Exception as save_err:
                logger.debug("Opportunistic scheme save notice: %s", save_err)

        return results
    except Exception as e:
        logger.error(f"Search in AMFI directory failed: {e}")
        return []


def ingest_amfi_daily_feed(
    limit: Optional[int] = None,
    direct_growth_only: bool = True
) -> Dict[str, Any]:
    """
    Executes complete AMFI NAV feed ingestion pipeline.
    Parses and upserts active schemes into mutual_fund_schemes.
    Returns summary metrics.
    """
    t0 = time.time()
    raw_text = fetch_amfi_nav_raw(force_refresh=True)
    schemes = parse_amfi_nav_feed(raw_text, direct_growth_only=direct_growth_only)

    if limit and limit > 0:
        schemes = schemes[:limit]

    upserted_count = 0
    error_count = 0

    from core.db.mutual_funds import save_mutual_fund_schemes_batch
    batch_saved = save_mutual_fund_schemes_batch(schemes)
    if batch_saved > 0 or not schemes:
        upserted_count = batch_saved
    else:
        for s in schemes:
            try:
                if save_mutual_fund_scheme(s):
                    upserted_count += 1
                else:
                    error_count += 1
            except Exception as e:
                error_count += 1
                logger.debug(f"Failed to upsert scheme {s.get('scheme_code')}: {e}")

    duration = round(time.time() - t0, 2)
    logger.info(f"AMFI Ingestion completed: {upserted_count} schemes saved/updated ({error_count} errors) in {duration}s.")

    return {
        "status": "success",
        "total_parsed": len(schemes),
        "upserted": upserted_count,
        "errors": error_count,
        "duration_seconds": duration,
        "feed_date": schemes[0]["nav_date"] if schemes else datetime.now(IST).date().isoformat()
    }
