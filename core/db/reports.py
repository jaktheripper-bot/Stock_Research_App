"""Equity research reports archive and differential historical revisions repository."""

import json
import logging
import os
import threading
import time
from datetime import datetime
from functools import lru_cache, wraps
import requests  # IndexNow ping
import asyncio

from normalizer import clean_ticker, extract_citations_from_report
from core.db.connection import init_db, get_db_connection, get_supabase_url, get_placeholder, IST
from core.db.compliance import log_compliance_event
from core.presentation.formatters import (
    format_52w_range,
    format_de_multiple,
    format_pct_metric,
    format_pe_multiple,
    format_standard_date,
    format_standard_timestamp,
)

logger = logging.getLogger("equity_research.core.db.reports")

def ttl_cache(ttl_seconds: int = 120, maxsize: int = 2):
    """Thread-safe in-memory TTL and LRU cache for high-frequency directory queries."""
    def decorator(fn):
        cache = {}
        lock = threading.Lock()

        @wraps(fn)
        def wrapped(*args, **kwargs):
            key = (args, tuple(sorted(kwargs.items())))
            now = time.time()
            with lock:
                if key in cache:
                    val, exp = cache[key]
                    if now < exp:
                        return val
                    del cache[key]
            res = fn(*args, **kwargs)
            if res is not None:
                with lock:
                    if len(cache) >= maxsize:
                        try:
                            oldest = min(cache.keys(), key=lambda k: cache[k][1])
                            cache.pop(oldest, None)
                        except Exception as pop_err:
                            logger.debug("TTL cache eviction notice: %s", pop_err)
                            cache.clear()
                    cache[key] = (res, now + ttl_seconds)
            return res

        def cache_clear():
            with lock:
                cache.clear()

        wrapped.cache_clear = cache_clear
        wrapped.clear = cache_clear
        return wrapped

    return decorator

def _format_timestamp(raw_ts) -> str:
    """Formats raw database timestamp (datetime, ISO string, YYYY-MM-DD, or Unix epoch) into IST."""
    if not raw_ts:
        return "Unknown Date"
    return format_standard_timestamp(raw_ts, fallback=str(raw_ts))

