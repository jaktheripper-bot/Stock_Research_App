"""
tests/unit/test_betterstack_logging.py
==============================================================================
Unit tests for Better Stack logging integration and telemetry configuration.
==============================================================================
"""

import os
import sys
import unittest
import logging
from unittest.mock import patch, MagicMock

from core.config import get_better_stack_config
from core.logging_config import (
    get_betterstack_handler,
    setup_logging,
    flush_betterstack_logs,
    is_test_environment,
    DEFAULT_BETTER_STACK_SOURCE_TOKEN,
    DEFAULT_BETTER_STACK_INGESTING_HOST,
)


class TestBetterStackLogging(unittest.TestCase):
    def setUp(self):
        # Reset any cached handler for isolation
        import core.logging_config as lc
        lc._BETTER_STACK_HANDLER = None
        lc._LOGGING_INITIALIZED = False

    def test_get_better_stack_config_defaults(self):
        """Verifies default credentials match specified Better Stack configuration."""
        cfg = get_better_stack_config()
        self.assertEqual(cfg["source_token"], DEFAULT_BETTER_STACK_SOURCE_TOKEN)
        self.assertTrue(cfg["host"].endswith(DEFAULT_BETTER_STACK_INGESTING_HOST))
        self.assertTrue(cfg["host"].startswith("https://"))

    def test_get_better_stack_config_env_override(self):
        """Verifies environment variables override default credentials."""
        with patch.dict(os.environ, {
            "BETTER_STACK_SOURCE_TOKEN": "custom_token_123",
            "BETTER_STACK_INGESTING_HOST": "custom.logs.betterstack.com",
        }):
            cfg = get_better_stack_config()
            self.assertEqual(cfg["source_token"], "custom_token_123")
            self.assertEqual(cfg["host"], "https://custom.logs.betterstack.com")

    def test_test_environment_isolation_guard(self):
        """Verifies remote handler is suppressed during unit tests unless forced."""
        self.assertTrue(is_test_environment())
        # In a test run without force=True, handler should return None to avoid test noise
        handler = get_betterstack_handler(force=False)
        self.assertIsNone(handler)

    def test_handler_creation_with_force(self):
        """Verifies handler can be instantiated with custom parameters."""
        handler = get_betterstack_handler(
            source_token="test_token_xyz",
            host="https://test.betterstackdata.com",
            force=True,
        )
        self.assertIsNotNone(handler)
        self.assertEqual(handler.source_token, "test_token_xyz")
        self.assertEqual(handler.host, "https://test.betterstackdata.com")

    def test_setup_logging_configuration(self):
        """Verifies setup_logging attaches stream formatter and configures loggers."""
        res = setup_logging(level=logging.INFO, attach_to_root=True)
        self.assertEqual(res["status"], "initialized")
        self.assertEqual(res["level"], logging.INFO)

        root = logging.getLogger()
        self.assertTrue(any(isinstance(h, logging.StreamHandler) for h in root.handlers))

    def test_structured_log_formatting(self):
        """Verifies python logger accepts structured extra parameters per Better Stack guide."""
        test_logger = logging.getLogger("equity_research.test_structured")
        mock_handler = MagicMock()
        mock_handler.level = logging.INFO
        test_logger.addHandler(mock_handler)


        test_logger.info("Sample structured log", extra={"item": "Orange Soda", "price": 100.0})
        self.assertTrue(mock_handler.handle.called)
        record = mock_handler.handle.call_args[0][0]
        self.assertEqual(getattr(record, "item", None), "Orange Soda")
        self.assertEqual(getattr(record, "price", None), 100.0)

    def test_flush_betterstack_logs_safe(self):
        """Verifies flush_betterstack_logs completes without error."""
        try:
            flush_betterstack_logs()
        except Exception as e:
            self.fail(f"flush_betterstack_logs raised unexpected exception: {e}")


if __name__ == "__main__":
    unittest.main()
