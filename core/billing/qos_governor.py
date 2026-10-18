"""
Wave 15: Actor-Scoped AI QoS Governor & Single-Flight Coalescer.
Guarantees paying/unlocked users NEVER experience degraded reports due to bot traffic
or background cron daemon spend.
"""
import logging
import os
import threading
import time
from collections import defaultdict, deque
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Deque, Dict, Iterator, Tuple

logger = logging.getLogger(__name__)

_USER_COPILOT_WINDOWS: Dict[str, Deque[float]] = defaultdict(deque)
_USER_SYNTHESIS_WINDOWS: Dict[str, Deque[float]] = defaultdict(deque)
_IP_BURST_WINDOWS: Dict[str, Deque[float]] = defaultdict(deque)
_WINDOW_LOCK = threading.Lock()

_INFLIGHT_TICKER_LOCKS: Dict[str, threading.Lock] = defaultdict(threading.Lock)
_INFLIGHT_META_LOCK = threading.Lock()

# Daemon daily spend tracking (in-memory with daily rollover)
_DAEMON_SPEND_LOCK = threading.Lock()
_DAEMON_DAILY_SPEND_USD: float = 0.0
_DAEMON_SPEND_DATE: str = datetime.now(timezone.utc).strftime("%Y-%m-%d")

MAX_COPILOT_TURNS_PER_USER_HOUR = int(os.environ.get("MAX_COPILOT_TURNS_PER_USER_HOUR", "40"))
MAX_SYNTHESIS_PER_USER_HOUR = int(os.environ.get("MAX_SYNTHESIS_PER_USER_HOUR", "20"))
MAX_ANON_REQUESTS_PER_IP_MINUTE = int(os.environ.get("MAX_ANON_REQUESTS_PER_IP_MINUTE", "30"))
MAX_DAEMON_DAILY_SPEND_USD = float(os.environ.get("MAX_DAEMON_DAILY_SPEND_USD", "5.00"))


def reset_qos_windows_for_test() -> None:
    """Clears in-memory rate-limit windows for deterministic unit testing."""
    with _WINDOW_LOCK:
        _USER_COPILOT_WINDOWS.clear()
        _USER_SYNTHESIS_WINDOWS.clear()
        _IP_BURST_WINDOWS.clear()
    with _DAEMON_SPEND_LOCK:
        global _DAEMON_DAILY_SPEND_USD, _DAEMON_SPEND_DATE
        _DAEMON_DAILY_SPEND_USD = 0.0
        _DAEMON_SPEND_DATE = datetime.now(timezone.utc).strftime("%Y-%m-%d")


def record_daemon_spend_usd(amount_usd: float) -> None:
    """Records daemon LLM spend for the current day."""
    global _DAEMON_DAILY_SPEND_USD, _DAEMON_SPEND_DATE
    today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    with _DAEMON_SPEND_LOCK:
        if _DAEMON_SPEND_DATE != today_str:
            _DAEMON_SPEND_DATE = today_str
            _DAEMON_DAILY_SPEND_USD = 0.0
        _DAEMON_DAILY_SPEND_USD += max(0.0, float(amount_usd))


def get_daemon_daily_spend_usd() -> float:
    """Retrieves current recorded daemon spend in USD for today."""
    today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    with _DAEMON_SPEND_LOCK:
        if _DAEMON_SPEND_DATE != today_str:
            return 0.0
        return _DAEMON_DAILY_SPEND_USD


def _prune_and_check(window: Deque[float], now: float, period_sec: float, limit: int) -> bool:
    cutoff = now - period_sec
    while window and window[0] < cutoff:
        window.popleft()
    if len(window) >= limit:
        return False
    window.append(now)
    return True


def authorize_llm_execution(
    actor_type: str,
    user_email: str = "",
    client_ip: str = "",
    has_unlocked_dossier: bool = False,
    current_daemon_spend_usd: float = 0.0,
) -> Tuple[bool, str]:
    """
    3-Lane Priority QoS Gate:
      - Lane 1 (ANON / Free-tier Copilot): Zero LLM burn; IP rate-limited.
      - Lane 2 (BACKGROUND_DAEMON): Capped at MAX_DAEMON_DAILY_SPEND_USD ($5.00/day).
      - Lane 3 (USER_SYNTHESIS / USER_COPILOT): VIP Lane. Immune to daemon or bot spend;
        protected only by per-user hourly velocity caps against account compromise.
    """
    now = time.time()

    # Lane 1: Unauthenticated or Free-Tier Copilot -> Never invoke paid LLM
    if actor_type == "ANON" or (actor_type == "USER_COPILOT" and not has_unlocked_dossier):
        with _WINDOW_LOCK:
            ip_ok = _prune_and_check(
                _IP_BURST_WINDOWS[client_ip or "anon_ip"],
                now,
                60.0,
                MAX_ANON_REQUESTS_PER_IP_MINUTE,
            )
        if not ip_ok:
            return False, "RATE_LIMIT_IP_BURST"
        return False, "FREE_TIER_DETERMINISTIC_ONLY"

    # Lane 2: Background Cron / Watcher Daemons -> Isolated daily spend cap
    if actor_type == "BACKGROUND_DAEMON":
        spend = current_daemon_spend_usd if current_daemon_spend_usd > 0.0 else get_daemon_daily_spend_usd()
        if spend >= MAX_DAEMON_DAILY_SPEND_USD:
            return False, f"DAEMON_BUDGET_PAUSED (${spend:.2f} >= ${MAX_DAEMON_DAILY_SPEND_USD:.2f})"
        return True, "DAEMON_AUTHORIZED"

    # Lane 3: Paying / Unlocked Users (VIP Lane) -> Never degraded by daemon/bot activity
    actor_key = (user_email or client_ip or "vip_user").strip().lower()
    with _WINDOW_LOCK:
        if actor_type == "USER_COPILOT":
            ok = _prune_and_check(
                _USER_COPILOT_WINDOWS[actor_key],
                now,
                3600.0,
                MAX_COPILOT_TURNS_PER_USER_HOUR,
            )
            if not ok:
                return False, "USER_COPILOT_HOURLY_VELOCITY_CAP"
            return True, "VIP_COPILOT_AUTHORIZED"

        if actor_type == "USER_SYNTHESIS":
            ok = _prune_and_check(
                _USER_SYNTHESIS_WINDOWS[actor_key],
                now,
                3600.0,
                MAX_SYNTHESIS_PER_USER_HOUR,
            )
            if not ok:
                return False, "USER_SYNTHESIS_HOURLY_VELOCITY_CAP"
            return True, "VIP_SYNTHESIS_AUTHORIZED"

    return False, f"UNKNOWN_ACTOR_TYPE:{actor_type}"


@contextmanager
def single_flight_ticker_lock(ticker: str) -> Iterator[None]:
    """
    Coalesces concurrent requests for the same ticker so only 1 LLM synthesis call executes.
    Waiters check the DB cache immediately after acquiring the lock.
    """
    clean_ticker = (ticker or "UNKNOWN").strip().upper()
    with _INFLIGHT_META_LOCK:
        lock = _INFLIGHT_TICKER_LOCKS[clean_ticker]
    lock.acquire()
    try:
        yield
    finally:
        lock.release()
