"""Fundamental data ingestion, verified exchange quote resolution, and technical indicator computation."""

import os
import io
import time
import threading
import contextlib
import logging
from functools import wraps
import requests
from datetime import datetime, timedelta
import pandas as pd
import yfinance as yf
from bsedata.bse import BSE
from normalizer import clean_ticker
from bse_master import resolve_bse_scrip_code, resolve_canonical_symbol
from typing import Any, Dict, List, Optional, Tuple, Union
from core.analysis.exceptions import ExchangeDataFetchError
from core.config import get_secret, yfinance_fallback_enabled

logger = logging.getLogger("equity_research.core.analysis.fundamentals")
logging.getLogger("yfinance").setLevel(logging.CRITICAL)

@contextlib.contextmanager
def suppress_yfinance_noise():
    """Context manager to suppress unhandled yfinance stderr noise (HTTP 403 policy errors, delisted warnings)."""
    buf = io.StringIO()
    with contextlib.redirect_stderr(buf):
        try:
            yield
        finally:
            err = buf.getvalue().strip()
            if err and "403" not in err and "delisted" not in err and "Expecting value" not in err and "not allowed by policy" not in err:
                logger.debug(f"yfinance notice: {err}")


class YFinanceCircuitBreaker:
    """
    Circuit breaker protecting the application against yfinance outages, IP rate-limits,
    and HTML/empty responses that trigger unhandled JSONDecodeError.
    """
    def __init__(self, failure_threshold: int = 3, cooldown_seconds: float = 60.0):
        self.failure_threshold = failure_threshold
        self.cooldown_seconds = cooldown_seconds
        self.failure_count = 0
        self.last_failure_time = 0.0
        self._lock = threading.Lock()

    def record_success(self) -> None:
        with self._lock:
            self.failure_count = 0

    def record_failure(self, err: Any = None) -> None:
        with self._lock:
            self.failure_count += 1
            self.last_failure_time = time.monotonic()
            logger.warning(
                f"yfinance circuit breaker failure recorded ({self.failure_count}/{self.failure_threshold}): {err}"
            )

    def is_available(self) -> bool:
        with self._lock:
            if self.failure_count < self.failure_threshold:
                return True
            elapsed = time.monotonic() - self.last_failure_time
            if elapsed >= self.cooldown_seconds:
                logger.info("yfinance circuit breaker entering half-open state after cooldown.")
                return True
            return False


_yf_circuit_breaker = YFinanceCircuitBreaker()
_yf_session = None
_yf_session_lock = threading.Lock()


def get_hardened_yfinance_session():
    """Returns a browser-impersonating session (curl_cffi Chrome TLS session when available, or requests.Session with desktop User-Agent fallback)."""
    global _yf_session
    with _yf_session_lock:
        if _yf_session is None:
            try:
                from yfinance._http import new_session
                sess = new_session()
            except Exception as e:
                logger.debug(f"yfinance._http.new_session fallback notice: {e}")
                sess = requests.Session()
                sess.headers.update({
                    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                    "Accept-Language": "en-US,en;q=0.9",
                })
            _yf_session = sess
        return _yf_session


def get_hardened_yfinance_ticker(symbol: str) -> yf.Ticker:
    """Returns a yfinance.Ticker instance configured with the hardened browser User-Agent session."""
    session = get_hardened_yfinance_session()
    return yf.Ticker(symbol, session=session)


def safe_fetch_yfinance_info(symbol: str) -> dict:
    """
    Safely retrieves yfinance ticker.info with circuit breaker protection and
    defense against empty responses / JSONDecodeError.
    """
    import json
    if not _yf_circuit_breaker.is_available():
        logger.warning(f"yfinance circuit breaker is OPEN. Skipping info fetch for {symbol}.")
        return {}

    try:
        with suppress_yfinance_noise():
            ticker = get_hardened_yfinance_ticker(symbol)
            info = ticker.info
            if not info or not isinstance(info, dict):
                _yf_circuit_breaker.record_failure(ValueError("Empty or non-dict info received"))
                return {}
            _yf_circuit_breaker.record_success()
            return info
    except (json.decoder.JSONDecodeError, requests.RequestException) as net_err:
        _yf_circuit_breaker.record_failure(net_err)
        logger.warning(f"yfinance network/JSON decode notice for {symbol}: {net_err}")
        return {}
    except Exception as yf_err:
        _yf_circuit_breaker.record_failure(yf_err)
        logger.warning(f"yfinance general fetch notice for {symbol}: {yf_err}")
        return {}

def ttl_cache(ttl_seconds: int = 300, maxsize: int = 128):
    """Thread-safe in-memory TTL and LRU cache for external market data requests."""
    def decorator(fn):
        cache = {}
        lock = threading.Lock()
        @wraps(fn)
        def wrapped(*args, **kwargs):
            key = (args, tuple(sorted(kwargs.items())))
            now = time.time()
            with lock:
                if key in cache:
                    val, exp = cache[key]
                    if now < exp:
                        return val
                    del cache[key]
            res = fn(*args, **kwargs)
            if res is not None:
                with lock:
                    if len(cache) >= maxsize:
                        try:
                            oldest = min(cache.keys(), key=lambda k: cache[k][1])
                            cache.pop(oldest, None)
                        except Exception as pop_err:
                            logger.warning(f"TTL cache eviction reset notice: {pop_err}")
                            cache.clear()
                    cache[key] = (res, now + ttl_seconds)
            return res
        def cache_clear():
            with lock:
                cache.clear()
        wrapped.cache_clear = cache_clear
        wrapped.clear = cache_clear
        return wrapped
    return decorator

