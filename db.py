import hashlib
import json
import logging
import os
import threading
from datetime import datetime, timezone, timedelta
import streamlit as st

from normalizer import clean_ticker, extract_citations_from_report

IST = timezone(timedelta(hours=5, minutes=30))
logger = logging.getLogger("equity_research.db")

MANDATORY_SEBI_DISCLAIMER = (
    "SEBI Safe Harbor & Statutory Compliance: Antigravity Equity Research Engine is a diagnostic "
    "algorithmic analytics and financial research tool developed strictly for informational, educational, "
    "and analytical purposes. It does NOT provide, and should NEVER be construed as providing, investment advice, "
    "recommendations, endorsements, or financial solicitations of any kind. Antigravity is not a SEBI-registered "
    "Research Analyst (RA) or Investment Adviser (IA). Indian securities markets are subject to high market risks; "
    "past performance, algorithmic valuations, fair values, and technical support/resistance bands are historical "
    "and model-based estimates that do not guarantee future returns. Users must consult a qualified, SEBI-registered "
    "financial adviser before executing any investment decisions."
)

_DB_INITIALIZED = False
_DB_INIT_LOCK = threading.Lock()

_CACHED_SUPABASE_URL = None
_SUPABASE_URL_RESOLVED = False

def get_supabase_url() -> str | None:
    """Returns configured Supabase DB URL, cached in memory after first resolution."""
    global _CACHED_SUPABASE_URL, _SUPABASE_URL_RESOLVED
    if not _SUPABASE_URL_RESOLVED:
        url = os.environ.get("SUPABASE_DB_URL")
        if not url:
            try:
                url = st.secrets.get("SUPABASE_DB_URL")
            except Exception:
                pass
        _CACHED_SUPABASE_URL = url
        _SUPABASE_URL_RESOLVED = True
    return _CACHED_SUPABASE_URL

def get_placeholder() -> str:
    """Returns '%s' for PostgreSQL/Supabase or '?' for SQLite."""
    return "%s" if get_supabase_url() else "?"

class _PooledConnectionProxy:
    """Proxy wrapper around a psycopg2 connection checked out from ThreadedConnectionPool.
    Calling .close() returns the connection to the pool rather than terminating the TCP/SSL socket."""
    def __init__(self, pool, conn):
        self._pool = pool
        self._conn = conn
        self._returned = False

    def __getattr__(self, name):
        return getattr(self._conn, name)

    def close(self):
        if not self._returned:
            self._returned = True
            try:
                if not self._conn.closed:
                    self._conn.rollback()
            except Exception:
                pass
            try:
                self._pool.putconn(self._conn)
            except Exception:
                try:
                    self._conn.close()
                except Exception:
                    pass

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

@st.cache_resource
def _get_pg_pool(dsn: str):
    import psycopg2.pool
    return psycopg2.pool.ThreadedConnectionPool(minconn=1, maxconn=10, dsn=dsn)

def _acquire_connection_from_pool(pool):
    conn = pool.getconn()
    is_bad = False
    try:
        if conn.closed != 0:
            is_bad = True
        else:
            conn.poll()
            if conn.status == 2:  # STATUS_IN_TRANSACTION
                conn.rollback()
    except Exception:
        is_bad = True

    if is_bad:
        try:
            pool.putconn(conn, close=True)
        except Exception:
            pass
        conn = pool.getconn()
    return conn

def get_db_connection():
    supabase_url = get_supabase_url()
    if supabase_url:
        try:
            pool = _get_pg_pool(supabase_url)
            raw_conn = _acquire_connection_from_pool(pool)
            return _PooledConnectionProxy(pool, raw_conn)
        except Exception:
            try:
                import psycopg2
                return psycopg2.connect(supabase_url)
            except Exception:
                pass
    
    import sqlite3
    conn = sqlite3.connect("reports.db", timeout=30.0, check_same_thread=False)
    try:
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA busy_timeout=30000;")
    except Exception:
        pass
    return conn

