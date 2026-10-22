"""
tests/security/test_p0_p1_financial_ledger_auth_integrity.py
=============================================================
Comprehensive Security, Ledger, Financial & Regulatory Integrity Tests:
1. P0: Atomic Race Conditions (Negative Balances Prevention via Atomic SQL Update)
2. P0: Database-Level Payment Idempotency (UNIQUE constraint & Disk-Level Replay Blocking)
3. P0: SEBI Safe Harbor Jailbreak Guardrails (System Boundary Directive & Output Scrubber)
4. P1: Admin Dev Bypass Security (Hardcoded Production Kill-Switch & Anti-Proxy Spoofing)
5. P1: Strict Production Boot Guards for HMAC Secrets (Runtime Refusal on Missing/Weak Keys)
"""

import os
import unittest
import uuid
import asyncio
import concurrent.futures
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

from web.main import app, init_db, verify_production_boot_guards
from web.common import is_production_environment, is_local_dev_request
from core.db import get_db_connection
from core.db.users import (
    get_or_create_user,
    get_user_credits_balance,
    deduct_user_credits,
    add_user_credits,
)
from core.agents.copilot.forensic_desk import (
    SEBI_SYSTEM_BOUNDARY_DIRECTIVE,
    scrub_prescriptive_tokens,
    scrub_streaming_yield,
    process_forensic_desk_turn,
)
from core.agents.copilot.research_desk import (
    process_research_desk_turn,
    SEBI_PRESCRIPTIVE_TOKENS_RE,
)