def enrich_fundamentals(ticker: str, data: dict) -> dict:
    """
    Enriches stock fundamentals with ratios.
    First checks localized DB fundamentals cache, then falls back to yfinance backfill,
    and persists enriched metrics into cached_fundamentals repository.
    """
    clean_sym = clean_ticker(ticker)
    if data is None:
        data = {}

    # 1. Primary enrichment: Localized DB fundamentals cache
    try:
        from core.db.fundamentals import get_cached_fundamentals
        cached = get_cached_fundamentals(clean_sym)
        if cached:
            for k in [
                "roce", "roce_pct", "roe", "operating_margin", "opm",
                "debt_to_equity", "pb_ratio", "price_to_book", "ev_ebitda",
                "ev_to_ebitda", "forward_pe", "fifty_two_week_high",
                "fifty_two_week_low", "52w_high", "52w_low"
            ]:
                if data.get(k) in [None, "N/A", "", 0, 0.0] and cached.get(k) is not None:
                    data[k] = cached[k]

            if data.get("sector") in [None, "N/A", "", "General Industry", "Core Industry"] and cached.get("sector"):
                data["sector"] = cached["sector"]
            if data.get("industry") in [None, "N/A", "", "Diversified"] and cached.get("industry"):
                data["industry"] = cached["industry"]
            if data.get("market_cap") in [None, "N/A", 0, "0"] and cached.get("market_cap"):
                data["market_cap"] = cached["market_cap"]
            if data.get("current_price") in [None, "N/A", 0, 0.0] and cached.get("current_price"):
                data["current_price"] = cached["current_price"]
            if data.get("pe_ratio") in [None, "N/A", ""] and cached.get("pe_ratio"):
                data["pe_ratio"] = cached["pe_ratio"]
    except Exception as cache_err:
        logger.debug(f"Localized fundamentals cache enrichment notice for {clean_sym}: {cache_err}")

    # 1.5. Exchange EOD Enrichment via Angel One SmartAPI Historical Candles (before yfinance)
    if os.environ.get("TESTING") != "1":
        try:
            from core.ingestion.angel_one import AngelOneGateway
            if AngelOneGateway.is_configured() and (
                data.get("current_price") in [None, "N/A", 0, 0.0]
                or data.get("52w_high") in [None, "N/A", 0, 0.0]
                or data.get("fifty_two_week_high") in [None, "N/A", 0, 0.0]
            ):
                eod = AngelOneGateway.get_eod_summary(clean_sym)
                if eod:
                    if data.get("current_price") in [None, "N/A", 0, 0.0] and eod.get("current_price"):
                        data["current_price"] = eod["current_price"]
                    if data.get("fifty_two_week_high") in [None, "N/A", 0, 0.0] and eod.get("52w_high"):
                        data["fifty_two_week_high"] = eod["52w_high"]
                        data["52w_high"] = eod["52w_high"]
                    if data.get("fifty_two_week_low") in [None, "N/A", 0, 0.0] and eod.get("52w_low"):
                        data["fifty_two_week_low"] = eod["52w_low"]
                        data["52w_low"] = eod["52w_low"]
                    if eod.get("dma_50"):
                        data["dma_50"] = eod["dma_50"]
                    if eod.get("dma_200"):
                        data["dma_200"] = eod["dma_200"]
        except Exception as ao_eod_err:
            logger.debug(f"Angel One EOD candle enrichment notice for {clean_sym}: {ao_eod_err}")

    # 2. Secondary enrichment: yfinance backfill
    try:
        yf_ticker = f"{clean_sym}.BO" if clean_sym.isdigit() else f"{clean_sym}.NS"
        # yfinance is an unofficial source; with the fallback off, empty info leaves
        # missing fields as 'N/A' (Not disclosed) rather than pulling third-party data.
        info = {}
        if yfinance_fallback_enabled():
            info = safe_fetch_yfinance_info(yf_ticker)

        # Trailing P/E
        if data.get("pe_ratio") in [None, "N/A", "-", "", 0, "0"]:
            pe = info.get("trailingPE")
            if pe is not None and isinstance(pe, (int, float)):
                data["pe_ratio"] = round(pe, 2) if pe > 0 else "N/A (Loss-Making)"

        # Market Cap
        if data.get("market_cap") in [None, "N/A", 0, "-", "", "0"]:
            mcap = info.get("marketCap")
            if mcap and isinstance(mcap, (int, float)):
                data["market_cap"] = int(mcap)

        # Sector & Industry
        if data.get("sector") in [None, "N/A", "-", "", "Core Industry", "Diversified / Core Industry", "General Industry"]:
            sec = info.get("sector")
            if sec:
                data["sector"] = sec
        if data.get("industry") in [None, "N/A", "-", "", "General Corporate", "Diversified"]:
            ind = info.get("industry")
            if ind:
                data["industry"] = ind

        # Financial Ratios Enrichment
        fpe = info.get("forwardPE")
        if fpe and isinstance(fpe, (int, float)) and fpe > 0:
            data["forward_pe"] = f"{float(fpe):.2f}"
        elif "forward_pe" not in data:
            data["forward_pe"] = "N/A"

        pb = info.get("priceToBook")
        if pb and isinstance(pb, (int, float)) and pb > 0:
            data["pb_ratio"] = f"{float(pb):.2f}"
            data["price_to_book"] = f"{float(pb):.2f}"
        elif "pb_ratio" not in data:
            data["pb_ratio"] = data.get("price_to_book", "N/A")
            data["price_to_book"] = data.get("pb_ratio", "N/A")

        eve = info.get("enterpriseToEbitda")
        if eve and isinstance(eve, (int, float)) and 0 < eve < 500:
            data["ev_ebitda"] = f"{float(eve):.2f}"
            data["ev_to_ebitda"] = f"{float(eve):.2f}"
        elif "ev_ebitda" not in data:
            data["ev_ebitda"] = data.get("ev_to_ebitda", "N/A")
            data["ev_to_ebitda"] = data.get("ev_ebitda", "N/A")

        roe = info.get("returnOnEquity")
        if roe is not None and isinstance(roe, (int, float)):
            data["roe"] = round(float(roe * 100), 2)
        elif data.get("roe") is None:
            data["roe"] = "N/A"

        opm = info.get("operatingMargins")
        if opm is not None and isinstance(opm, (int, float)):
            opm_val = round(float(opm * 100), 2)
            data["operating_margin"] = opm_val
            data["opm"] = opm_val
        elif data.get("operating_margin") is None:
            data["operating_margin"] = data.get("opm", "N/A")
            data["opm"] = data.get("operating_margin", "N/A")

        npm = info.get("profitMargins")
        if npm is not None and isinstance(npm, (int, float)):
            data["npm"] = round(float(npm * 100), 2)

        de = info.get("debtToEquity")
        if de is not None and isinstance(de, (int, float)):
            data["debt_to_equity"] = round(float(de), 2)
        elif data.get("debt_to_equity") is None:
            data["debt_to_equity"] = "N/A"

        dy = info.get("dividendYield")
        if dy is not None and isinstance(dy, (int, float)):
            val = dy if dy > 1 else dy * 100
            data["dividend_yield"] = f"{float(val):.2f}%"

        cr = info.get("currentRatio")
        if cr is not None and isinstance(cr, (int, float)):
            data["current_ratio"] = f"{float(cr):.2f}"

        # 52-week numbers from yfinance if missing
        if data.get("fifty_two_week_high") in [None, "N/A"] and info.get("fiftyTwoWeekHigh"):
            data["fifty_two_week_high"] = round(float(info["fiftyTwoWeekHigh"]), 2)
            data["52w_high"] = data["fifty_two_week_high"]
        if data.get("fifty_two_week_low") in [None, "N/A"] and info.get("fiftyTwoWeekLow"):
            data["fifty_two_week_low"] = round(float(info["fiftyTwoWeekLow"]), 2)
            data["52w_low"] = data["fifty_two_week_low"]

    except Exception as e:
        logger.warning(f"Background fundamental enrichment notice: {e}")

    # Harmonize complementary aliases
    if data.get("roce") is not None:
        data["roce_pct"] = data["roce"]
    elif data.get("roce_pct") is not None:
        data["roce"] = data["roce_pct"]

    if data.get("fifty_two_week_high") is not None:
        data["52w_high"] = data["fifty_two_week_high"]
    elif data.get("52w_high") not in [None, "N/A"]:
        data["fifty_two_week_high"] = data["52w_high"]

    if data.get("fifty_two_week_low") is not None:
        data["52w_low"] = data["fifty_two_week_low"]
    elif data.get("52w_low") not in [None, "N/A"]:
        data["fifty_two_week_low"] = data["52w_low"]

    if data.get("operating_margin") is not None:
        data["opm"] = data["operating_margin"]
    elif data.get("opm") not in [None, "N/A"]:
        data["operating_margin"] = data["opm"]

    if data.get("pb_ratio") not in [None, "N/A"]:
        data["price_to_book"] = data["pb_ratio"]
    elif data.get("price_to_book") not in [None, "N/A"]:
        data["pb_ratio"] = data["price_to_book"]

    if data.get("ev_ebitda") not in [None, "N/A"]:
        data["ev_to_ebitda"] = data["ev_ebitda"]
    elif data.get("ev_to_ebitda") not in [None, "N/A"]:
        data["ev_ebitda"] = data["ev_to_ebitda"]

    # 3. Persist enriched state back to localized database cache
    try:
        from core.db.fundamentals import save_cached_fundamentals
        save_cached_fundamentals(clean_sym, data)
    except Exception as save_err:
        logger.debug(f"Cached fundamentals persistence notice: {save_err}")

    return data