def init_db(force: bool = False):
    global _DB_INITIALIZED
    if _DB_INITIALIZED and not force:
        return

    with _DB_INIT_LOCK:
        if _DB_INITIALIZED and not force:
            return

        conn = get_db_connection()
        cursor = conn.cursor()
        supabase_url = get_supabase_url()
    
    try:
        # Schema Migration Engine: Ensure migrations table exists
        if supabase_url:
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    version TEXT PRIMARY KEY,
                    applied_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
                );
            ''')
        else:
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    version TEXT PRIMARY KEY,
                    applied_at DATETIME DEFAULT CURRENT_TIMESTAMP
                );
            ''')
        conn.commit()

        cursor.execute("SELECT version FROM schema_migrations;")
        applied = {row[0] for row in cursor.fetchall()}

        # Migration v001: Core institutional schema
        if "v001_core_schema" not in applied:
            logger.info("Applying schema migration: v001_core_schema...")
            if supabase_url:
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS reports (
                        ticker TEXT PRIMARY KEY,
                        short_name TEXT,
                        report_text TEXT,
                        timestamp TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
                        baseline_price NUMERIC,
                        baseline_pe TEXT,
                        baseline_mcap NUMERIC,
                        latest_announcement TEXT
                    );
                ''')
                # Add columns if migrating an existing table
                for col, col_type in [("baseline_price", "NUMERIC"), ("baseline_pe", "TEXT"), ("baseline_mcap", "NUMERIC"), ("latest_announcement", "TEXT")]:
                    cursor.execute(f"ALTER TABLE reports ADD COLUMN IF NOT EXISTS {col} {col_type};")

                # Differential Engine: Append-Only revisions table
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS report_revisions (
                        id SERIAL PRIMARY KEY,
                        ticker TEXT NOT NULL,
                        short_name TEXT,
                        report_text TEXT NOT NULL,
                        timestamp TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
                        baseline_price NUMERIC,
                        baseline_pe TEXT,
                        baseline_mcap NUMERIC,
                        latest_announcement TEXT,
                        revision_trigger TEXT
                    );
                ''')
                # Granular Alerting Engine: Watchlist & Alert Events tables
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS watchlist (
                        id SERIAL PRIMARY KEY,
                        ticker TEXT UNIQUE NOT NULL,
                        short_name TEXT,
                        scrip_code TEXT,
                        added_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
                        alert_material BOOLEAN DEFAULT TRUE,
                        alert_fundamental BOOLEAN DEFAULT TRUE,
                        alert_valuation BOOLEAN DEFAULT TRUE,
                        digest_mode TEXT DEFAULT 'instant',
                        last_scanned_price NUMERIC,
                        last_scanned_announcement TEXT,
                        last_scanned_at TIMESTAMPTZ
                    );
                ''')
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS alert_events (
                        id SERIAL PRIMARY KEY,
                        ticker TEXT NOT NULL,
                        category TEXT NOT NULL,
                        severity TEXT DEFAULT 'medium',
                        title TEXT NOT NULL,
                        details TEXT,
                        timestamp TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
                        is_read BOOLEAN DEFAULT FALSE,
                        source TEXT DEFAULT 'BSE Polling Engine'
                    );
                ''')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_alert_events_ticker ON alert_events (ticker, timestamp DESC);')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_alert_events_unread ON alert_events (is_read, timestamp DESC);')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_report_revisions_ticker ON report_revisions (ticker);')
                cursor.execute("INSERT INTO schema_migrations (version) VALUES ('v001_core_schema') ON CONFLICT DO NOTHING;")
            else:
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS reports (
                        ticker TEXT PRIMARY KEY,
                        short_name TEXT,
                        report_text TEXT,
                        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                        baseline_price REAL,
                        baseline_pe TEXT,
                        baseline_mcap REAL,
                        latest_announcement TEXT
                    );
                ''')
                # SQLite migration for reports table
                cursor.execute("PRAGMA table_info(reports);")
                existing_cols = [c[1] for c in cursor.fetchall()]
                for col, col_type in [("baseline_price", "REAL"), ("baseline_pe", "TEXT"), ("baseline_mcap", "REAL"), ("latest_announcement", "TEXT")]:
                    if col not in existing_cols:
                        try:
                            cursor.execute(f"ALTER TABLE reports ADD COLUMN {col} {col_type};")
                        except Exception:
                            pass

                # Differential Engine: Append-Only revisions table in SQLite
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS report_revisions (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        ticker TEXT NOT NULL,
                        short_name TEXT,
                        report_text TEXT NOT NULL,
                        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                        baseline_price REAL,
                        baseline_pe TEXT,
                        baseline_mcap REAL,
                        latest_announcement TEXT,
                        revision_trigger TEXT
                    );
                ''')
                # Granular Alerting Engine: Watchlist & Alert Events tables in SQLite
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS watchlist (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        ticker TEXT UNIQUE NOT NULL,
                        short_name TEXT,
                        scrip_code TEXT,
                        added_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                        alert_material INTEGER DEFAULT 1,
                        alert_fundamental INTEGER DEFAULT 1,
                        alert_valuation INTEGER DEFAULT 1,
                        digest_mode TEXT DEFAULT 'instant',
                        last_scanned_price REAL,
                        last_scanned_announcement TEXT,
                        last_scanned_at DATETIME
                    );
                ''')
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS alert_events (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        ticker TEXT NOT NULL,
                        category TEXT NOT NULL,
                        severity TEXT DEFAULT 'medium',
                        title TEXT NOT NULL,
                        details TEXT,
                        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                        is_read INTEGER DEFAULT 0,
                        source TEXT DEFAULT 'BSE Polling Engine'
                    );
                ''')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_alert_events_ticker ON alert_events (ticker, timestamp DESC);')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_alert_events_unread ON alert_events (is_read, timestamp DESC);')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_report_revisions_ticker ON report_revisions (ticker);')
                cursor.execute("INSERT OR IGNORE INTO schema_migrations (version) VALUES ('v001_core_schema');")
            conn.commit()

        # Migration v002: SEBI Compliance & Retention Audit Trail
        if "v002_compliance_audit_log" not in applied:
            logger.info("Applying schema migration: v002_compliance_audit_log...")
            if supabase_url:
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS compliance_audit_log (
                        id SERIAL PRIMARY KEY,
                        ticker TEXT NOT NULL,
                        disclaimer_version TEXT NOT NULL,
                        disclaimer_hash TEXT NOT NULL,
                        timestamp TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
                    );
                ''')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_compliance_audit_ticker ON compliance_audit_log (ticker, timestamp DESC);')
                cursor.execute("INSERT INTO schema_migrations (version) VALUES ('v002_compliance_audit_log') ON CONFLICT DO NOTHING;")
            else:
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS compliance_audit_log (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        ticker TEXT NOT NULL,
                        disclaimer_version TEXT NOT NULL,
                        disclaimer_hash TEXT NOT NULL,
                        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                    );
                ''')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_compliance_audit_ticker ON compliance_audit_log (ticker, timestamp DESC);')
                cursor.execute("INSERT OR IGNORE INTO schema_migrations (version) VALUES ('v002_compliance_audit_log');")
            conn.commit()

        # Migration v003: Backend Site Usage Measurements & Telemetry Analytics
        if "v003_site_usage_analytics" not in applied:
            logger.info("Applying schema migration: v003_site_usage_analytics...")
            if supabase_url:
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS site_usage_events (
                        id SERIAL PRIMARY KEY,
                        event_type VARCHAR(50) NOT NULL,
                        ticker VARCHAR(20),
                        latency_ms REAL DEFAULT 0.0,
                        cost_saved_usd REAL DEFAULT 0.0,
                        details TEXT,
                        timestamp TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
                    );
                ''')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_site_usage_event_type ON site_usage_events (event_type, timestamp DESC);')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_site_usage_ticker ON site_usage_events (ticker, timestamp DESC);')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_site_usage_timestamp ON site_usage_events (timestamp DESC);')
                cursor.execute("INSERT INTO schema_migrations (version) VALUES ('v003_site_usage_analytics') ON CONFLICT DO NOTHING;")
            else:
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS site_usage_events (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        event_type TEXT NOT NULL,
                        ticker TEXT,
                        latency_ms REAL DEFAULT 0.0,
                        cost_saved_usd REAL DEFAULT 0.0,
                        details TEXT,
                        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                    );
                ''')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_site_usage_event_type ON site_usage_events (event_type, timestamp DESC);')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_site_usage_ticker ON site_usage_events (ticker, timestamp DESC);')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_site_usage_timestamp ON site_usage_events (timestamp DESC);')
                cursor.execute("INSERT OR IGNORE INTO schema_migrations (version) VALUES ('v003_site_usage_analytics');")
            conn.commit()

        # Migration v004: Traffic Attribution, Visitor Demographics & Session Tracking
        if "v004_traffic_attribution_and_session_tracking" not in applied:
            logger.info("Applying schema migration: v004_traffic_attribution_and_session_tracking...")
            if supabase_url:
                cursor.execute('''
                    ALTER TABLE site_usage_events ADD COLUMN IF NOT EXISTS session_id VARCHAR(64);
                    ALTER TABLE site_usage_events ADD COLUMN IF NOT EXISTS traffic_source VARCHAR(100);
                    ALTER TABLE site_usage_events ADD COLUMN IF NOT EXISTS referrer TEXT;
                    ALTER TABLE site_usage_events ADD COLUMN IF NOT EXISTS country VARCHAR(20);
                    ALTER TABLE site_usage_events ADD COLUMN IF NOT EXISTS device_type VARCHAR(30);
                    ALTER TABLE site_usage_events ADD COLUMN IF NOT EXISTS browser VARCHAR(50);
                    ALTER TABLE site_usage_events ADD COLUMN IF NOT EXISTS os VARCHAR(50);
                ''')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_site_usage_session ON site_usage_events (session_id, timestamp DESC);')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_site_usage_source ON site_usage_events (traffic_source, timestamp DESC);')
                cursor.execute("INSERT INTO schema_migrations (version) VALUES ('v004_traffic_attribution_and_session_tracking') ON CONFLICT DO NOTHING;")
            else:
                cursor.execute("PRAGMA table_info(site_usage_events);")
                existing_cols = [c[1] for c in cursor.fetchall()]
                for col, col_type in [
                    ("session_id", "TEXT"),
                    ("traffic_source", "TEXT"),
                    ("referrer", "TEXT"),
                    ("country", "TEXT"),
                    ("device_type", "TEXT"),
                    ("browser", "TEXT"),
                    ("os", "TEXT")
                ]:
                    if col not in existing_cols:
                        try:
                            cursor.execute(f"ALTER TABLE site_usage_events ADD COLUMN {col} {col_type};")
                        except Exception:
                            pass
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_site_usage_session ON site_usage_events (session_id, timestamp DESC);')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_site_usage_source ON site_usage_events (traffic_source, timestamp DESC);')
                cursor.execute("INSERT OR IGNORE INTO schema_migrations (version) VALUES ('v004_traffic_attribution_and_session_tracking');")
            conn.commit()

        # Migration v005: System Settings & Dynamic Configuration
        if "v005_system_settings" not in applied:
            logger.info("Applying schema migration: v005_system_settings...")
            if supabase_url:
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS system_settings (
                        key VARCHAR(64) PRIMARY KEY,
                        value TEXT NOT NULL,
                        updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
                    );
                ''')
                cursor.execute("INSERT INTO schema_migrations (version) VALUES ('v005_system_settings') ON CONFLICT DO NOTHING;")
            else:
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS system_settings (
                        key TEXT PRIMARY KEY,
                        value TEXT NOT NULL,
                        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
                    );
                ''')
                cursor.execute("INSERT OR IGNORE INTO schema_migrations (version) VALUES ('v005_system_settings');")
            conn.commit()

        # Migration v006: Visual Source Attribution & Footnote Citations Engine
        if "v006_report_citations" not in applied:
            logger.info("Applying schema migration: v006_report_citations...")
            if supabase_url:
                cursor.execute("ALTER TABLE reports ADD COLUMN IF NOT EXISTS citations_json TEXT;")
                cursor.execute("ALTER TABLE report_revisions ADD COLUMN IF NOT EXISTS citations_json TEXT;")
                cursor.execute("INSERT INTO schema_migrations (version) VALUES ('v006_report_citations') ON CONFLICT DO NOTHING;")
            else:
                cursor.execute("PRAGMA table_info(reports);")
                existing_rep_cols = [c[1] for c in cursor.fetchall()]
                if "citations_json" not in existing_rep_cols:
                    try:
                        cursor.execute("ALTER TABLE reports ADD COLUMN citations_json TEXT;")
                    except Exception:
                        pass
                cursor.execute("PRAGMA table_info(report_revisions);")
                existing_rev_cols = [c[1] for c in cursor.fetchall()]
                if "citations_json" not in existing_rev_cols:
                    try:
                        cursor.execute("ALTER TABLE report_revisions ADD COLUMN citations_json TEXT;")
                    except Exception:
                        pass
                cursor.execute("INSERT OR IGNORE INTO schema_migrations (version) VALUES ('v006_report_citations');")
            conn.commit()

        _DB_INITIALIZED = True
    except Exception as e:
        logger.error(f"Error during init_db migrations: {e}")
        raise
    finally:
        cursor.close()
        conn.close()

