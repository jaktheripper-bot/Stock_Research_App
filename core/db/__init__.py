"""
Core Database Package for Equity Research App.

Modularized dual-binding (Supabase PostgreSQL / SQLite fallback) persistence layer.
Divided into specialized submodules:
- connection: Connection pooling, migrations (v001-v006), database initialization, schema setup.
- compliance: SEBI safe-harbor audit logging and mandatory regulatory disclaimers.
- reports: Research report snapshots, differential historical revisions, and full retrieval.
- watchlist: Watched equities, scan timestamps, and tracking state.
- alerts: Real-time surveillance events, notification badges, and user dismissals.
- telemetry: Site usage analytics, session journeys, and API credit savings tracking.
- settings: Dynamic system configuration key-value store.
"""

from core.db.connection import (
    IST,
    _CACHED_SUPABASE_URL,
    _DB_INITIALIZED,
    _DB_INIT_LOCK,
    _PooledConnectionProxy,
    _acquire_connection_from_pool,
    _get_pg_pool,
    get_supabase_url,
    get_placeholder,
    get_db_connection,
    init_db,
)

from core.db.compliance import (
    MANDATORY_SEBI_DISCLAIMER,
    log_compliance_event,
    get_compliance_audit_logs,
)

from core.db.reports import (
    _format_timestamp,
    save_report_to_archive,
    get_archived_reports,
    get_report_by_ticker,
    get_report_revisions,
    get_revision_by_id,
)

from core.db.watchlist import (
    get_watchlist,
    add_to_watchlist,
    remove_from_watchlist,
    is_ticker_in_watchlist,
    update_watchlist_scan_state,
)

from core.db.alerts import (
    record_alert_event,
    get_alert_events,
    mark_alert_as_read,
    mark_all_alerts_as_read,
    dismiss_alert,
    dismiss_all_alerts,
    get_unread_alert_count,
)

from core.db.telemetry import (
    record_usage_event,
    _build_telemetry_time_filter,
    get_site_usage_summary,
    get_session_journeys,
    get_user_usage_analytics,
)

from core.db.settings import (
    get_system_setting,
    set_system_setting,
)

from core.db.users import (
    get_or_create_user,
    get_user_by_id,
    get_user_by_email,
    get_user_credits_balance,
    deduct_user_credits,
    add_user_credits,
    get_user_transactions,
    get_user_usage_history,
    get_all_billables,
    get_revenue_analytics_summary,
    process_refund,
)

from core.db.discovery import (
    save_discovery_reel,
    get_active_discovery_reel,
    get_available_discovery_editions,
)

from core.db.support import (
    create_support_ticket,
    get_support_tickets,
    update_ticket_status,
    get_open_tickets_count,
)

__all__ = [
    # connection
    "IST",
    "_CACHED_SUPABASE_URL",
    "_DB_INITIALIZED",
    "_DB_INIT_LOCK",
    "_PooledConnectionProxy",
    "_acquire_connection_from_pool",
    "_get_pg_pool",
    "get_supabase_url",
    "get_placeholder",
    "get_db_connection",
    "init_db",
    # compliance
    "MANDATORY_SEBI_DISCLAIMER",
    "log_compliance_event",
    "get_compliance_audit_logs",
    # reports
    "_format_timestamp",
    "save_report_to_archive",
    "get_archived_reports",
    "get_report_by_ticker",
    "get_report_revisions",
    "get_revision_by_id",
    # watchlist
    "get_watchlist",
    "add_to_watchlist",
    "remove_from_watchlist",
    "is_ticker_in_watchlist",
    "update_watchlist_scan_state",
    # alerts
    "record_alert_event",
    "get_alert_events",
    "mark_alert_as_read",
    "mark_all_alerts_as_read",
    "dismiss_alert",
    "dismiss_all_alerts",
    "get_unread_alert_count",
    # telemetry
    "record_usage_event",
    "_build_telemetry_time_filter",
    "get_site_usage_summary",
    "get_session_journeys",
    # settings
    "get_system_setting",
    "set_system_setting",
    # users & monetization
    "get_or_create_user",
    "get_user_by_id",
    "get_user_by_email",
    "get_user_credits_balance",
    "deduct_user_credits",
    "add_user_credits",
    "get_user_transactions",
    "get_user_usage_history",
    # discovery reel
    "save_discovery_reel",
    "get_active_discovery_reel",
    "get_available_discovery_editions",
    # support & grievances
    "create_support_ticket",
    "get_support_tickets",
    "update_ticket_status",
    "get_open_tickets_count",
]