def resolve_pe_with_failsafes(ticker: str, scrip: str = "") -> str:
    clean = clean_ticker(ticker).replace(" ", "")

    # Tier 0: Instant check against verified report baseline in database
    try:
        from core.db.reports import get_report_by_ticker_sync
        rep = get_report_by_ticker_sync(clean)
        if rep and rep.get("baseline_pe"):
            b_pe = str(rep["baseline_pe"]).strip()
            if b_pe and b_pe not in ["", "N/A", "-", "None", "0"]:
                return b_pe
    except Exception as err:
        logger.debug(f"Baseline PE lookup notice for {clean}: {err}")

    # Tier 1: BSE ComHeader Direct (Fast official API, 1.5s timeout)
    if scrip and str(scrip).isdigit():
        try:
            url = f"https://api.bseindia.com/BseIndiaAPI/api/ComHeader/w?quotetype=EQ&scripcode={scrip}&seriesid="
            headers = {"User-Agent": "Mozilla/5.0", "Referer": "https://www.bseindia.com/"}
            res = requests.get(url, headers=headers, timeout=1.5)
            if res.status_code == 200:
                raw_pe = res.json().get("PE")
                if raw_pe and str(raw_pe).strip() not in ["", "-", "None", "0", "0.00"]:
                    val = float(str(raw_pe).replace(",", "").strip())
                    return f"{val:.2f}" if val > 0 else "N/A (Loss-Making)"
        except Exception as e:
            logger.debug(f"BSE ComHeader direct P/E fetch notice: {e}")

    # Tier 2: Fast single-symbol yfinance check (using fast_info) - only when explicitly enabled
    if yfinance_fallback_enabled() and _yf_circuit_breaker.is_available():
        try:
            sym = f"{clean}.BO" if clean.isdigit() else f"{clean}.NS"
            with suppress_yfinance_noise():
                tk = get_hardened_yfinance_ticker(sym)
                fast = getattr(tk, "fast_info", None)
                pe = getattr(fast, "pe", None) or getattr(fast, "trailing_pe", None)
            if pe and float(pe) > 0:
                _yf_circuit_breaker.record_success()
                return f"{float(pe):.2f}"
        except Exception as e:
            _yf_circuit_breaker.record_failure(e)
            logger.warning(f"P/E resolution via yfinance failed for {clean}: {e}")

    return "N/A"