def save_report_to_archive(stock_data: dict, report_text: str, announcement: str = "", revision_trigger: str = "", citations: list = None):
    init_db()
    conn = get_db_connection()
    cursor = conn.cursor()
    supabase_url = get_supabase_url()
    placeholder = get_placeholder()
    
    clean_sym = clean_ticker(stock_data.get("ticker", ""))
    short_name = stock_data.get("short_name") or clean_sym

    curr_price = stock_data.get("current_price") or stock_data.get("currentValue") or 0.0
    try:
        curr_price = float(str(curr_price).replace(",", "").strip())
    except Exception:
        curr_price = 0.0

    mcap = stock_data.get("market_cap") or stock_data.get("marketCapFull") or 0.0
    try:
        mcap = float(str(mcap).replace(",", "").strip())
    except Exception:
        mcap = 0.0

    pe = str(stock_data.get("pe_ratio", "N/A"))

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
            st.cache_data.clear()
        except Exception:
            pass
        # SEBI Compliance: Record statutory Safe Harbor disclaimer audit event
        try:
            log_compliance_event(clean_sym)
        except Exception as ce:
            logger.error(f"Failed to record SEBI compliance event during archive: {ce}")
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        logger.error(f"Failed to save report to archive for {clean_sym}: {e}")
        raise
    finally:
        cursor.close()
        conn.close()

def log_compliance_event(ticker: str, disclaimer_text: str = None) -> bool:
    """Records a SEBI Safe Harbor disclaimer attachment event in the immutable audit log."""
    init_db()
    conn = get_db_connection()
    cursor = conn.cursor()
    supabase_url = get_supabase_url()
    placeholder = get_placeholder()

    clean_sym = clean_ticker(ticker)
    target_disclaimer = disclaimer_text or MANDATORY_SEBI_DISCLAIMER
    disclaimer_hash = hashlib.sha256(target_disclaimer.encode("utf-8")).hexdigest()
    disclaimer_version = "SEBI-RA-2024-V1"

    try:
        query = f'''
            INSERT INTO compliance_audit_log (ticker, disclaimer_version, disclaimer_hash)
            VALUES ({placeholder}, {placeholder}, {placeholder})
        '''
        cursor.execute(query, (clean_sym, disclaimer_version, disclaimer_hash))
        conn.commit()
        logger.info(f"Recorded SEBI compliance audit event for {clean_sym} (hash={disclaimer_hash[:8]}...)")
        return True
    except Exception as e:
        logger.error(f"Error logging compliance event for {clean_sym}: {e}")
        return False
    finally:
        cursor.close()
        conn.close()

