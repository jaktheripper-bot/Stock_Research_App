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
from core.analysis.exceptions import ExchangeDataFetchError
from core.config import get_secret

logger = logging.getLogger("equity_research.core.analysis.fundamentals")

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
            with lock:
                if len(cache) >= maxsize:
                    try:
                        oldest = min(cache.keys(), key=lambda k: cache[k][1])
                        cache.pop(oldest, None)
                    except Exception:
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

def get_eodhd_api_key() -> str:
    """Safely retrieves EODHD API token from environment or secrets."""
    for key_name in ["EODHD_API_KEY", "EOHD_API_KEY"]:
        key = get_secret(key_name)
        if key and str(key).strip() and not str(key).strip().startswith("your_"):
            return str(key).strip()
    return ""

_EODHD_SUPPORTED = {"NSE": False, "BSE": False, "tested": False}

def fetch_eodhd_stock_data(query: str, scrip_code: str = "") -> dict:
    """
    Fetches real-time quotes and fundamental metrics from European vendor EODHD (https://eodhd.com).
    Supports .NSE and .BSE exchange suffixes for broad Indian market coverage.
    Returns normalized stock data dictionary or None if key is absent or fetch fails.
    """
    token = get_eodhd_api_key()
    if not token:
        return None

    global _EODHD_SUPPORTED
    if _EODHD_SUPPORTED["tested"] and not _EODHD_SUPPORTED["NSE"] and not _EODHD_SUPPORTED["BSE"]:
        # Indian exchange coverage not active on this EODHD plan
        return None

    clean = clean_ticker(query).upper()
    candidates = []
    if "." in query:
        candidates.append(query.upper())
    if scrip_code and str(scrip_code).isdigit():
        candidates.append(f"{scrip_code}.BSE")
    if not clean.isdigit():
        candidates.append(f"{clean}.NSE")
        candidates.append(f"{clean}.BSE")

    for symbol in candidates:
        try:
            # 1. Fetch Real-Time Quote with rapid 1.5s timeout
            quote_url = f"https://eodhd.com/api/real-time/{symbol}?api_token={token}&fmt=json"
            q_res = requests.get(quote_url, timeout=1.5)
            if q_res.status_code in (403, 404):
                _EODHD_SUPPORTED["tested"] = True
                _EODHD_SUPPORTED["NSE"] = False
                _EODHD_SUPPORTED["BSE"] = False
                return None
            if q_res.status_code != 200:
                continue
            q_json = q_res.json()
            if not isinstance(q_json, dict) or not q_json.get("close"):
                continue

            price = float(q_json.get("close", 0))
            if price <= 0:
                continue

            # 2. Fetch Fundamentals (filtered to General, Highlights, Valuation, Technicals)
            fund_url = f"https://eodhd.com/api/v1.1/fundamentals/{symbol}?api_token={token}&filter=General,Highlights,Valuation,Technicals&fmt=json"
            f_res = requests.get(fund_url, timeout=6)
            f_json = f_res.json() if f_res.status_code == 200 and isinstance(f_res.json(), dict) else {}

            gen = f_json.get("General") or {}
            hl = f_json.get("Highlights") or {}
            val = f_json.get("Valuation") or {}

            # Parse MCap
            mcap = hl.get("MarketCapitalization") or "N/A"
            if mcap and str(mcap).replace(".", "").isdigit():
                mcap = int(float(mcap))

            # Parse PE
            pe = hl.get("PERatio") or val.get("TrailingPE") or "N/A"
            if isinstance(pe, (int, float)):
                pe = f"{float(pe):.2f}" if float(pe) > 0 else "N/A (Loss-Making)"

            high_52 = q_json.get("high") or "N/A"
            low_52 = q_json.get("low") or "N/A"

            return {
                "ticker": clean,
                "short_name": gen.get("Name") or clean,
                "scrip_code": scrip_code or (clean if clean.isdigit() else ""),
                "current_price": round(price, 2),
                "market_cap": mcap,
                "pe_ratio": pe,
                "sector": gen.get("Sector") or "Core Industry",
                "industry": gen.get("Industry") or "General Corporate",
                "52w_high": high_52,
                "52w_low": low_52,
                "description": gen.get("Description") or f"EODHD verified exchange quote for {clean}.",
                "exchange_status": "Active / Verified (EODHD REST)",
                "is_fallback": False
            }
        except Exception as e:
            logger.debug(f"EODHD probe notice for {symbol}: {e}")
            continue

    return None