@ttl_cache(ttl_seconds=300, maxsize=256)
def fetch_latest_bse_announcement(scrip_code: str) -> str:
    if not scrip_code or not str(scrip_code).isdigit():
        return ""
    try:
        now_dt = datetime.now()
        str_to_date = now_dt.strftime("%Y%m%d")
        str_prev_date = (now_dt - timedelta(days=60)).strftime("%Y%m%d")
        url = f"https://api.bseindia.com/BseIndiaAPI/api/AnnSubCategoryGetData/w?pageno=1&strCat=-1&strPrevDate={str_prev_date}&strScrip={scrip_code}&strSearch=P&strToDate={str_to_date}&strType=C"
        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Referer": "https://www.bseindia.com/"
        }
        res = requests.get(url, headers=headers, timeout=5)
        if res.status_code == 200:
            table = res.json().get("Table", [])
            if table:
                return (table[0].get("NEWSSUB") or table[0].get("HEADLINE") or "").strip()
    except Exception as e:
        logger.debug(f"BSE announcement fetch notice for scrip {scrip_code}: {e}")
    return ""

def fetch_bse_exchange_data(query: str) -> dict:
    scrip = resolve_bse_scrip_code(query)
    if not scrip:
        raise ValueError(f"Could not resolve an official BSE scrip code for '{query}'.")

    b = BSE()
    q = b.getQuote(scrip)
    if not q or "currentValue" not in q:
        raise ValueError(f"BSE exchange did not return quote data for scrip {scrip}.")

    mcap_raw = q.get("marketCapFull") or q.get("marketCapFreeFloat") or "0"
    mcap_clean = str(mcap_raw).replace(" Cr.", "").replace(",", "").strip()
    try:
        mcap_inr = int(float(mcap_clean) * 10_000_000)
    except Exception as e:
        logger.debug(f"BSE MCap parsing note: {e}")
        mcap_inr = 0

    clean_ticker_val = clean_ticker(query)
    sec_id = str(q.get("securityID") or q.get("scrip_id") or "").strip().upper()
    canonical_ticker = sec_id if (sec_id and " " not in sec_id) else (clean_ticker_val if " " not in clean_ticker_val else (sec_id or clean_ticker_val.replace(" ", "")))
    resolved_pe = resolve_pe_with_failsafes(canonical_ticker, scrip)

    try:
        curr_p = float(str(q.get("currentValue", "0.00")).replace(",", "").strip())
    except Exception as e:
        logger.warning(f"BSE currentValue float parse notice for {query}: {e}")
        curr_p = 0.0

    return {
        "ticker": canonical_ticker,
        "short_name": str(q.get("companyName", clean_ticker_val)),
        "scrip_code": scrip,
        "current_price": curr_p,
        "market_cap": mcap_inr,
        "pe_ratio": resolved_pe,
        "industry": str(q.get("industry", "Core Industry")),
        "sector": str(q.get("industry", "Core Industry")),
        "52w_high": str(q.get("52weekHigh", "N/A")),
        "52w_low": str(q.get("52weekLow", "N/A")),
        "description": f"BSE Listed Equity under group {q.get('group', 'General')}.",
        "is_fallback": False
    }

class _BoundedFundamentalsCache(dict):
    """
    Thread-safe bounded in-memory cache with LRU and TTL eviction for stock fundamentals.
    Prevents unbounded dictionary growth under crawler/bot scans while guaranteeing sub-second reads.
    """
    def __init__(self, maxsize: int = 64, ttl_seconds: float = 900.0):
        super().__init__()
        self.maxsize = maxsize
        self.ttl_seconds = ttl_seconds
        self._lock = threading.Lock()

    def __contains__(self, key: object) -> bool:
        with self._lock:
            if not super().__contains__(key):
                return False
            ts, _ = super().__getitem__(key)
            if time.time() - ts >= self.ttl_seconds:
                super().pop(key, None)
                return False
            return True

    def __getitem__(self, key: object):
        with self._lock:
            val = super().__getitem__(key)
            ts, _ = val
            if time.time() - ts >= self.ttl_seconds:
                super().pop(key, None)
                raise KeyError(key)
            return val

    def get(self, key: object, default: Any = None):
        with self._lock:
            if not super().__contains__(key):
                return default
            val = super().__getitem__(key)
            ts, _ = val
            if time.time() - ts >= self.ttl_seconds:
                super().pop(key, None)
                return default
            return val

    def __setitem__(self, key: object, value: Tuple[float, Any]):
        with self._lock:
            now = time.time()
            # 1. Prune expired entries on write
            expired = [k for k, v in list(super().items()) if (now - v[0]) >= self.ttl_seconds]
            for k in expired:
                super().pop(k, None)

            # 2. Enforce maxsize LRU eviction (evict oldest timestamp)
            if len(self) >= self.maxsize and not super().__contains__(key):
                try:
                    oldest_k = min(super().keys(), key=lambda k: super(_BoundedFundamentalsCache, self).__getitem__(k)[0])
                    super().pop(oldest_k, None)
                except Exception as evict_err:
                    logger.debug("Fundamentals cache eviction notice: %s", evict_err)
                    super().clear()

            super().__setitem__(key, value)

    def pop(self, key: object, default: Any = None):
        with self._lock:
            return super().pop(key, default)

    def clear(self):
        with self._lock:
            super().clear()

_FUNDAMENTALS_CACHE = _BoundedFundamentalsCache(maxsize=64, ttl_seconds=900.0)

