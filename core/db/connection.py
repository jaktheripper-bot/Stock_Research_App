"""Database connection, connection pooling, and schema migration engine."""

import logging
import os
import threading
from datetime import timezone, timedelta
from core.config import get_secret

IST = timezone(timedelta(hours=5, minutes=30))
logger = logging.getLogger("equity_research.core.db.connection")

_DB_INITIALIZED = False
_DB_INIT_LOCK = threading.Lock()

_CACHED_SUPABASE_URL = None
_SUPABASE_URL_RESOLVED = False

def get_supabase_url() -> str | None:
    """Returns configured Supabase DB URL, cached in memory after first resolution."""
    global _CACHED_SUPABASE_URL, _SUPABASE_URL_RESOLVED
    if not _SUPABASE_URL_RESOLVED:
        url = get_secret("SUPABASE_DB_URL")
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

_PG_POOLS = {}
_PG_POOL_LOCK = threading.Lock()

def _get_pg_pool(dsn: str):
    """Thread-safe singleton ThreadedConnectionPool without Streamlit runtime dependency."""
    global _PG_POOLS
    if dsn not in _PG_POOLS:
        with _PG_POOL_LOCK:
            if dsn not in _PG_POOLS:
                import psycopg2.pool
                # Enable TCP keepalive to improve connection reliability
                _PG_POOLS[dsn] = psycopg2.pool.ThreadedConnectionPool(
                    minconn=1,
                    maxconn=300,
                    dsn=dsn,
                    keepalives=1,
                    keepalives_idle=30,
                    keepalives_interval=10,
                    keepalives_count=5,
                )
    return _PG_POOLS[dsn]

def _acquire_connection_from_pool(pool):
    for attempt in range(5):
        conn = None
        try:
            conn = pool.getconn()
            if conn.closed != 0:
                try:
                    pool.putconn(conn, close=True)
                except Exception:
                    pass
                continue
            with conn.cursor() as cur:
                cur.execute("SELECT 1;")
            return conn
        except Exception:
            if conn:
                try:
                    pool.putconn(conn, close=True)
                except Exception:
                    pass
    import psycopg2
    supabase_url = get_supabase_url()
    return psycopg2.connect(supabase_url)