def enrich_fundamentals(ticker: str, data: dict) -> dict:
    """Enriches stock fundamentals with institutional ratios (EODHD if token present, fallback to yfinance)."""
    # 1. Primary EODHD Fundamental Enrichment (if configured and supported)
    token = get_eodhd_api_key()
    global _EODHD_SUPPORTED
    if token and not (_EODHD_SUPPORTED["tested"] and not _EODHD_SUPPORTED["NSE"]):
        try:
            clean_sym = clean_ticker(ticker).upper()
            candidates = [f"{clean_sym}.NSE", f"{clean_sym}.BSE"] if not clean_sym.isdigit() else [f"{clean_sym}.BSE"]
            for sym in candidates:
                url = f"https://eodhd.com/api/v1.1/fundamentals/{sym}?api_token={token}&filter=General,Highlights,Valuation,Technicals&fmt=json"
                res = requests.get(url, timeout=1.5)
                if res.status_code in (403, 404):
                    _EODHD_SUPPORTED["tested"] = True
                    _EODHD_SUPPORTED["NSE"] = False
                    _EODHD_SUPPORTED["BSE"] = False
                    break
                if res.status_code == 200 and isinstance(res.json(), dict):
                    f_json = res.json()
                    gen = f_json.get("General") or {}
                    hl = f_json.get("Highlights") or {}
                    val = f_json.get("Valuation") or {}

                    # Trailing P/E
                    if data.get("pe_ratio") in [None, "N/A", "-", "", 0, "0"]:
                        pe = hl.get("PERatio") or val.get("TrailingPE")
                        if pe is not None and isinstance(pe, (int, float)):
                            data["pe_ratio"] = round(pe, 2) if pe > 0 else "N/A (Loss-Making)"

                    # Market Cap
                    if data.get("market_cap") in [None, "N/A", 0, "-", "", "0"]:
                        mcap = hl.get("MarketCapitalization")
                        if mcap and isinstance(mcap, (int, float)):
                            data["market_cap"] = int(mcap)

                    # Sector & Industry
                    if data.get("sector") in [None, "N/A", "-", "", "Core Industry", "Diversified / Core Industry"]:
                        sec = gen.get("Sector")
                        if sec:
                            data["sector"] = sec
                    if data.get("industry") in [None, "N/A", "-", "", "General Corporate"]:
                        ind = gen.get("Industry")
                        if ind:
                            data["industry"] = ind

                    # Forward P/E
                    if not data.get("forward_pe") or data.get("forward_pe") == "N/A":
                        fpe = val.get("ForwardPE")
                        if fpe and isinstance(fpe, (int, float)) and fpe > 0:
                            data["forward_pe"] = f"{float(fpe):.2f}"

                    # Price to Book
                    if not data.get("price_to_book") or data.get("price_to_book") == "N/A":
                        pb = val.get("PriceBookMRQ")
                        if pb and isinstance(pb, (int, float)) and pb > 0:
                            data["price_to_book"] = f"{float(pb):.2f}"

                    # EV to EBITDA
                    if not data.get("ev_to_ebitda") or data.get("ev_to_ebitda") == "N/A":
                        eve = val.get("EnterpriseValueEbitda")
                        if eve and isinstance(eve, (int, float)) and 0 < eve < 500:
                            data["ev_to_ebitda"] = f"{float(eve):.2f}"

                    # ROE
                    if not data.get("roe") or data.get("roe") == "N/A":
                        roe = hl.get("ReturnOnEquityTTM")
                        if roe is not None and isinstance(roe, (int, float)):
                            data["roe"] = f"{float(roe * 100):.1f}%"

                    # OPM
                    if not data.get("opm") or data.get("opm") == "N/A":
                        opm = hl.get("OperatingMarginTTM")
                        if opm is not None and isinstance(opm, (int, float)):
                            data["opm"] = f"{float(opm * 100):.1f}%"

                    # Dividend Yield
                    if not data.get("dividend_yield") or data.get("dividend_yield") == "N/A":
                        dy = hl.get("DividendYield")
                        if dy is not None and isinstance(dy, (int, float)):
                            val_dy = dy if dy > 1 else dy * 100
                            data["dividend_yield"] = f"{float(val_dy):.2f}%"

                    break
        except Exception as e:
            logger.debug(f"EODHD fundamental enrichment notice: {e}")

    # 2. Secondary enrichment: yfinance backfill
    try:
        clean_sym = clean_ticker(ticker)
        yf_ticker = f"{clean_sym}.BO" if clean_sym.isdigit() else f"{clean_sym}.NS"
        info = yf.Ticker(yf_ticker).info or {}

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
        if data.get("sector") in [None, "N/A", "-", "", "Core Industry", "Diversified / Core Industry"]:
            sec = info.get("sector")
            if sec:
                data["sector"] = sec
        if data.get("industry") in [None, "N/A", "-", "", "General Corporate"]:
            ind = info.get("industry")
            if ind:
                data["industry"] = ind

        # Institutional Financial Ratios Enrichment
        fpe = info.get("forwardPE")
        if fpe and isinstance(fpe, (int, float)) and fpe > 0:
            data["forward_pe"] = f"{float(fpe):.2f}"
        else:
            data["forward_pe"] = data.get("forward_pe", "N/A")

        pb = info.get("priceToBook")
        if pb and isinstance(pb, (int, float)) and pb > 0:
            data["price_to_book"] = f"{float(pb):.2f}"
        else:
            data["price_to_book"] = data.get("price_to_book", "N/A")

        eve = info.get("enterpriseToEbitda")
        if eve and isinstance(eve, (int, float)) and 0 < eve < 500:
            data["ev_to_ebitda"] = f"{float(eve):.2f}"
        else:
            data["ev_to_ebitda"] = data.get("ev_to_ebitda", "N/A")

        roe = info.get("returnOnEquity")
        if roe is not None and isinstance(roe, (int, float)):
            data["roe"] = f"{float(roe * 100):.1f}%"
        else:
            data["roe"] = data.get("roe", "N/A")

        opm = info.get("operatingMargins")
        if opm is not None and isinstance(opm, (int, float)):
            data["opm"] = f"{float(opm * 100):.1f}%"
        else:
            data["opm"] = data.get("opm", "N/A")

        npm = info.get("profitMargins")
        if npm is not None and isinstance(npm, (int, float)):
            data["npm"] = f"{float(npm * 100):.1f}%"
        else:
            data["npm"] = data.get("npm", "N/A")

        de = info.get("debtToEquity")
        if de is not None and isinstance(de, (int, float)):
            data["debt_to_equity"] = f"{float(de):.2f}"
        else:
            data["debt_to_equity"] = data.get("debt_to_equity", "N/A")

        dy = info.get("dividendYield")
        if dy is not None and isinstance(dy, (int, float)):
            val = dy if dy > 1 else dy * 100
            data["dividend_yield"] = f"{float(val):.2f}%"
        else:
            data["dividend_yield"] = data.get("dividend_yield", "N/A")

        cr = info.get("currentRatio")
        if cr is not None and isinstance(cr, (int, float)):
            data["current_ratio"] = f"{float(cr):.2f}"
        else:
            data["current_ratio"] = data.get("current_ratio", "N/A")
    except Exception as e:
        logger.warning(f"Background fundamental enrichment notice: {e}")
    return data