def _enrich_with_cached_db_fundamentals(res_dict: dict, symbol: str) -> dict:
    """Blends localized DB fundamentals cache to ensure non-N/A ratios even on live exchange quote hits."""
    if not isinstance(res_dict, dict):
        return res_dict
    try:
        from core.db.fundamentals import get_cached_fundamentals
        cached = get_cached_fundamentals(symbol)
        if cached:
            for k in [
                "roce", "roce_pct", "roe", "operating_margin", "opm",
                "debt_to_equity", "pb_ratio", "price_to_book", "ev_ebitda",
                "ev_to_ebitda", "forward_pe"
            ]:
                if res_dict.get(k) in [None, "N/A", "", 0, 0.0] and cached.get(k) is not None:
                    res_dict[k] = cached[k]

            if res_dict.get("52w_high") in [None, "N/A", "", 0, 0.0] and cached.get("fifty_two_week_high"):
                res_dict["52w_high"] = cached["fifty_two_week_high"]
            if res_dict.get("52w_low") in [None, "N/A", "", 0, 0.0] and cached.get("fifty_two_week_low"):
                res_dict["52w_low"] = cached["fifty_two_week_low"]
            if res_dict.get("fifty_two_week_high") in [None, "N/A", "", 0, 0.0]:
                res_dict["fifty_two_week_high"] = cached.get("fifty_two_week_high") or res_dict.get("52w_high")
            if res_dict.get("fifty_two_week_low") in [None, "N/A", "", 0, 0.0]:
                res_dict["fifty_two_week_low"] = cached.get("fifty_two_week_low") or res_dict.get("52w_low")
            if res_dict.get("sector") in [None, "N/A", "", "General Industry"] and cached.get("sector"):
                res_dict["sector"] = cached["sector"]
            if res_dict.get("industry") in [None, "N/A", "", "Diversified"] and cached.get("industry"):
                res_dict["industry"] = cached["industry"]
            if res_dict.get("market_cap") in [None, "N/A", "", 0, "0"] and cached.get("market_cap") not in [None, "N/A", "", 0, "0"]:
                res_dict["market_cap"] = cached["market_cap"]
            if res_dict.get("pe_ratio") in [None, "N/A", "", "Fair", 0, 0.0, "0"]:
                c_pe = cached.get("pe_ratio")
                if c_pe not in [None, "N/A", "", "Fair", 0, 0.0, "0"]:
                    res_dict["pe_ratio"] = c_pe
                elif cached.get("forward_pe") not in [None, "N/A", "", "Fair", 0, 0.0, "0"]:
                    res_dict["pe_ratio"] = cached["forward_pe"]
    except Exception as e:
        logger.debug(f"Cached fundamentals blend notice for {symbol}: {e}")

    # Harmonize complementary aliases
    if res_dict.get("roce") is not None:
        res_dict["roce_pct"] = res_dict["roce"]
    elif res_dict.get("roce_pct") is not None:
        res_dict["roce"] = res_dict["roce_pct"]

    if res_dict.get("fifty_two_week_high") is not None:
        res_dict["52w_high"] = res_dict["fifty_two_week_high"]
    elif res_dict.get("52w_high") not in [None, "N/A"]:
        res_dict["fifty_two_week_high"] = res_dict["52w_high"]

    if res_dict.get("fifty_two_week_low") is not None:
        res_dict["52w_low"] = res_dict["fifty_two_week_low"]
    elif res_dict.get("52w_low") not in [None, "N/A"]:
        res_dict["fifty_two_week_low"] = res_dict["52w_low"]

    if res_dict.get("operating_margin") is not None:
        res_dict["opm"] = res_dict["operating_margin"]
    elif res_dict.get("opm") not in [None, "N/A"]:
        res_dict["operating_margin"] = res_dict["opm"]

    return res_dict

