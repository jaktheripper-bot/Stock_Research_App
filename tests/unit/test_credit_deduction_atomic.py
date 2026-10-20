"""Unit tests for Atomic Dual-Bound Credit Deduction & Race Condition Guard.

Verifies:
1. CreditDeductionResult backward compatibility (unpacks as 3-tuple, indexes as dictionary).
2. Atomic deduction across valid balance states and ledger audit tracking.
3. Insufficient credits rejection returning standardized INSUFFICIENT_CREDITS payload.
4. Thread-safe concurrency: multi-threaded deduction prevents check-then-act double-spending.
5. Pro subscription entitlement exemptions for price & filing refreshes and PDF exports.
6. Error handling and rollback for unauthenticated or non-existent user accounts.
"""

import threading
import unittest
import uuid
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, MagicMock

from core.db.connection import init_db, get_db_connection, get_placeholder
from core.db.users import (
    CreditDeductionResult,
    deduct_user_credits,
    get_or_create_user,
    get_user_credits_balance,
    add_user_credits,
)


class TestCreditDeductionAtomic(unittest.TestCase):
    """Unit test suite for atomic credit deduction and concurrency guardrails."""

    def setUp(self):
        init_db()

    def test_credit_deduction_result_dual_contract(self):
        """CreditDeductionResult must support both 3-tuple unpacking and dictionary access."""
        # 1. Failure result
        res_fail = CreditDeductionResult(
            success=False,
            credits_balance=0.5,
            message="Insufficient research credits.",
            error="INSUFFICIENT_CREDITS"
        )
        # Tuple unpacking
        ok, bal, msg = res_fail
        self.assertFalse(ok)
        self.assertEqual(bal, 0.5)
        self.assertEqual(msg, "Insufficient research credits.")

        # Dict access
        self.assertFalse(res_fail["success"])
        self.assertEqual(res_fail["credits_balance"], 0.5)
        self.assertEqual(res_fail["error"], "INSUFFICIENT_CREDITS")
        self.assertEqual(res_fail["message"], "Insufficient research credits.")
        self.assertEqual(res_fail.get("error"), "INSUFFICIENT_CREDITS")
        self.assertIn("success", res_fail)
        self.assertIn("credits_balance", res_fail)

        # Boolean evaluation
        self.assertFalse(bool(res_fail))

        # 2. Success result
        res_ok = CreditDeductionResult(
            success=True,
            credits_balance=4.0,
            message="Success: 1.00 credit(s) consumed.",
            error=None
        )
        ok2, bal2, msg2 = res_ok
        self.assertTrue(ok2)
        self.assertEqual(bal2, 4.0)
        self.assertTrue(res_ok["success"])
        self.assertIsNone(res_ok["error"])
        self.assertTrue(bool(res_ok))

        # Dict conversion
        d = res_ok.to_dict()
        self.assertIsInstance(d, dict)
        self.assertTrue(d["success"])
        self.assertEqual(d["credits_balance"], 4.0)

    def test_atomic_credit_deduction_success_and_updated_at(self):
        """Deduction successfully updates balance, populates updated_at, and writes ledger."""
        uid = f"usr_atomic_{uuid.uuid4().hex[:8]}"
        email = f"{uid}@example.com"
        get_or_create_user(uid, email)  # Starts with 2.0 credits

        res = deduct_user_credits(
            user_id=uid,
            ticker="INFY",
            action_type="FULL_SYNTHESIS",
            amount=1.0
        )

        self.assertTrue(res["success"])
        self.assertEqual(res["credits_balance"], 1.0)
        self.assertIsNone(res["error"])

        # Verify DB state directly
        conn = get_db_connection()
        cursor = conn.cursor()
        p = get_placeholder()
        cursor.execute(f"SELECT credits_balance, updated_at FROM user_accounts WHERE id = {p};", (uid,))
        row = cursor.fetchone()
        self.assertIsNotNone(row)
        self.assertEqual(float(row[0]), 1.0)
        self.assertIsNotNone(row[1], "updated_at must be populated after deduction")

        # Verify ledger entry
        cursor.execute(
            f"SELECT credits_consumed, balance_after, action_type FROM credit_usage_ledger WHERE user_id = {p} AND action_type = 'FULL_SYNTHESIS';",
            (uid,)
        )
        ledger_row = cursor.fetchone()
        self.assertIsNotNone(ledger_row)
        self.assertEqual(float(ledger_row[0]), 1.0)
        self.assertEqual(float(ledger_row[1]), 1.0)
        self.assertEqual(ledger_row[2], "FULL_SYNTHESIS")

        cursor.close()
        conn.close()

    def test_insufficient_credits_rejection(self):
        """Attempting to deduct more credits than available must return INSUFFICIENT_CREDITS."""
        uid = f"usr_insuf_{uuid.uuid4().hex[:8]}"
        email = f"{uid}@example.com"
        get_or_create_user(uid, email)  # Balance 2.0

        res = deduct_user_credits(
            user_id=uid,
            ticker="TCS",
            action_type="FULL_SYNTHESIS",
            amount=5.0
        )

        self.assertFalse(res["success"])
        self.assertEqual(res["error"], "INSUFFICIENT_CREDITS")
        self.assertEqual(res["credits_balance"], 2.0)
        self.assertIn("Insufficient research credits", res["message"])

        # Unpacking contract
        ok, bal, msg = res
        self.assertFalse(ok)
        self.assertEqual(bal, 2.0)

        # Assert balance remains unchanged
        current_bal = get_user_credits_balance(uid)
        self.assertEqual(current_bal, 2.0)

    def test_concurrency_race_condition_guard(self):
        """Multiple concurrent threads attempting to deduct credits must never double-spend."""
        uid = f"usr_race_unit_{uuid.uuid4().hex[:8]}"
        email = f"{uid}@example.com"
        get_or_create_user(uid, email)  # Initial balance: 2.0

        results = []
        lock = threading.Lock()

        def worker():
            res = deduct_user_credits(
                user_id=uid,
                ticker="RELIANCE",
                action_type="CONCURRENT_SYNTH",
                amount=1.0
            )
            with lock:
                results.append(res)

        threads = [threading.Thread(target=worker) for _ in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        successes = [r for r in results if r["success"]]
        failures = [r for r in results if not r["success"]]

        self.assertEqual(len(successes), 2, f"Exactly 2 deductions must succeed; got {len(successes)}")
        self.assertEqual(len(failures), 6, f"Exactly 6 deductions must fail; got {len(failures)}")

        for f in failures:
            self.assertEqual(f["error"], "INSUFFICIENT_CREDITS")

        final_bal = get_user_credits_balance(uid)
        self.assertEqual(final_bal, 0.0)

    def test_pro_subscription_entitlements(self):
        """Active Pro subscribers must have uncapped price & filing refreshes and PDF exports."""
        uid = f"usr_pro_{uuid.uuid4().hex[:8]}"
        email = f"{uid}@example.com"
        get_or_create_user(uid, email)

        # Upgrade to pro_monthly
        conn = get_db_connection()
        cursor = conn.cursor()
        p = get_placeholder()
        future_iso = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()
        cursor.execute(
            f"UPDATE user_accounts SET subscription_tier = 'pro_monthly', subscription_expires_at = {p} WHERE id = {p};",
            (future_iso, uid)
        )
        conn.commit()
        cursor.close()
        conn.close()

        # Price & Filing refresh costs 0 for Pro
        res_sr = deduct_user_credits(uid, "HDFCBANK", "SURGICAL_REFRESH", 1.0)
        self.assertTrue(res_sr["success"])
        self.assertEqual(res_sr["credits_balance"], 2.0)
        self.assertIn("Pro subscription", res_sr["message"])

        # PDF export costs 0 for Pro
        res_pdf = deduct_user_credits(uid, "HDFCBANK", "PDF_EXPORT", 1.0)
        self.assertTrue(res_pdf["success"])
        self.assertEqual(res_pdf["credits_balance"], 2.0)

    def test_unauthenticated_and_missing_user(self):
        """Empty user_id or non-existent user must return appropriate failure results."""
        res_no_user = deduct_user_credits("", "INFY", "TEST", 1.0)
        self.assertFalse(res_no_user["success"])
        self.assertEqual(res_no_user["error"], "AUTH_REQUIRED")

        res_missing = deduct_user_credits("usr_non_existent_999", "INFY", "TEST", 1.0)
        self.assertFalse(res_missing["success"])
        self.assertEqual(res_missing["error"], "USER_NOT_FOUND")

    def test_postgres_branch_simulation(self):
        """Simulates PostgreSQL branch execution to verify RETURNING credits_balance flow."""
        uid = f"usr_pg_sim_{uuid.uuid4().hex[:8]}"
        email = f"{uid}@example.com"
        get_or_create_user(uid, email)

        # Mock connection to simulate is_postgres_connection returning True
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor

        # 1. Initial balance check
        mock_cursor.fetchone.side_effect = [
            (uid, 5.0, "free", None),  # SELECT id, credits_balance...
            (4.0,),                    # RETURNING credits_balance
        ]

        with patch("core.db.users.get_db_connection", return_value=mock_conn), \
             patch("core.db.users.is_postgres_connection", return_value=True):
            res = deduct_user_credits(uid, "INFY", "FULL_SYNTHESIS", 1.0)

        self.assertTrue(res["success"])
        self.assertEqual(res["credits_balance"], 4.0)
        self.assertIsNone(res["error"])

        # Verify SQL executed was the PostgreSQL RETURNING query
        sql_calls = [str(call[0][0]) for call in mock_cursor.execute.call_args_list]
        self.assertTrue(any("RETURNING credits_balance" in s for s in sql_calls))


if __name__ == "__main__":
    unittest.main()