class TestP0FinancialAndLedgerIntegrity(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ["TESTING"] = "1"
        init_db()
        cls.client = TestClient(app)

    def test_prevent_atomic_race_condition_negative_balances(self):
        """
        The Exploit: A user with 1 credit fires 10 simultaneous requests to unlock 10 tickers.
        A standard check-then-act pattern allows all 10 to pass before DB updates (-9 balance).
        Verification:
        - Exactly 1 request succeeds; 9 requests fail with INSUFFICIENT_CREDITS.
        - Balance is never negative (ends at exactly 0.0, never -9.0).
        """
        user_id = f"usr_race_{uuid.uuid4().hex[:8]}"
        email = f"{user_id}@example.com"
        get_or_create_user(user_id, email)

        # Set user balance to exactly 1.0 credit
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE user_accounts SET credits_balance = 1.0 WHERE id = ?", (user_id,))
        conn.commit()
        cursor.close()
        conn.close()

        self.assertEqual(get_user_credits_balance(user_id), 1.0)

        # Fire 10 simultaneous deductions in parallel threads
        tickers = [f"TICKER_{i}" for i in range(10)]
        results = []

        def _deduct(ticker_symbol):
            return deduct_user_credits(user_id, ticker_symbol, "DOSSIER_UNLOCK", 1.0)

        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(_deduct, t) for t in tickers]
            for f in concurrent.futures.as_completed(futures):
                results.append(f.result())

        success_count = sum(1 for r in results if r.success)
        failure_count = sum(1 for r in results if not r.success)

        self.assertEqual(success_count, 1, f"Expected exactly 1 successful deduction, got {success_count}")
        self.assertEqual(failure_count, 9, f"Expected exactly 9 failed deductions, got {failure_count}")

        # Final balance MUST be exactly 0.0, never negative
        final_balance = get_user_credits_balance(user_id)
        self.assertEqual(final_balance, 0.0, f"Balance must be exactly 0.0, but got {final_balance}")

    def test_database_level_payment_idempotency_constraint(self):
        """
        The Exploit: An attacker intercepts a successful Razorpay webhook payload and replays it
        multiple times to fraudulently mint credits.
        Verification:
        - The credit_transactions table enforces a UNIQUE(gateway_payment_id) constraint.
        - Replay attacks are blocked natively at the disk level.
        - Repeated calls to add_user_credits with the same gateway_payment_id preserve balance.
        """
        user_id = f"usr_idemp_{uuid.uuid4().hex[:8]}"
        email = f"{user_id}@example.com"
        get_or_create_user(user_id, email)

        initial_balance = get_user_credits_balance(user_id)
        gateway_payment_id = f"pay_test_{uuid.uuid4().hex[:12]}"
        gateway_order_id = f"order_test_{uuid.uuid4().hex[:12]}"

        # First legitimate payment webhook processing
        ok1, bal1 = add_user_credits(
            user_id=user_id,
            amount_inr=500.0,
            credits_added=25.0,
            pack_type="PRO_PACK",
            gateway_order_id=gateway_order_id,
            gateway_payment_id=gateway_payment_id,
            status="success"
        )
        self.assertTrue(ok1)
        expected_balance = initial_balance + 25.0
        self.assertEqual(bal1, expected_balance)

        # Attacker replays identical webhook payload
        ok2, bal2 = add_user_credits(
            user_id=user_id,
            amount_inr=500.0,
            credits_added=25.0,
            pack_type="PRO_PACK",
            gateway_order_id=gateway_order_id,
            gateway_payment_id=gateway_payment_id,
            status="success"
        )
        self.assertTrue(ok2)
        # Balance must remain unchanged; no double credits minted
        self.assertEqual(bal2, expected_balance)
        self.assertEqual(get_user_credits_balance(user_id), expected_balance)

        # Verify disk-level UNIQUE violation when attempting raw SQL duplicate insert
        conn = get_db_connection()
        cursor = conn.cursor()
        tx_duplicate_id = f"tx_dup_{uuid.uuid4().hex[:8]}"
        with self.assertRaises(Exception) as ctx:
            cursor.execute(
                """
                INSERT INTO credit_transactions (
                    id, user_id, amount_inr, credits_added, payment_gateway,
                    gateway_order_id, gateway_payment_id, status, pack_type
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (tx_duplicate_id, user_id, 500.0, 25.0, "razorpay", gateway_order_id, gateway_payment_id, "success", "PRO_PACK")
            )
            conn.commit()
        cursor.close()
        conn.close()
        self.assertIn("unique", str(ctx.exception).lower())


class TestP0SEBIJailbreakGuardrails(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ["TESTING"] = "1"
        init_db()

    def test_sebi_system_boundary_directive_defined(self):
        """Verifies the non-negotiable System Boundary Directive is immutable and explicit."""
        self.assertIn("CRITICAL NON-NEGOTIABLE SYSTEM BOUNDARY DIRECTIVE", SEBI_SYSTEM_BOUNDARY_DIRECTIVE)
        self.assertIn("NEVER output explicit transactional commands", SEBI_SYSTEM_BOUNDARY_DIRECTIVE)
        self.assertIn("NEVER prescribe price targets", SEBI_SYSTEM_BOUNDARY_DIRECTIVE)
        self.assertIn("SEBI Research Analyst Regulations, 2014 Section 2(u)", SEBI_SYSTEM_BOUNDARY_DIRECTIVE)

    def test_output_scrubber_redacts_prescriptive_tokens(self):
        """
        Verifies that regex-based scrubber intercepts and redacts advisory tokens
        (BUY, SELL, Target Price, Strong Buy, Accumulate, Reduce) before reaching UI.
        """
        test_cases = [
            ("My recommendation is BUY at current market price.", "My recommendation is [REDACTED — SEBI NON-ADVISORY COMPLIANCE] at current market price."),
            ("You should SELL this immediately.", "You should [REDACTED — SEBI NON-ADVISORY COMPLIANCE] this immediately."),
            ("Target Price: ₹1,550 by next quarter.", "[REDACTED — SEBI NON-ADVISORY COMPLIANCE] by next quarter."),
            ("Price Target of INR 2400.", "[REDACTED — SEBI NON-ADVISORY COMPLIANCE]."),
            ("We issue a STRONG BUY rating.", "We issue a [REDACTED — SEBI NON-ADVISORY COMPLIANCE] rating."),
            ("We issue a STRONG SELL recommendation.", "We issue a [REDACTED — SEBI NON-ADVISORY COMPLIANCE] recommendation."),
            ("ACCUMULATE on dips with a stop loss of 450.", "[REDACTED — SEBI NON-ADVISORY COMPLIANCE] on dips with a [REDACTED — SEBI NON-ADVISORY COMPLIANCE]."),
            ("REDUCE exposure due to debt overhang.", "[REDACTED — SEBI NON-ADVISORY COMPLIANCE] exposure due to debt overhang."),
        ]
        for raw, expected in test_cases:
            scrubbed = scrub_prescriptive_tokens(raw)
            self.assertEqual(scrubbed, expected, f"Failed scrubbing: {raw}")
            # Ensure none of the forbidden prescriptive words remain unredacted
            self.assertFalse(bool(SEBI_PRESCRIPTIVE_TOKENS_RE.search(scrubbed)), f"Prescriptive token leaked in: {scrubbed}")

    def test_output_scrubber_preserves_legitimate_financial_terms(self):
        """Verifies that non-advisory words (buyback, buy-side, buyers, sellers) are not corrupted."""
        safe_cases = [
            "TCS completed a share buyback of ₹17,000 crore.",
            "Buy-side institutional investors held their allocations.",
            "Strong buyer interest was observed at the 50-day moving average.",
            "Secondary market sellers pushed yields higher.",
        ]
        for text in safe_cases:
            scrubbed = scrub_prescriptive_tokens(text)
            self.assertEqual(scrubbed, text, f"Legitimate text was falsely redacted: {scrubbed}")

    def test_streaming_yield_scrubber(self):
        """Verifies that the async streaming yield scrubber redacts chunks in real-time."""
        async def _test_stream():
            async def _dummy_stream():
                yield "The valuation looks favorable. "
                yield "Therefore, our rating is BUY "
                yield "with a Target Price: ₹2,100."

            chunks = []
            async for chunk in scrub_streaming_yield(_dummy_stream()):
                chunks.append(chunk)

            full_streamed = "".join(chunks)
            self.assertNotIn("BUY", full_streamed)
            self.assertNotIn("Target Price", full_streamed)
            self.assertIn("[REDACTED — SEBI NON-ADVISORY COMPLIANCE]", full_streamed)

        asyncio.run(_test_stream())

    def test_forensic_desk_reexport_parity(self):
        """Verifies forensic_desk.py provides full functional parity with research_desk.py."""
        async def _run():
            res = await process_forensic_desk_turn(
                conversation_id="TEST-FORENSIC-PARITY",
                user_message="Explain the capital allocation framework",
                ticker="TCS",
                asset_type="equity",
                deep_dive_unlocked=False
            )
            self.assertIn("response", res)
            self.assertIn("Desk Mode", res["response"])
        asyncio.run(_run())


class TestP1AdminDevBypassAndHMACBootGuards(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ["TESTING"] = "1"
        init_db()
        cls.client = TestClient(app)

    def test_admin_dev_bypass_hardcoded_production_killswitch(self):
        """
        Verifies that when ENVIRONMENT == 'production' or RENDER == 'true',
        admin dev-login is HARD-KILLED regardless of IP or headers.
        """
        req_mock = MagicMock()
        req_mock.client.host = "127.0.0.1"
        req_mock.url.hostname = "localhost"
        req_mock.headers = {}

        # In production, dev bypass must strictly return False
        with patch.dict(os.environ, {"ENVIRONMENT": "production", "RENDER": "false"}):
            self.assertTrue(is_production_environment())
            self.assertFalse(is_local_dev_request(req_mock))

        with patch.dict(os.environ, {"ENVIRONMENT": "development", "RENDER": "true"}):
            self.assertTrue(is_production_environment())
            self.assertFalse(is_local_dev_request(req_mock))

        with patch.dict(os.environ, {"PRODUCTION": "true"}):
            self.assertTrue(is_production_environment())
            self.assertFalse(is_local_dev_request(req_mock))

    def test_admin_dev_bypass_proxy_spoofing_rejected(self):
        """
        The Exploit: An attacker injects X-Forwarded-For: 127.0.0.1 to spoof local dev status.
        Verification: Any presence of proxy headers (X-Forwarded-For, X-Real-IP) rejects dev bypass.
        """
        # Non-production environment
        with patch.dict(os.environ, {"ENVIRONMENT": "development", "RENDER": "false", "PRODUCTION": "false"}):
            # Legitimate local developer on 127.0.0.1 without proxy headers
            legit_req = MagicMock()
            legit_req.client.host = "127.0.0.1"
            legit_req.url.hostname = "localhost"
            legit_req.headers = {}
            self.assertTrue(is_local_dev_request(legit_req))

            # Attacker from external IP spoofing X-Forwarded-For: 127.0.0.1
            spoofed_req = MagicMock()
            spoofed_req.client.host = "198.51.100.22"
            spoofed_req.url.hostname = "localhost"
            spoofed_req.headers = {"x-forwarded-for": "127.0.0.1"}
            self.assertFalse(is_local_dev_request(spoofed_req))

            # Attacker traversing a proxy with Forwarded or X-Real-IP
            proxy_req = MagicMock()
            proxy_req.client.host = "127.0.0.1"
            proxy_req.url.hostname = "localhost"
            proxy_req.headers = {"x-real-ip": "127.0.0.1"}
            self.assertFalse(is_local_dev_request(proxy_req))

    def test_admin_dev_login_endpoint_blocks_production_and_proxies(self):
        """Verifies HTTP POST /admin/auth/dev-login rejects requests in production."""
        with patch.dict(os.environ, {"ENVIRONMENT": "production"}):
            resp = self.client.post("/admin/auth/dev-login")
            self.assertEqual(resp.status_code, 403)
            self.assertIn("Direct dev login only allowed on local environments", resp.text)

    def test_strict_boot_guards_for_hmac_secrets(self):
        """
        The Exploit: In production, app boots with missing, weak, or default SECRET_KEY.
        Verification: verify_production_boot_guards raises RuntimeError and refuses to start.
        """
        # 1. Missing SECRET_KEY in production -> RuntimeError
        with patch.dict(os.environ, {"ENVIRONMENT": "production", "SECRET_KEY": ""}, clear=False):
            with patch("core.config.get_secret", return_value=""):
                with self.assertRaises(RuntimeError) as ctx:
                    verify_production_boot_guards()
                self.assertIn("CRITICAL PRODUCTION BOOT FAILURE: SECRET_KEY is missing", str(ctx.exception))

        # 2. Short SECRET_KEY (< 32 chars) in production -> RuntimeError
        with patch.dict(os.environ, {"ENVIRONMENT": "production", "SECRET_KEY": "too_short_key_under_32_chars"}, clear=False):
            with patch("core.config.get_secret", return_value=""):
                with self.assertRaises(RuntimeError) as ctx:
                    verify_production_boot_guards()
                self.assertIn("shorter than 32 characters", str(ctx.exception))

        # 3. Known insecure default SECRET_KEY -> RuntimeError
        for insecure_key in ("dev_secret", "stock_research_user_session_salt_2026", "changeme"):
            with patch.dict(os.environ, {"ENVIRONMENT": "production", "SECRET_KEY": insecure_key}, clear=False):
                with patch("core.config.get_secret", return_value=""):
                    with self.assertRaises(RuntimeError) as ctx:
                        verify_production_boot_guards()
                    self.assertIn("insecure default", str(ctx.exception))

        # 4. Valid, high-entropy SECRET_KEY in production -> Passes cleanly
        valid_key = "a" * 64
        with patch.dict(os.environ, {"ENVIRONMENT": "production", "SECRET_KEY": valid_key}, clear=False):
            with patch("core.config.get_secret", return_value=""):
                # Should not raise any error
                verify_production_boot_guards()


if __name__ == "__main__":
    unittest.main()