def save_report_to_archive(stock_data: dict, report_text: str, announcement: str = "", revision_trigger: str = "", citations: list = None):
    """
    Saves or updates the current report snapshot in 'reports' and appends an immutable
    historical revision record in 'report_revisions' to power the differential engine.
    """
    init_db()
    conn = get_db_connection()
    cursor = conn.cursor()
    placeholder = get_placeholder()

    clean_sym = clean_ticker(stock_data.get("ticker", ""))
    short_name = stock_data.get("short_name") or clean_sym

    curr_price = stock_data.get("current_price") or stock_data.get("currentValue") or 0.0
    try:
        curr_price = float(str(curr_price).replace(",", "").strip())
    except Exception as e:
        logger.debug("Failed parsing curr_price: %s", e)
        curr_price = 0.0

    mcap = stock_data.get("market_cap") or stock_data.get("marketCapFull") or 0.0
    try:
        mcap = float(str(mcap).replace(",", "").strip())
    except Exception as e:
        logger.debug("Failed parsing mcap: %s", e)
        mcap = 0.0

    pe = str(stock_data.get("pe_ratio", "N/A"))

    if report_text:
        try:
            from core.analysis.language_filter import enforce_indian_english
            report_text = enforce_indian_english(report_text)
        except Exception as filter_err:
            logger.debug("Language filter normalization notice: %s", filter_err)

    if citations is None:
        citations = extract_citations_from_report(report_text)
    citations_json = json.dumps(citations) if citations else None

    try:
        # 1. Update/Upsert the current snapshot in 'reports'
        query_snapshot = f'''
            INSERT INTO reports (ticker, short_name, report_text, baseline_price, baseline_pe, baseline_mcap, latest_announcement, citations_json)
            VALUES ({placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder})
            ON CONFLICT (ticker) 
            DO UPDATE SET 
                short_name = EXCLUDED.short_name,
                report_text = EXCLUDED.report_text,
                timestamp = CURRENT_TIMESTAMP,
                baseline_price = EXCLUDED.baseline_price,
                baseline_pe = EXCLUDED.baseline_pe,
                baseline_mcap = EXCLUDED.baseline_mcap,
                latest_announcement = EXCLUDED.latest_announcement,
                citations_json = EXCLUDED.citations_json
        '''
        cursor.execute(query_snapshot, (
            clean_sym, 
            short_name, 
            report_text,
            curr_price,
            pe,
            mcap,
            announcement,
            citations_json
        ))

        # 2. Append-Only Historical Archiving for Differential Tracking Engine
        query_revision = f'''
            INSERT INTO report_revisions (ticker, short_name, report_text, baseline_price, baseline_pe, baseline_mcap, latest_announcement, revision_trigger, citations_json)
            VALUES ({placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder})
        '''
        cursor.execute(query_revision, (
            clean_sym,
            short_name,
            report_text,
            curr_price,
            pe,
            mcap,
            announcement,
            revision_trigger or "Material Update",
            citations_json
        ))

        conn.commit()
        try:
            get_archived_reports.cache_clear()
            get_report_by_ticker.cache_clear()
            get_report_revisions.cache_clear()
            get_all_equities_directory_sync.cache_clear()
        except Exception as clear_err:
            logger.debug("Reports cache clear notice: %s", clear_err)
        # SEBI Compliance: Record statutory Safe Harbor disclaimer audit event
        # IndexNow instant ping – notify search engines of the new/updated dossier
        try:
            from core.seo.indexnow import ping_indexnow_urls
            base_url = (os.getenv("CANONICAL_DOMAIN") or "https://moatnomics.com").rstrip("/")
            url = f"{base_url}/dossier/{clean_sym}"
            ping_indexnow_urls(url)
        except Exception as ping_err:
            logger.debug(f"IndexNow ping notice for {clean_sym}: {ping_err}")

        try:
            log_compliance_event(clean_sym)
        except Exception as ce:
            logger.error(f"Failed to record SEBI compliance event during archive: {ce}")

        # Supabase Cloud Dual-Write Sync (PostgREST)
        try:
            from core.config import get_secret
            sb_url = get_secret("SUPABASE_URL")
            sb_key = get_secret("SUPABASE_SERVICE_ROLE_KEY")
            if sb_url and sb_key and not get_supabase_url():
                import requests
                rest_url = f"{sb_url.rstrip('/')}/rest/v1/reports"
                payload = {
                    "ticker": clean_sym,
                    "short_name": short_name,
                    "report_text": report_text,
                    "baseline_price": curr_price,
                    "baseline_pe": str(pe or ""),
                    "baseline_mcap": mcap,
                    "latest_announcement": announcement,
                    "citations_json": citations_json
                }
                requests.post(
                    rest_url,
                    headers={
                        "apikey": sb_key,
                        "Authorization": f"Bearer {sb_key}",
                        "Content-Type": "application/json",
                        "Prefer": "resolution=merge-duplicates"
                    },
                    json=payload,
                    timeout=5
                )
        except Exception as sb_err:
            logger.debug(f"Dual-write to Supabase REST skipped: {sb_err}")
    except Exception as e:
        try:
            conn.rollback()
        except Exception as rb_err:
            logger.debug("Report save rollback notice: %s", rb_err)
        logger.error(f"Failed to save report to archive for {clean_sym}: {e}")
        raise
    finally:
        cursor.close()
        conn.close()

class AwaitableList(list):
    def __await__(self):
        async def _async_self():
            return self
        return _async_self().__await__()

class AwaitableDict(dict):
    def __await__(self):
        async def _async_self():
            return self
        return _async_self().__await__()

