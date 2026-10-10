"""
Angel One SmartAPI Gateway with Selective Static Proxy Routing
============================================================
Provides official, exchange-authorized market data ingestion for Indian equities:
1. Selective Static Proxy Routing:
   - Routes ONLY Angel One SmartAPI traffic through SMARTAPI_PROXY_URL (e.g., QuotaGuard / Fixie).
   - Preserves proxy quota; all other traffic (Supabase DB, Gemini LLM, web assets) bypasses proxy.
2. Zero-Dependency RFC 6238 TOTP Generator:
   - Pure Python standard library implementation (hmac, hashlib, time, struct, base64).
   - Eliminates pyotp installation requirements.
3. Level-2 Market Depth & Order Imbalance Computation:
   - Evaluates institutional buying vs selling pressure from top-5 order books.
4. Seamless Fallback Resilience:
   - Gracefully falls back if credentials or proxy are unconfigured, returning None so secondary
     gateways (BSE Direct / yfinance fast_info) take over with zero user disruption.
"""

import os
import time
import json
import hmac
import hashlib
import struct
import base64
import socket
import logging
from typing import Optional, Dict, Any, Tuple
import requests

from core.config import get_secret

logger = logging.getLogger("equity_research.core.ingestion.angel_one")


def generate_rfc6238_totp(secret: str, digits: int = 6, interval: int = 30) -> str:
    """
    Generates a standard 6-digit Time-based One-Time Password (RFC 6238).
    Pure Python standard library implementation with zero external dependencies.
    """
    clean_secret = secret.strip().replace(" ", "").upper()
    # Add padding if required
    missing_padding = len(clean_secret) % 8
    if missing_padding:
        clean_secret += "=" * (8 - missing_padding)
    
    key = base64.b32decode(clean_secret)
    counter = int(time.time() // interval)
    msg = struct.pack(">Q", counter)
    digest = hmac.new(key, msg, hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    code = (struct.unpack(">I", digest[offset:offset + 4])[0] & 0x7FFFFFFF) % (10 ** digits)
    return str(code).zfill(digits)


class AngelOneGateway:
    """
    Exchange-compliant Angel One SmartAPI client with selective static proxy egress.
    """

    BASE_URL: str = "https://apiconnect.angelone.in"
    LOGIN_ENDPOINT: str = "/rest/auth/angelbroking/user/v1/loginByPassword"
    QUOTE_ENDPOINT: str = "/rest/secure/angelbroking/market/v1/quote/"
    HISTORICAL_ENDPOINT: str = "/rest/secure/angelbroking/historical/v1/getCandleData"

    _session_cache: Dict[str, Any] = {}
    _session_lock = False

    @classmethod
    def get_proxy_config(cls) -> Optional[Dict[str, str]]:
        """
        Returns the requests proxy dictionary if SMARTAPI_PROXY_URL is configured.
        """
        proxy_url = get_secret("SMARTAPI_PROXY_URL") or os.environ.get("SMARTAPI_PROXY_URL")
        if proxy_url and proxy_url.strip():
            p_clean = proxy_url.strip()
            return {
                "http": p_clean,
                "https": p_clean,
            }
        return None

    @classmethod
    def probe_outbound_ip(cls) -> Dict[str, Any]:
        """
        Probes the exact outbound public IPv4 address seen by external servers.
        Uses SMARTAPI_PROXY_URL if configured, otherwise direct connection.
        """
        proxies = cls.get_proxy_config()
        is_proxied = proxies is not None
        proxy_masked = ""
        if is_proxied and proxies:
            raw = proxies.get("http", "")
            if "@" in raw:
                auth, host = raw.split("@", 1)
                proxy_masked = f"{auth.split('://')[0]}://***:***@{host}"
            else:
                proxy_masked = raw

        endpoints = [
            "https://api.ipify.org?format=json",
            "https://ifconfig.me/all.json",
            "https://icanhazip.com",
        ]

        detected_ip = "Unknown"
        error_msg = None

        for ep in endpoints:
            try:
                resp = requests.get(ep, proxies=proxies, timeout=6)
                if resp.status_code == 200:
                    text = resp.text.strip()
                    if "ip" in text:
                        try:
                            detected_ip = resp.json().get("ip") or text
                        except Exception:
                            detected_ip = text
                    else:
                        detected_ip = text
                    break
            except Exception as e:
                error_msg = str(e)
                continue

        return {
            "outbound_ip": detected_ip,
            "is_proxied": is_proxied,
            "proxy_url_masked": proxy_masked,
            "status": "SUCCESS" if detected_ip != "Unknown" else "ERROR",
            "error": error_msg,
        }

    @classmethod
    def is_configured(cls) -> bool:
        """
        Returns True if all required Angel One SmartAPI credentials exist in environment.
        """
        api_key = get_secret("ANGEL_API_KEY") or os.environ.get("ANGEL_API_KEY")
        client_code = get_secret("ANGEL_CLIENT_CODE") or os.environ.get("ANGEL_CLIENT_CODE")
        pin = get_secret("ANGEL_PIN") or os.environ.get("ANGEL_PIN")
        totp_key = get_secret("ANGEL_TOTP_KEY") or os.environ.get("ANGEL_TOTP_KEY")
        return bool(api_key and client_code and pin and totp_key)

    @classmethod
    def authenticate(cls, force_refresh: bool = False) -> Optional[str]:
        """
        Authenticates with Angel One SmartAPI and caches the JWT bearer token.
        Returns the valid JWT token, or None if authentication fails.
        """
        now = time.time()
        cached = cls._session_cache.get("jwt_token")
        cached_exp = cls._session_cache.get("token_expiry", 0)

        if not force_refresh and cached and now < cached_exp:
            return cached

        if not cls.is_configured():
            logger.debug("Angel One SmartAPI credentials not fully configured; skipping.")
            return None

        api_key = (get_secret("ANGEL_API_KEY") or os.environ.get("ANGEL_API_KEY", "")).strip()
        client_code = (get_secret("ANGEL_CLIENT_CODE") or os.environ.get("ANGEL_CLIENT_CODE", "")).strip()
        pin = (get_secret("ANGEL_PIN") or os.environ.get("ANGEL_PIN", "")).strip()
        totp_key = (get_secret("ANGEL_TOTP_KEY") or os.environ.get("ANGEL_TOTP_KEY", "")).strip()

        try:
            totp_code = generate_rfc6238_totp(totp_key)
        except Exception as e:
            logger.error(f"Failed to generate RFC 6238 TOTP for Angel One: {e}")
            return None

        local_ip = "127.0.0.1"
        try:
            local_ip = socket.gethostbyname(socket.gethostname())
        except Exception:
            pass

        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "X-UserType": "USER",
            "X-SourceID": "WEB",
            "X-ClientLocalIP": local_ip,
            "X-ClientPublicIP": local_ip,
            "X-MACAddress": "00:00:00:00:00:00",
            "X-PrivateKey": api_key,
        }

        payload = {
            "clientcode": client_code,
            "password": pin,
            "totp": totp_code,
        }

        proxies = cls.get_proxy_config()
        url = f"{cls.BASE_URL}{cls.LOGIN_ENDPOINT}"

        try:
            logger.info("Connecting to Angel One SmartAPI auth gateway via selective proxy...")
            resp = requests.post(url, json=payload, headers=headers, proxies=proxies, timeout=10)
            data = resp.json()

            if resp.status_code == 200 and data.get("status") and data.get("data"):
                token_data = data["data"]
                jwt_token = token_data.get("jwtToken")
                feed_token = token_data.get("feedToken")
                # Token valid for ~20 hours (standard SmartAPI TTL is 24h)
                cls._session_cache = {
                    "jwt_token": jwt_token,
                    "feed_token": feed_token,
                    "token_expiry": now + (20 * 3600),
                }
                logger.info("Successfully established verified Angel One SmartAPI session.")
                return jwt_token
            else:
                err_code = data.get("errorcode", "UNKNOWN")
                err_msg = data.get("message", "Authentication rejected")
                logger.warning(f"Angel One SmartAPI login failed [{err_code}]: {err_msg}")
                if "IP" in err_msg or err_code in ["AG8001", "AB1004"]:
                    logger.error(
                        "Angel One IP Whitelist Alert: The outbound IP is not registered as the "
                        "Primary Static IP in your SmartAPI dashboard. Check scripts/verify_angel_proxy_ip.py."
                    )
                return None
        except Exception as req_err:
            logger.warning(f"Angel One SmartAPI connection notice: {req_err}")
            return None

    @classmethod
    def get_quote_with_depth(
        cls,
        exchange: str,
        symbol_token: str,
    ) -> Optional[Dict[str, Any]]:
        """
        Fetches Level-2 market depth (5-tier book) and calculates order imbalance.
        """
        jwt_token = cls.authenticate()
        if not jwt_token:
            return None

        api_key = (get_secret("ANGEL_API_KEY") or os.environ.get("ANGEL_API_KEY", "")).strip()
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "X-UserType": "USER",
            "X-SourceID": "WEB",
            "X-PrivateKey": api_key,
            "Authorization": f"Bearer {jwt_token}",
        }

        payload = {
            "mode": "FULL",
            "exchangeTokens": {
                exchange.upper(): [str(symbol_token)],
            },
        }

        proxies = cls.get_proxy_config()
        url = f"{cls.BASE_URL}{cls.QUOTE_ENDPOINT}"

        try:
            resp = requests.post(url, json=payload, headers=headers, proxies=proxies, timeout=6)
            data = resp.json()
            if resp.status_code == 200 and data.get("status") and data.get("data"):
                fetched = data["data"].get("fetched", [])
                if not fetched:
                    return None
                q = fetched[0]
                
                # Depth analysis: Order Imbalance Ratio
                depth = q.get("depth", {})
                buy_book = depth.get("buy", [])
                sell_book = depth.get("sell", [])
                
                tot_buy_qty = sum(float(b.get("quantity", 0)) for b in buy_book)
                tot_sell_qty = sum(float(s.get("quantity", 0)) for s in sell_book)
                
                denom = tot_buy_qty + tot_sell_qty
                imbalance_ratio = ((tot_buy_qty - tot_sell_qty) / denom) if denom > 0 else 0.0

                return {
                    "exchange": exchange.upper(),
                    "symbol_token": symbol_token,
                    "trading_symbol": q.get("tradingSymbol", ""),
                    "ltp": float(q.get("ltp", 0)),
                    "open": float(q.get("open", 0)),
                    "high": float(q.get("high", 0)),
                    "low": float(q.get("low", 0)),
                    "close": float(q.get("close", 0)),
                    "volume": int(q.get("volume", 0)),
                    "upper_circuit": float(q.get("upperCircuit", 0)),
                    "lower_circuit": float(q.get("lowerCircuit", 0)),
                    "52w_high": float(q.get("52WeekHigh", 0)),
                    "52w_low": float(q.get("52WeekLow", 0)),
                    "total_buy_qty": tot_buy_qty,
                    "total_sell_qty": tot_sell_qty,
                    "order_imbalance_ratio": round(imbalance_ratio, 3),
                    "depth_buy_5": buy_book,
                    "depth_sell_5": sell_book,
                    "source": "Angel One SmartAPI (Exchange Audited)",
                }
        except Exception as e:
            logger.debug(f"Angel One quote fetch notice: {e}")
            return None
        return None
