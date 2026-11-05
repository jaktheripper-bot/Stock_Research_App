"""
Centralized Configuration & Secrets Ingestion Engine.

Provides zero-dependency, runtime-agnostic configuration resolution:
1. Environment variables (os.environ) - primary for Render, Docker, CI/CD
2. .env file via python-dotenv if installed
3. Local secrets.toml using standard library tomllib (Python 3.11+).
"""

import os
import sys
import logging
from typing import Any, Optional

logger = logging.getLogger("equity_research.core.config")

# Attempt loading .env unless isolated subprocess explicitly opts out
if os.environ.get("SKIP_DOTENV_IN_SUBPROCESS") != "1":
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except Exception as e:
        logger.debug("dotenv load notice: %s", e)

_SECRETS_CACHE: Optional[dict] = None
_SECRETS_LOADED = False
_DB_SECRETS_CACHE: dict[str, tuple[Optional[str], float]] = {}
_DB_SECRET_TTL = 300.0
_DB_SYNCABLE_SECRET_KEYS = frozenset({
    "GEMINI_API_KEY",
    "GOOGLE_GENAI_USE_VERTEXAI",
    "ANGEL_API_KEY",
    "ANGEL_ONE_API_KEY",
    "ANGEL_CLIENT_CODE",
    "ANGEL_PIN",
    "ANGEL_TOTP_KEY",
    "SMARTAPI_PROXY_URL",
    "AWS_PROXY_URL",
    "PERPLEXITY_API_KEY",
    "BETTER_STACK_TELEMETRY_TOKEN",
    "BETTER_STACK_INCIDENTS_TOKEN",
    "BETTER_STACK_HEARTBEAT_URL",
})
_TEST_GUARDED_SECRET_KEYS = frozenset({
    "RESEND_API_KEY",
    "SMTP_HOST",
    "SMTP_USER",
    "SMTP_PASSWORD",
})


def _is_test_runtime() -> bool:
    """Detects active unittest/pytest runners or isolated test subprocesses."""
    argv0 = sys.argv[0] if sys.argv else ""
    is_test_entrypoint = any(runner in argv0 for runner in ("unittest", "pytest"))
    return (
        os.environ.get("TESTING") == "1"
        or os.environ.get("ENVIRONMENT") == "testing"
        or os.environ.get("SKIP_DOTENV_IN_SUBPROCESS") == "1"
        or bool(os.environ.get("PYTEST_CURRENT_TEST"))
        or "pytest" in sys.modules
        or is_test_entrypoint
    )


def _load_local_secrets() -> dict:
    """Reads secrets from local TOML files if they exist on disk, using stdlib tomllib."""
    global _SECRETS_CACHE, _SECRETS_LOADED
    if os.environ.get("SKIP_DOTENV_IN_SUBPROCESS") == "1":
        return {}
    if _SECRETS_LOADED:
        return _SECRETS_CACHE or {}

    is_test = _is_test_runtime()
    secrets = {}
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    candidate_paths = [
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
                        # Never auto-inject live outgoing email credentials into os.environ during tests
                        if is_test and k in _TEST_GUARDED_SECRET_KEYS:
                            continue
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
    3. RLS-protected Supabase PostgreSQL system_settings (for synced cloud gateway keys)
    4. default fallback
    """
    def _fetch_db_secret(secret_key: str) -> Optional[str]:
        import time
        now = time.time()
        cached = _DB_SECRETS_CACHE.get(secret_key)
        if cached is not None and (now - cached[1]) < _DB_SECRET_TTL:
            return cached[0]
        try:
            from core.db.settings import get_system_setting
            db_val = get_system_setting(secret_key)
            clean_db_val = str(db_val).strip() if db_val and str(db_val).strip() else None
            _DB_SECRETS_CACHE[secret_key] = (clean_db_val, now)
            return clean_db_val
        except Exception as e:
            logger.debug("Database secret lookup notice for %s: %s", secret_key, e)
            _DB_SECRETS_CACHE[secret_key] = (None, now)
            return None

    val = os.environ.get(key)
    clean_env = str(val).strip() if val is not None and str(val).strip() else None

    # Cloud self-heal: if GOOGLE_GENAI_USE_VERTEXAI=true on host (e.g. Render) while env still holds
    # a stale AI Studio AIza* key, promote the synced AQ.* Vertex Express key from system_settings.
    if (
        key == "GEMINI_API_KEY"
        and clean_env
        and not clean_env.startswith("AQ.")
        and not _is_test_runtime()
        and os.environ.get("GOOGLE_GENAI_USE_VERTEXAI", "").strip().lower() == "true"
    ):
        db_vertex_key = _fetch_db_secret("GEMINI_API_KEY")
        if db_vertex_key and db_vertex_key.startswith("AQ."):
            os.environ["GEMINI_API_KEY"] = db_vertex_key
            return db_vertex_key

    if clean_env:
        return clean_env

    secrets = _load_local_secrets()
    if key in secrets:
        sec_val = secrets[key]
        if sec_val is not None:
            return sec_val

    if key in _DB_SYNCABLE_SECRET_KEYS and not _is_test_runtime():
        clean_db_val = _fetch_db_secret(key)
        if clean_db_val:
            os.environ[key] = clean_db_val
            return clean_db_val

    return default


def yfinance_fallback_enabled() -> bool:
    """Whether the unofficial yfinance gap-filler may be used.

    Disabled by default ("0") in production now that Angel One SmartAPI and direct BSE
    exchange feeds serve as primary market gateways. Only activates if explicitly opted in
    via YFINANCE_FALLBACK=1 (or in isolated unit tests that mock yfinance offline).
    """
    explicit = get_secret("YFINANCE_FALLBACK")
    if explicit is not None:
        return str(explicit).strip().lower() in ("1", "true", "yes", "on")
    if os.environ.get("TESTING") == "1":
        return True
    return False


def get_better_stack_config() -> dict:
    """Retrieves Better Stack telemetry ingestion configuration credentials.

    Returns dict containing source_token and ingesting_host.
    """
    token = get_secret(
        "BETTER_STACK_SOURCE_TOKEN",
        get_secret("LOGTAIL_SOURCE_TOKEN", "")
    )
    host = get_secret(
        "BETTER_STACK_INGESTING_HOST",
        get_secret("LOGTAIL_INGESTING_HOST", "s2808842.us-west-2a.betterstackdata.com")
    )
    if host and not host.startswith("http://") and not host.startswith("https://"):
        host = f"https://{host}"
    return {
        "source_token": str(token).strip() if token else "",
        "host": str(host).strip() if host else "",
    }