def resolve_pe_with_failsafes(ticker: str, scrip: str = "") -> str:
    clean = clean_ticker(ticker).replace(" ", "")
    # Tier 1: Consolidated yfinance
    try:
        symbols = [f"{clean}.NS", f"{clean}.BO"]
        if scrip and str(scrip).isdigit():
            symbols.append(f"{scrip}.BO")
        with contextlib.redirect_stderr(io.StringIO()):
            for s in symbols:
                try:
                    tk = yf.Ticker(s)
                    info = tk.info or {}
                    trailing_eps = info.get("trailingEps")
                    trailing_pe = info.get("trailingPE")
                    if trailing_eps is not None and float(trailing_eps) <= 0:
                        return "N/A (Loss-Making)"
                    if trailing_pe and float(trailing_pe) > 0:
                        return f"{float(trailing_pe):.2f}"
                except Exception as err:
                    logger.debug(f"yfinance Ticker probe notice for {s}: {err}")
                    continue
    except Exception as e:
        logger.debug(f"P/E resolution via yfinance failed: {e}")

    # Tier 2: BSE ComHeader Direct
    if scrip and str(scrip).isdigit():
        try:
            url = f"https://api.bseindia.com/BseIndiaAPI/api/ComHeader/w?quotetype=EQ&scripcode={scrip}&seriesid="
            headers = {"User-Agent": "Mozilla/5.0", "Referer": "https://www.bseindia.com/"}
            res = requests.get(url, headers=headers, timeout=3)
            if res.status_code == 200:
                raw_pe = res.json().get("PE")
                if raw_pe and str(raw_pe).strip() not in ["", "-", "None", "0", "0.00"]:
                    val = float(str(raw_pe).replace(",", "").strip())
                    return f"{val:.2f}" if val > 0 else "N/A (Loss-Making)"
        except Exception as e:
            logger.debug(f"BSE ComHeader direct P/E fetch notice: {e}")
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
    except Exception:
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

