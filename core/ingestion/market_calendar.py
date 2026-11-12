"""
NSE equity trading-holiday calendar (live).

Used by the timed email senders so no research email goes out for a date the cash market was
closed. Each successful fetch is stored in `system_settings` (key `nse_equity_holidays`), because
NSE sometimes refuses requests from cloud servers; when the live fetch fails, that last official
copy is used if it covers the requested year. Fails closed: with neither, `MarketCalendarUnavailable`
is raised and the caller must not send.
"""
import json
import logging
from datetime import datetime, timezone
from typing import Set

import requests

logger = logging.getLogger(__name__)

NSE_HOLIDAY_URL = "https://www.nseindia.com/api/holiday-master?type=trading"
NSE_EQUITY_SEGMENT = "CM"
_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0 Safari/537.36",
    "Accept": "application/json",
    "Referer": "https://www.nseindia.com/",
}
_CACHE: dict = {}
STORED_SETTING_KEY = "nse_equity_holidays"


class MarketCalendarUnavailable(RuntimeError):
    """The official NSE holiday list could not be fetched or parsed."""


def parse_nse_holidays(payload: dict, segment: str = NSE_EQUITY_SEGMENT) -> Set[str]:
    """Returns ISO dates (YYYY-MM-DD) from NSE's holiday-master payload for `segment`."""
    rows = (payload or {}).get(segment)
    if not isinstance(rows, list) or not rows:
        raise MarketCalendarUnavailable(f"NSE holiday list has no '{segment}' entries.")
    dates = set()
    for row in rows:
        raw = str((row or {}).get("tradingDate") or "").strip()
        try:
            dates.add(datetime.strptime(raw, "%d-%b-%Y").date().isoformat())
        except ValueError as err:
            raise MarketCalendarUnavailable(f"Unparseable NSE holiday date {raw!r}") from err
    return dates


def _store_holidays(dates: Set[str]) -> None:
    """Keeps the last official list in the database for runs where NSE cannot be reached."""
    try:
        from core.db.settings import set_system_setting

        payload = {"fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "dates": sorted(dates)}
        if not set_system_setting(STORED_SETTING_KEY, json.dumps(payload)):
            logger.warning("Could not store the NSE holiday list in system_settings.")
    except Exception as err:
        logger.warning("Could not store the NSE holiday list: %s", err)


def _load_stored_holidays() -> Set[str]:
    """Returns the last stored official list, or an empty set if none is stored or it is unreadable."""
    try:
        from core.db.settings import get_system_setting

        raw = get_system_setting(STORED_SETTING_KEY)
        if not raw:
            return set()
        payload = json.loads(raw)
        dates = {str(d) for d in payload.get("dates", [])}
        for d in dates:
            datetime.strptime(d, "%Y-%m-%d")
        logger.warning(
            "Using stored NSE holiday list fetched at %s (%d dates).", payload.get("fetched_at"), len(dates)
        )
        return dates
    except Exception as err:
        logger.warning("Stored NSE holiday list is unavailable: %s", err)
        return set()


def fetch_nse_equity_holidays(timeout: float = 15.0) -> Set[str]:
    """Fetches this year's NSE equity holidays (cached per process, stored in the database).

    If NSE cannot be reached or returns an unreadable list, the last stored official list is
    returned instead; with no stored list, MarketCalendarUnavailable is raised.
    """
    if "dates" in _CACHE:
        return _CACHE["dates"]
    try:
        resp = requests.get(NSE_HOLIDAY_URL, headers=_HEADERS, timeout=timeout)
        resp.raise_for_status()
        dates = parse_nse_holidays(resp.json())
    except Exception as err:
        live_err = err if isinstance(err, MarketCalendarUnavailable) else MarketCalendarUnavailable(
            f"NSE holiday list fetch failed: {err}"
        )
        logger.warning("Live NSE holiday list unavailable (%s); trying the stored copy.", live_err)
        stored = _load_stored_holidays()
        if not stored:
            raise live_err from err
        _CACHE["dates"] = stored
        return stored
    _CACHE["dates"] = dates
    _store_holidays(dates)
    logger.info("Loaded %d NSE equity trading holidays.", len(dates))
    return dates


def is_nse_trading_holiday(date_str: str) -> bool:
    """True when `date_str` is an NSE equity holiday. Raises MarketCalendarUnavailable if unknown."""
    iso = str(date_str)[:10]
    dates = fetch_nse_equity_holidays()
    years = {d[:4] for d in dates}
    if iso[:4] not in years:
        raise MarketCalendarUnavailable(f"NSE holiday list does not cover {iso[:4]}.")
    return iso in dates
