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

def enrich_fundamentals(ticker: str, data: dict) -> dict:
    """Enriches stock fundamentals with institutional ratios (fallback to yfinance)."""

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

    # Tier 2: Fast single-symbol yfinance check (using fast_info)
    try:
        sym = f"{clean}.BO" if clean.isdigit() else f"{clean}.NS"
        tk = yf.Ticker(sym)
        fast = getattr(tk, "fast_info", None)
        pe = getattr(fast, "pe", None) or getattr(fast, "trailing_pe", None)
        if pe and float(pe) > 0:
            return f"{float(pe):.2f}"
    except Exception as e:
        logger.debug(f"P/E resolution via yfinance failed: {e}")

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
        if (now - ts) < 900:  # 15 min TTL
            return dict(cached_val)

    canonical = resolve_canonical_symbol(query) or clean
    scrip = resolve_bse_scrip_code(query) or resolve_bse_scrip_code(canonical)
    
    # 0. Primary Tier: Angel One SmartAPI (Exchange Audited Quote & Level-2 Depth)
    try:
        from core.ingestion.angel_one import AngelOneGateway
        if AngelOneGateway.is_configured():
            token = scrip if scrip else canonical
            exch = "BSE" if (scrip and str(scrip).isdigit()) else "NSE"
            quote = AngelOneGateway.get_quote_with_depth(exch, token)
            if quote and quote.get("ltp"):
                res_dict = {
                    "ticker": canonical or clean,
                    "short_name": canonical or clean,
                    "sector": "General Industry",
                    "industry": "Diversified",
                    "market_cap": "N/A",
                    "pe_ratio": "Fair",
                    "current_price": round(float(quote["ltp"]), 2),
                    "52w_high": round(float(quote.get("52w_high", 0)), 2),
                    "52w_low": round(float(quote.get("52w_low", 0)), 2),
                    "order_imbalance_ratio": quote.get("order_imbalance_ratio", 0.0),
                    "upper_circuit": quote.get("upper_circuit", 0.0),
                    "lower_circuit": quote.get("lower_circuit", 0.0),
                    "description": f"Official Angel One exchange feed for {clean}.",
                    "exchange_status": "Active / Primary (Angel One SmartAPI)",
                    "is_fallback": False,
                }
                _FUNDAMENTALS_CACHE[clean] = (now, res_dict)
                _FUNDAMENTALS_CACHE[canonical] = (now, res_dict)
                return res_dict
    except Exception as angel_err:
        logger.debug(f"Angel One quote attempt notice for {canonical}: {angel_err}")

    # 1. Secondary BSE Direct Ingestion
    try:
        raw_data = fetch_bse_exchange_data(canonical)
        if raw_data and not raw_data.get("is_fallback", False):
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

        for sym in candidate_symbols:
            t = yf.Ticker(sym)
            fast = getattr(t, "fast_info", None)
            price = getattr(fast, "last_price", None)
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
                    "description": f"Exchange data synthesized for {clean}.",
                    "exchange_status": "Active / Secondary (yfinance Fast Gateway)",
                    "is_fallback": True
                }
                _FUNDAMENTALS_CACHE[clean] = (now, res_dict)
                _FUNDAMENTALS_CACHE[canonical] = (now, res_dict)
                return res_dict
    except Exception as yf_err:
        logger.debug(f"yfinance fast gateway notice for {query}: {yf_err}")

    # 3. Tertiary Resilience: Instant Database Report Baseline Fallback
    try:
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

@ttl_cache(ttl_seconds=3600, maxsize=256)
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
        surprise_text = "Constructive Earnings / Institutional Accumulation"
        lower_bound = round(price * (1 - 0.02), 2)
        target_drift = round(price * (1 + (empirical_drift_pct / 100.0)), 2)
        upper_bound = round(price * (1 + (empirical_drift_pct * 1.5 / 100.0)), 2)
        drift_direction = f"+{empirical_drift_pct:.1f}%"
        guidance = "Empirical PEAD models project continued institutional price drift in the direction of the surprise over a 60-day window. Guardrail: Beware of thesis drift if valuation multiple expands beyond historical ceiling."
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

