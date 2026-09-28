import hashlib
import logging
import os
import threading
from datetime import datetime, timezone, timedelta
import streamlit as st

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
    supabase_url = st.secrets.get("SUPABASE_DB_URL") or os.environ.get("SUPABASE_DB_URL")
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

    conn = get_db_connection()
    cursor = conn.cursor()
    supabase_url = st.secrets.get("SUPABASE_DB_URL") or os.environ.get("SUPABASE_DB_URL")
    
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

        _DB_INITIALIZED = True
    except Exception as e:
        logger.error(f"Error during init_db migrations: {e}")
        raise
    finally:
        cursor.close()
        conn.close()

def save_report_to_archive(stock_data: dict, report_text: str, announcement: str = "", revision_trigger: str = ""):
    init_db()
    conn = get_db_connection()
    cursor = conn.cursor()
    supabase_url = st.secrets.get("SUPABASE_DB_URL") or os.environ.get("SUPABASE_DB_URL")
    placeholder = "%s" if supabase_url else "?"
    
    clean_ticker = str(stock_data.get("ticker", "")).strip().upper().replace(".NS", "").replace(".BO", "")
    short_name = stock_data.get("short_name") or clean_ticker

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

    try:
        # 1. Update/Upsert the current snapshot in 'reports'
        query_snapshot = f'''
            INSERT INTO reports (ticker, short_name, report_text, baseline_price, baseline_pe, baseline_mcap, latest_announcement)
            VALUES ({placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder})
            ON CONFLICT (ticker) 
            DO UPDATE SET 
                short_name = EXCLUDED.short_name,
                report_text = EXCLUDED.report_text,
                timestamp = CURRENT_TIMESTAMP,
                baseline_price = EXCLUDED.baseline_price,
                baseline_pe = EXCLUDED.baseline_pe,
                baseline_mcap = EXCLUDED.baseline_mcap,
                latest_announcement = EXCLUDED.latest_announcement
        '''
        cursor.execute(query_snapshot, (
            clean_ticker, 
            short_name, 
            report_text,
            curr_price,
            pe,
            mcap,
            announcement
        ))

        # 2. Append-Only Historical Archiving for Differential Tracking Engine
        query_revision = f'''
            INSERT INTO report_revisions (ticker, short_name, report_text, baseline_price, baseline_pe, baseline_mcap, latest_announcement, revision_trigger)
            VALUES ({placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder})
        '''
        cursor.execute(query_revision, (
            clean_ticker,
            short_name,
            report_text,
            curr_price,
            pe,
            mcap,
            announcement,
            revision_trigger or "Material Update"
        ))

        conn.commit()
        try:
            st.cache_data.clear()
        except Exception:
            pass
        # SEBI Compliance: Record statutory Safe Harbor disclaimer audit event
        try:
            log_compliance_event(clean_ticker)
        except Exception as ce:
            logger.error(f"Failed to record SEBI compliance event during archive: {ce}")
    finally:
        cursor.close()
        conn.close()

def log_compliance_event(ticker: str, disclaimer_text: str = None) -> bool:
    """Records a SEBI Safe Harbor disclaimer attachment event in the immutable audit log."""
    init_db()
    conn = get_db_connection()
    cursor = conn.cursor()
    supabase_url = st.secrets.get("SUPABASE_DB_URL") or os.environ.get("SUPABASE_DB_URL")
    placeholder = "%s" if supabase_url else "?"

    clean_ticker = str(ticker).strip().upper().replace(".NS", "").replace(".BO", "")
    target_disclaimer = disclaimer_text or MANDATORY_SEBI_DISCLAIMER
    disclaimer_hash = hashlib.sha256(target_disclaimer.encode("utf-8")).hexdigest()
    disclaimer_version = "SEBI-RA-2024-V1"

    try:
        query = f'''
            INSERT INTO compliance_audit_log (ticker, disclaimer_version, disclaimer_hash)
            VALUES ({placeholder}, {placeholder}, {placeholder})
        '''
        cursor.execute(query, (clean_ticker, disclaimer_version, disclaimer_hash))
        conn.commit()
        logger.info(f"Recorded SEBI compliance audit event for {clean_ticker} (hash={disclaimer_hash[:8]}...)")
        return True
    except Exception as e:
        logger.error(f"Error logging compliance event for {clean_ticker}: {e}")
        return False
    finally:
        cursor.close()
        conn.close()