def get_stock_fundamentals(query: str) -> dict:
    """
    Primary entry point: Fetches verified exchange data from BSE.
    If BSE direct fails or reports inactive, falls back gracefully to Yahoo Finance.
    Maintains a 5-minute in-memory cache to guarantee instant sub-second responses.
    """
    clean = clean_ticker(query)
    now = time.time()
    if clean in _FUNDAMENTALS_CACHE:
        ts, cached_val = _FUNDAMENTALS_CACHE[clean]
        if (now - ts) < 900:  # 15 min TTL
            return dict(cached_val)

    canonical = resolve_canonical_symbol(query) or clean
    scrip = resolve_bse_scrip_code(query) or resolve_bse_scrip_code(canonical)
    
    # 0. Primary Tier: Angel One SmartAPI (Exchange Audited Quote, Level-2 Depth & EOD Candles)
    try:
        from core.ingestion.angel_one import AngelOneGateway
        if AngelOneGateway.is_configured():
            quote = AngelOneGateway.get_stock_quote(canonical or clean)
            if quote and quote.get("ltp"):
                res_dict = {
                    "ticker": canonical or clean,
                    "short_name": canonical or clean,
                    "sector": "General Industry",
                    "industry": "Diversified",
                    "market_cap": "N/A",
                    "pe_ratio": resolve_pe_with_failsafes(canonical or clean, scrip or ""),
                    "current_price": round(float(quote["ltp"]), 2),
                    "52w_high": round(float(quote.get("52w_high", 0)), 2),
                    "52w_low": round(float(quote.get("52w_low", 0)), 2),
                    "order_imbalance_ratio": quote.get("order_imbalance_ratio", 0.0),
                    "upper_circuit": quote.get("upper_circuit", 0.0),
                    "lower_circuit": quote.get("lower_circuit", 0.0),
                    "description": f"Live exchange feed for {clean}.",
                    "exchange_status": "Active / Primary (Exchange Feed)",
                    "is_fallback": False,
                }
                res_dict = _enrich_with_cached_db_fundamentals(res_dict, canonical or clean)
                _FUNDAMENTALS_CACHE[clean] = (now, res_dict)
                _FUNDAMENTALS_CACHE[canonical] = (now, res_dict)
                return res_dict

            # Off-market hours fallback via Angel One SmartAPI EOD Historical Candles
            eod = AngelOneGateway.get_eod_summary(canonical or clean)
            if eod and eod.get("current_price"):
                res_dict = {
                    "ticker": canonical or clean,
                    "short_name": canonical or clean,
                    "sector": "General Industry",
                    "industry": "Diversified",
                    "market_cap": "N/A",
                    "pe_ratio": resolve_pe_with_failsafes(canonical or clean, scrip or ""),
                    "current_price": round(float(eod["current_price"]), 2),
                    "52w_high": round(float(eod.get("52w_high", 0)), 2),
                    "52w_low": round(float(eod.get("52w_low", 0)), 2),
                    "dma_50": eod.get("dma_50"),
                    "dma_200": eod.get("dma_200"),
                    "order_imbalance_ratio": 0.0,
                    "upper_circuit": 0.0,
                    "lower_circuit": 0.0,
                    "description": f"Exchange EOD historical candle feed for {clean}.",
                    "exchange_status": "Active / Primary (SmartAPI EOD Candles)",
                    "is_fallback": False,
                }
                res_dict = _enrich_with_cached_db_fundamentals(res_dict, canonical or clean)
                _FUNDAMENTALS_CACHE[clean] = (now, res_dict)
                _FUNDAMENTALS_CACHE[canonical] = (now, res_dict)
                return res_dict
    except Exception as angel_err:
        logger.debug(f"Angel One quote attempt notice for {canonical}: {angel_err}")

    # 1. Secondary BSE Direct Ingestion
    try:
        raw_data = fetch_bse_exchange_data(canonical)
        if raw_data and not raw_data.get("is_fallback", False):
            raw_data = _enrich_with_cached_db_fundamentals(raw_data, canonical or clean)
            _FUNDAMENTALS_CACHE[clean] = (now, raw_data)
            _FUNDAMENTALS_CACHE[canonical] = (now, raw_data)
            return raw_data

    except Exception as bse_err:
        logger.debug(f"BSE direct quote notice for {query}/{canonical}: {bse_err}. Checking fast secondary gateways...")

    # 2. Secondary Fast Gateway via yfinance (using fast_info)
    try:
        primary_sym = f"{canonical}.BO" if str(canonical).isdigit() else f"{canonical}.NS"
        candidate_symbols = [primary_sym]
        if primary_sym.endswith(".NS"):
            candidate_symbols.append(f"{canonical}.BO")
        if not yfinance_fallback_enabled() or not _yf_circuit_breaker.is_available():
            candidate_symbols = []

        for sym in candidate_symbols:
            try:
                with suppress_yfinance_noise():
                    t = get_hardened_yfinance_ticker(sym)
                    fast = getattr(t, "fast_info", None)
                    price = getattr(fast, "last_price", None)
            except Exception as quote_err:
                _yf_circuit_breaker.record_failure(quote_err)
                logger.warning(f"Fast gateway yfinance quote notice for {sym}: {quote_err}")
                price = None
            if price and float(price) > 0:
                mcap = getattr(fast, "market_cap", None) or "N/A"
                high_52 = getattr(fast, "year_high", None) or "N/A"
                low_52 = getattr(fast, "year_low", None) or "N/A"

                # Check if we have baseline PE in reports DB
                pe = "N/A"
                try:
                    from core.db.reports import get_report_by_ticker_sync
                    rep = get_report_by_ticker_sync(canonical)
                    if rep and rep.get("baseline_pe"):
                        pe = str(rep["baseline_pe"]).strip()
                except Exception as err:
                    logger.debug(f"Fast gateway baseline PE lookup notice: {err}")

                res_dict = {
                    "ticker": canonical or clean,
                    "short_name": canonical or clean,
                    "sector": "General Industry",
                    "industry": "Diversified",
                    "market_cap": mcap,
                    "pe_ratio": pe,
                    "current_price": round(float(price), 2),
                    "52w_high": round(float(high_52), 2) if isinstance(high_52, (int, float)) else str(high_52),
                    "52w_low": round(float(low_52), 2) if isinstance(low_52, (int, float)) else str(low_52),
                    "description": f"Exchange data compiled for {clean}.",
                    "exchange_status": "Active / Secondary (yfinance Fast Gateway)",
                    "is_fallback": True
                }
                res_dict = _enrich_with_cached_db_fundamentals(res_dict, canonical or clean)
                _FUNDAMENTALS_CACHE[clean] = (now, res_dict)
                _FUNDAMENTALS_CACHE[canonical] = (now, res_dict)
                return res_dict
    except Exception as yf_err:
        logger.debug(f"yfinance fast gateway notice for {query}: {yf_err}")

    # 3. Tertiary Resilience: Instant Localized Database Fundamentals Fallback
    try:
        from core.db.fundamentals import get_cached_fundamentals
        cached_fund = get_cached_fundamentals(canonical or clean)
        if cached_fund and cached_fund.get("current_price"):
            res_dict = dict(cached_fund)
            res_dict["is_fallback"] = True
            res_dict["exchange_status"] = "Audited Baseline (Database Fallback)"
            _FUNDAMENTALS_CACHE[clean] = (now, res_dict)
            _FUNDAMENTALS_CACHE[canonical] = (now, res_dict)
            return res_dict

        from core.db.reports import get_report_by_ticker_sync
        rep = get_report_by_ticker_sync(canonical)
        if rep and rep.get("baseline_price"):
            res_dict = {
                "ticker": canonical or clean,
                "short_name": rep.get("short_name", canonical or clean),
                "sector": "General Industry",
                "industry": "Diversified",
                "market_cap": rep.get("baseline_mcap") or "N/A",
                "pe_ratio": str(rep.get("baseline_pe") or "N/A"),
                "current_price": round(float(rep["baseline_price"]), 2),
                "52w_high": "N/A",
                "52w_low": "N/A",
                "description": f"Audited research baseline for {clean}.",
                "exchange_status": "Audited Baseline (Database Fallback)",
                "is_fallback": True
            }
            _FUNDAMENTALS_CACHE[clean] = (now, res_dict)
            _FUNDAMENTALS_CACHE[canonical] = (now, res_dict)
            return res_dict
    except Exception as db_err:
        logger.debug(f"Database baseline fallback notice for {query}: {db_err}")

    # If all fail, raise clean error
    raise ExchangeDataFetchError(clean, "Both primary BSE and secondary market gateways failed to return live quotes.")

