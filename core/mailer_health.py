"""
Mailer health for an external uptime monitor (GET /api/health/mailers).

Answers one question: did the most recent Market Close Wrap and Fund NAV Update that should have
gone out by now actually go out? A free Better Stack URL monitor polls the endpoint and alerts on
any non-200 answer, which replaces two paid heartbeats and also catches a sender that never ran.

Schedule (IST), for trading day D (weekday, not an NSE holiday):
- Market Close Wrap for D: sender starts 19:30 on D, waits up to 60 min  -> due by 21:00 on D.
- Fund NAV Update for D:   sender starts 07:30 on D+1, waits up to 45 min -> due by 08:45 on D+1.

Only "sent or not" is exposed (from `digest_dispatches`, status COMPLETED or PARTIAL); never
subscriber counts or addresses. A database error reads as "not sent", so the monitor alerts.
"""
import logging
import threading
import time
from datetime import date, datetime, time as dtime, timedelta, timezone
from typing import Any, Callable, Dict, Optional, Tuple

logger = logging.getLogger(__name__)

IST = timezone(timedelta(hours=5, minutes=30))

# Editions before the Render-timed senders went live are not judged.
MAILER_HEALTH_START_DATE = date(2026, 11, 12)
LOOKBACK_DAYS = 14
CACHE_SECONDS = 60

# kind -> (days after D the email is due, IST time it is due by)
EDITION_DUE: Dict[str, Tuple[int, dtime]] = {
    "MARKET_CLOSE": (0, dtime(21, 0)),
    "FUND_NAV": (1, dtime(8, 45)),
}

_cache: Dict[str, Any] = {}
_cache_lock = threading.Lock()


def _default_is_holiday(day: date) -> bool:
    """NSE holiday check; if the calendar is unavailable the day is treated as a trading day,
    so a doubtful day errs towards an alert rather than silence."""
    from core.ingestion.market_calendar import MarketCalendarUnavailable, is_nse_trading_holiday

    try:
        return is_nse_trading_holiday(day.isoformat())
    except MarketCalendarUnavailable as err:
        logger.warning("Mailer health: holiday calendar unavailable (%s); treating %s as a trading day.", err, day)
        return False


def _default_was_sent(day: date, kind: str) -> bool:
    from core.db.digest import has_edition_been_dispatched

    return has_edition_been_dispatched(day.isoformat(), kind)


def due_at(day: date, kind: str) -> datetime:
    offset_days, by = EDITION_DUE[kind]
    return datetime.combine(day + timedelta(days=offset_days), by, tzinfo=IST)


def latest_expected_edition(
    now: datetime, kind: str, is_holiday: Callable[[date], bool]
) -> Optional[date]:
    """Most recent trading day whose `kind` email should have gone out by `now` (None if none)."""
    day = now.astimezone(IST).date()
    for _ in range(LOOKBACK_DAYS + 1):
        if day < MAILER_HEALTH_START_DATE:
            return None
        if day.weekday() < 5 and due_at(day, kind) <= now and not is_holiday(day):
            return day
        day -= timedelta(days=1)
    return None


def evaluate_mailer_health(
    now: Optional[datetime] = None,
    is_holiday: Callable[[date], bool] = _default_is_holiday,
    was_sent: Callable[[date, str], bool] = _default_was_sent,
) -> Dict[str, Any]:
    """Returns {"status": "ok"|"late", "checked_at", "editions": {kind: {...}}}."""
    now = (now or datetime.now(IST)).astimezone(IST)
    editions: Dict[str, Any] = {}
    late = False
    for kind in EDITION_DUE:
        expected = latest_expected_edition(now, kind, is_holiday)
        if expected is None:
            editions[kind] = {"expected_edition": None, "due_by": None, "sent": None}
            continue
        sent = bool(was_sent(expected, kind))
        late = late or not sent
        editions[kind] = {
            "expected_edition": expected.isoformat(),
            "due_by": due_at(expected, kind).isoformat(),
            "sent": sent,
        }
    return {"status": "late" if late else "ok", "checked_at": now.isoformat(timespec="seconds"), "editions": editions}


def cached_mailer_health() -> Dict[str, Any]:
    """evaluate_mailer_health() with a short in-process cache, so frequent polling stays cheap."""
    with _cache_lock:
        hit = _cache.get("result")
        if hit and time.monotonic() - hit[0] < CACHE_SECONDS:
            return hit[1]
    result = evaluate_mailer_health()
    with _cache_lock:
        _cache["result"] = (time.monotonic(), result)
    return result
