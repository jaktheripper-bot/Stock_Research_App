"""
Actor-Scoped AI QoS Governor & Single-Flight Coalescer (Analytics Namespace).
Guarantees paying/unlocked users NEVER experience degraded reports due to bot traffic
or background cron daemon spend.
"""
from core.billing.qos_governor import (
    MAX_ANON_REQUESTS_PER_IP_MINUTE,
    MAX_COPILOT_TURNS_PER_USER_HOUR,
    MAX_DAEMON_DAILY_SPEND_USD,
    MAX_SYNTHESIS_PER_USER_HOUR,
    authorize_llm_execution,
    get_daemon_daily_spend_usd,
    record_daemon_spend_usd,
    reset_qos_windows_for_test,
    single_flight_ticker_lock,
)

__all__ = [
    "MAX_ANON_REQUESTS_PER_IP_MINUTE",
    "MAX_COPILOT_TURNS_PER_USER_HOUR",
    "MAX_DAEMON_DAILY_SPEND_USD",
    "MAX_SYNTHESIS_PER_USER_HOUR",
    "authorize_llm_execution",
    "get_daemon_daily_spend_usd",
    "record_daemon_spend_usd",
    "reset_qos_windows_for_test",
    "single_flight_ticker_lock",
]