# LRU cached version (returns AwaitableList so it can be called synchronously or awaited)
@lru_cache(maxsize=16)
def get_archived_reports(include_text: bool = False) -> list:
    """Synchronous helper returning archived reports, cached for 5 minutes via manual invalidation."""
    init_db()
    conn = get_db_connection()
    cursor = conn.cursor()
    results = []
    try:
        if include_text:
            cursor.execute('''
                SELECT r.ticker, r.short_name, r.report_text, r.timestamp, r.baseline_price, r.baseline_pe, r.baseline_mcap, r.latest_announcement,
                       COALESCE(rc.rev_count, 0) AS rev_count, r.citations_json
                FROM reports r 
                LEFT JOIN (SELECT ticker, COUNT(*) AS rev_count FROM report_revisions GROUP BY ticker) rc ON rc.ticker = r.ticker
                WHERE r.report_text IS NOT NULL
                  AND TRIM(r.report_text) != ''
                  AND r.ticker NOT LIKE 'TEST_%' 
                  AND r.ticker NOT LIKE 'UNIT_%'
                  AND r.ticker NOT LIKE 'COAL_%'
                  AND r.ticker NOT LIKE 'UNITCOAL_%'
                  AND r.ticker NOT IN ('TESTCORP', 'TESTPEER', 'ZZTESTONLY', 'COALESCE_TEST')
                ORDER BY r.timestamp DESC
            ''')
        else:
            cursor.execute('''
                SELECT r.ticker, r.short_name, '' AS report_text, r.timestamp, r.baseline_price, r.baseline_pe, r.baseline_mcap, r.latest_announcement,
                       COALESCE(rc.rev_count, 0) AS rev_count, NULL AS citations_json
                FROM reports r 
                LEFT JOIN (SELECT ticker, COUNT(*) AS rev_count FROM report_revisions GROUP BY ticker) rc ON rc.ticker = r.ticker
                WHERE r.report_text IS NOT NULL
                  AND TRIM(r.report_text) != ''
                  AND r.ticker NOT LIKE 'TEST_%' 
                  AND r.ticker NOT LIKE 'UNIT_%'
                  AND r.ticker NOT LIKE 'COAL_%'
                  AND r.ticker NOT LIKE 'UNITCOAL_%'
                  AND r.ticker NOT IN ('TESTCORP', 'TESTPEER', 'ZZTESTONLY', 'COALESCE_TEST')
                ORDER BY r.timestamp DESC
            ''')
        rows = cursor.fetchall()
        for row in rows:
            rep_text = row[2]
            cit_data = []
            if len(row) > 9 and row[9]:
                try:
                    cit_data = json.loads(row[9])
                except Exception as e:
                    logger.debug("Failed parsing citations_json in get_archived_reports: %s", e)
                    cit_data = []
            if not cit_data and rep_text:
                cit_data = extract_citations_from_report(rep_text)
            results.append({
                "ticker": row[0],
                "short_name": row[1] or row[0],
                "report_text": rep_text,
                "raw_timestamp": row[3],
                "formatted_date": _format_timestamp(row[3]),
                "baseline_price": row[4],
                "baseline_pe": row[5],
                "baseline_mcap": row[6],
                "latest_announcement": row[7] or "",
                "revision_count": int(row[8]) if len(row) > 8 and row[8] is not None else 0,
                "citations": cit_data
            })
    except Exception as e:
        logger.error(f"Database query error in get_archived_reports: {e}")
    finally:
        cursor.close()
        conn.close()
    return AwaitableList(results)

_get_archived_reports_sync = get_archived_reports
get_archived_reports_sync = get_archived_reports

# LRU cached sync helper for single ticker (returns AwaitableDict)
@lru_cache(maxsize=48)
def get_report_by_ticker(ticker: str) -> dict:
    """Fetch report by ticker, cached, returns AwaitableDict."""
    init_db()
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        clean = clean_ticker(ticker)
        placeholder = get_placeholder()
        cursor.execute(f'''
            SELECT ticker, short_name, report_text, timestamp, baseline_price, baseline_pe, baseline_mcap, latest_announcement, citations_json
            FROM reports 
            WHERE ticker = {placeholder}
        ''', (clean,))
        row = cursor.fetchone()
        if not row:
            return AwaitableDict({})
        rep_text = row[2]
        cit_data = []
        if len(row) > 8 and row[8]:
            try:
                cit_data = json.loads(row[8])
            except Exception as e:
                logger.debug("Failed parsing citations_json in get_report_by_ticker: %s", e)
                cit_data = []
        if not cit_data and rep_text:
            cit_data = extract_citations_from_report(rep_text)
        return AwaitableDict({
            "ticker": row[0],
            "short_name": row[1] or row[0],
            "report_text": rep_text,
            "raw_timestamp": row[3],
            "timestamp": row[3],
            "formatted_date": _format_timestamp(row[3]),
            "baseline_price": row[4],
            "baseline_pe": row[5],
            "baseline_mcap": row[6],
            "latest_announcement": row[7] or "",
            "citations": cit_data
        })
    finally:
        cursor.close()
        conn.close()