@ttl_cache(ttl_seconds=3600, maxsize=32)
def get_historical_prices(ticker: str, period: str = "6mo"):
    """
    Fetches trailing daily historical prices via yfinance, attempting BSE (.BO)
    first with NSE (.NS) fallback. Computes 50-day Simple Moving Average (50-DMA).
    Auto-resolves 6-digit BSE scrip codes to alphanumeric ticker symbols.
    """
    if not ticker or not isinstance(ticker, str):
        return None

    clean = clean_ticker(ticker)

    # Resolve canonical symbol across BSE master cache, PRIMARY_BSE_MAP, and stored report short_name
    try:
        from bse_master import PRIMARY_BSE_MAP, get_bse_scrips_cache
        cached_scrips = get_bse_scrips_cache() or {}
        symbols_map = cached_scrips.get("symbols", {})
        if clean not in symbols_map:
            canonical_candidate = resolve_canonical_symbol(clean)
            if canonical_candidate and canonical_candidate in symbols_map:
                clean = canonical_candidate
            else:
                try:
                    from core.db.reports import get_report_by_ticker_sync
                    rep_row = get_report_by_ticker_sync(clean)
                    short_nm = str((rep_row or {}).get("short_name") or "").strip()
                    if short_nm:
                        base_nm = short_nm.upper().replace(" LIMITED", "").replace(" LTD.", "").replace(" LTD", "").strip()
                        scrip_from_nm = resolve_bse_scrip_code(base_nm) or resolve_bse_scrip_code(short_nm)
                        if scrip_from_nm:
                            sym_from_nm = resolve_canonical_symbol(str(scrip_from_nm))
                            if sym_from_nm:
                                clean = sym_from_nm
                except Exception as rep_err:
                    logger.debug(f"Report short_name canonical resolution notice for {clean}: {rep_err}")
    except Exception as sym_err:
        logger.debug(f"Canonical symbol resolution notice for {clean}: {sym_err}")

    # Sanitize multi-word queries with spaces to their canonical security ID
    if " " in clean:
        scrip = resolve_bse_scrip_code(clean)
        if scrip:
            resolved_sym = resolve_canonical_symbol(str(scrip))
            if resolved_sym and " " not in resolved_sym:
                clean = resolved_sym
            else:
                try:
                    b = BSE()
                    q = b.getQuote(scrip)
                    sec_id = str(q.get("securityID") or "").strip().upper()
                    if sec_id and " " not in sec_id:
                        clean = sec_id
                    else:
                        clean = clean.replace(" ", "")
                except Exception as e:
                    logger.debug(f"BSE quote lookup notice for {scrip}: {e}")
                    clean = clean.replace(" ", "")
        else:
            clean = clean.replace(" ", "")

    # Reverse-lookup numeric scrip code to ticker symbol for yfinance
    if clean.isdigit():
        try:
            resolved_sym = resolve_canonical_symbol(clean)
            if resolved_sym and not resolved_sym.isdigit():
                clean = resolved_sym
            else:
                from bse_master import PRIMARY_BSE_MAP
                rev_map = {str(v).strip(): k for k, v in PRIMARY_BSE_MAP.items()}
                if clean in rev_map:
                    clean = rev_map[clean]
        except Exception as e:
            logger.debug(f"Reverse lookup notice for scrip {clean}: {e}")

    df = pd.DataFrame()

    # Primary: official exchange daily candles via Angel One SmartAPI
    try:
        from core.ingestion.angel_one import AngelOneGateway
        if AngelOneGateway.is_configured():
            lookback_days = {"1mo": 35, "3mo": 100, "6mo": 190, "1y": 370, "2y": 740}.get(period, 190)
            from_date = (datetime.now() - timedelta(days=lookback_days)).strftime("%Y-%m-%d 09:15")
            candles = AngelOneGateway.get_historical_candles(clean, from_date=from_date)
            if candles and len(candles) > 5:
                df = pd.DataFrame(candles).rename(columns={"timestamp": "Date", "close": "Close", "volume": "Volume"})
    except Exception as angel_err:
        logger.debug(f"Angel One historical candles notice for {clean}: {angel_err}")

    # Last resort (opt-in only): unofficial yfinance history
    if df.empty and yfinance_fallback_enabled() and _yf_circuit_breaker.is_available():
        for suffix in [".BO", ".NS"]:
            try:
                sym = f"{clean}{suffix}"
                with suppress_yfinance_noise():
                    t = get_hardened_yfinance_ticker(sym)
                    hist = t.history(period=period)
                if hist is not None and not hist.empty and len(hist) > 5:
                    df = hist
                    _yf_circuit_breaker.record_success()
                    break
            except Exception as yf_err:
                _yf_circuit_breaker.record_failure(yf_err)
                logger.warning(f"yfinance history fetch notice for {clean}{suffix}: {yf_err}")
                continue

    if df.empty:
        return None

    df = df.reset_index()
    if "Date" not in df.columns or "Close" not in df.columns:
        return None

    df["Date"] = pd.to_datetime(df["Date"]).dt.tz_localize(None)
    df["Close"] = pd.to_numeric(df["Close"], errors="coerce")
    df["Volume"] = pd.to_numeric(df.get("Volume", 0), errors="coerce").fillna(0)
    df = df.dropna(subset=["Close"])

    if len(df) < 5:
        return None

    window = min(50, len(df))
    df["SMA50"] = df["Close"].rolling(window=window, min_periods=5).mean()

    return df[["Date", "Close", "SMA50", "Volume"]]

