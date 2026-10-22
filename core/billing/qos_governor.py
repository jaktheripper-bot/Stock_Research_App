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

# Denial-of-Wallet Shield: Daily Live Generation (Cache Miss) Velocity Tracking
_USER_DAILY_LIVE_GEN_WINDOWS: Dict[str, Deque[float]] = defaultdict(deque)
_IP_DAILY_LIVE_GEN_WINDOWS: Dict[str, Deque[float]] = defaultdict(deque)

_WINDOW_LOCK = threading.RLock()

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

# Strict per-user / per-IP daily caps on live generations (cache misses)
MAX_DAILY_LIVE_GENERATIONS_PER_USER = int(os.environ.get("MAX_DAILY_LIVE_GENERATIONS_PER_USER", "25"))
MAX_DAILY_LIVE_GENERATIONS_PER_IP = int(os.environ.get("MAX_DAILY_LIVE_GENERATIONS_PER_IP", "50"))


def reset_qos_windows_for_test() -> None:
    """Clears in-memory rate-limit windows for deterministic unit testing."""
    with _WINDOW_LOCK:
        _USER_COPILOT_WINDOWS.clear()
        _USER_SYNTHESIS_WINDOWS.clear()
        _IP_BURST_WINDOWS.clear()
        _USER_DAILY_LIVE_GEN_WINDOWS.clear()
        _IP_DAILY_LIVE_GEN_WINDOWS.clear()
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


def authorize_live_generation(
    user_email: str = "",
    client_ip: str = ""
) -> Tuple[bool, str]:
    """
    Enforces a strict per-user and per-IP daily velocity cap on live generations (cache misses)
    to defeat Denial-of-Wallet attacks across micro-cap penny stocks.
    Returns (True, "AUTHORIZED") or (False, reason).
    """
    try:
        now = time.time()
        actor_user = (user_email or "").strip().lower()
        actor_ip = (client_ip or "").strip()

        with _WINDOW_LOCK:
            cutoff = now - 86400.0
            if actor_ip:
                ip_win = _IP_DAILY_LIVE_GEN_WINDOWS[actor_ip]
                while ip_win and ip_win[0] < cutoff:
                    ip_win.popleft()
                if len(ip_win) >= MAX_DAILY_LIVE_GENERATIONS_PER_IP:
                    return False, f"DAILY_IP_LIVE_GEN_CAP_EXCEEDED (Max {MAX_DAILY_LIVE_GENERATIONS_PER_IP}/day per IP)"

            if actor_user:
                user_win = _USER_DAILY_LIVE_GEN_WINDOWS[actor_user]
                while user_win and user_win[0] < cutoff:
                    user_win.popleft()
                if len(user_win) >= MAX_DAILY_LIVE_GENERATIONS_PER_USER:
                    return False, f"DAILY_USER_LIVE_GEN_CAP_EXCEEDED (Max {MAX_DAILY_LIVE_GENERATIONS_PER_USER}/day per account)"

            if actor_ip:
                _IP_DAILY_LIVE_GEN_WINDOWS[actor_ip].append(now)
            if actor_user:
                _USER_DAILY_LIVE_GEN_WINDOWS[actor_user].append(now)

        return True, "AUTHORIZED"
    except Exception as e:
        logger.error(f"QoS Governor live generation check error (failing closed): {e}")
        return False, "System busy verifying live generation velocity limits. Please retry later."


def record_live_generation(user_email: str = "", client_ip: str = "") -> None:
    """Manually registers a live generation occurrence under user and IP tracking windows."""
    now = time.time()
    actor_user = (user_email or "").strip().lower()
    actor_ip = (client_ip or "").strip()
    with _WINDOW_LOCK:
        if actor_ip:
            _IP_DAILY_LIVE_GEN_WINDOWS[actor_ip].append(now)
        if actor_user:
            _USER_DAILY_LIVE_GEN_WINDOWS[actor_user].append(now)


def is_live_generation_allowed(user_email: str = "", client_ip: str = "") -> bool:
    """Convenience boolean helper checking if live generation is permitted without recording."""
    now = time.time()
    actor_user = (user_email or "").strip().lower()
    actor_ip = (client_ip or "").strip()
    cutoff = now - 86400.0
    with _WINDOW_LOCK:
        if actor_ip:
            ip_win = _IP_DAILY_LIVE_GEN_WINDOWS[actor_ip]
            ip_count = sum(1 for t in ip_win if t >= cutoff)
            if ip_count >= MAX_DAILY_LIVE_GENERATIONS_PER_IP:
                return False
        if actor_user:
            user_win = _USER_DAILY_LIVE_GEN_WINDOWS[actor_user]
            user_count = sum(1 for t in user_win if t >= cutoff)
            if user_count >= MAX_DAILY_LIVE_GENERATIONS_PER_USER:
                return False
        if not actor_ip and not actor_user:
            # If no actor specified, check whether any active IP or user is currently capped
            for ip_win in _IP_DAILY_LIVE_GEN_WINDOWS.values():
                if sum(1 for t in ip_win if t >= cutoff) >= MAX_DAILY_LIVE_GENERATIONS_PER_IP:
                    return False
            for user_win in _USER_DAILY_LIVE_GEN_WINDOWS.values():
                if sum(1 for t in user_win if t >= cutoff) >= MAX_DAILY_LIVE_GENERATIONS_PER_USER:
                    return False
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
    try:
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
                
                # Denial-of-Wallet Shield: check daily live generation cap (cache misses)
                live_ok, live_reason = authorize_live_generation(user_email=user_email, client_ip=client_ip)
                if not live_ok:
                    return False, live_reason

                return True, "VIP_SYNTHESIS_AUTHORIZED"

        return False, f"UNKNOWN_ACTOR_TYPE:{actor_type}"
    except Exception as e:
        logger.error(f"QoS Governor DB check error (failing closed): {e}")
        return False, "System busy verifying AI capacity limits. Please retry in a few seconds."


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