_get_report_by_ticker_sync = get_report_by_ticker
get_report_by_ticker_sync = get_report_by_ticker
get_latest_report = get_report_by_ticker

@lru_cache(maxsize=32)
def get_report_revisions(ticker: str, include_text: bool = False) -> list:
    """Retrieves immutable revision history for a stock to power the differential engine."""
    init_db()
    conn = get_db_connection()
    cursor = conn.cursor()
    clean = clean_ticker(ticker)
    placeholder = get_placeholder()
    revisions = []
    try:
        if include_text:
            cursor.execute(f'''
                SELECT id, ticker, short_name, report_text, timestamp, baseline_price, baseline_pe, baseline_mcap, latest_announcement, revision_trigger, citations_json
                FROM report_revisions
                WHERE ticker = {placeholder}
                ORDER BY timestamp DESC
            ''', (clean,))
        else:
            cursor.execute(f'''
                SELECT id, ticker, short_name, '' AS report_text, timestamp, baseline_price, baseline_pe, baseline_mcap, latest_announcement, revision_trigger, NULL AS citations_json
                FROM report_revisions
                WHERE ticker = {placeholder}
                ORDER BY timestamp DESC
            ''', (clean,))
        rows = cursor.fetchall()
        for row in rows:
            rep_text = row[3] if include_text else ""
            cit_data = []
            if include_text:
                if len(row) > 10 and row[10]:
                    try:
                        cit_data = json.loads(row[10])
                    except Exception as e:
                        logger.debug("Failed parsing citations_json in get_report_revisions: %s", e)
                        cit_data = []
                if not cit_data and rep_text:
                    cit_data = extract_citations_from_report(rep_text)
            revisions.append({
                "id": row[0],
                "ticker": row[1],
                "short_name": row[2] or row[1],
                "report_text": rep_text,
                "raw_timestamp": row[4],
                "formatted_date": _format_timestamp(row[4]),
                "baseline_price": row[5],
                "baseline_pe": row[6],
                "baseline_mcap": row[7],
                "latest_announcement": row[8] or "",
                "revision_trigger": row[9] or "Initial Baseline",
                "citations": cit_data
            })

        # Self-healing: Seed initial baseline revision if reports table has a snapshot but revisions table is empty
        if not revisions:
            cursor.execute(f'''
                SELECT ticker, short_name, report_text, timestamp, baseline_price, baseline_pe, baseline_mcap, latest_announcement, citations_json
                FROM reports
                WHERE ticker = {placeholder}
            ''', (clean,))
            rep_row = cursor.fetchone()
            if rep_row:
                rep_cits = rep_row[8] if len(rep_row) > 8 else None
                cursor.execute(f'''
                    INSERT INTO report_revisions (ticker, short_name, report_text, timestamp, baseline_price, baseline_pe, baseline_mcap, latest_announcement, revision_trigger, citations_json)
                    VALUES ({placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder})
                ''', (
                    rep_row[0], rep_row[1], rep_row[2], rep_row[3],
                    rep_row[4], rep_row[5], rep_row[6], rep_row[7],
                    "Archived Baseline",
                    rep_cits
                ))
                conn.commit()
                if include_text:
                    cursor.execute(f'''
                        SELECT id, ticker, short_name, report_text, timestamp, baseline_price, baseline_pe, baseline_mcap, latest_announcement, revision_trigger, citations_json
                        FROM report_revisions
                        WHERE ticker = {placeholder}
                        ORDER BY timestamp DESC
                    ''', (clean,))
                else:
                    cursor.execute(f'''
                        SELECT id, ticker, short_name, '' AS report_text, timestamp, baseline_price, baseline_pe, baseline_mcap, latest_announcement, revision_trigger, NULL AS citations_json
                        FROM report_revisions
                        WHERE ticker = {placeholder}
                        ORDER BY timestamp DESC
                    ''', (clean,))
                for s_row in cursor.fetchall():
                    s_text = s_row[3] if include_text else ""
                    s_cit = []
                    if include_text:
                        if len(s_row) > 10 and s_row[10]:
                            try:
                                s_cit = json.loads(s_row[10])
                            except Exception as e:
                                logger.debug("Failed parsing citations_json in self-healing revision: %s", e)
                                s_cit = []
                        if not s_cit and s_text:
                            s_cit = extract_citations_from_report(s_text)
                    revisions.append({
                        "id": s_row[0],
                        "ticker": s_row[1],
                        "short_name": s_row[2] or s_row[1],
                        "report_text": s_text,
                        "raw_timestamp": s_row[4],
                        "formatted_date": _format_timestamp(s_row[4]),
                        "baseline_price": s_row[5],
                        "baseline_pe": s_row[6],
                        "baseline_mcap": s_row[7],
                        "latest_announcement": s_row[8] or "",
                        "revision_trigger": s_row[9] or "Archived Baseline",
                        "citations": s_cit
                    })
    except Exception as e:
        logger.error(f"Database query error in get_report_revisions: {e}")
    finally:
        cursor.close()
        conn.close()
    return revisions