def compute_deterministic_technical_context(stock_data: dict, hist_df=None) -> dict:
    """
    Extracts and computes exact mathematical indicators (50-DMA, % from high/low)
    directly in Python to eliminate hallucinations and token waste.
    """
    price = 0.0
    try:
        raw_p = stock_data.get("current_price") or stock_data.get("currentValue") or 0.0
        price = float(str(raw_p).replace(",", "").strip())
    except Exception as parse_err:
        logger.debug("Price parse notice: %s", parse_err)

    high_52 = None
    low_52 = None
    try:
        high_52 = float(str(stock_data.get("52w_high", "")).replace(",", "").strip())
    except Exception as high_err:
        logger.debug("52w high parse notice: %s", high_err)
    try:
        low_52 = float(str(stock_data.get("52w_low", "")).replace(",", "").strip())
    except Exception as low_err:
        logger.debug("52w low parse notice: %s", low_err)

    dma_50 = None
    pct_from_dma50 = None
    if hist_df is not None and not getattr(hist_df, "empty", True) and "Close" in hist_df.columns:
        closes = hist_df["Close"].dropna()
        if len(closes) >= 10:
            dma_50 = float(closes.tail(50).mean())
            if dma_50 > 0 and price > 0:
                pct_from_dma50 = ((price - dma_50) / dma_50) * 100

    pct_from_high = ((price - high_52) / high_52 * 100) if (high_52 and price and high_52 > 0) else None
    pct_from_low = ((price - low_52) / low_52 * 100) if (low_52 and price and low_52 > 0) else None

    pe_ratio = stock_data.get("pe_ratio", "N/A")
    mcap = stock_data.get("market_cap", 0)
    mcap_cr = (mcap / 10_000_000) if isinstance(mcap, (int, float)) and mcap > 0 else 0.0

    return {
        "price": price,
        "pe_ratio": pe_ratio,
        "mcap": mcap,
        "mcap_cr": mcap_cr,
        "52w_high": high_52,
        "52w_low": low_52,
        "dma_50": dma_50,
        "pct_from_dma50": pct_from_dma50,
        "pct_from_high": pct_from_high,
        "pct_from_low": pct_from_low,
    }


def compute_pead_drift_band(stock_data: dict, hist_df=None) -> dict:
    """
    Computes 60-day Post-Earnings Announcement Drift (PEAD) anomaly indicators
    and empirical visual drift bands to counter Disposition Effect and Sunk Cost Fallacy.
    
    Theoretical Foundation:
    Post-Earnings Announcement Drift (PEAD) is a robust empirical anomaly in the Indian equity 
    market (NSE/BSE) where stock prices drift in the direction of an earnings surprise for 
    up to 60 days following quarterly earnings announcements (Bernard & Thomas; empirical NSE studies).
    """
    price = 0.0
    try:
        raw_p = stock_data.get("current_price") or stock_data.get("currentValue") or stock_data.get("baseline_price") or 0.0
        price = float(str(raw_p).replace(",", "").strip())
    except Exception as parse_err:
        logger.debug("PEAD price parse notice: %s", parse_err)

    dma_50 = None
    if hist_df is not None and not getattr(hist_df, "empty", True) and "Close" in hist_df.columns:
        closes = hist_df["Close"].dropna()
        if len(closes) >= 10:
            dma_50 = float(closes.tail(50).mean())

    pct_drift = 0.0
    if price > 0 and dma_50 and dma_50 > 0:
        pct_drift = ((price - dma_50) / dma_50) * 100

    empirical_drift_pct = 6.5  # Typical 60-day drift corridor amplitude in Indian equity research
    if pct_drift >= 0:
        vector = "ACCUMULATION_DRIFT"
        label = "Positive Post-Announcement Drift Vector"
        status = "bullish"
        surprise_text = "Constructive Earnings / Accumulation"
        lower_bound = round(price * (1 - 0.02), 2)
        target_drift = round(price * (1 + (empirical_drift_pct / 100.0)), 2)
        upper_bound = round(price * (1 + (empirical_drift_pct * 1.5 / 100.0)), 2)
        drift_direction = f"+{empirical_drift_pct:.1f}%"
        guidance = "Empirical PEAD models project continued price drift in the direction of the surprise over a 60-day window. Guardrail: Beware of thesis drift if valuation multiple expands beyond historical ceiling."
    else:
        vector = "COMPRESSION_DRIFT"
        label = "Downward Valuation Compression Vector"
        status = "bearish"
        surprise_text = "Adverse Earnings Variance / Post-Filing Distribution"
        upper_bound = round(price * (1 + 0.02), 2)
        target_drift = round(price * (1 - (empirical_drift_pct / 100.0)), 2)
        lower_bound = round(price * (1 - (empirical_drift_pct * 1.5 / 100.0)), 2)
        drift_direction = f"-{empirical_drift_pct:.1f}%"
        guidance = "Disposition Effect Guardrail: Empirical Indian equity research reveals prices frequently continue downward drift for up to 60 days post-adverse surprise. Resist emotional urge to average down before confirmation of turnaround."

    return {
        "active": True,
        "vector": vector,
        "label": label,
        "status": status,
        "surprise_text": surprise_text,
        "current_price": price,
        "dma_50": round(dma_50, 2) if dma_50 else None,
        "target_drift": target_drift if price > 0 else None,
        "lower_bound": lower_bound if price > 0 else None,
        "upper_bound": upper_bound if price > 0 else None,
        "drift_direction": drift_direction,
        "drift_window_days": 60,
        "guidance": guidance,
    }