_FUNDAMENTALS_CACHE = {}

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
        if (now - ts) < 300:  # 5 min TTL
            return dict(cached_val)

    canonical = resolve_canonical_symbol(query) or clean
    scrip = resolve_bse_scrip_code(query) or resolve_bse_scrip_code(canonical)
    
    # 1. Primary BSE Ingestion
    try:
        raw_data = fetch_bse_exchange_data(canonical)
        if raw_data and not raw_data.get("is_fallback", False):
            _FUNDAMENTALS_CACHE[clean] = (now, raw_data)
            _FUNDAMENTALS_CACHE[canonical] = (now, raw_data)
            return raw_data
    except Exception as bse_err:
        logger.warning(f"BSE direct quote failed for {query}/{canonical} ({bse_err}). Attempting secondary gateways...")

    # 2. Secondary Resilience: EODHD REST Gateway (European vendor, comprehensive BSE/NSE)
    try:
        eodhd_data = fetch_eodhd_stock_data(canonical, scrip)
        if eodhd_data:
            logger.info(f"Resolved verified quote for {canonical} via EODHD REST API.")
            return eodhd_data
    except Exception as eodhd_err:
        logger.debug(f"EODHD REST gateway notice for {canonical}: {eodhd_err}")

    # 3. Tertiary Resilience Fallback via yfinance
    try:
        candidate_symbols = [f"{canonical}.NS", f"{canonical}.BO"]
        if clean != canonical:
            candidate_symbols.extend([f"{clean}.NS", f"{clean}.BO"])
        for sym in candidate_symbols:
            t = yf.Ticker(sym)
            fast = getattr(t, "fast_info", None)
            info = {}
            try:
                info = t.info or {}
            except Exception as err:
                logger.debug(f"yfinance info notice for {sym}: {err}")

            price = None
            if fast and hasattr(fast, "last_price") and fast.last_price:
                price = fast.last_price
            elif info.get("currentPrice"):
                price = info.get("currentPrice")
            elif info.get("regularMarketPrice"):
                price = info.get("regularMarketPrice")

            if price:
                mcap = getattr(fast, "market_cap", None) or info.get("marketCap") or "N/A"
                pe = info.get("trailingPE") or info.get("forwardPE") or "N/A"
                if isinstance(pe, (int, float)) and pe <= 0:
                    pe = "N/A"

                res_dict = {
                    "ticker": canonical or clean,
                    "short_name": info.get("shortName") or info.get("longName") or canonical or clean,
                    "sector": info.get("sector") or "General Industry",
                    "industry": info.get("industry") or "Diversified",
                    "market_cap": mcap,
                    "pe_ratio": f"{pe:.2f}" if isinstance(pe, (int, float)) else str(pe),
                    "current_price": round(price, 2),
                    "52w_high": getattr(fast, "year_high", None) or info.get("fiftyTwoWeekHigh") or "N/A",
                    "52w_low": getattr(fast, "year_low", None) or info.get("fiftyTwoWeekLow") or "N/A",
                    "description": info.get("longBusinessSummary") or f"Exchange data synthesized for {clean}.",
                    "exchange_status": "Active / Secondary (yfinance Fallback)",
                    "is_fallback": True
                }
                _FUNDAMENTALS_CACHE[clean] = (now, res_dict)
                _FUNDAMENTALS_CACHE[canonical] = (now, res_dict)
                return res_dict
    except Exception as yf_err:
        logger.error(f"yfinance fallback also failed for {query}: {yf_err}")

    # If both fail, raise clean error
    raise ExchangeDataFetchError(clean, "Both primary BSE and secondary market gateways failed to return live quotes.")

@ttl_cache(ttl_seconds=900, maxsize=128)
def get_historical_prices(ticker: str, period: str = "6mo"):
    """
    Fetches trailing daily historical prices via yfinance, attempting BSE (.BO)
    first with NSE (.NS) fallback. Computes 50-day Simple Moving Average (50-DMA).
    Auto-resolves 6-digit BSE scrip codes to alphanumeric ticker symbols.
    """
    if not ticker or not isinstance(ticker, str):
        return None

    clean = clean_ticker(ticker)

    # Sanitize multi-word queries with spaces to their canonical security ID
    if " " in clean:
        scrip = resolve_bse_scrip_code(clean)
        if scrip:
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
            from bse_master import PRIMARY_BSE_MAP
            rev_map = {str(v).strip(): k for k, v in PRIMARY_BSE_MAP.items()}
            if clean in rev_map:
                clean = rev_map[clean]
        except Exception as e:
            logger.debug(f"Reverse lookup notice for scrip {clean}: {e}")

    df = pd.DataFrame()
    for suffix in [".BO", ".NS"]:
        try:
            sym = f"{clean}{suffix}"
            t = yf.Ticker(sym)
            hist = t.history(period=period)
            if hist is not None and not hist.empty and len(hist) > 5:
                df = hist
                break
        except Exception:
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
    except Exception:
        pass

    high_52 = None
    low_52 = None
    try:
        high_52 = float(str(stock_data.get("52w_high", "")).replace(",", "").strip())
    except Exception:
        pass
    try:
        low_52 = float(str(stock_data.get("52w_low", "")).replace(",", "").strip())
    except Exception:
        pass

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