def get_db_connection():
    """Returns a pooled PostgreSQL connection or WAL-mode SQLite fallback connection."""
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
    """Initializes tables and executes incremental schema migrations (v001 - v007)."""
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
                    for col, col_type in [("baseline_price", "NUMERIC"), ("baseline_pe", "TEXT"), ("baseline_mcap", "NUMERIC"), ("latest_announcement", "TEXT")]:
                        cursor.execute(f"ALTER TABLE reports ADD COLUMN IF NOT EXISTS {col} {col_type};")

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
                    cursor.execute("PRAGMA table_info(reports);")
                    existing_cols = [c[1] for c in cursor.fetchall()]
                    for col, col_type in [("baseline_price", "REAL"), ("baseline_pe", "TEXT"), ("baseline_mcap", "REAL"), ("latest_announcement", "TEXT")]:
                        if col not in existing_cols:
                            try:
                                cursor.execute(f"ALTER TABLE reports ADD COLUMN {col} {col_type};")
                            except Exception:
                                pass

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

            # Migration v007: User Accounts, Credits, Transactions & Usage Ledger
            if "v007_user_accounts_and_credits" not in applied:
                logger.info("Applying schema migration: v007_user_accounts_and_credits...")
                if supabase_url:
                    cursor.execute('''
                        CREATE TABLE IF NOT EXISTS user_accounts (
                            id TEXT PRIMARY KEY,
                            email TEXT UNIQUE NOT NULL,
                            full_name TEXT,
                            avatar_url TEXT,
                            credits_balance NUMERIC DEFAULT 2.0,
                            subscription_tier TEXT DEFAULT 'free',
                            subscription_expires_at TIMESTAMPTZ,
                            created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
                            last_login_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
                        );
                    ''')
                    cursor.execute('CREATE INDEX IF NOT EXISTS idx_user_accounts_email ON user_accounts (email);')

                    cursor.execute('''
                        CREATE TABLE IF NOT EXISTS credit_transactions (
                            id TEXT PRIMARY KEY,
                            user_id TEXT NOT NULL,
                            amount_inr NUMERIC NOT NULL,
                            credits_added NUMERIC NOT NULL,
                            payment_gateway TEXT DEFAULT 'razorpay',
                            gateway_order_id TEXT,
                            gateway_payment_id TEXT,
                            status TEXT DEFAULT 'success',
                            pack_type TEXT NOT NULL,
                            invoice_number TEXT,
                            created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
                        );
                    ''')
                    cursor.execute('CREATE INDEX IF NOT EXISTS idx_credit_transactions_user ON credit_transactions (user_id, created_at DESC);')

                    cursor.execute('''
                        CREATE TABLE IF NOT EXISTS credit_usage_ledger (
                            id SERIAL PRIMARY KEY,
                            user_id TEXT NOT NULL,
                            ticker TEXT NOT NULL,
                            action_type TEXT NOT NULL,
                            credits_consumed NUMERIC NOT NULL,
                            balance_after NUMERIC NOT NULL,
                            created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
                        );
                    ''')
                    cursor.execute('CREATE INDEX IF NOT EXISTS idx_credit_usage_user ON credit_usage_ledger (user_id, created_at DESC);')
                    cursor.execute('CREATE INDEX IF NOT EXISTS idx_credit_usage_ticker ON credit_usage_ledger (ticker, created_at DESC);')
                    cursor.execute("INSERT INTO schema_migrations (version) VALUES ('v007_user_accounts_and_credits') ON CONFLICT DO NOTHING;")
                else:
                    cursor.execute('''
                        CREATE TABLE IF NOT EXISTS user_accounts (
                            id TEXT PRIMARY KEY,
                            email TEXT UNIQUE NOT NULL,
                            full_name TEXT,
                            avatar_url TEXT,
                            credits_balance REAL DEFAULT 2.0,
                            subscription_tier TEXT DEFAULT 'free',
                            subscription_expires_at DATETIME,
                            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                            last_login_at DATETIME DEFAULT CURRENT_TIMESTAMP
                        );
                    ''')
                    cursor.execute('CREATE INDEX IF NOT EXISTS idx_user_accounts_email ON user_accounts (email);')

                    cursor.execute('''
                        CREATE TABLE IF NOT EXISTS credit_transactions (
                            id TEXT PRIMARY KEY,
                            user_id TEXT NOT NULL,
                            amount_inr REAL NOT NULL,
                            credits_added REAL NOT NULL,
                            payment_gateway TEXT DEFAULT 'razorpay',
                            gateway_order_id TEXT,
                            gateway_payment_id TEXT,
                            status TEXT DEFAULT 'success',
                            pack_type TEXT NOT NULL,
                            invoice_number TEXT,
                            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                        );
                    ''')
                    cursor.execute('CREATE INDEX IF NOT EXISTS idx_credit_transactions_user ON credit_transactions (user_id, created_at DESC);')

                    cursor.execute('''
                        CREATE TABLE IF NOT EXISTS credit_usage_ledger (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            user_id TEXT NOT NULL,
                            ticker TEXT NOT NULL,
                            action_type TEXT NOT NULL,
                            credits_consumed REAL NOT NULL,
                            balance_after REAL NOT NULL,
                            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                        );
                    ''')
                    cursor.execute('CREATE INDEX IF NOT EXISTS idx_credit_usage_user ON credit_usage_ledger (user_id, created_at DESC);')
                    cursor.execute('CREATE INDEX IF NOT EXISTS idx_credit_usage_ticker ON credit_usage_ledger (ticker, created_at DESC);')
                    cursor.execute("INSERT OR IGNORE INTO schema_migrations (version) VALUES ('v007_user_accounts_and_credits');")
                conn.commit()

            # Migration v008: Morning Discovery Reel & Under-the-Radar Cohort
            if "v008_discovery_reel" not in applied:
                logger.info("Applying schema migration: v008_discovery_reel...")
                if supabase_url:
                    cursor.execute('''
                        CREATE TABLE IF NOT EXISTS discovery_reel (
                            id SERIAL PRIMARY KEY,
                            edition_date DATE NOT NULL,
                            ticker TEXT NOT NULL,
                            company_name TEXT NOT NULL,
                            sector TEXT NOT NULL,
                            market_cap_tier TEXT DEFAULT 'Small-Cap',
                            current_price NUMERIC,
                            pe_ratio TEXT,
                            roce_pct NUMERIC,
                            debt_to_equity NUMERIC,
                            sales_growth_3y NUMERIC,
                            ria_thesis TEXT NOT NULL,
                            catalyst_headline TEXT,
                            key_metrics_json TEXT,
                            is_active BOOLEAN DEFAULT TRUE,
                            created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
                        );
                    ''')
                    cursor.execute('CREATE INDEX IF NOT EXISTS idx_discovery_reel_edition ON discovery_reel (edition_date, is_active);')
                    cursor.execute('CREATE INDEX IF NOT EXISTS idx_discovery_reel_ticker ON discovery_reel (ticker);')
                    cursor.execute("INSERT INTO schema_migrations (version) VALUES ('v008_discovery_reel') ON CONFLICT DO NOTHING;")
                else:
                    cursor.execute('''
                        CREATE TABLE IF NOT EXISTS discovery_reel (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            edition_date TEXT NOT NULL,
                            ticker TEXT NOT NULL,
                            company_name TEXT NOT NULL,
                            sector TEXT NOT NULL,
                            market_cap_tier TEXT DEFAULT 'Small-Cap',
                            current_price REAL,
                            pe_ratio TEXT,
                            roce_pct REAL,
                            debt_to_equity REAL,
                            sales_growth_3y REAL,
                            ria_thesis TEXT NOT NULL,
                            catalyst_headline TEXT,
                            key_metrics_json TEXT,
                            is_active INTEGER DEFAULT 1,
                            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                        );
                    ''')
                    cursor.execute('CREATE INDEX IF NOT EXISTS idx_discovery_reel_edition ON discovery_reel (edition_date, is_active);')
                    cursor.execute('CREATE INDEX IF NOT EXISTS idx_discovery_reel_ticker ON discovery_reel (ticker);')
                    cursor.execute("INSERT OR IGNORE INTO schema_migrations (version) VALUES ('v008_discovery_reel');")
                conn.commit()

            # Migration v009: Support Tickets, User Grievances & Redressal Ledger
            if "v009_support_tickets_and_feedback" not in applied:
                logger.info("Applying schema migration: v009_support_tickets_and_feedback...")
                if supabase_url:
                    cursor.execute('''
                        CREATE TABLE IF NOT EXISTS support_tickets (
                            id SERIAL PRIMARY KEY,
                            ticket_id TEXT UNIQUE NOT NULL,
                            user_email TEXT NOT NULL,
                            user_name TEXT,
                            category TEXT NOT NULL DEFAULT 'general',
                            subject TEXT NOT NULL,
                            message TEXT NOT NULL,
                            status TEXT NOT NULL DEFAULT 'open',
                            admin_notes TEXT,
                            source TEXT DEFAULT 'web_contact',
                            created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
                            updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
                        );
                    ''')
                    cursor.execute('CREATE INDEX IF NOT EXISTS idx_support_tickets_status ON support_tickets (status, created_at DESC);')
                    cursor.execute('CREATE INDEX IF NOT EXISTS idx_support_tickets_email ON support_tickets (user_email);')
                    cursor.execute("INSERT INTO schema_migrations (version) VALUES ('v009_support_tickets_and_feedback') ON CONFLICT DO NOTHING;")
                else:
                    cursor.execute('''
                        CREATE TABLE IF NOT EXISTS support_tickets (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            ticket_id TEXT UNIQUE NOT NULL,
                            user_email TEXT NOT NULL,
                            user_name TEXT,
                            category TEXT NOT NULL DEFAULT 'general',
                            subject TEXT NOT NULL,
                            message TEXT NOT NULL,
                            status TEXT NOT NULL DEFAULT 'open',
                            admin_notes TEXT,
                            source TEXT DEFAULT 'web_contact',
                            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
                        );
                    ''')
                    cursor.execute('CREATE INDEX IF NOT EXISTS idx_support_tickets_status ON support_tickets (status, created_at DESC);')
                    cursor.execute('CREATE INDEX IF NOT EXISTS idx_support_tickets_email ON support_tickets (user_email);')
            # Migration v010: User Usage Attribution & Billables Audit Ledger
            if "v010_user_usage_and_billables_audit" not in applied:
                logger.info("Applying schema migration: v010_user_usage_and_billables_audit...")
                if supabase_url:
                    cursor.execute('''
                        ALTER TABLE site_usage_events ADD COLUMN IF NOT EXISTS user_id VARCHAR(64);
                        ALTER TABLE site_usage_events ADD COLUMN IF NOT EXISTS user_email VARCHAR(255);
                        CREATE INDEX IF NOT EXISTS idx_site_usage_user ON site_usage_events (user_id, timestamp DESC);
                        CREATE INDEX IF NOT EXISTS idx_site_usage_email ON site_usage_events (user_email, timestamp DESC);

                        ALTER TABLE credit_transactions ADD COLUMN IF NOT EXISTS customer_email TEXT;
                        ALTER TABLE credit_transactions ADD COLUMN IF NOT EXISTS customer_name TEXT;
                        ALTER TABLE credit_transactions ADD COLUMN IF NOT EXISTS base_amount_inr NUMERIC DEFAULT 0.0;
                        ALTER TABLE credit_transactions ADD COLUMN IF NOT EXISTS tax_gst_inr NUMERIC DEFAULT 0.0;
                        ALTER TABLE credit_transactions ADD COLUMN IF NOT EXISTS sac_code TEXT DEFAULT '998314';
                        ALTER TABLE credit_transactions ADD COLUMN IF NOT EXISTS refund_amount_inr NUMERIC DEFAULT 0.0;
                        ALTER TABLE credit_transactions ADD COLUMN IF NOT EXISTS refund_reason TEXT;
                        ALTER TABLE credit_transactions ADD COLUMN IF NOT EXISTS gateway_refund_id TEXT;
                        ALTER TABLE credit_transactions ADD COLUMN IF NOT EXISTS refunded_at TIMESTAMPTZ;
                        CREATE INDEX IF NOT EXISTS idx_credit_transactions_status ON credit_transactions (status, created_at DESC);
                        CREATE INDEX IF NOT EXISTS idx_credit_transactions_invoice ON credit_transactions (invoice_number);
                        INSERT INTO schema_migrations (version) VALUES ('v010_user_usage_and_billables_audit') ON CONFLICT DO NOTHING;
                    ''')
                else:
                    # SQLite alter table columns wrapped safely
                    for col_def in [
                        ("site_usage_events", "user_id TEXT"),
                        ("site_usage_events", "user_email TEXT"),
                        ("credit_transactions", "customer_email TEXT"),
                        ("credit_transactions", "customer_name TEXT"),
                        ("credit_transactions", "base_amount_inr REAL DEFAULT 0.0"),
                        ("credit_transactions", "tax_gst_inr REAL DEFAULT 0.0"),
                        ("credit_transactions", "sac_code TEXT DEFAULT '998314'"),
                        ("credit_transactions", "refund_amount_inr REAL DEFAULT 0.0"),
                        ("credit_transactions", "refund_reason TEXT"),
                        ("credit_transactions", "gateway_refund_id TEXT"),
                        ("credit_transactions", "refunded_at DATETIME"),
                    ]:
                        try:
                            cursor.execute(f"ALTER TABLE {col_def[0]} ADD COLUMN {col_def[1]};")
                        except Exception:
                            pass
                    try:
                        cursor.execute("CREATE INDEX IF NOT EXISTS idx_site_usage_user ON site_usage_events (user_id, timestamp DESC);")
                        cursor.execute("CREATE INDEX IF NOT EXISTS idx_site_usage_email ON site_usage_events (user_email, timestamp DESC);")
                        cursor.execute("CREATE INDEX IF NOT EXISTS idx_credit_transactions_status ON credit_transactions (status, created_at DESC);")
                        cursor.execute("CREATE INDEX IF NOT EXISTS idx_credit_transactions_invoice ON credit_transactions (invoice_number);")
                    except Exception:
                        pass
                    cursor.execute("INSERT OR IGNORE INTO schema_migrations (version) VALUES ('v010_user_usage_and_billables_audit');")
                conn.commit()

            # Migration v011: MSME Firms table
            if "v011_msme_firms" not in applied:
                logger.info("Applying schema migration: v011_msme_firms...")
                if supabase_url:
                    cursor.execute("""
                        CREATE TABLE IF NOT EXISTS msme_firms (
                            uin VARCHAR PRIMARY KEY,
                            name TEXT NOT NULL,
                            sector_code VARCHAR,
                            sector_name TEXT,
                            city TEXT,
                            state TEXT,
                            annual_turnover NUMERIC,
                            employee_count INTEGER,
                            registration_date DATE,
                            source VARCHAR NOT NULL,
                            last_updated TIMESTAMPTZ DEFAULT now()
                        );
                        CREATE INDEX IF NOT EXISTS idx_msme_sector ON msme_firms(sector_name);
                        CREATE INDEX IF NOT EXISTS idx_msme_state ON msme_firms(state);
                        INSERT INTO schema_migrations (version) VALUES ('v011_msme_firms') ON CONFLICT DO NOTHING;
                    """)
                else:
                    cursor.execute("""
                        CREATE TABLE IF NOT EXISTS msme_firms (
                            uin TEXT PRIMARY KEY,
                            name TEXT NOT NULL,
                            sector_code TEXT,
                            sector_name TEXT,
                            city TEXT,
                            state TEXT,
                            annual_turnover REAL,
                            employee_count INTEGER,
                            registration_date TEXT,
                            source TEXT NOT NULL,
                            last_updated TEXT DEFAULT (datetime('now'))
                        );
                    """)
                    cursor.execute("CREATE INDEX IF NOT EXISTS idx_msme_sector ON msme_firms(sector_name);")
                    cursor.execute("CREATE INDEX IF NOT EXISTS idx_msme_state ON msme_firms(state);")
                    cursor.execute("INSERT OR IGNORE INTO schema_migrations (version) VALUES ('v011_msme_firms');")
                conn.commit()

            # Migration v012: Corporate Debt Securities and Credit Rating Events
            if "v012_corporate_debt_and_credit_ratings" not in applied:
                logger.info("Applying schema migration: v012_corporate_debt_and_credit_ratings...")
                if supabase_url:
                    cursor.execute("""
                        CREATE TABLE IF NOT EXISTS corporate_debt_securities (
                            isin VARCHAR(20) PRIMARY KEY,
                            ticker VARCHAR(50) NOT NULL,
                            scrip_code VARCHAR(20),
                            series VARCHAR(20),
                            instrument_name TEXT NOT NULL,
                            instrument_type VARCHAR(50) NOT NULL,
                            seniority_tier VARCHAR(50) NOT NULL,
                            face_value NUMERIC NOT NULL DEFAULT 10000.0,
                            coupon_rate_pct NUMERIC NOT NULL,
                            coupon_frequency VARCHAR(20) NOT NULL DEFAULT 'ANNUAL',
                            issue_date DATE,
                            maturity_date DATE NOT NULL,
                            credit_rating VARCHAR(50) NOT NULL,
                            credit_rating_agency VARCHAR(50) NOT NULL,
                            asset_cover_ratio NUMERIC DEFAULT 1.0,
                            is_listed BOOLEAN DEFAULT TRUE,
                            exchange VARCHAR(20) DEFAULT 'BSE',
                            is_sdi BOOLEAN DEFAULT FALSE,
                            originator TEXT,
                            fldg_pct NUMERIC DEFAULT 0.0,
                            last_traded_price NUMERIC,
                            ytm_pct NUMERIC,
                            macaulay_duration_years NUMERIC,
                            modified_duration_years NUMERIC,
                            metadata_json TEXT DEFAULT '{}',
                            created_at TIMESTAMPTZ DEFAULT now(),
                            last_updated TIMESTAMPTZ DEFAULT now()
                        );
                        CREATE INDEX IF NOT EXISTS idx_debt_ticker ON corporate_debt_securities(ticker);
                        CREATE INDEX IF NOT EXISTS idx_debt_type ON corporate_debt_securities(instrument_type);
                        CREATE INDEX IF NOT EXISTS idx_debt_seniority ON corporate_debt_securities(seniority_tier);
                        CREATE INDEX IF NOT EXISTS idx_debt_rating ON corporate_debt_securities(credit_rating);

                        CREATE TABLE IF NOT EXISTS credit_rating_events (
                            id SERIAL PRIMARY KEY,
                            isin VARCHAR(20) NOT NULL,
                            ticker VARCHAR(50) NOT NULL,
                            rating_agency VARCHAR(50) NOT NULL,
                            rating_symbol VARCHAR(20) NOT NULL,
                            outlook VARCHAR(30) DEFAULT 'STABLE',
                            action_type VARCHAR(30) NOT NULL,
                            event_date DATE NOT NULL,
                            action_rationale TEXT,
                            created_at TIMESTAMPTZ DEFAULT now()
                        );
                        CREATE INDEX IF NOT EXISTS idx_rating_isin ON credit_rating_events(isin);
                        CREATE INDEX IF NOT EXISTS idx_rating_ticker ON credit_rating_events(ticker);
                        CREATE INDEX IF NOT EXISTS idx_rating_date ON credit_rating_events(event_date);

                        INSERT INTO schema_migrations (version) VALUES ('v012_corporate_debt_and_credit_ratings') ON CONFLICT DO NOTHING;
                    """)
                else:
                    cursor.execute("""
                        CREATE TABLE IF NOT EXISTS corporate_debt_securities (
                            isin TEXT PRIMARY KEY,
                            ticker TEXT NOT NULL,
                            scrip_code TEXT,
                            series TEXT,
                            instrument_name TEXT NOT NULL,
                            instrument_type TEXT NOT NULL,
                            seniority_tier TEXT NOT NULL,
                            face_value REAL NOT NULL DEFAULT 10000.0,
                            coupon_rate_pct REAL NOT NULL,
                            coupon_frequency TEXT NOT NULL DEFAULT 'ANNUAL',
                            issue_date TEXT,
                            maturity_date TEXT NOT NULL,
                            credit_rating TEXT NOT NULL,
                            credit_rating_agency TEXT NOT NULL,
                            asset_cover_ratio REAL DEFAULT 1.0,
                            is_listed INTEGER DEFAULT 1,
                            exchange TEXT DEFAULT 'BSE',
                            is_sdi INTEGER DEFAULT 0,
                            originator TEXT,
                            fldg_pct REAL DEFAULT 0.0,
                            last_traded_price REAL,
                            ytm_pct REAL,
                            macaulay_duration_years REAL,
                            modified_duration_years REAL,
                            metadata_json TEXT DEFAULT '{}',
                            created_at TEXT DEFAULT (datetime('now')),
                            last_updated TEXT DEFAULT (datetime('now'))
                        );
                    """)
                    cursor.execute("CREATE INDEX IF NOT EXISTS idx_debt_ticker ON corporate_debt_securities(ticker);")
                    cursor.execute("CREATE INDEX IF NOT EXISTS idx_debt_type ON corporate_debt_securities(instrument_type);")
                    cursor.execute("CREATE INDEX IF NOT EXISTS idx_debt_seniority ON corporate_debt_securities(seniority_tier);")
                    cursor.execute("CREATE INDEX IF NOT EXISTS idx_debt_rating ON corporate_debt_securities(credit_rating);")

                    cursor.execute("""
                        CREATE TABLE IF NOT EXISTS credit_rating_events (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            isin TEXT NOT NULL,
                            ticker TEXT NOT NULL,
                            rating_agency TEXT NOT NULL,
                            rating_symbol TEXT NOT NULL,
                            outlook TEXT DEFAULT 'STABLE',
                            action_type TEXT NOT NULL,
                            event_date TEXT NOT NULL,
                            action_rationale TEXT,
                            created_at TEXT DEFAULT (datetime('now'))
                        );
                    """)
                    cursor.execute("CREATE INDEX IF NOT EXISTS idx_rating_isin ON credit_rating_events(isin);")
                    cursor.execute("CREATE INDEX IF NOT EXISTS idx_rating_ticker ON credit_rating_events(ticker);")
                    cursor.execute("CREATE INDEX IF NOT EXISTS idx_rating_date ON credit_rating_events(event_date);")
                    cursor.execute("INSERT OR IGNORE INTO schema_migrations (version) VALUES ('v012_corporate_debt_and_credit_ratings');")
                conn.commit()

            # Migration v013: Mutual Fund Schemes and Granular Holdings Portfolio
            if "v013_mutual_fund_schemes_and_portfolios" not in applied:
                logger.info("Applying schema migration: v013_mutual_fund_schemes_and_portfolios...")
                if supabase_url:
                    cursor.execute("""
                        CREATE TABLE IF NOT EXISTS mutual_fund_schemes (
                            scheme_code VARCHAR(50) PRIMARY KEY,
                            scheme_name TEXT NOT NULL,
                            fund_house VARCHAR(100) NOT NULL,
                            category VARCHAR(100) NOT NULL,
                            broad_category VARCHAR(50) NOT NULL,
                            benchmark_index VARCHAR(150) NOT NULL,
                            aum_crores NUMERIC DEFAULT 0.0,
                            nav NUMERIC DEFAULT 0.0,
                            ter_direct_pct NUMERIC DEFAULT 0.0,
                            ter_regular_pct NUMERIC DEFAULT 0.0,
                            portfolio_turnover_ratio_pct NUMERIC DEFAULT 0.0,
                            active_share_pct NUMERIC DEFAULT 0.0,
                            risk_grade VARCHAR(50) DEFAULT 'Very High',
                            fund_manager VARCHAR(150),
                            metadata_json TEXT DEFAULT '{}',
                            last_portfolio_date DATE,
                            created_at TIMESTAMPTZ DEFAULT now(),
                            last_updated TIMESTAMPTZ DEFAULT now()
                        );
                        CREATE INDEX IF NOT EXISTS idx_mf_category ON mutual_fund_schemes(category);
                        CREATE INDEX IF NOT EXISTS idx_mf_broad_category ON mutual_fund_schemes(broad_category);
                        CREATE INDEX IF NOT EXISTS idx_mf_fund_house ON mutual_fund_schemes(fund_house);

                        CREATE TABLE IF NOT EXISTS mutual_fund_holdings (
                            id SERIAL PRIMARY KEY,
                            scheme_code VARCHAR(50) NOT NULL,
                            holding_type VARCHAR(50) NOT NULL,
                            identifier VARCHAR(50) NOT NULL,
                            holding_name TEXT NOT NULL,
                            weight_pct NUMERIC NOT NULL,
                            sector_or_rating VARCHAR(100),
                            instrument_details TEXT DEFAULT '{}',
                            portfolio_date DATE NOT NULL,
                            created_at TIMESTAMPTZ DEFAULT now()
                        );
                        CREATE INDEX IF NOT EXISTS idx_mf_holdings_scheme ON mutual_fund_holdings(scheme_code);
                        CREATE INDEX IF NOT EXISTS idx_mf_holdings_ident ON mutual_fund_holdings(identifier);
                        CREATE INDEX IF NOT EXISTS idx_mf_holdings_type ON mutual_fund_holdings(holding_type);

                        INSERT INTO schema_migrations (version) VALUES ('v013_mutual_fund_schemes_and_portfolios') ON CONFLICT DO NOTHING;
                    """)
                else:
                    cursor.execute("""
                        CREATE TABLE IF NOT EXISTS mutual_fund_schemes (
                            scheme_code TEXT PRIMARY KEY,
                            scheme_name TEXT NOT NULL,
                            fund_house TEXT NOT NULL,
                            category TEXT NOT NULL,
                            broad_category TEXT NOT NULL,
                            benchmark_index TEXT NOT NULL,
                            aum_crores REAL DEFAULT 0.0,
                            nav REAL DEFAULT 0.0,
                            ter_direct_pct REAL DEFAULT 0.0,
                            ter_regular_pct REAL DEFAULT 0.0,
                            portfolio_turnover_ratio_pct REAL DEFAULT 0.0,
                            active_share_pct REAL DEFAULT 0.0,
                            risk_grade TEXT DEFAULT 'Very High',
                            fund_manager TEXT,
                            metadata_json TEXT DEFAULT '{}',
                            last_portfolio_date TEXT,
                            created_at TEXT DEFAULT (datetime('now')),
                            last_updated TEXT DEFAULT (datetime('now'))
                        );
                    """)
                    cursor.execute("CREATE INDEX IF NOT EXISTS idx_mf_category ON mutual_fund_schemes(category);")
                    cursor.execute("CREATE INDEX IF NOT EXISTS idx_mf_broad_category ON mutual_fund_schemes(broad_category);")
                    cursor.execute("CREATE INDEX IF NOT EXISTS idx_mf_fund_house ON mutual_fund_schemes(fund_house);")

                    cursor.execute("""
                        CREATE TABLE IF NOT EXISTS mutual_fund_holdings (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            scheme_code TEXT NOT NULL,
                            holding_type TEXT NOT NULL,
                            identifier TEXT NOT NULL,
                            holding_name TEXT NOT NULL,
                            weight_pct REAL NOT NULL,
                            sector_or_rating TEXT,
                            instrument_details TEXT DEFAULT '{}',
                            portfolio_date TEXT NOT NULL,
                            created_at TEXT DEFAULT (datetime('now'))
                        );
                    """)
                    cursor.execute("CREATE INDEX IF NOT EXISTS idx_mf_holdings_scheme ON mutual_fund_holdings(scheme_code);")
                    cursor.execute("CREATE INDEX IF NOT EXISTS idx_mf_holdings_ident ON mutual_fund_holdings(identifier);")
                    cursor.execute("CREATE INDEX IF NOT EXISTS idx_mf_holdings_type ON mutual_fund_holdings(holding_type);")
                    cursor.execute("INSERT OR IGNORE INTO schema_migrations (version) VALUES ('v013_mutual_fund_schemes_and_portfolios');")
                conn.commit()

            # Migration v014: Administrator Whitelist, Roles & Immutable Audit Trail
            if "v014_admin_users_and_audit_trail" not in applied:
                logger.info("Applying schema migration: v014_admin_users_and_audit_trail...")
                if supabase_url:
                    cursor.execute("""
                        CREATE TABLE IF NOT EXISTS admin_users (
                            id VARCHAR(64) PRIMARY KEY,
                            email VARCHAR(255) UNIQUE NOT NULL,
                            role VARCHAR(32) NOT NULL DEFAULT 'admin',
                            totp_secret VARCHAR(64),
                            totp_enabled BOOLEAN DEFAULT FALSE,
                            invited_by VARCHAR(255),
                            created_at TIMESTAMPTZ DEFAULT now(),
                            updated_at TIMESTAMPTZ DEFAULT now(),
                            last_login_at TIMESTAMPTZ
                        );

                        CREATE TABLE IF NOT EXISTS admin_audit_log (
                            id VARCHAR(64) PRIMARY KEY,
                            admin_email VARCHAR(255) NOT NULL,
                            action VARCHAR(64) NOT NULL,
                            target_type VARCHAR(64),
                            target_id VARCHAR(255),
                            details TEXT,
                            ip_address VARCHAR(64),
                            user_agent TEXT,
                            created_at TIMESTAMPTZ DEFAULT now()
                        );
                        CREATE INDEX IF NOT EXISTS idx_admin_audit_created ON admin_audit_log(created_at DESC);
                        CREATE INDEX IF NOT EXISTS idx_admin_audit_email ON admin_audit_log(admin_email);

                        INSERT INTO admin_users (id, email, role, totp_enabled, created_at, updated_at)
                        VALUES ('adm_owner_lyndon', 'lyndnpnto@gmail.com', 'owner', FALSE, now(), now())
                        ON CONFLICT (email) DO NOTHING;

                        INSERT INTO schema_migrations (version) VALUES ('v014_admin_users_and_audit_trail') ON CONFLICT DO NOTHING;
                    """)
                else:
                    cursor.execute("""
                        CREATE TABLE IF NOT EXISTS admin_users (
                            id TEXT PRIMARY KEY,
                            email TEXT UNIQUE NOT NULL,
                            role TEXT NOT NULL DEFAULT 'admin',
                            totp_secret TEXT,
                            totp_enabled INTEGER DEFAULT 0,
                            invited_by TEXT,
                            created_at TEXT DEFAULT (datetime('now')),
                            updated_at TEXT DEFAULT (datetime('now')),
                            last_login_at TEXT
                        );
                    """)
                    cursor.execute("""
                        CREATE TABLE IF NOT EXISTS admin_audit_log (
                            id TEXT PRIMARY KEY,
                            admin_email TEXT NOT NULL,
                            action TEXT NOT NULL,
                            target_type TEXT,
                            target_id TEXT,
                            details TEXT,
                            ip_address TEXT,
                            user_agent TEXT,
                            created_at TEXT DEFAULT (datetime('now'))
                        );
                    """)
                    cursor.execute("CREATE INDEX IF NOT EXISTS idx_admin_audit_created ON admin_audit_log(created_at DESC);")
                    cursor.execute("CREATE INDEX IF NOT EXISTS idx_admin_audit_email ON admin_audit_log(admin_email);")
                    cursor.execute("""
                        INSERT OR IGNORE INTO admin_users (id, email, role, totp_enabled)
                        VALUES ('adm_owner_lyndon', 'lyndnpnto@gmail.com', 'owner', 0);
                    """)
                    cursor.execute("INSERT OR IGNORE INTO schema_migrations (version) VALUES ('v014_admin_users_and_audit_trail');")
                conn.commit()

            # Migration v015: Always-On Asset Scan Runs & Multi-Asset Audit Ledger
            if "v015_asset_scan_runs" not in applied:
                logger.info("Applying schema migration: v015_asset_scan_runs...")
                if supabase_url:
                    cursor.execute("""
                        CREATE TABLE IF NOT EXISTS asset_scan_runs (
                            id SERIAL PRIMARY KEY,
                            scan_id VARCHAR(64) UNIQUE NOT NULL,
                            scan_type VARCHAR(50) NOT NULL,
                            status VARCHAR(20) NOT NULL,
                            items_scanned INTEGER DEFAULT 0,
                            items_added INTEGER DEFAULT 0,
                            items_updated INTEGER DEFAULT 0,
                            items_archived INTEGER DEFAULT 0,
                            details_json TEXT DEFAULT '{}',
                            triggered_by VARCHAR(50) DEFAULT 'scheduled_cron',
                            started_at TIMESTAMPTZ DEFAULT now(),
                            completed_at TIMESTAMPTZ,
                            error_message TEXT
                        );
                        CREATE INDEX IF NOT EXISTS idx_scan_runs_type ON asset_scan_runs(scan_type, started_at DESC);
                        INSERT INTO schema_migrations (version) VALUES ('v015_asset_scan_runs') ON CONFLICT DO NOTHING;
                    """)
                else:
                    cursor.execute("""
                        CREATE TABLE IF NOT EXISTS asset_scan_runs (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            scan_id TEXT UNIQUE NOT NULL,
                            scan_type TEXT NOT NULL,
                            status TEXT NOT NULL,
                            items_scanned INTEGER DEFAULT 0,
                            items_added INTEGER DEFAULT 0,
                            items_updated INTEGER DEFAULT 0,
                            items_archived INTEGER DEFAULT 0,
                            details_json TEXT DEFAULT '{}',
                            triggered_by TEXT DEFAULT 'scheduled_cron',
                            started_at TEXT DEFAULT (datetime('now')),
                            completed_at TEXT,
                            error_message TEXT
                        );
                    """)
                    cursor.execute("CREATE INDEX IF NOT EXISTS idx_scan_runs_type ON asset_scan_runs(scan_type, started_at DESC);")
                    cursor.execute("INSERT OR IGNORE INTO schema_migrations (version) VALUES ('v015_asset_scan_runs');")
                conn.commit()

            # Migration v016: Sovereign benchmarks and ETF matrix (Priority 3)
            if "v016_sovereign_benchmarks_and_etfs" not in applied:
                logger.info("Applying schema migration: v016_sovereign_benchmarks_and_etfs...")
                if supabase_url:
                    cursor.execute("""
                        CREATE TABLE IF NOT EXISTS sovereign_benchmarks (
                            id SERIAL PRIMARY KEY,
                            tenor_label VARCHAR(64) UNIQUE NOT NULL,
                            instrument_type VARCHAR(20) NOT NULL,
                            maturity_years NUMERIC NOT NULL,
                            cut_off_yield NUMERIC NOT NULL,
                            auction_date VARCHAR(20) NOT NULL,
                            source VARCHAR(64) DEFAULT 'RBI_AUCTION_CUTOFF',
                            updated_at TIMESTAMPTZ DEFAULT now()
                        );
                        CREATE TABLE IF NOT EXISTS etf_matrix (
                            id SERIAL PRIMARY KEY,
                            symbol VARCHAR(64) UNIQUE NOT NULL,
                            scheme_name VARCHAR(255) NOT NULL,
                            category VARCHAR(50) NOT NULL,
                            underlying_index VARCHAR(100) NOT NULL,
                            last_price NUMERIC NOT NULL,
                            nav NUMERIC NOT NULL,
                            premium_discount_pct NUMERIC DEFAULT 0.0,
                            tracking_error_1y NUMERIC DEFAULT 0.0,
                            expense_ratio_pct NUMERIC DEFAULT 0.0,
                            aum_crores NUMERIC DEFAULT 0.0,
                            avg_daily_volume NUMERIC DEFAULT 0.0,
                            avg_daily_turnover_cr NUMERIC DEFAULT 0.0,
                            liquidity_tier VARCHAR(30) DEFAULT 'HIGH_LIQUIDITY',
                            updated_at TIMESTAMPTZ DEFAULT now()
                        );
                        INSERT INTO schema_migrations (version) VALUES ('v016_sovereign_benchmarks_and_etfs') ON CONFLICT DO NOTHING;
                    """)
                else:
                    cursor.execute("""
                        CREATE TABLE IF NOT EXISTS sovereign_benchmarks (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            tenor_label TEXT UNIQUE NOT NULL,
                            instrument_type TEXT NOT NULL,
                            maturity_years REAL NOT NULL,
                            cut_off_yield REAL NOT NULL,
                            auction_date TEXT NOT NULL,
                            source TEXT DEFAULT 'RBI_AUCTION_CUTOFF',
                            updated_at TEXT DEFAULT (datetime('now'))
                        );
                    """)
                    cursor.execute("""
                        CREATE TABLE IF NOT EXISTS etf_matrix (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            symbol TEXT UNIQUE NOT NULL,
                            scheme_name TEXT NOT NULL,
                            category TEXT NOT NULL,
                            underlying_index TEXT NOT NULL,
                            last_price REAL NOT NULL,
                            nav REAL NOT NULL,
                            premium_discount_pct REAL DEFAULT 0.0,
                            tracking_error_1y REAL DEFAULT 0.0,
                            expense_ratio_pct REAL DEFAULT 0.0,
                            aum_crores REAL DEFAULT 0.0,
                            avg_daily_volume REAL DEFAULT 0.0,
                            avg_daily_turnover_cr REAL DEFAULT 0.0,
                            liquidity_tier TEXT DEFAULT 'HIGH_LIQUIDITY',
                            updated_at TEXT DEFAULT (datetime('now'))
                        );
                    """)
                    cursor.execute("INSERT OR IGNORE INTO schema_migrations (version) VALUES ('v016_sovereign_benchmarks_and_etfs');")
                conn.commit()

            # Migration v017: SM REITs, InvITs, and SGB tranches (Priority 4)
            if "v017_sm_reits_invits_and_sgb" not in applied:
                logger.info("Applying schema migration: v017_sm_reits_invits_and_sgb...")
                if supabase_url:
                    cursor.execute("""
                        CREATE TABLE IF NOT EXISTS reits_and_invits (
                            id SERIAL PRIMARY KEY,
                            symbol VARCHAR(64) UNIQUE NOT NULL,
                            name VARCHAR(255) NOT NULL,
                            structure_type VARCHAR(50) NOT NULL,
                            current_price NUMERIC NOT NULL,
                            nav_per_unit NUMERIC NOT NULL,
                            discount_to_nav_pct NUMERIC DEFAULT 0.0,
                            distribution_yield_pct NUMERIC DEFAULT 0.0,
                            occupancy_pct NUMERIC DEFAULT 0.0,
                            ndcf_payout_purity_pct NUMERIC DEFAULT 100.0,
                            ltv_ratio_pct NUMERIC DEFAULT 0.0,
                            wale_years NUMERIC DEFAULT 0.0,
                            sponsor_holding_pct NUMERIC DEFAULT 0.0,
                            sebi_compliant BOOLEAN DEFAULT TRUE,
                            details_json TEXT DEFAULT '{}',
                            updated_at TIMESTAMPTZ DEFAULT now()
                        );
                        CREATE TABLE IF NOT EXISTS sgb_tranches (
                            id SERIAL PRIMARY KEY,
                            symbol VARCHAR(64) UNIQUE NOT NULL,
                            series_name VARCHAR(255) NOT NULL,
                            issue_price NUMERIC NOT NULL,
                            market_price NUMERIC NOT NULL,
                            spot_gold_price NUMERIC NOT NULL,
                            discount_to_spot_pct NUMERIC DEFAULT 0.0,
                            annual_coupon_rate NUMERIC DEFAULT 2.50,
                            maturity_date VARCHAR(20) NOT NULL,
                            ytm_annualized_pct NUMERIC DEFAULT 0.0,
                            tax_treatment VARCHAR(100) DEFAULT '100% Tax-Free Capital Gains (Sec 47(viic))',
                            etf_tax_adjusted_spread_pct NUMERIC DEFAULT 0.0,
                            updated_at TIMESTAMPTZ DEFAULT now()
                        );
                        INSERT INTO schema_migrations (version) VALUES ('v017_sm_reits_invits_and_sgb') ON CONFLICT DO NOTHING;
                    """)
                else:
                    cursor.execute("""
                        CREATE TABLE IF NOT EXISTS reits_and_invits (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            symbol TEXT UNIQUE NOT NULL,
                            name TEXT NOT NULL,
                            structure_type TEXT NOT NULL,
                            current_price REAL NOT NULL,
                            nav_per_unit REAL NOT NULL,
                            discount_to_nav_pct REAL DEFAULT 0.0,
                            distribution_yield_pct REAL DEFAULT 0.0,
                            occupancy_pct REAL DEFAULT 0.0,
                            ndcf_payout_purity_pct REAL DEFAULT 100.0,
                            ltv_ratio_pct REAL DEFAULT 0.0,
                            wale_years REAL DEFAULT 0.0,
                            sponsor_holding_pct REAL DEFAULT 0.0,
                            sebi_compliant INTEGER DEFAULT 1,
                            details_json TEXT DEFAULT '{}',
                            updated_at TEXT DEFAULT (datetime('now'))
                        );
                    """)
                    cursor.execute("""
                        CREATE TABLE IF NOT EXISTS sgb_tranches (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            symbol TEXT UNIQUE NOT NULL,
                            series_name TEXT NOT NULL,
                            issue_price REAL NOT NULL,
                            market_price REAL NOT NULL,
                            spot_gold_price REAL NOT NULL,
                            discount_to_spot_pct REAL DEFAULT 0.0,
                            annual_coupon_rate REAL DEFAULT 2.50,
                            maturity_date TEXT NOT NULL,
                            ytm_annualized_pct REAL DEFAULT 0.0,
                            tax_treatment TEXT DEFAULT '100% Tax-Free Capital Gains (Sec 47(viic))',
                            etf_tax_adjusted_spread_pct REAL DEFAULT 0.0,
                            updated_at TEXT DEFAULT (datetime('now'))
                        );
                    """)
                    cursor.execute("INSERT OR IGNORE INTO schema_migrations (version) VALUES ('v017_sm_reits_invits_and_sgb');")
                conn.commit()

            # Migration v018: Retail alternative yield & shadow banking safety radar (Priority 5)
            if "v018_retail_safety_radar" not in applied:
                logger.info("Applying schema migration: v018_retail_safety_radar...")
                if supabase_url:
                    cursor.execute("""
                        CREATE TABLE IF NOT EXISTS alternative_yield_products (
                            id SERIAL PRIMARY KEY,
                            product_id VARCHAR(64) UNIQUE NOT NULL,
                            product_name VARCHAR(255) NOT NULL,
                            category VARCHAR(50) NOT NULL,
                            promoted_yield_pct NUMERIC NOT NULL,
                            danger_score INTEGER NOT NULL DEFAULT 50,
                            regulatory_status VARCHAR(50) NOT NULL,
                            counterparty_risk_level VARCHAR(30) NOT NULL,
                            principal_guarantee_validity BOOLEAN DEFAULT FALSE,
                            rbi_warning_circular TEXT DEFAULT '',
                            liquidity_lock_months INTEGER DEFAULT 0,
                            precedent_losses_summary TEXT DEFAULT '',
                            safe_alternative_recommendation TEXT DEFAULT '',
                            audit_matrix_json TEXT DEFAULT '{}',
                            updated_at TIMESTAMPTZ DEFAULT now()
                        );
                        INSERT INTO schema_migrations (version) VALUES ('v018_retail_safety_radar') ON CONFLICT DO NOTHING;
                    """)
                else:
                    cursor.execute("""
                        CREATE TABLE IF NOT EXISTS alternative_yield_products (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            product_id TEXT UNIQUE NOT NULL,
                            product_name TEXT NOT NULL,
                            category TEXT NOT NULL,
                            promoted_yield_pct REAL NOT NULL,
                            danger_score INTEGER NOT NULL DEFAULT 50,
                            regulatory_status TEXT NOT NULL,
                            counterparty_risk_level TEXT NOT NULL,
                            principal_guarantee_validity INTEGER DEFAULT 0,
                            rbi_warning_circular TEXT DEFAULT '',
                            liquidity_lock_months INTEGER DEFAULT 0,
                            precedent_losses_summary TEXT DEFAULT '',
                            safe_alternative_recommendation TEXT DEFAULT '',
                            audit_matrix_json TEXT DEFAULT '{}',
                            updated_at TEXT DEFAULT (datetime('now'))
                        );
                    """)
                    cursor.execute("INSERT OR IGNORE INTO schema_migrations (version) VALUES ('v018_retail_safety_radar');")
                conn.commit()

            _DB_INITIALIZED = True
        except Exception as e:
            logger.error(f"Error during init_db migrations: {e}")
            raise
        finally:
            cursor.close()
            conn.close()