def get_compliance_audit_logs(ticker: str = None, limit: int = 50) -> list:
    """Retrieves immutable SEBI Safe Harbor compliance audit events."""
    init_db()
    conn = get_db_connection()
    cursor = conn.cursor()
    supabase_url = get_supabase_url()
    placeholder = get_placeholder()

    try:
        if ticker:
            clean_sym = clean_ticker(ticker)
            query = f'''
                SELECT id, ticker, disclaimer_version, disclaimer_hash, timestamp
                FROM compliance_audit_log
                WHERE ticker = {placeholder}
                ORDER BY timestamp DESC
                LIMIT {placeholder}
            '''
            cursor.execute(query, (clean_sym, limit))
        else:
            query = f'''
                SELECT id, ticker, disclaimer_version, disclaimer_hash, timestamp
                FROM compliance_audit_log
                ORDER BY timestamp DESC
                LIMIT {placeholder}
            '''
            cursor.execute(query, (limit,))

        rows = cursor.fetchall()
        logs = []
        for row in rows:
            ts = row[4]
            if isinstance(ts, str):
                try:
                    ts = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                except Exception:
                    pass
            if hasattr(ts, "astimezone"):
                ts = ts.astimezone(IST)
            formatted_date = ts.strftime("%d-%m-%Y %H:%M IST") if hasattr(ts, "strftime") else str(ts)
            logs.append({
                "id": row[0],
                "ticker": row[1],
                "disclaimer_version": row[2],
                "disclaimer_hash": row[3],
                "timestamp": ts,
                "formatted_date": formatted_date
            })
        return logs
    except Exception as e:
        logger.error(f"Error fetching compliance audit logs: {e}")
        return []
    finally:
        cursor.close()
        conn.close()

def _format_timestamp(raw_ts) -> str:
    if not raw_ts:
        return "Unknown Date"
    try:
        if isinstance(raw_ts, datetime):
            dt = raw_ts
        else:
            s = str(raw_ts).strip()
            if s.endswith("Z"):
                s = s[:-1] + "+00:00"
            dt = datetime.fromisoformat(s)

        if dt.tzinfo is None:
            # Default database timestamps without explicit tz to UTC
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(IST).strftime("%d-%b-%Y %H:%M IST")
    except Exception:
        return f"{str(raw_ts)[:16]} IST"

@st.cache_data(ttl="5m", max_entries=5)
def get_archived_reports(include_text: bool = False) -> list:
    init_db()
    conn = get_db_connection()
    cursor = conn.cursor()
    results = []
    try:
        if include_text:
            cursor.execute('''
                SELECT r.ticker, r.short_name, r.report_text, r.timestamp, r.baseline_price, r.baseline_pe, r.baseline_mcap, r.latest_announcement,
                       COALESCE(rc.rev_count, 0) AS rev_count
                FROM reports r 
                LEFT JOIN (SELECT ticker, COUNT(*) AS rev_count FROM report_revisions GROUP BY ticker) rc ON rc.ticker = r.ticker
                ORDER BY r.timestamp DESC
            ''')
        else:
            cursor.execute('''
                SELECT r.ticker, r.short_name, '' AS report_text, r.timestamp, r.baseline_price, r.baseline_pe, r.baseline_mcap, r.latest_announcement,
                       COALESCE(rc.rev_count, 0) AS rev_count
                FROM reports r 
                LEFT JOIN (SELECT ticker, COUNT(*) AS rev_count FROM report_revisions GROUP BY ticker) rc ON rc.ticker = r.ticker
                ORDER BY r.timestamp DESC
            ''')
        rows = cursor.fetchall()
        for row in rows:
            results.append({
                "ticker": row[0],
                "short_name": row[1] or row[0],
                "report_text": row[2],
                "raw_timestamp": row[3],
                "formatted_date": _format_timestamp(row[3]),
                "baseline_price": row[4],
                "baseline_pe": row[5],
                "baseline_mcap": row[6],
                "latest_announcement": row[7] or "",
                "revision_count": int(row[8]) if len(row) > 8 and row[8] is not None else 0
            })
    except Exception as e:
        logger.error(f"Database query error in get_archived_reports: {e}")
    finally:
        cursor.close()
        conn.close()
    return results

@st.cache_data(ttl="5m", max_entries=50)
def get_report_by_ticker(ticker: str) -> dict:
    init_db()
    conn = get_db_connection()
    cursor = conn.cursor()
    clean = clean_ticker(ticker)
    supabase_url = get_supabase_url()
    placeholder = get_placeholder()
    
    record = None
    try:
        cursor.execute(f'''
            SELECT ticker, short_name, report_text, timestamp, baseline_price, baseline_pe, baseline_mcap, latest_announcement, citations_json
            FROM reports 
            WHERE ticker = {placeholder}
        ''', (clean,))
        row = cursor.fetchone()
        if row:
            rep_text = row[2]
            cit_data = []
            if len(row) > 8 and row[8]:
                try:
                    cit_data = json.loads(row[8])
                except Exception:
                    cit_data = []
            if not cit_data and rep_text:
                cit_data = extract_citations_from_report(rep_text)
            record = {
                "ticker": row[0],
                "short_name": row[1] or row[0],
                "report_text": rep_text,
                "raw_timestamp": row[3],
                "formatted_date": _format_timestamp(row[3]),
                "baseline_price": row[4],
                "baseline_pe": row[5],
                "baseline_mcap": row[6],
                "latest_announcement": row[7] or "",
                "citations": cit_data
            }
    except Exception as e:
        logger.error(f"Database query error in get_report_by_ticker: {e}")
    finally:
        cursor.close()
        conn.close()
    return record

@st.cache_data(ttl="5m", max_entries=50)
def get_report_revisions(ticker: str) -> list:
    """Retrieves immutable revision history for a stock to power the differential engine."""
    init_db()
    conn = get_db_connection()
    cursor = conn.cursor()
    clean = clean_ticker(ticker)
    supabase_url = get_supabase_url()
    placeholder = get_placeholder()
    revisions = []
    try:
        cursor.execute(f'''
            SELECT id, ticker, short_name, report_text, timestamp, baseline_price, baseline_pe, baseline_mcap, latest_announcement, revision_trigger, citations_json
            FROM report_revisions
            WHERE ticker = {placeholder}
            ORDER BY timestamp DESC
        ''', (clean,))
        rows = cursor.fetchall()
        for row in rows:
            rep_text = row[3]
            cit_data = []
            if len(row) > 10 and row[10]:
                try:
                    cit_data = json.loads(row[10])
                except Exception:
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
                cursor.execute(f'''
                    SELECT id, ticker, short_name, report_text, timestamp, baseline_price, baseline_pe, baseline_mcap, latest_announcement, revision_trigger, citations_json
                    FROM report_revisions
                    WHERE ticker = {placeholder}
                    ORDER BY timestamp DESC
                ''', (clean,))
                for s_row in cursor.fetchall():
                    s_text = s_row[3]
                    s_cit = []
                    if len(s_row) > 10 and s_row[10]:
                        try:
                            s_cit = json.loads(s_row[10])
                        except Exception:
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
    supabase_url = get_supabase_url()
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


# ==========================================
# GRANULAR ALERTING & WATCHLIST SUBSYSTEM
# ==========================================