def get_revision_by_id(rev_id: int) -> dict:
    """Retrieves a single immutable revision snapshot by ID."""
    init_db()
    conn = get_db_connection()
    cursor = conn.cursor()
    placeholder = get_placeholder()
    record = None
    try:
        cursor.execute(f'''
            SELECT id, ticker, short_name, report_text, timestamp, baseline_price, baseline_pe, baseline_mcap, latest_announcement, revision_trigger
            FROM report_revisions
            WHERE id = {placeholder}
        ''', (rev_id,))
        row = cursor.fetchone()
        if row:
            record = {
                "id": row[0],
                "ticker": row[1],
                "short_name": row[2] or row[1],
                "report_text": row[3],
                "raw_timestamp": row[4],
                "formatted_date": _format_timestamp(row[4]),
                "baseline_price": row[5],
                "baseline_pe": row[6],
                "baseline_mcap": row[7],
                "latest_announcement": row[8] or "",
                "revision_trigger": row[9] or "Initial"
            }
    except Exception as e:
        logger.error(f"Database query error in get_revision_by_id: {e}")
    finally:
        cursor.close()
        conn.close()
    return record


# ==============================================================================
# All Equities Directory
# ==============================================================================

SECTOR_TAXONOMY = {
    "IT_TECH": ("IT & Technology", "icon-sector-technology"),
    "BFSI": ("BFSI & Financials", "icon-sector-financials"),
    "HEALTHCARE_PHARMA": ("Healthcare & Pharma", "icon-sector-healthcare"),
    "CAPITAL_GOODS_INFRA": ("Capital Goods & Infra", "icon-sector-capital-goods"),
    "AUTOMOTIVE": ("Automotive & Mobility", "icon-sector-automotive"),
    "CONSUMER_FMCG": ("Consumer & Retail", "icon-sector-consumer"),
    "CHEMICALS_MATERIALS": ("Chemicals & Materials", "icon-sector-chemicals"),
    "COMMODITIES_ENERGY": ("Energy & Commodities", "icon-sector-energy"),
    "EMS_DEFENCE": ("EMS & Defence", "icon-sector-defence"),
    "DIVERSIFIED": ("Diversified Industrials", "icon-sector-diversified"),
}

SECTOR_SVG_IDS = {
    "IT_TECH": "icon-sector-technology",
    "BFSI": "icon-sector-financials",
    "HEALTHCARE_PHARMA": "icon-sector-healthcare",
    "CAPITAL_GOODS_INFRA": "icon-sector-capital-goods",
    "AUTOMOTIVE": "icon-sector-automotive",
    "CONSUMER_FMCG": "icon-sector-consumer",
    "CHEMICALS_MATERIALS": "icon-sector-chemicals",
    "COMMODITIES_ENERGY": "icon-sector-energy",
    "EMS_DEFENCE": "icon-sector-defence",
    "DIVERSIFIED": "icon-sector-diversified",
}


