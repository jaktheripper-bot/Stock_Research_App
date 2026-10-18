"""
Core Analytics Package.
"""
from core.analytics.ai_qos_governor import (
    authorize_llm_execution,
    reset_qos_windows_for_test,
    single_flight_ticker_lock,
    MAX_COPILOT_TURNS_PER_USER_HOUR,
    MAX_SYNTHESIS_PER_USER_HOUR,
    MAX_ANON_REQUESTS_PER_IP_MINUTE,
    MAX_DAEMON_DAILY_SPEND_USD,
)

__all__ = [
    "authorize_llm_execution",
    "reset_qos_windows_for_test",
    "single_flight_ticker_lock",
    "MAX_COPILOT_TURNS_PER_USER_HOUR",
    "MAX_SYNTHESIS_PER_USER_HOUR",
    "MAX_ANON_REQUESTS_PER_IP_MINUTE",
    "MAX_DAEMON_DAILY_SPEND_USD",
]