@st.cache_data(ttl="60s")
def get_watchlist() -> list:
    """Retrieves all tracked stocks in the surveillance watchlist."""
    init_db()
    conn = get_db_connection()
    cursor = conn.cursor()
    items = []
    try:
        cursor.execute('''
            SELECT id, ticker, short_name, scrip_code, added_at,
                   alert_material, alert_fundamental, alert_valuation,
                   digest_mode, last_scanned_price, last_scanned_announcement, last_scanned_at
            FROM watchlist
            ORDER BY ticker ASC
        ''')
        for row in cursor.fetchall():
            items.append({
                "id": row[0],
                "ticker": row[1],
                "short_name": row[2] or row[1],
                "scrip_code": row[3] or "",
                "added_at": _format_timestamp(row[4]),
                "alert_material": bool(row[5]),
                "alert_fundamental": bool(row[6]),
                "alert_valuation": bool(row[7]),
                "digest_mode": row[8] or "instant",
                "last_scanned_price": float(row[9]) if row[9] is not None else None,
                "last_scanned_announcement": row[10] or "",
                "last_scanned_at": _format_timestamp(row[11]) if row[11] else "Not yet scanned"
            })
    except Exception as e:
        logger.error(f"Database query error in get_watchlist: {e}")
    finally:
        cursor.close()
        conn.close()
    return items

def add_to_watchlist(ticker: str, short_name: str = "", scrip_code: str = "",
                     alert_material: bool = True, alert_fundamental: bool = True,
                     alert_valuation: bool = True, digest_mode: str = "instant",
                     initial_price: float = None) -> bool:
    """Adds a stock to the surveillance watchlist or updates its subscription preferences."""
    init_db()
    conn = get_db_connection()
    cursor = conn.cursor()
    clean = clean_ticker(ticker)
    supabase_url = get_supabase_url()
    placeholder = get_placeholder()
    success = False
    try:
        if supabase_url:
            query = f'''
                INSERT INTO watchlist (ticker, short_name, scrip_code, alert_material, alert_fundamental, alert_valuation, digest_mode, last_scanned_price)
                VALUES ({placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder})
                ON CONFLICT (ticker) DO UPDATE SET
                    short_name = COALESCE(EXCLUDED.short_name, watchlist.short_name),
                    scrip_code = COALESCE(EXCLUDED.scrip_code, watchlist.scrip_code),
                    alert_material = EXCLUDED.alert_material,
                    alert_fundamental = EXCLUDED.alert_fundamental,
                    alert_valuation = EXCLUDED.alert_valuation,
                    digest_mode = EXCLUDED.digest_mode
            '''
        else:
            query = f'''
                INSERT INTO watchlist (ticker, short_name, scrip_code, alert_material, alert_fundamental, alert_valuation, digest_mode, last_scanned_price)
                VALUES ({placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder})
                ON CONFLICT (ticker) DO UPDATE SET
                    short_name = COALESCE(excluded.short_name, watchlist.short_name),
                    scrip_code = COALESCE(excluded.scrip_code, watchlist.scrip_code),
                    alert_material = excluded.alert_material,
                    alert_fundamental = excluded.alert_fundamental,
                    alert_valuation = excluded.alert_valuation,
                    digest_mode = excluded.digest_mode
            '''
        cursor.execute(query, (
            clean,
            short_name or clean,
            scrip_code,
            alert_material,
            alert_fundamental,
            alert_valuation,
            digest_mode,
            initial_price
        ))
        conn.commit()
        try:
            st.cache_data.clear()
        except Exception:
            pass
        success = True
    except Exception as e:
        logger.error(f"Database error in add_to_watchlist: {e}")
    finally:
        cursor.close()
        conn.close()
    return success

def remove_from_watchlist(ticker: str) -> bool:
    """Removes a stock from the surveillance watchlist."""
    init_db()
    conn = get_db_connection()
    cursor = conn.cursor()
    clean = clean_ticker(ticker)
    supabase_url = get_supabase_url()
    placeholder = get_placeholder()
    success = False
    try:
        cursor.execute(f"DELETE FROM watchlist WHERE ticker = {placeholder}", (clean,))
        conn.commit()
        try:
            st.cache_data.clear()
        except Exception:
            pass
        success = True
    except Exception as e:
        logger.error(f"Database error in remove_from_watchlist: {e}")
    finally:
        cursor.close()
        conn.close()
    return success

def is_ticker_in_watchlist(ticker: str) -> bool:
    """Checks whether a ticker is currently active on the surveillance watchlist."""
    init_db()
    conn = get_db_connection()
    cursor = conn.cursor()
    clean = clean_ticker(ticker)
    supabase_url = get_supabase_url()
    placeholder = get_placeholder()
    in_watch = False
    try:
        cursor.execute(f"SELECT 1 FROM watchlist WHERE ticker = {placeholder}", (clean,))
        in_watch = cursor.fetchone() is not None
    except Exception:
        pass
    finally:
        cursor.close()
        conn.close()
    return in_watch

def update_watchlist_scan_state(ticker: str, price: float = None, announcement: str = None):
    """Updates the last scanned price and announcement for a watchlisted stock."""
    init_db()
    conn = get_db_connection()
    cursor = conn.cursor()
    clean = clean_ticker(ticker)
    supabase_url = get_supabase_url()
    placeholder = get_placeholder()
    try:
        cursor.execute(f'''
            UPDATE watchlist
            SET last_scanned_price = COALESCE({placeholder}, last_scanned_price),
                last_scanned_announcement = COALESCE({placeholder}, last_scanned_announcement),
                last_scanned_at = CURRENT_TIMESTAMP
            WHERE ticker = {placeholder}
        ''', (price, announcement, clean))
        conn.commit()
    except Exception as e:
        logger.error(f"Error in update_watchlist_scan_state: {e}")
    finally:
        cursor.close()
        conn.close()

def record_alert_event(ticker: str, category: str, severity: str, title: str, details: str = "", source: str = "BSE Surveillance") -> int:
    """Records an immutable alert event for a stock."""
    init_db()
    conn = get_db_connection()
    cursor = conn.cursor()
    clean = clean_ticker(ticker)
    supabase_url = get_supabase_url()
    placeholder = get_placeholder()
    new_id = None
    try:
        query = f'''
            INSERT INTO alert_events (ticker, category, severity, title, details, source)
            VALUES ({placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder})
        '''
        if supabase_url:
            query += " RETURNING id"
            cursor.execute(query, (clean, category, severity, title, details, source))
            row = cursor.fetchone()
            if row:
                new_id = row[0]
        else:
            cursor.execute(query, (clean, category, severity, title, details, source))
            new_id = cursor.lastrowid
        conn.commit()
    except Exception as e:
        logger.error(f"Error in record_alert_event: {e}")
    finally:
        cursor.close()
        conn.close()
    return new_id

