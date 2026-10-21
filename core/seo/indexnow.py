"""
Moatnomics IndexNow Instant Notification Engine
===============================================
Dispatches real-time IndexNow pings to search engines (Bing, Yandex, Copilot, ChatGPT Search)
upon publication or updates of asset dossiers and directories.

Reference: https://www.indexnow.org/documentation
"""

import os
import logging
from typing import List, Union, Optional
import requests
from core.config import get_secret

logger = logging.getLogger("equity_research.core.seo.indexnow")

INDEXNOW_ENDPOINT = "https://api.indexnow.org/indexnow"


def get_indexnow_key() -> str:
    """Retrieves configured IndexNow key from environment or secrets."""
    return str(get_secret("INDEXNOW_KEY") or os.getenv("INDEXNOW_KEY") or "").strip()


def ping_indexnow_urls(urls: Union[str, List[str]], host: Optional[str] = None) -> bool:
    """
    Submits one or more URLs to IndexNow.
    Supports single-URL GET and multi-URL POST according to IndexNow specifications.
    """
    key = get_indexnow_key()
    if not key:
        logger.debug("INDEXNOW_KEY not set - skipping IndexNow submission.")
        return False

    if isinstance(urls, str):
        urls = [urls]

    clean_urls = [u.strip() for u in urls if u and str(u).startswith("http")]
    if not clean_urls:
        return False

    base_domain = (host or os.getenv("CANONICAL_DOMAIN") or "https://moatnomics.com").rstrip("/")
    key_location = f"{base_domain}/{key}.txt"

    # Single URL: Fast GET request
    if len(clean_urls) == 1:
        target_url = clean_urls[0]
        try:
            resp = requests.get(
                INDEXNOW_ENDPOINT,
                params={
                    "url": target_url,
                    "key": key,
                    "keyLocation": key_location,
                },
                timeout=5,
            )
            if resp.status_code in (200, 202):
                logger.info(f"IndexNow ping succeeded for {target_url} (HTTP {resp.status_code}).")
                return True
            else:
                logger.warning(f"IndexNow ping returned HTTP {resp.status_code} for {target_url}.")
                return False
        except Exception as e:
            logger.debug(f"IndexNow single-URL ping notice for {target_url}: {e}")
            return False

    # Multi-URL Batch: Standard JSON POST
    try:
        from urllib.parse import urlparse
        parsed = urlparse(base_domain)
        host_name = parsed.netloc or "moatnomics.com"

        payload = {
            "host": host_name,
            "key": key,
            "keyLocation": key_location,
            "urlList": clean_urls[:10000],  # IndexNow limit per request
        }
        resp = requests.post(
            INDEXNOW_ENDPOINT,
            json=payload,
            headers={"Content-Type": "application/json; charset=utf-8"},
            timeout=10,
        )
        if resp.status_code in (200, 202):
            logger.info(f"IndexNow batch submission succeeded for {len(clean_urls)} URLs (HTTP {resp.status_code}).")
            return True
        else:
            logger.warning(f"IndexNow batch submission returned HTTP {resp.status_code}.")
            return False
    except Exception as batch_err:
        logger.debug(f"IndexNow batch submission notice: {batch_err}")
        return False
