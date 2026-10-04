"""Database connection, connection pooling, and schema migration engine."""

import logging
import os
import threading
from datetime import timezone, timedelta
import streamlit as st

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
    # Enable TCP keepalive to improve connection reliability
    return psycopg2.pool.ThreadedConnectionPool(
        minconn=1,
        maxconn=300,
        dsn=dsn,
        keepalives=1,
        keepalives_idle=30,
        keepalives_interval=10,
        keepalives_count=5,
    )

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

            _DB_INITIALIZED = True
        except Exception as e:
            logger.error(f"Error during init_db migrations: {e}")
            raise
        finally:
            cursor.close()
            conn.close()