def get_alert_events(ticker: str = None, category: str = None, unread_only: bool = False, limit: int = 50) -> list:
    """Retrieves recorded alert events with optional filters."""
    init_db()
    conn = get_db_connection()
    cursor = conn.cursor()
    supabase_url = get_supabase_url()
    placeholder = get_placeholder()
    alerts = []
    try:
        conditions = []
        params = []
        if ticker:
            clean = clean_ticker(ticker)
            conditions.append(f"ticker = {placeholder}")
            params.append(clean)
        if category and category.lower() != "all":
            conditions.append(f"category = {placeholder}")
            params.append(category.lower())
        if unread_only:
            conditions.append("is_read = FALSE" if supabase_url else "is_read = 0")
        
        where_clause = " WHERE " + " AND ".join(conditions) if conditions else ""
        query = f'''
            SELECT id, ticker, category, severity, title, details, timestamp, is_read, source
            FROM alert_events
            {where_clause}
            ORDER BY timestamp DESC
            LIMIT {placeholder}
        '''
        params.append(int(limit))
        cursor.execute(query, tuple(params))
        for row in cursor.fetchall():
            alerts.append({
                "id": row[0],
                "ticker": row[1],
                "category": row[2],
                "severity": row[3] or "medium",
                "title": row[4],
                "details": row[5] or "",
                "timestamp": _format_timestamp(row[6]),
                "is_read": bool(row[7]),
                "source": row[8] or "BSE Surveillance"
            })
    except Exception as e:
        logger.error(f"Error in get_alert_events: {e}")
    finally:
        cursor.close()
        conn.close()
    return alerts

def mark_alert_as_read(alert_id: int):
    """Marks a single alert event as read."""
    init_db()
    conn = get_db_connection()
    cursor = conn.cursor()
    supabase_url = get_supabase_url()
    placeholder = get_placeholder()
    try:
        val = "TRUE" if supabase_url else "1"
        cursor.execute(f"UPDATE alert_events SET is_read = {val} WHERE id = {placeholder}", (alert_id,))
        conn.commit()
        try:
            st.cache_data.clear()
        except Exception:
            pass
    except Exception as e:
        logger.error(f"Error in mark_alert_as_read: {e}")
    finally:
        cursor.close()
        conn.close()

def mark_all_alerts_as_read(ticker: str = None):
    """Marks all alerts (optionally filtered by ticker) as read."""
    init_db()
    conn = get_db_connection()
    cursor = conn.cursor()
    supabase_url = get_supabase_url()
    placeholder = get_placeholder()
    try:
        val = "TRUE" if supabase_url else "1"
        if ticker:
            clean = clean_ticker(ticker)
            cursor.execute(f"UPDATE alert_events SET is_read = {val} WHERE ticker = {placeholder}", (clean,))
        else:
            cursor.execute(f"UPDATE alert_events SET is_read = {val}")
        conn.commit()
        try:
            st.cache_data.clear()
        except Exception:
            pass
    except Exception as e:
        logger.error(f"Error in mark_all_alerts_as_read: {e}")
    finally:
        cursor.close()
        conn.close()

def dismiss_alert(alert_id: int) -> bool:
    """Permanently dismisses and deletes an alert event from the database."""
    init_db()
    conn = get_db_connection()
    cursor = conn.cursor()
    supabase_url = get_supabase_url()
    placeholder = get_placeholder()
    success = False
    try:
        cursor.execute(f"DELETE FROM alert_events WHERE id = {placeholder}", (alert_id,))
        conn.commit()
        try:
            st.cache_data.clear()
        except Exception:
            pass
        success = True
    except Exception as e:
        logger.error(f"Error in dismiss_alert: {e}")
    finally:
        cursor.close()
        conn.close()
    return success

def dismiss_all_alerts(unread_only: bool = False) -> bool:
    """Permanently dismisses and deletes alerts."""
    init_db()
    conn = get_db_connection()
    cursor = conn.cursor()
    supabase_url = get_supabase_url()
    success = False
    try:
        if unread_only:
            unread_cond = "is_read = FALSE" if supabase_url else "is_read = 0"
            cursor.execute(f"DELETE FROM alert_events WHERE {unread_cond}")
        else:
            cursor.execute("DELETE FROM alert_events")
        conn.commit()
        try:
            st.cache_data.clear()
        except Exception:
            pass
        success = True
    except Exception as e:
        logger.error(f"Error in dismiss_all_alerts: {e}")
    finally:
        cursor.close()
        conn.close()
    return success

def get_unread_alert_count(ticker: str = None) -> int:
    """Returns the total number of unread alerts."""
    init_db()
    conn = get_db_connection()
    cursor = conn.cursor()
    supabase_url = get_supabase_url()
    placeholder = get_placeholder()
    count = 0
    try:
        unread_cond = "is_read = FALSE" if supabase_url else "is_read = 0"
        if ticker:
            clean = clean_ticker(ticker)
            cursor.execute(f"SELECT COUNT(*) FROM alert_events WHERE {unread_cond} AND ticker = {placeholder}", (clean,))
        else:
            cursor.execute(f"SELECT COUNT(*) FROM alert_events WHERE {unread_cond}")
        row = cursor.fetchone()
        if row:
            count = row[0]
    except Exception:
        pass
    finally:
        cursor.close()
        conn.close()
    return count

def record_usage_event(
    event_type: str,
    ticker: str = "",
    latency_ms: float = 0.0,
    cost_saved_usd: float = 0.0,
    details: dict = None,
    session_id: str = None,
    traffic_source: str = None,
    referrer: str = None,
    country: str = None,
    device_type: str = None,
    browser: str = None,
    os: str = None
):
    """
    Records a telemetry event for backend site usage measurement.
    Non-blocking: catches exceptions gracefully so app operations never fail if telemetry is unavailable.
    """
    try:
        init_db()
        conn = get_db_connection()
        cursor = conn.cursor()
        placeholder = get_placeholder()
        clean_t = clean_ticker(ticker) if ticker else ""
        details_json = json.dumps(details or {})
        try:
            query = f'''
                INSERT INTO site_usage_events (
                    event_type, ticker, latency_ms, cost_saved_usd, details,
                    session_id, traffic_source, referrer, country, device_type, browser, os
                )
                VALUES ({placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder},
                        {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder})
            '''
            cursor.execute(query, (
                event_type, clean_t, latency_ms, cost_saved_usd, details_json,
                session_id, traffic_source, referrer, country, device_type, browser, os
            ))
        except Exception:
            # Fallback for earlier schema if columns not yet committed
            query_fallback = f'''
                INSERT INTO site_usage_events (event_type, ticker, latency_ms, cost_saved_usd, details)
                VALUES ({placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder})
            '''
            cursor.execute(query_fallback, (event_type, clean_t, latency_ms, cost_saved_usd, details_json))
        conn.commit()
    except Exception as e:
        logger.debug(f"Telemetry recording notice: {e}")
    finally:
        try:
            cursor.close()
            conn.close()
        except Exception:
            pass

