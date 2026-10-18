"""Unit tests for Payment Gateway ID Unique Idempotency Index.

Verifies:
1. Partial unique index idx_credit_tx_unique_payment_id is registered in schema_migrations v033.
2. Direct insertion of duplicate non-null gateway_payment_id raises IntegrityError.
3. Multiple transactions with NULL gateway_payment_id are allowed (system grants, welcome credits).
4. Multiple transactions with empty string gateway_payment_id are allowed.
5. Consecutive admin_grant_user_credits calls succeed without unique constraint collisions.
6. add_user_credits enforces application-level and db-level idempotency on replayed payment IDs.
"""

import sqlite3
import unittest
import uuid
from datetime import datetime, timezone

from core.db.connection import init_db, get_db_connection, get_placeholder
from core.db.users import (
    get_or_create_user,
    get_user_credits_balance,
    add_user_credits,
)
from core.db.admin import admin_grant_user_credits


class TestPaymentIdempotencyIndex(unittest.TestCase):
    """Unit test suite for partial unique index on credit_transactions(gateway_payment_id)."""

    def setUp(self):
        init_db()

    def test_schema_migration_v033_and_index_registered(self):
        """Verify migration v033 is recorded and index exists with partial WHERE clause."""
        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            # Verify migration record
            cursor.execute("SELECT COUNT(*) FROM schema_migrations WHERE version = 'v033_credit_transactions_unique_payment_id';")
            mig_count = cursor.fetchone()[0]
            self.assertGreaterEqual(mig_count, 1, "Migration v033 must be recorded in schema_migrations.")

            # Verify index in SQLite master
            cursor.execute("SELECT sql FROM sqlite_master WHERE type='index' AND name='idx_credit_tx_unique_payment_id';")
            row = cursor.fetchone()
            self.assertIsNotNone(row, "Index idx_credit_tx_unique_payment_id must exist.")
            sql = row[0].upper()
            self.assertIn("UNIQUE", sql)
            self.assertIn("GATEWAY_PAYMENT_ID", sql)
            self.assertIn("IS NOT NULL", sql)
            self.assertIn("!=", sql)
        finally:
            cursor.close()
            conn.close()

    def test_unique_payment_id_direct_sql_rejection(self):
        """Direct SQL insert of duplicate gateway_payment_id must raise an IntegrityError."""
        conn = get_db_connection()
        cursor = conn.cursor()
        p = get_placeholder()
        unique_pay_id = f"pay_test_{uuid.uuid4().hex[:12]}"
        tx1_id = f"tx_test_{uuid.uuid4().hex[:12]}"
        tx2_id = f"tx_test_{uuid.uuid4().hex[:12]}"

        try:
            # First insert succeeds
            cursor.execute(
                f"""
                INSERT INTO credit_transactions (
                    id, user_id, amount_inr, credits_added, payment_gateway,
                    gateway_order_id, gateway_payment_id, status, pack_type
                ) VALUES ({p}, {p}, 100.0, 10.0, 'razorpay', 'order_1', {p}, 'success', 'STARTER');
                """,
                (tx1_id, "usr_test_idemp_1", unique_pay_id)
            )
            conn.commit()

            # Second insert with same payment_id must fail
            with self.assertRaises(sqlite3.IntegrityError):
                cursor.execute(
                    f"""
                    INSERT INTO credit_transactions (
                        id, user_id, amount_inr, credits_added, payment_gateway,
                        gateway_order_id, gateway_payment_id, status, pack_type
                    ) VALUES ({p}, {p}, 100.0, 10.0, 'razorpay', 'order_2', {p}, 'success', 'STARTER');
                    """,
                    (tx2_id, "usr_test_idemp_2", unique_pay_id)
                )
                conn.commit()
        finally:
            try:
                conn.rollback()
            except Exception:
                pass
            cursor.close()
            conn.close()

    def test_null_payment_id_multiple_rows_allowed(self):
        """Multiple transactions with NULL gateway_payment_id must be accepted by partial index."""
        conn = get_db_connection()
        cursor = conn.cursor()
        p = get_placeholder()

        try:
            for i in range(3):
                tx_id = f"tx_null_{uuid.uuid4().hex[:12]}"
                cursor.execute(
                    f"""
                    INSERT INTO credit_transactions (
                        id, user_id, amount_inr, credits_added, payment_gateway,
                        gateway_order_id, gateway_payment_id, status, pack_type
                    ) VALUES ({p}, {p}, 0.0, 2.0, 'system_grant', 'GRANT', NULL, 'success', 'WELCOME_GRANT');
                    """,
                    (tx_id, f"usr_null_{i}")
                )
            conn.commit()
        finally:
            cursor.close()
            conn.close()

    def test_empty_payment_id_multiple_rows_allowed(self):
        """Multiple transactions with empty string '' gateway_payment_id must be accepted."""
        conn = get_db_connection()
        cursor = conn.cursor()
        p = get_placeholder()

        try:
            for i in range(3):
                tx_id = f"tx_empty_{uuid.uuid4().hex[:12]}"
                cursor.execute(
                    f"""
                    INSERT INTO credit_transactions (
                        id, user_id, amount_inr, credits_added, payment_gateway,
                        gateway_order_id, gateway_payment_id, status, pack_type
                    ) VALUES ({p}, {p}, 0.0, 1.0, 'manual', '', '', 'success', 'ADJUSTMENT');
                    """,
                    (tx_id, f"usr_empty_{i}")
                )
            conn.commit()
        finally:
            cursor.close()
            conn.close()

    def test_consecutive_admin_grants_do_not_collide(self):
        """Consecutive admin grants must not collide on gateway_payment_id."""
        user_id = f"usr_{uuid.uuid4().hex[:12]}"
        user_email = f"test_grant_user_{uuid.uuid4().hex[:6]}@example.com"
        admin_email = f"admin_{uuid.uuid4().hex[:6]}@example.com"
        user = get_or_create_user(user_id=user_id, email=user_email, full_name="Grant Test User")

        # First grant
        res1 = admin_grant_user_credits(
            admin_email=admin_email,
            target_user_identifier=user_email,
            credits_amount=3.0,
            reason_code="GOODWILL",
            admin_note="First grant test"
        )
        self.assertTrue(res1.get("success"), f"Grant 1 failed: {res1.get('error')}")

        # Second grant by same admin to same user
        res2 = admin_grant_user_credits(
            admin_email=admin_email,
            target_user_identifier=user_email,
            credits_amount=2.0,
            reason_code="GOODWILL",
            admin_note="Second grant test"
        )
        self.assertTrue(res2.get("success"), f"Grant 2 failed: {res2.get('error')}")

        # Verify balance updated correctly
        final_balance = get_user_credits_balance(user_id)
        self.assertAlmostEqual(final_balance, 2.0 + 3.0 + 2.0, places=2)

    def test_add_user_credits_idempotency_prevents_duplicate_credits(self):
        """Replaying add_user_credits with identical gateway_payment_id preserves balance."""
        user_id = f"usr_{uuid.uuid4().hex[:12]}"
        user_email = f"test_idemp_user_{uuid.uuid4().hex[:6]}@example.com"
        user = get_or_create_user(user_id=user_id, email=user_email, full_name="Idempotent User")
        initial_balance = get_user_credits_balance(user_id)

        pay_id = f"pay_sim_{uuid.uuid4().hex[:12]}"
        order_id = f"order_sim_{uuid.uuid4().hex[:12]}"

        # First payment credit addition
        ok1, bal1 = add_user_credits(
            user_id=user_id,
            amount_inr=500.0,
            credits_added=25.0,
            pack_type="PRO_PACK",
            gateway_order_id=order_id,
            gateway_payment_id=pay_id
        )
        self.assertTrue(ok1)
        self.assertEqual(bal1, initial_balance + 25.0)

        # Replay attempt with same pay_id
        ok2, bal2 = add_user_credits(
            user_id=user_id,
            amount_inr=500.0,
            credits_added=25.0,
            pack_type="PRO_PACK",
            gateway_order_id=order_id,
            gateway_payment_id=pay_id
        )
        self.assertTrue(ok2, "Idempotent replay should return success=True")
        self.assertEqual(bal2, bal1, "Idempotent replay must NOT add additional credits")

        # Confirm user balance in DB remains unchanged
        confirmed_balance = get_user_credits_balance(user_id)
        self.assertEqual(confirmed_balance, bal1)


if __name__ == "__main__":
    unittest.main()