def resolve_equity_sector(ticker: str, name: str, cached_sec: str = None) -> str:
    """Classifies an equity into standard sector taxonomies."""
    from core.analysis.sector_scoring import (
        KNOWN_TICKER_SECTORS,
        _COMPILED_SECTOR_PATTERNS,
        _CORP_NOISE_RE,
    )
    c_sec = str(cached_sec or "")
    if "Specialty Chemicals" in c_sec:
        return "CHEMICALS_MATERIALS"
    if "EMS & Defence" in c_sec:
        return "EMS_DEFENCE"
    if "Precision Engineering" in c_sec or "Building Materials" in c_sec or "Industrial Machinery" in c_sec:
        return "CAPITAL_GOODS_INFRA"
    if "Renewables & Power" in c_sec:
        return "COMMODITIES_ENERGY"
    if "Healthcare" in c_sec:
        return "HEALTHCARE_PHARMA"
    if "Automotive" in c_sec:
        return "AUTOMOTIVE"
    if ticker in KNOWN_TICKER_SECTORS:
        return KNOWN_TICKER_SECTORS[ticker]
    clean_name = _CORP_NOISE_RE.sub(" ", str(name or "")).strip()
    combined = f"{ticker} {clean_name}".strip()
    for sec_slug, patterns in _COMPILED_SECTOR_PATTERNS.items():
        for pat in patterns:
            if pat.search(combined):
                return sec_slug
    return "DIVERSIFIED"


