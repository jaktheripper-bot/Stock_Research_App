"""
Centralized Configuration & Secrets Ingestion Engine.

Provides zero-dependency, runtime-agnostic configuration resolution:
1. Environment variables (os.environ) - primary for Render, Docker, CI/CD
2. .env file via python-dotenv if installed
3. Local secrets.toml or .streamlit/secrets.toml using standard library tomllib (Python 3.11+)
   without requiring Streamlit to be installed or initialized.
"""

import os
import sys
import logging
from typing import Any, Optional

logger = logging.getLogger("equity_research.core.config")

# Attempt loading .env
try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception as e:
    logger.debug("dotenv load notice: %s", e)

_SECRETS_CACHE: Optional[dict] = None
_SECRETS_LOADED = False

def _load_local_secrets() -> dict:
    """Reads secrets from local TOML files if they exist on disk, using stdlib tomllib."""
    global _SECRETS_CACHE, _SECRETS_LOADED
    if _SECRETS_LOADED:
        return _SECRETS_CACHE or {}

    secrets = {}
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    candidate_paths = [
        os.path.join(base_dir, ".streamlit", "secrets.toml"),
        os.path.join(base_dir, "secrets.toml"),
    ]

    for p in candidate_paths:
        if os.path.exists(p):
            try:
                # Use standard library tomllib if available (Python 3.11+)
                if sys.version_info >= (3, 11):
                    import tomllib
                    with open(p, "rb") as f:
                        loaded = tomllib.load(f)
                else:
                    import toml
                    with open(p, "r", encoding="utf-8") as f:
                        loaded = toml.load(f)
                
                if isinstance(loaded, dict):
                    # Flatten top-level keys
                    for k, v in loaded.items():
                        secrets[k] = v
                        # If not already in os.environ and is a string, populate os.environ
                        if isinstance(v, str) and k not in os.environ:
                            os.environ[k] = v
            except Exception as e:
                logger.debug(f"Could not parse secrets from {p}: {e}")

    _SECRETS_CACHE = secrets
    _SECRETS_LOADED = True
    return _SECRETS_CACHE

def get_secret(key: str, default: Any = None) -> Any:
    """
    Retrieves configuration value from:
    1. os.environ
    2. Local secrets.toml
    3. default fallback
    """
    val = os.environ.get(key)
    if val is not None and str(val).strip():
        return str(val).strip()

    secrets = _load_local_secrets()
    if key in secrets:
        sec_val = secrets[key]
        if sec_val is not None:
            return sec_val

    return default
