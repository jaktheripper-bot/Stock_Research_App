#!/usr/bin/env python3
"""
scripts/test_betterstack.py
==============================================================================
Verification tool to test the live connection from Python to Better Stack.

Follows the Better Stack integration guide (https://betterstack.com/docs/logs/python.md).
Uses $SOURCE_TOKEN and $INGESTING_HOST to dispatch a structured test log event.
==============================================================================
"""

import sys
import logging
from pathlib import Path

# Add project root to sys.path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.config import get_better_stack_config
from core.logging_config import get_betterstack_handler, flush_betterstack_logs


def main():
    print("=" * 70)
    print("MOATNOMICS BETTER STACK TELEMETRY CONNECTION TEST")
    print("=" * 70)

    cfg = get_better_stack_config()
    source_token = cfg["source_token"]
    ingest_host = cfg["host"]

    masked_token = f"{source_token[:6]}...{source_token[-4:]}" if len(source_token) >= 10 else "***"
    print(f"Target Ingesting Host: {ingest_host}")
    print(f"Source Token:          {masked_token}")

    handler = get_betterstack_handler(
        source_token=source_token,
        host=ingest_host,
        raise_exceptions=True,
        force=True,
    )

    if handler is None:
        print("❌ FAILED: Better Stack LogtailHandler could not be initialized.")
        sys.exit(1)

    test_logger = logging.getLogger("equity_research.betterstack_test")
    test_logger.setLevel(logging.INFO)
    test_logger.handlers = [handler]

    print("\n--> Dispatching structured test log to Better Stack...")
    test_logger.info(
        "Moatnomics Python to Better Stack connection verified successfully.",
        extra={
            "service": "moatnomics",
            "component": "telemetry_probe",
            "ingesting_host": ingest_host,
            "test_status": "passed",
        }
    )

    print("--> Flushing log queue to remote endpoint...")
    flush_betterstack_logs()

    print("✅ SUCCESS! Log event transmitted.")
    print("Check your Better Stack Live Tail at: https://telemetry.betterstack.com/team/0/tail")
    print("=" * 70)


if __name__ == "__main__":
    main()