@ttl_cache(ttl_seconds=120, maxsize=2)
def get_all_equities_directory_sync() -> list:
    """
    Returns complete list of all 143 verified equities joined with
    cached fundamentals, sector taxonomy, market cap tiers, and revision metadata.
    """
    init_db()
    conn = get_db_connection()
    cursor = conn.cursor()
    equities = []
    try:
        cursor.execute('''
            SELECT 
                r.ticker, 
                r.short_name, 
                r.timestamp, 
                COALESCE(rev.cnt, 1) as rev_count,
                f.company_name, 
                f.sector, 
                f.industry, 
                COALESCE(f.current_price, r.baseline_price) as current_price, 
                COALESCE(f.market_cap, r.baseline_mcap) as market_cap, 
                CASE WHEN f.pe_ratio IS NOT NULL AND f.pe_ratio NOT IN ('N/A', 'Fair', '', '-') THEN f.pe_ratio ELSE r.baseline_pe END as pe_ratio, 
                f.roce, 
                f.roe, 
                f.debt_to_equity, 
                f.operating_margin, 
                f.fifty_two_week_high, 
                f.fifty_two_week_low
            FROM reports r
            LEFT JOIN (SELECT ticker, COUNT(*) as cnt FROM report_revisions GROUP BY ticker) rev ON r.ticker = rev.ticker
            LEFT JOIN cached_fundamentals f ON r.ticker = f.ticker
            WHERE r.ticker NOT LIKE 'TEST_%'
              AND r.ticker NOT LIKE 'UNIT_%'
              AND r.ticker NOT LIKE 'COAL_%'
              AND r.ticker NOT LIKE 'UNITCOAL_%'
              AND r.ticker NOT IN ('TESTCORP', 'TESTPEER', 'ZZTESTONLY', 'COALESCE_TEST')
        ''')
        rows = cursor.fetchall()
        for r in rows:
            ticker = r[0]
            short_name = r[1] or ticker
            raw_ts = r[2]
            rev_cnt = int(r[3]) if r[3] else 1
            comp_name = r[4]
            cached_sec = r[5]
            ind = r[6] or "Diversified"
            cmp_val = r[7]
            mcap_val = r[8]
            pe_val = r[9]
            roce_val = r[10]
            roe_val = r[11]
            de_val = r[12]
            opm_val = r[13]
            high52 = r[14]
            low52 = r[15]

            # Prefer descriptive company name
            name = short_name if (short_name and short_name != ticker) else (comp_name or ticker)

            # Resolve Sector
            sec_slug = resolve_equity_sector(ticker, name, cached_sec)
            sec_label, sec_icon = SECTOR_TAXONOMY.get(sec_slug, ("Diversified Industrials", "icon-sector-diversified"))
            sec_svg_id = SECTOR_SVG_IDS.get(sec_slug, "icon-sector-industrials")

            # Market Cap in Crores
            mcap_cr = round(float(mcap_val) / 1e7, 1) if mcap_val else 0.0
            if mcap_cr >= 100000:
                tier, tier_slug = "Mega-Cap", "MEGA"
            elif mcap_cr >= 25000:
                tier, tier_slug = "Large-Cap", "LARGE"
            elif mcap_cr >= 5000:
                tier, tier_slug = "Mid-Cap", "MID"
            else:
                tier, tier_slug = "Small-Cap", "SMALL"

            # Parse CMP
            try:
                cmp_float = float(str(cmp_val).replace(",", "").strip()) if cmp_val else 0.0
            except Exception as e:
                logger.debug("Failed parsing cmp_val: %s", e)
                cmp_float = 0.0

            # Parse standardized institutional multiples & return ratios (Feedback #4 & #10)
            pe_meta = format_pe_multiple(pe_val)
            pe_float = pe_meta["float_val"]
            pe_str = pe_meta["display"]

            roce_meta = format_pct_metric(roce_val, metric_name="Return on Capital Employed (ROCE)")
            roce_float = roce_meta["float_val"]

            roe_meta = format_pct_metric(roe_val, metric_name="Return on Equity (ROE)")
            roe_float = roe_meta["float_val"]

            de_meta = format_de_multiple(
                de_val,
                ticker=ticker,
                sector_slug=sec_slug,
                sector_label=sec_label,
                industry=ind,
                company_name=name,
            )
            de_float = de_meta["float_val"]

            opm_meta = format_pct_metric(opm_val, metric_name="Operating Margin (OPM)")
            opm_float = opm_meta["float_val"]

            # Calculate recently inducted status (within last 48 hours)
            is_recently_inducted = False
            if raw_ts:
                try:
                    from core.presentation.formatters import _coerce_datetime
                    ts_dt = _coerce_datetime(raw_ts)
                    if ts_dt and (datetime.now(IST) - ts_dt).total_seconds() < 48 * 3600:
                        is_recently_inducted = True
                except Exception as e:
                    logger.debug("Failed parsing raw_ts for recently inducted: %s", e)
                    is_recently_inducted = False

            equities.append({
                "ticker": ticker,
                "name": name,
                "short_name": short_name,
                "company_name": comp_name or name,
                "sector": sec_label,
                "sector_slug": sec_slug,
                "sector_icon": sec_icon,
                "sector_svg_id": sec_svg_id,
                "industry": ind,
                "current_price": cmp_float,
                "formatted_price": f"₹{cmp_float:,.2f}" if cmp_float > 0 else "—",
                "market_cap_cr": mcap_cr,
                "formatted_mcap": f"₹{mcap_cr:,.0f} Cr" if mcap_cr > 0 else "—",
                "market_cap_tier": tier,
                "market_cap_tier_slug": tier_slug,
                "pe_ratio": pe_str,
                "pe_float": pe_float,
                "pe_tooltip": pe_meta["tooltip"],
                "pe_status": pe_meta["status"],
                "roce": roce_float,
                "roce_pct": roce_meta["display"],
                "roce_tooltip": roce_meta["tooltip"],
                "roe": roe_float,
                "roe_pct": roe_meta["display"],
                "roe_tooltip": roe_meta["tooltip"],
                "debt_to_equity": de_meta["display"],
                "debt_to_equity_float": de_float,
                "de_tooltip": de_meta["tooltip"],
                "de_status": de_meta["status"],
                "operating_margin": opm_meta["display"],
                "operating_margin_float": opm_float,
                "opm_tooltip": opm_meta["tooltip"],
                "fifty_two_week_high": high52 or "—",
                "fifty_two_week_low": low52 or "—",
                "formatted_52w_range": format_52w_range(low52, high52),
                "revision_count": rev_cnt,
                "formatted_date": format_standard_date(raw_ts, fallback="Archived"),
                "formatted_timestamp": _format_timestamp(raw_ts),
                "dossier_url": f"/dossier/{ticker}",
                "is_recently_inducted": is_recently_inducted,
            })
    except Exception as e:
        logger.error(f"Database query error in get_all_equities_directory_sync: {e}")
    finally:
        cursor.close()
        conn.close()
    return equities
