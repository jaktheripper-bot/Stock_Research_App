"""
core/logging_config.py
==============================================================================
Centralized Logging & Better Stack Telemetry Ingestion Architecture.

Integrates Python standard library logging with Better Stack (Logtail) via
LogtailHandler:
- Ingesting Host: s2808842.us-west-2a.betterstackdata.com (or via BETTER_STACK_INGESTING_HOST)
- Source Token: n9BuFhtn6SwGdLrRd4A8wFn6 (or via BETTER_STACK_SOURCE_TOKEN)
- Structured logging with custom context attributes (extra={'...': '...'})
- StreamHandler for local console output with ISO timestamps
- Clean flush on server shutdown (flush_betterstack_logs)
- Test isolation: Silent local-only during unit test runs unless explicitly forced
==============================================================================
"""

import os
import sys
import logging
from typing import Optional, Dict, Any, List

from core.config import get_secret

logger = logging.getLogger("equity_research.core.logging_config")

DEFAULT_BETTER_STACK_SOURCE_TOKEN = "n9BuFhtn6SwGdLrRd4A8wFn6"
DEFAULT_BETTER_STACK_INGESTING_HOST = "s2808842.us-west-2a.betterstackdata.com"

try:
    from logtail import LogtailHandler
    HAS_LOGTAIL = True
except ImportError:
    LogtailHandler = None  # type: ignore
    HAS_LOGTAIL = False

_BETTER_STACK_HANDLER: Optional[logging.Handler] = None
_LOGGING_INITIALIZED: bool = False


def is_test_environment() -> bool:
    """Detects whether code is executing within automated test suites."""
    return (
        os.environ.get("TESTING") == "1"
        or "pytest" in sys.modules
        or "unittest" in sys.modules
        or os.environ.get("DISABLE_BETTER_STACK") == "1"
    )


def get_betterstack_handler(
    source_token: Optional[str] = None,
    host: Optional[str] = None,
    raise_exceptions: bool = False,
    force: bool = False,
) -> Optional[logging.Handler]:
    """Creates or retrieves the configured Better Stack LogtailHandler singleton.

    Args:
        source_token: Optional override for Better Stack source token.
        host: Optional override for Better Stack ingesting host.
        raise_exceptions: If True, raises exceptions when dispatch fails (debugging).
        force: If True, initializes even inside test environments.

    Returns:
        Configured LogtailHandler instance or None if unavailable/disabled.
    """
    global _BETTER_STACK_HANDLER
    if _BETTER_STACK_HANDLER is not None and not force:
        return _BETTER_STACK_HANDLER

    # Test isolation guard: do not open remote HTTP logtail pipes during unit testing
    if is_test_environment() and not force and os.environ.get("ENABLE_BETTER_STACK_IN_TESTS") != "1":
        return None

    if not HAS_LOGTAIL or LogtailHandler is None:
        logger.warning("logtail-python is not installed. Remote Better Stack logging disabled.")
        return None

    token = (
        source_token
        or os.environ.get("BETTER_STACK_SOURCE_TOKEN")
        or os.environ.get("LOGTAIL_SOURCE_TOKEN")
        or get_secret("BETTER_STACK_SOURCE_TOKEN")
        or get_secret("LOGTAIL_SOURCE_TOKEN")
        or DEFAULT_BETTER_STACK_SOURCE_TOKEN
    )

    ingest_host = (
        host
        or os.environ.get("BETTER_STACK_INGESTING_HOST")
        or os.environ.get("LOGTAIL_INGESTING_HOST")
        or get_secret("BETTER_STACK_INGESTING_HOST")
        or get_secret("LOGTAIL_INGESTING_HOST")
        or DEFAULT_BETTER_STACK_INGESTING_HOST
    )

    if not ingest_host.startswith("http://") and not ingest_host.startswith("https://"):
        ingest_host = f"https://{ingest_host}"

    try:
        handler = LogtailHandler(
            source_token=str(token).strip(),
            host=str(ingest_host).strip(),
            raise_exceptions=raise_exceptions,
        )
        handler.setLevel(logging.INFO)
        _BETTER_STACK_HANDLER = handler
        return _BETTER_STACK_HANDLER
    except Exception as e:
        logger.warning("Failed to initialize Better Stack LogtailHandler: %s", e)
        return None


def setup_logging(
    level: int = logging.INFO,
    attach_to_root: bool = True,
    app_logger_names: Optional[List[str]] = None,
    force_betterstack: bool = False,
) -> Dict[str, Any]:
    """Configures centralized logging for Moatnomics with Better Stack ingestion.

    Attaches console StreamHandler and remote LogtailHandler to the root
    logger and 'equity_research' namespace.

    Args:
        level: Root and application log level (default: logging.INFO).
        attach_to_root: Whether to attach handlers to the root logger.
        app_logger_names: List of logger namespace names to attach to.
        force_betterstack: Force initialization even in test environments.

    Returns:
        Dict detailing logging initialization status.
    """
    global _LOGGING_INITIALIZED
    log_format = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    formatter = logging.Formatter(log_format)

    # Console stream handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    console_handler.setLevel(level)

    target_loggers: List[logging.Logger] = []
    if attach_to_root:
        root_logger = logging.getLogger()
        root_logger.setLevel(level)
        # Avoid duplicate console handlers
        if not any(isinstance(h, logging.StreamHandler) and not (HAS_LOGTAIL and isinstance(h, LogtailHandler)) for h in root_logger.handlers):
            root_logger.addHandler(console_handler)
        target_loggers.append(root_logger)

    names = app_logger_names or ["equity_research"]
    for name in names:
        app_logger = logging.getLogger(name)
        app_logger.setLevel(level)
        target_loggers.append(app_logger)

    # Better Stack remote logtail handler
    bs_handler = get_betterstack_handler(force=force_betterstack)
    if bs_handler is not None:
        for t_logger in target_loggers:
            # Avoid duplicate LogtailHandler
            if not any(isinstance(h, type(bs_handler)) for h in t_logger.handlers):
                t_logger.addHandler(bs_handler)

    _LOGGING_INITIALIZED = True
    return {
        "status": "initialized",
        "better_stack_active": bs_handler is not None,
        "level": level,
        "has_logtail_pkg": HAS_LOGTAIL,
    }


def flush_betterstack_logs(timeout: Optional[float] = 5.0) -> None:
    """Flushes any queued logtail events before process termination."""
    global _BETTER_STACK_HANDLER
    if _BETTER_STACK_HANDLER is not None and hasattr(_BETTER_STACK_HANDLER, "flush"):
        try:
            _BETTER_STACK_HANDLER.flush()
        except Exception as e:
            logger.warning("Error during Better Stack log flush: %s", e)