def _build_telemetry_time_filter(supabase_url: str, days: int = None, start_date = None, end_date = None) -> str:
    """Constructs dynamic SQL WHERE clause for relative days or exact start/end date ranges."""
    if start_date and end_date:
        s_str = start_date.strftime("%Y-%m-%d") if hasattr(start_date, "strftime") else str(start_date)[:10]
        e_str = end_date.strftime("%Y-%m-%d") if hasattr(end_date, "strftime") else str(end_date)[:10]
        if supabase_url:
            return f"timestamp >= '{s_str} 00:00:00+05:30' AND timestamp <= '{e_str} 23:59:59+05:30'"
        else:
            return f"timestamp >= '{s_str} 00:00:00' AND timestamp <= '{e_str} 23:59:59'"
    
    num_days = days if days is not None else 30
    if supabase_url:
        return f"timestamp >= NOW() - INTERVAL '{num_days} days'"
    else:
        return f"timestamp >= datetime('now', '-{num_days} days')"

def get_site_usage_summary(days: int = None, start_date = None, end_date = None) -> dict:
    """Aggregates backend usage analytics, visitor origins, demographics, and credit savings across a selectable date range."""
    init_db()
    conn = get_db_connection()
    cursor = conn.cursor()
    supabase_url = get_supabase_url()
    
    summary = {
        "unique_sessions": 0,
        "total_actions": 0,
        "total_queries": 0,
        "cache_hits": 0,
        "surgical_refreshes": 0,
        "full_syntheses": 0,
        "cache_efficiency_pct": 0.0,
        "total_cost_saved_usd": 0.0,
        "pdf_downloads": 0,
        "comparisons": 0,
        "watchlist_actions": 0,
        "action_breakdown": {},
        "top_searched_tickers": [],
        "traffic_sources": [],
        "top_referrers": [],
        "geographic_distribution": [],
        "device_breakdown": [],
        "browser_breakdown": [],
        "os_breakdown": [],
        "recent_events": [],
    }
    try:
        time_filter = _build_telemetry_time_filter(supabase_url, days=days, start_date=start_date, end_date=end_date)

        # 1. Total Events & Cost Savings by Event Type
        cursor.execute(f'''
            SELECT event_type, COUNT(*), COALESCE(SUM(cost_saved_usd), 0.0)
            FROM site_usage_events
            WHERE {time_filter}
            GROUP BY event_type
        ''')
        for row in cursor.fetchall():
            ev, count, saved = row[0], int(row[1]), float(row[2])
            summary["action_breakdown"][ev] = count
            summary["total_actions"] += count
            summary["total_cost_saved_usd"] += saved
            if ev in ["SEARCH", "QUERY", "SEARCH_QUERY"]:
                summary["total_queries"] += count
            elif ev == "CACHE_HIT":
                summary["cache_hits"] += count
            elif ev == "SURGICAL_REFRESH":
                summary["surgical_refreshes"] += count
            elif ev == "FULL_SYNTHESIS":
                summary["full_syntheses"] += count
            elif ev == "PDF_DOWNLOAD":
                summary["pdf_downloads"] += count
            elif ev in ["COMPARE", "COMPARE_STOCKS", "PEER_COMPARISON"]:
                summary["comparisons"] += count
            elif ev in ["WATCHLIST_ADD", "WATCHLIST_REMOVE", "WATCHLIST"]:
                summary["watchlist_actions"] += count

        effective_searches = max(summary["total_queries"], summary["cache_hits"] + summary["full_syntheses"] + summary["surgical_refreshes"])
        summary["total_queries"] = effective_searches
        if effective_searches > 0:
            free_served = summary["cache_hits"] + summary["surgical_refreshes"]
            summary["cache_efficiency_pct"] = round((free_served / effective_searches) * 100.0, 1)

        # 2. Unique Visitor Sessions
        try:
            cursor.execute(f'''
                SELECT COUNT(DISTINCT session_id)
                FROM site_usage_events
                WHERE {time_filter} AND session_id IS NOT NULL AND session_id != ''
            ''')
            row = cursor.fetchone()
            summary["unique_sessions"] = int(row[0]) if row and row[0] is not None else max(1, summary["total_actions"] // 4)
        except Exception:
            summary["unique_sessions"] = max(1, summary["total_actions"] // 4)

        # 3. Top Searched Equities
        cursor.execute(f'''
            SELECT ticker, COUNT(*) as cnt
            FROM site_usage_events
            WHERE {time_filter} AND ticker IS NOT NULL AND ticker != '' AND ticker != 'APP'
            GROUP BY ticker
            ORDER BY cnt DESC
            LIMIT 8
        ''')
        summary["top_searched_tickers"] = [{"ticker": row[0], "count": int(row[1])} for row in cursor.fetchall()]

        # 4. Traffic Sources ("Where they are coming from")
        try:
            cursor.execute(f'''
                SELECT COALESCE(traffic_source, 'Direct / Bookmark'), COUNT(*) as cnt
                FROM site_usage_events
                WHERE {time_filter}
                GROUP BY COALESCE(traffic_source, 'Direct / Bookmark')
                ORDER BY cnt DESC
                LIMIT 8
            ''')
            src_rows = cursor.fetchall()
            total_src = sum(r[1] for r in src_rows) or 1
            summary["traffic_sources"] = [
                {"source": row[0], "count": int(row[1]), "pct": round((row[1] / total_src) * 100.0, 1)}
                for row in src_rows
            ]
        except Exception:
            summary["traffic_sources"] = [{"source": "Direct / Bookmark", "count": summary["total_actions"], "pct": 100.0}]

        # 5. Top Referring URLs
        try:
            cursor.execute(f'''
                SELECT referrer, COUNT(*) as cnt
                FROM site_usage_events
                WHERE {time_filter} AND referrer IS NOT NULL AND referrer != '' AND referrer != 'Direct'
                GROUP BY referrer
                ORDER BY cnt DESC
                LIMIT 8
            ''')
            summary["top_referrers"] = [{"referrer": row[0], "count": int(row[1])} for row in cursor.fetchall()]
        except Exception:
            summary["top_referrers"] = []

        # 6. Geographic Distribution (Countries)
        try:
            cursor.execute(f'''
                SELECT COALESCE(country, 'IN'), COUNT(*) as cnt
                FROM site_usage_events
                WHERE {time_filter}
                GROUP BY COALESCE(country, 'IN')
                ORDER BY cnt DESC
                LIMIT 8
            ''')
            summary["geographic_distribution"] = [{"country": row[0], "count": int(row[1])} for row in cursor.fetchall()]
        except Exception:
            summary["geographic_distribution"] = [{"country": "IN", "count": summary["total_actions"]}]

        # 7. Device Types, Browsers, and OS
        try:
            cursor.execute(f'''
                SELECT COALESCE(device_type, 'Desktop'), COUNT(*) as cnt
                FROM site_usage_events
                WHERE {time_filter}
                GROUP BY COALESCE(device_type, 'Desktop')
                ORDER BY cnt DESC
            ''')
            summary["device_breakdown"] = [{"device": row[0], "count": int(row[1])} for row in cursor.fetchall()]

            cursor.execute(f'''
                SELECT COALESCE(browser, 'Chrome'), COUNT(*) as cnt
                FROM site_usage_events
                WHERE {time_filter}
                GROUP BY COALESCE(browser, 'Chrome')
                ORDER BY cnt DESC
                LIMIT 6
            ''')
            summary["browser_breakdown"] = [{"browser": row[0], "count": int(row[1])} for row in cursor.fetchall()]

            cursor.execute(f'''
                SELECT COALESCE(os, 'macOS'), COUNT(*) as cnt
                FROM site_usage_events
                WHERE {time_filter}
                GROUP BY COALESCE(os, 'macOS')
                ORDER BY cnt DESC
                LIMIT 6
            ''')
            summary["os_breakdown"] = [{"os": row[0], "count": int(row[1])} for row in cursor.fetchall()]
        except Exception:
            pass

        # 8. Recent Audit Events
        try:
            cursor.execute(f'''
                SELECT event_type, ticker, latency_ms, cost_saved_usd, timestamp,
                       COALESCE(session_id, '-'), COALESCE(traffic_source, 'Direct'),
                       COALESCE(country, 'IN'), COALESCE(device_type, 'Desktop')
                FROM site_usage_events
                ORDER BY timestamp DESC
                LIMIT 50
            ''')
            for row in cursor.fetchall():
                summary["recent_events"].append({
                    "event_type": row[0],
                    "ticker": row[1] or "-",
                    "latency_ms": round(float(row[2] or 0), 1),
                    "cost_saved_usd": round(float(row[3] or 0), 3),
                    "formatted_time": _format_timestamp(row[4]),
                    "session_id": str(row[5])[:10],
                    "source": row[6],
                    "country": row[7],
                    "device": row[8],
                })
        except Exception:
            # Fallback if new columns not yet queried
            cursor.execute(f'''
                SELECT event_type, ticker, latency_ms, cost_saved_usd, timestamp
                FROM site_usage_events
                ORDER BY timestamp DESC
                LIMIT 20
            ''')
            for row in cursor.fetchall():
                summary["recent_events"].append({
                    "event_type": row[0],
                    "ticker": row[1] or "-",
                    "latency_ms": round(float(row[2] or 0), 1),
                    "cost_saved_usd": round(float(row[3] or 0), 3),
                    "formatted_time": _format_timestamp(row[4]),
                    "session_id": "-",
                    "source": "Direct",
                    "country": "IN",
                    "device": "Desktop",
                })
    except Exception as e:
        logger.error(f"Error fetching site usage summary: {e}")
    finally:
        cursor.close()
        conn.close()
    return summary

def get_session_journeys(days: int = None, start_date = None, end_date = None, limit: int = 25) -> list:
    """Reconstructs chronological user journeys grouped by session ID across a selectable date range."""
    init_db()
    conn = get_db_connection()
    cursor = conn.cursor()
    supabase_url = get_supabase_url()
    journeys = []
    try:
        time_filter = _build_telemetry_time_filter(supabase_url, days=days, start_date=start_date, end_date=end_date)

        cursor.execute(f'''
            SELECT session_id,
                   MIN(timestamp) as session_start,
                   MAX(traffic_source) as source,
                   MAX(referrer) as ref,
                   MAX(country) as country,
                   MAX(device_type) as device,
                   MAX(browser) as browser,
                   COUNT(*) as action_count
            FROM site_usage_events
            WHERE {time_filter} AND session_id IS NOT NULL AND session_id != ''
            GROUP BY session_id
            ORDER BY session_start DESC
            LIMIT {limit}
        ''')
        sessions = cursor.fetchall()
        placeholder = get_placeholder()
        for s in sessions:
            sess_id, start_ts, source, ref, country, device, browser, count = s
            cursor.execute(f'''
                SELECT event_type, ticker, timestamp
                FROM site_usage_events
                WHERE session_id = {placeholder}
                ORDER BY timestamp ASC
            ''', (sess_id,))
            events = []
            for ev in cursor.fetchall():
                ev_type, ev_ticker, ev_ts = ev
                events.append({
                    "event_type": ev_type,
                    "ticker": ev_ticker or "",
                    "timestamp": _format_timestamp(ev_ts)
                })
            journeys.append({
                "session_id": sess_id,
                "start_time": _format_timestamp(start_ts),
                "traffic_source": source or "Direct / Bookmark",
                "referrer": ref or "Direct",
                "country": country or "IN",
                "device_type": device or "Desktop",
                "browser": browser or "Unknown",
                "action_count": count,
                "events": events
            })
    except Exception as e:
        logger.error(f"Error fetching session journeys: {e}")
    finally:
        cursor.close()
        conn.close()
    return journeys

def get_system_setting(key: str, default: str | None = None) -> str | None:
    """Retrieve a persisted system setting from PostgreSQL/SQLite."""
    init_db()
    conn = get_db_connection()
    cursor = conn.cursor()
    placeholder = get_placeholder()
    try:
        cursor.execute(f"SELECT value FROM system_settings WHERE key = {placeholder};", (key,))
        row = cursor.fetchone()
        if row and row[0] is not None:
            return str(row[0])
        return default
    except Exception as e:
        logger.error(f"Error fetching system setting '{key}': {e}")
        return default
    finally:
        cursor.close()
        conn.close()

def set_system_setting(key: str, value: str) -> bool:
    """Upsert a persisted system setting in PostgreSQL/SQLite."""
    init_db()
    conn = get_db_connection()
    cursor = conn.cursor()
    supabase_url = get_supabase_url()
    placeholder = get_placeholder()
    try:
        if supabase_url:
            cursor.execute(
                f"""
                INSERT INTO system_settings (key, value, updated_at)
                VALUES ({placeholder}, {placeholder}, CURRENT_TIMESTAMP)
                ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = CURRENT_TIMESTAMP;
                """,
                (key, value)
            )
        else:
            cursor.execute(
                f"""
                INSERT INTO system_settings (key, value, updated_at)
                VALUES ({placeholder}, {placeholder}, CURRENT_TIMESTAMP)
                ON CONFLICT (key) DO UPDATE SET value = excluded.value, updated_at = CURRENT_TIMESTAMP;
                """,
                (key, value)
            )
        conn.commit()
        return True
    except Exception as e:
        logger.error(f"Error persisting system setting '{key}': {e}")
        try:
            conn.rollback()
        except Exception:
            pass
        return False
    finally:
        cursor.close()
        conn.close()