def get_compliance_audit_logs(ticker: str = None, limit: int = 50) -> list:
    """Retrieves immutable SEBI Safe Harbor compliance audit events."""
    init_db()
    conn = get_db_connection()
    cursor = conn.cursor()
    supabase_url = st.secrets.get("SUPABASE_DB_URL") or os.environ.get("SUPABASE_DB_URL")
    placeholder = "%s" if supabase_url else "?"

    try:
        if ticker:
            clean_ticker = str(ticker).strip().upper().replace(".NS", "").replace(".BO", "")
            query = f'''
                SELECT id, ticker, disclaimer_version, disclaimer_hash, timestamp
                FROM compliance_audit_log
                WHERE ticker = {placeholder}
                ORDER BY timestamp DESC
                LIMIT {placeholder}
            '''
            cursor.execute(query, (clean_ticker, limit))
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
    clean = ticker.strip().upper().replace(".NS", "").replace(".BO", "")
    supabase_url = st.secrets.get("SUPABASE_DB_URL") or os.environ.get("SUPABASE_DB_URL")
    placeholder = "%s" if supabase_url else "?"
    
    record = None
    try:
        cursor.execute(f'''
            SELECT ticker, short_name, report_text, timestamp, baseline_price, baseline_pe, baseline_mcap, latest_announcement
            FROM reports 
            WHERE ticker = {placeholder}
        ''', (clean,))
        row = cursor.fetchone()
        if row:
            record = {
                "ticker": row[0],
                "short_name": row[1] or row[0],
                "report_text": row[2],
                "raw_timestamp": row[3],
                "formatted_date": _format_timestamp(row[3]),
                "baseline_price": row[4],
                "baseline_pe": row[5],
                "baseline_mcap": row[6],
                "latest_announcement": row[7] or ""
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
    clean = ticker.strip().upper().replace(".NS", "").replace(".BO", "")
    supabase_url = st.secrets.get("SUPABASE_DB_URL") or os.environ.get("SUPABASE_DB_URL")
    placeholder = "%s" if supabase_url else "?"
    revisions = []
    try:
        cursor.execute(f'''
            SELECT id, ticker, short_name, report_text, timestamp, baseline_price, baseline_pe, baseline_mcap, latest_announcement, revision_trigger
            FROM report_revisions
            WHERE ticker = {placeholder}
            ORDER BY timestamp DESC
        ''', (clean,))
        rows = cursor.fetchall()
        for row in rows:
            revisions.append({
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
                "revision_trigger": row[9] or "Initial Baseline"
            })

        # Self-healing: Seed initial baseline revision if reports table has a snapshot but revisions table is empty
        if not revisions:
            cursor.execute(f'''
                SELECT ticker, short_name, report_text, timestamp, baseline_price, baseline_pe, baseline_mcap, latest_announcement
                FROM reports
                WHERE ticker = {placeholder}
            ''', (clean,))
            rep_row = cursor.fetchone()
            if rep_row:
                cursor.execute(f'''
                    INSERT INTO report_revisions (ticker, short_name, report_text, timestamp, baseline_price, baseline_pe, baseline_mcap, latest_announcement, revision_trigger)
                    VALUES ({placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder})
                ''', (
                    rep_row[0], rep_row[1], rep_row[2], rep_row[3],
                    rep_row[4], rep_row[5], rep_row[6], rep_row[7],
                    "Archived Baseline"
                ))
                conn.commit()
                cursor.execute(f'''
                    SELECT id, ticker, short_name, report_text, timestamp, baseline_price, baseline_pe, baseline_mcap, latest_announcement, revision_trigger
                    FROM report_revisions
                    WHERE ticker = {placeholder}
                    ORDER BY timestamp DESC
                ''', (clean,))
                for s_row in cursor.fetchall():
                    revisions.append({
                        "id": s_row[0],
                        "ticker": s_row[1],
                        "short_name": s_row[2] or s_row[1],
                        "report_text": s_row[3],
                        "raw_timestamp": s_row[4],
                        "formatted_date": _format_timestamp(s_row[4]),
                        "baseline_price": s_row[5],
                        "baseline_pe": s_row[6],
                        "baseline_mcap": s_row[7],
                        "latest_announcement": s_row[8] or "",
                        "revision_trigger": s_row[9] or "Archived Baseline"
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
    supabase_url = st.secrets.get("SUPABASE_DB_URL") or os.environ.get("SUPABASE_DB_URL")
    placeholder = "%s" if supabase_url else "?"
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
    clean = ticker.strip().upper().replace(".NS", "").replace(".BO", "")
    supabase_url = st.secrets.get("SUPABASE_DB_URL") or os.environ.get("SUPABASE_DB_URL")
    placeholder = "%s" if supabase_url else "?"
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
    clean = ticker.strip().upper().replace(".NS", "").replace(".BO", "")
    supabase_url = st.secrets.get("SUPABASE_DB_URL") or os.environ.get("SUPABASE_DB_URL")
    placeholder = "%s" if supabase_url else "?"
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
    clean = ticker.strip().upper().replace(".NS", "").replace(".BO", "")
    supabase_url = st.secrets.get("SUPABASE_DB_URL") or os.environ.get("SUPABASE_DB_URL")
    placeholder = "%s" if supabase_url else "?"
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
    clean = ticker.strip().upper().replace(".NS", "").replace(".BO", "")
    supabase_url = st.secrets.get("SUPABASE_DB_URL") or os.environ.get("SUPABASE_DB_URL")
    placeholder = "%s" if supabase_url else "?"
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
    clean = ticker.strip().upper().replace(".NS", "").replace(".BO", "")
    supabase_url = st.secrets.get("SUPABASE_DB_URL") or os.environ.get("SUPABASE_DB_URL")
    placeholder = "%s" if supabase_url else "?"
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
    supabase_url = st.secrets.get("SUPABASE_DB_URL") or os.environ.get("SUPABASE_DB_URL")
    placeholder = "%s" if supabase_url else "?"
    alerts = []
    try:
        conditions = []
        params = []
        if ticker:
            clean = ticker.strip().upper().replace(".NS", "").replace(".BO", "")
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
            LIMIT {limit}
        '''
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
    supabase_url = st.secrets.get("SUPABASE_DB_URL") or os.environ.get("SUPABASE_DB_URL")
    placeholder = "%s" if supabase_url else "?"
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
    supabase_url = st.secrets.get("SUPABASE_DB_URL") or os.environ.get("SUPABASE_DB_URL")
    placeholder = "%s" if supabase_url else "?"
    try:
        val = "TRUE" if supabase_url else "1"
        if ticker:
            clean = ticker.strip().upper().replace(".NS", "").replace(".BO", "")
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
    supabase_url = st.secrets.get("SUPABASE_DB_URL") or os.environ.get("SUPABASE_DB_URL")
    placeholder = "%s" if supabase_url else "?"
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
    supabase_url = st.secrets.get("SUPABASE_DB_URL") or os.environ.get("SUPABASE_DB_URL")
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
    supabase_url = st.secrets.get("SUPABASE_DB_URL") or os.environ.get("SUPABASE_DB_URL")
    placeholder = "%s" if supabase_url else "?"
    count = 0
    try:
        unread_cond = "is_read = FALSE" if supabase_url else "is_read = 0"
        if ticker:
            clean = ticker.strip().upper().replace(".NS", "").replace(".BO", "")
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
