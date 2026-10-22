"""
Cortex alias module for Actor-Scoped AI QoS Governor & Single-Flight Coalescer.
Re-exports from core.billing.qos_governor.
"""
from core.billing.qos_governor import (
    authorize_llm_execution,
    single_flight_ticker_lock,
    reset_qos_windows_for_test,
    record_daemon_spend_usd,
    get_daemon_daily_spend_usd,
    authorize_live_generation,
    record_live_generation,
    is_live_generation_allowed,
    MAX_COPILOT_TURNS_PER_USER_HOUR,
    MAX_SYNTHESIS_PER_USER_HOUR,
    MAX_ANON_REQUESTS_PER_IP_MINUTE,
    MAX_DAEMON_DAILY_SPEND_USD,
    MAX_DAILY_LIVE_GENERATIONS_PER_USER,
    MAX_DAILY_LIVE_GENERATIONS_PER_IP,
)

__all__ = [
    "authorize_llm_execution",
    "single_flight_ticker_lock",
    "reset_qos_windows_for_test",
    "record_daemon_spend_usd",
    "get_daemon_daily_spend_usd",
    "authorize_live_generation",
    "record_live_generation",
    "is_live_generation_allowed",
    "MAX_COPILOT_TURNS_PER_USER_HOUR",
    "MAX_SYNTHESIS_PER_USER_HOUR",
    "MAX_ANON_REQUESTS_PER_IP_MINUTE",
    "MAX_DAEMON_DAILY_SPEND_USD",
    "MAX_DAILY_LIVE_GENERATIONS_PER_USER",
    "MAX_DAILY_LIVE_GENERATIONS_PER_IP",
]
