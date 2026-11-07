"""
tests/unit/test_p0_credit_and_db_containment.py
==============================================================================
Verifies Milestone 1 (P0 Containment) invariants:
1. Shared DB boundary fails closed on PostgreSQL outage in hosted/configured mode:
   zero fallback writes to local SQLite across payments, credits, unlocks, admin grants,
   and report saves, while FastAPI routes return HTTP 503 Service Unavailable.
2. FORCE_LOCAL_SQLITE=1 cannot override hosted production detection.
3. Admin Copilot proposals are stored server-side, bound to actor, and consumed once:
   - Self-grants are never auto-executed by chat/LLM turns.
   - Replay of a consumed proposal_id is rejected.
   - Tampering with target_user or credits payload on execute is rejected.
   - Another admin attempting to execute someone else's proposal_id is rejected.
   - Non-finite (NaN/Inf), negative, or over-limit (>10.0) credit amounts are rejected without clipping.
   - Cumulative 24h target (10.0) and actor (25.0) limits block excess grants.
4. Razorpay payment reconciliation uses a single durable intent and atomic fulfilment path:
   - Dropped browser callback recovered by webhook credits account once.
   - Duplicate webhook delivery is idempotent (credits once).
   - Browser callback racing webhook in parallel threads credits account once.
   - Mismatched amount, currency, plan, or user_id is rejected with zero credits added.
"""

import asyncio
import hashlib
import hmac
import json
import os
import sqlite3
import tempfile
import threading
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from unittest.mock import patch

from fastapi.testclient import TestClient

from core.agents.copilot.admin_copilot import (
    AdminActionType,
    execute_confirmed_admin_action,
    process_admin_copilot_turn,
)
from core.billing.razorpay import (
    create_razorpay_order,
    fulfill_razorpay_order,
    process_successful_payment,
    verify_webhook_signature,
)
from core.db.admin import (
    admin_grant_user_credits,
    store_admin_action_proposal,
)
from core.db.connection import (
    AuthoritativeDatabaseUnavailable,
    get_db_connection,
    init_db,
)
from core.db.reports import save_report_to_archive
from core.db.users import (
    add_user_credits,
    deduct_user_credits,
    get_or_create_user,
    get_user_credits_balance,
    unlock_ticker_for_user,
)
from web.main import app


class TestP0CreditAndDbContainment(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.tmp_dir.name, "test_p0.db")
        self.env_patcher = patch.dict(
            os.environ,
            {
                "TESTING": "1",
                "FORCE_LOCAL_SQLITE": "1",
                "TEST_DB_PATH": self.db_path,
                "RAZORPAY_KEY_ID": "",
                "RAZORPAY_KEY_SECRET": "",
                "RAZORPAY_WEBHOOK_SECRET": "test_webhook_secret_888",
                "ADMIN_PASSWORD": "test_admin_pwd_default",
            },
        )
        self.env_patcher.start()
        import core.db.connection as db_conn

        db_conn._DB_INITIALIZED = False
        db_conn._INITIALIZED_DBS.clear()
        db_conn._SUPABASE_URL_RESOLVED = False
        db_conn._PG_AVAILABLE = None
        init_db(force=True)

        get_or_create_user("usr_alice", "alice@example.com", "Alice Sharma")
        get_or_create_user("usr_bob", "bob@example.com", "Bob Verma")
        get_or_create_user("usr_admin", "owner@example.com", "Owner Admin")

    def tearDown(self):
        self.env_patcher.stop()
        import core.db.connection as db_conn

        db_conn._DB_INITIALIZED = False
        db_conn._INITIALIZED_DBS.clear()
        db_conn._SUPABASE_URL_RESOLVED = False
        db_conn._PG_AVAILABLE = None
        self.tmp_dir.cleanup()

    def _sqlite_DataVersion(self) -> int:
        with sqlite3.connect(self.db_path) as raw_sq:
            return int(raw_sq.execute("PRAGMA data_version;").fetchone()[0])

    def _sqlite_row_counts(self) -> dict:
        with sqlite3.connect(self.db_path) as raw_sq:
            tables = (
                "user_accounts",
                "credit_transactions",
                "credit_usage_ledger",
                "user_unlocked_dossiers",
                "admin_audit_log",
                "admin_action_proposals",
                "billing_order_intents",
                "reports",
            )
            return {
                tbl: int(raw_sq.execute(f"SELECT COUNT(*) FROM {tbl};").fetchone()[0])
                for tbl in tables
            }

    def test_postgres_outage_fails_closed_with_zero_sqlite_writes_and_http_503(self):
        """Inject a PostgreSQL outage in hosted production mode (even with FORCE_LOCAL_SQLITE=1) and verify 503 + zero writes to SQLite."""
        before_alice = get_user_credits_balance("usr_alice")
        counts_before = self._sqlite_row_counts()
        client = TestClient(app, raise_server_exceptions=False)

        with patch.dict(
            os.environ,
            {
                "RENDER": "true",
                "ENVIRONMENT": "production",
                "FORCE_LOCAL_SQLITE": "1",  # Must be ignored in hosted production
                "SUPABASE_DB_URL": "postgresql://unreachable_user:pwd@127.0.0.1:59999/unreach_db",
                "RAZORPAY_KEY_ID": "rzp_test_livecheck",
                "RAZORPAY_KEY_SECRET": "rzp_secret_livecheck",
            },
        ):
            import core.db.connection as db_conn

            db_conn._SUPABASE_URL_RESOLVED = False
            db_conn._PG_AVAILABLE = None

            # 1. Direct connection acquisition must raise AuthoritativeDatabaseUnavailable (first failure & cooldown)
            with self.assertRaises(AuthoritativeDatabaseUnavailable):
                get_db_connection()
            with self.assertRaises(AuthoritativeDatabaseUnavailable):
                get_db_connection()

            # 2. Credit deduction, top-up, unlock, admin grant, and report save must all fail closed
            with self.assertRaises(AuthoritativeDatabaseUnavailable):
                deduct_user_credits("usr_alice", "INFY", "DEEP_DIVE_UNLOCK", 1.0)

            with self.assertRaises(AuthoritativeDatabaseUnavailable):
                add_user_credits("usr_alice", 299.0, 1.0, "SINGLE_PASS", "ord_1", "pay_1")

            with self.assertRaises(AuthoritativeDatabaseUnavailable):
                unlock_ticker_for_user("usr_alice", "INFY", 1.0)

            with self.assertRaises(AuthoritativeDatabaseUnavailable):
                admin_grant_user_credits("owner@example.com", "alice@example.com", 2.0)

            with self.assertRaises(AuthoritativeDatabaseUnavailable):
                save_report_to_archive({"ticker": "INFY", "current_price": 1500}, "A" * 600)

            # 3. HTTP routes (webhook, verify) report 503 Service Unavailable during PG outage
            webhook_payload = json.dumps({
                "event": "payment.captured",
                "payload": {
                    "payment": {
                        "entity": {
                            "id": "pay_outage_1",
                            "order_id": "order_outage_1",
                            "status": "captured",
                            "amount": 29900,
                            "currency": "INR",
                        }
                    }
                },
            }).encode("utf-8")
            wh_sig = hmac.new(b"test_webhook_secret_888", webhook_payload, hashlib.sha256).hexdigest()
            resp_wh = client.post(
                "/api/billing/webhook",
                content=webhook_payload,
                headers={"Content-Type": "application/json", "X-Razorpay-Signature": wh_sig},
            )
            self.assertEqual(resp_wh.status_code, 503)

            pay_sig = hmac.new(b"rzp_secret_livecheck", b"order_outage_1|pay_outage_1", hashlib.sha256).hexdigest()
            with patch("core.billing.razorpay.get_razorpay_client") as mock_rzp_client:
                mock_rzp_client.return_value.payment.fetch.return_value = {
                    "id": "pay_outage_1", "order_id": "order_outage_1", "status": "captured",
                    "amount": 29900, "currency": "INR",
                }
                resp_ver = client.post(
                    "/api/billing/verify",
                    json={
                        "order_id": "order_outage_1",
                        "payment_id": "pay_outage_1",
                        "signature": pay_sig,
                        "user_id": "usr_alice",
                        "plan_id": "single_pass",
                    },
                )
            self.assertEqual(resp_ver.status_code, 503)

        # Verify local SQLite had ZERO writes across every table during the simulated outage
        import core.db.connection as db_conn

        db_conn._SUPABASE_URL_RESOLVED = False
        db_conn._PG_AVAILABLE = None
        after_alice = get_user_credits_balance("usr_alice")
        counts_after = self._sqlite_row_counts()
        self.assertEqual(before_alice, after_alice)
        self.assertEqual(counts_before, counts_after)


    @staticmethod
    def _wrap_conn_with_audit_read_latency(delay_sec: float = 0.05):
        """Inject latency on admin_audit_log reads to expose any check-then-insert race."""
        import core.db.admin as adm_mod

        orig_get_conn = adm_mod.get_db_connection

        class _LatencyCursor:
            def __init__(self, cur):
                self._cur = cur

            def execute(self, sql, *args, **kwargs):
                res = self._cur.execute(sql, *args, **kwargs)
                if "FROM admin_audit_log" in str(sql):
                    time.sleep(delay_sec)
                return res

            def __getattr__(self, name):
                return getattr(self._cur, name)

        class _LatencyConn:
            def __init__(self, conn):
                self._conn = conn

            def cursor(self, *args, **kwargs):
                return _LatencyCursor(self._conn.cursor(*args, **kwargs))

            def __getattr__(self, name):
                return getattr(self._conn, name)

        return patch.object(adm_mod, "get_db_connection", side_effect=lambda: _LatencyConn(orig_get_conn()))

    def test_concurrent_grants_share_target_cap_across_id_and_email(self):
        starting_balance = get_user_credits_balance("usr_alice")
        barrier = threading.Barrier(2)

        def grant(actor, target):
            barrier.wait(timeout=5)
            return admin_grant_user_credits(actor, target, 6.0)

        with self._wrap_conn_with_audit_read_latency(0.05), ThreadPoolExecutor(max_workers=2) as pool:
            first = pool.submit(grant, "owner@example.com", "usr_alice")
            second = pool.submit(grant, "other-admin@example.com", "alice@example.com")
            results = [first.result(timeout=10), second.result(timeout=10)]

        self.assertEqual(sum(result["success"] for result in results), 1, results)
        rejected = next(result for result in results if not result["success"])
        self.assertIn("24h target grant limit exceeded", rejected["error"])
        self.assertEqual(get_user_credits_balance("usr_alice"), starting_balance + 6.0)

    def test_concurrent_grants_share_actor_cap_across_targets(self):
        get_or_create_user("usr_carol", "carol@example.com", "Carol")
        get_or_create_user("usr_dan", "dan@example.com", "Dan")
        actor = "owner@example.com"
        for target in ("usr_alice", "usr_bob"):
            self.assertTrue(admin_grant_user_credits(actor, target, 10.0)["success"])
        targets = ("usr_carol", "usr_dan")
        starting_total = sum(get_user_credits_balance(target) for target in targets)
        barrier = threading.Barrier(2)

        def grant(target):
            barrier.wait(timeout=5)
            return admin_grant_user_credits(actor, target, 4.0)

        with self._wrap_conn_with_audit_read_latency(0.05), ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(grant, targets))

        self.assertEqual(sum(result["success"] for result in results), 1, results)
        rejected = next(result for result in results if not result["success"])
        self.assertIn("24h administrator grant limit exceeded", rejected["error"])
        self.assertEqual(sum(get_user_credits_balance(target) for target in targets), starting_total + 4.0)

    def test_postgres_grant_cap_locks_actor_and_target_before_reading_audit_history(self):
        """PostgreSQL path must take the actor advisory lock and the target FOR UPDATE lock BEFORE reading admin_audit_log."""
        executed_sql = []

        class _FakePgCursor:
            def execute(self, sql, params=None):
                norm = " ".join(str(sql).split())
                executed_sql.append((norm, params))
                self._last = norm

            def fetchone(self):
                if "FROM user_accounts" in self._last:
                    return ("usr_alice", "alice@example.com", "Alice Sharma", 2.0)
                return None

            def fetchall(self):
                if "FROM admin_audit_log" in self._last:
                    return [(json.dumps({"user_id": "usr_alice", "user_email": "alice@example.com", "credits_granted": 6.0}), "other@example.com")]
                return []

            def close(self):
                pass

        class _FakePgConn:
            def cursor(self):
                return _FakePgCursor()

            def commit(self):
                pass

            def rollback(self):
                pass

            def close(self):
                pass

        with patch("core.db.admin.is_postgres_connection", return_value=True):
            res = admin_grant_user_credits(
                "owner@example.com",
                "alice@example.com",
                6.0,
                connection=_FakePgConn(),
            )
        self.assertFalse(res["success"])
        self.assertIn("24h target grant limit exceeded", res["error"])
        queries = [q for q, _ in executed_sql]
        adv_idx = next((i for i, q in enumerate(queries) if "pg_advisory_xact_lock(193759, hashtext(%s))" in q), -1)
        usr_idx = next((i for i, q in enumerate(queries) if "FROM user_accounts" in q and "FOR UPDATE" in q), -1)
        aud_idx = next((i for i, q in enumerate(queries) if "FROM admin_audit_log" in q and "statement_timestamp()" in q), -1)
        self.assertGreaterEqual(adv_idx, 0, f"Missing pg_advisory_xact_lock in: {queries}")
        self.assertGreater(usr_idx, adv_idx, f"user_accounts FOR UPDATE must follow advisory lock: {queries}")
        self.assertGreater(aud_idx, usr_idx, f"admin_audit_log read must follow both locks: {queries}")

    def _insert_grant_audit(self, audit_id, details, created_at=None, admin="other@example.com"):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO admin_audit_log
                    (id, admin_email, action, details, created_at)
                VALUES (?, ?, 'GRANT_USER_CREDITS', ?, COALESCE(?, datetime('now')))
                """,
                (audit_id, admin, details, created_at),
            )
            conn.commit()

    def test_credit_grant_history_fails_closed_on_invalid_recent_amounts(self):
        original_balance = get_user_credits_balance("usr_alice")
        invalid_details = (
            "{not-json",
            json.dumps({}),
            json.dumps({"credits_granted": "NaN"}),
            json.dumps({"credits_granted": -1}),
        )

        for index, details in enumerate(invalid_details):
            with self.subTest(details=details):
                with sqlite3.connect(self.db_path) as conn:
                    conn.execute(
                        "DELETE FROM admin_audit_log WHERE action = 'GRANT_USER_CREDITS'"
                    )
                    conn.commit()

                self._insert_grant_audit(f"aud_invalid_{index}", details)
                result = admin_grant_user_credits(
                    "owner@example.com",
                    "alice@example.com",
                    1.0,
                )
                self.assertFalse(result["success"])
                self.assertIn("history failed integrity validation", result["error"])
                self.assertEqual(
                    get_user_credits_balance("usr_alice"),
                    original_balance,
                )

    def test_email_identity_and_ist_boundary_control_target_cap(self):
        from core.db.connection import IST

        now_ist = datetime.now(IST)
        old_timestamp = (now_ist - timedelta(hours=25)).isoformat(
            sep=" ", timespec="seconds"
        )
        recent_timestamp = (now_ist - timedelta(hours=2)).isoformat(
            sep=" ", timespec="seconds"
        )

        self._insert_grant_audit(
            "aud_expired_bob",
            json.dumps(
                {
                    "user_id": "usr_bob",
                    "user_email": "bob@example.com",
                    "credits_granted": 9.0,
                }
            ),
            old_timestamp,
        )
        self._insert_grant_audit(
            "aud_prior_alice_id",
            json.dumps(
                {
                    "user_id": "usr_legacy_alice",
                    "user_email": "alice@example.com",
                    "credits_granted": 7.0,
                }
            ),
            recent_timestamp,
        )

        self.assertTrue(
            admin_grant_user_credits(
                "owner@example.com", "usr_bob", 5.0
            )["success"]
        )
        result = admin_grant_user_credits(
            "owner@example.com", "usr_alice", 4.0
        )
        self.assertFalse(result["success"])
        self.assertIn("24h target grant limit exceeded", result["error"])

    def test_ticket_reply_reports_rejected_remedial_grant_truthfully(self):
        from core.db.support import create_support_ticket
        from web.common import ADMIN_COOKIE_NAME, _generate_admin_token

        self._insert_grant_audit(
            "aud_alice_cap",
            json.dumps(
                {
                    "user_id": "usr_prior_alice",
                    "user_email": "alice@example.com",
                    "credits_granted": 10.0,
                }
            ),
        )
        ticket = create_support_ticket(
            "alice@example.com",
            "Credit issue",
            "Please review",
            user_name="Alice Sharma",
        )
        cookie = _generate_admin_token("owner@example.com", "owner")
        client = TestClient(app, raise_server_exceptions=False)
        response = client.post(
            "/api/admin/tickets/reply",
            data={
                "ticket_id": ticket["ticket_id"],
                "reply_message": "We investigated the issue.",
                "dispatch_email": "off",
                "grant_remedial_credits": "1.0",
            },
            headers={
                "Cookie": f"{ADMIN_COOKIE_NAME}={cookie}",
                "Origin": "http://testserver",
                "Accept": "application/json",
                "X-Requested-With": "XMLHttpRequest",
            },
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["credits_granted"], 0.0)
        self.assertIn("24h target grant limit exceeded", body["grant_error"])

    def test_admin_copilot_proposal_binding_one_time_consumption_and_tamper_rejection(self):
        """Verify self-grants require confirmation, proposals are actor-bound, tamper-proof, one-time, and enforce finite/cumulative limits."""
        admin_user = {"email": "owner@example.com", "role": "owner"}
        start_bal = get_user_credits_balance("usr_admin")

        # 1. Self-grant prompt must NOT auto-execute; it must return a stored proposal
        turn = asyncio.run(process_admin_copilot_turn(admin_user, "Grant 5 credits to myself"))
        self.assertNotEqual(turn.get("status"), "COMPLETED_EXECUTED")
        proposal = turn.get("action_proposal")
        self.assertIsNotNone(proposal)
        prop_id = proposal["proposal_id"]
        self.assertEqual(get_user_credits_balance("usr_admin"), start_bal)

        # 2. Executing without proposal_id must be rejected
        missing_prop = execute_confirmed_admin_action(
            action_type=AdminActionType.GRANT_CREDITS,
            payload=proposal["payload"],
            admin_user=admin_user,
        )
        self.assertFalse(missing_prop["success"])

        # 3. Tampering with payload (changing credits from 5.0 to 10.0) must be rejected without granting
        tampered = execute_confirmed_admin_action(
            proposal_id=prop_id,
            action_type=AdminActionType.GRANT_CREDITS,
            payload={**proposal["payload"], "credits": 10.0},
            admin_user=admin_user,
        )
        self.assertFalse(tampered["success"])
        self.assertEqual(get_user_credits_balance("usr_admin"), start_bal)

        # 4. Different administrator attempting to execute owner's proposal must be rejected
        other_admin = {"email": "other_admin@example.com", "role": "admin"}
        wrong_actor = execute_confirmed_admin_action(
            proposal_id=prop_id,
            admin_user=other_admin,
        )
        self.assertFalse(wrong_actor["success"])
        self.assertIn("different administrator", wrong_actor["error"])

        # 5. Valid confirmation by the original actor succeeds once (+5.0 credits)
        ok_res = execute_confirmed_admin_action(
            proposal_id=prop_id,
            action_type=proposal["action_type"],
            payload=proposal["payload"],
            admin_user=admin_user,
        )
        self.assertTrue(ok_res["success"], f"Expected success, got: {ok_res}")
        self.assertEqual(get_user_credits_balance("usr_admin"), start_bal + 5.0)

        # 6. Replaying the exact same proposal_id a second time must fail
        replay = execute_confirmed_admin_action(
            proposal_id=prop_id,
            action_type=proposal["action_type"],
            payload=proposal["payload"],
            admin_user=admin_user,
        )
        self.assertFalse(replay["success"])
        self.assertEqual(get_user_credits_balance("usr_admin"), start_bal + 5.0)

        # 7. Over-limit (>10.0) and non-finite (NaN/Inf) amounts are rejected, never clipped
        over_turn = asyncio.run(process_admin_copilot_turn(admin_user, "Grant 50 credits to alice@example.com"))
        self.assertIsNone(over_turn.get("action_proposal"))
        self.assertIn("must be between 0.1 and 10.0", over_turn.get("reply", ""))

        nan_prop_id = store_admin_action_proposal(
            "owner@example.com",
            AdminActionType.GRANT_CREDITS,
            {"target_user": "alice@example.com", "credits": "nan"},
        )
        nan_res = execute_confirmed_admin_action(proposal_id=nan_prop_id, admin_user=admin_user)
        self.assertFalse(nan_res["success"])

        # 8. Cumulative 24h target limit (10.0/24h): granting another 6.0 to usr_admin (already received 5.0) fails
        second_turn = asyncio.run(process_admin_copilot_turn(admin_user, "Grant 6 credits to myself"))
        second_prop = second_turn["action_proposal"]
        second_exec = execute_confirmed_admin_action(proposal_id=second_prop["proposal_id"], admin_user=admin_user)
        self.assertFalse(second_exec["success"])
        self.assertIn("24h target grant limit exceeded", second_exec["error"])
        self.assertEqual(get_user_credits_balance("usr_admin"), start_bal + 5.0)

    def test_browser_callback_requires_captured_payment_for_exact_order(self):
        order_id, payment_id = "order_capture_fixture", "pay_capture_fixture"
        payment = {
            "id": payment_id, "order_id": order_id, "status": "captured",
            "amount": 29900, "currency": "INR",
        }
        with (
            patch("core.billing.razorpay.verify_payment_signature", return_value=True),
            patch("core.billing.razorpay.get_razorpay_client") as client,
            patch("core.billing.razorpay.fulfill_razorpay_order", return_value=(True, 1.0, "INV", "OK")) as fulfill,
        ):
            fetch = client.return_value.payment.fetch
            for value in (
                None,
                {**payment, "status": "authorized"},
                {**payment, "status": "failed"},
                {**payment, "id": "pay_other"},
                {**payment, "order_id": "order_other"},
                {**payment, "amount": True},
                {**payment, "currency": None},
            ):
                with self.subTest(value=value):
                    fetch.return_value = value
                    result = process_successful_payment("usr_alice", "single_pass", order_id, payment_id, "signed")
                    self.assertFalse(result[0])
                    fulfill.assert_not_called()

            fetch.return_value = payment
            result = process_successful_payment("usr_alice", "single_pass", order_id, payment_id, "signed")
            self.assertTrue(result[0])
            fetch.assert_called_with(payment_id, timeout=8)
            client.return_value.order.fetch.assert_not_called()
            fulfill.assert_called_once_with(
                order_id=order_id, payment_id=payment_id, claimed_user_id="usr_alice",
                claimed_plan_id="single_pass", verified_amount_paise=29900, verified_currency="INR",
            )

        # If webhook already fulfilled the order, a later browser callback during a gateway outage
        # must return the idempotent fulfilled receipt (never "Credits have not been issued").
        from core.billing.razorpay import _record_order_intent
        live_oid, live_pid = "order_live_webhook_first", "pay_live_webhook_first"
        _record_order_intent(live_oid, "usr_alice", "single_pass", 29900, user_email="alice@example.com", is_simulated=False)
        bal_before = get_user_credits_balance("usr_alice")
        wh_ok, wh_bal, wh_inv, _ = fulfill_razorpay_order(
            order_id=live_oid, payment_id=live_pid, verified_amount_paise=29900, verified_currency="INR",
        )
        self.assertTrue(wh_ok)
        self.assertEqual(wh_bal, bal_before + 1.0)
        with (
            patch("core.billing.razorpay.verify_payment_signature", return_value=True),
            patch("core.billing.razorpay.get_razorpay_client", return_value=None),
        ):
            cb_ok, cb_bal, cb_inv, cb_msg = process_successful_payment(
                "usr_alice", "single_pass", live_oid, live_pid, "signed"
            )
            self.assertTrue(cb_ok, f"Expected idempotent success after webhook fulfilment, got: {cb_msg}")
            self.assertEqual(cb_bal, wh_bal)
            self.assertEqual(cb_inv, wh_inv)
            self.assertIn("idempotent replay", cb_msg)

    def test_razorpay_dropped_callback_duplicate_webhook_race_and_mismatch(self):
        """Test dropped browser callback recovered by webhook, duplicate webhook, callback racing webhook, and mismatched details."""
        start_bal = get_user_credits_balance("usr_alice")
        bob_start_bal = get_user_credits_balance("usr_bob")
        client = TestClient(app)

        # Case A: Dropped browser callback -> fulfilled by signed server webhook (/api/billing/webhook)
        order_a = create_razorpay_order(plan_id="analyst_3pack", user_id="usr_alice", user_email="alice@example.com")
        oid_a = order_a["order_id"]
        pid_a = "pay_sim_webhook_001"

        # Mismatched amount (29900 paise instead of 69900 paise for analyst_3pack) must fail
        bad_amt_ok, _, _, _ = fulfill_razorpay_order(
            order_id=oid_a,
            payment_id=pid_a,
            verified_amount_paise=29900,
            verified_currency="INR",
        )
        self.assertFalse(bad_amt_ok)
        self.assertEqual(get_user_credits_balance("usr_alice"), start_bal)

        # Mismatched user_id claim must fail
        bad_usr_ok, _, _, _ = fulfill_razorpay_order(
            order_id=oid_a,
            payment_id=pid_a,
            claimed_user_id="usr_bob",
            verified_amount_paise=69900,
            verified_currency="INR",
        )
        self.assertFalse(bad_usr_ok)

        # Signed webhook delivery succeeds (+3.0 credits) even if notes try to spoof user/plan
        wh_body = json.dumps({
            "event": "payment.captured",
            "payload": {
                "payment": {
                    "entity": {
                        "id": pid_a,
                        "order_id": oid_a,
                        "status": "captured",
                        "amount": 69900,
                        "currency": "INR",
                        "notes": {"user_id": "usr_bob", "plan_id": "pro_annual"},
                    }
                }
            },
        }).encode("utf-8")
        wh_sig = hmac.new(b"test_webhook_secret_888", wh_body, hashlib.sha256).hexdigest()
        self.assertTrue(verify_webhook_signature(wh_body, wh_sig))
        self.assertFalse(verify_webhook_signature(wh_body, "bad_sig"))

        r_wh1 = client.post(
            "/api/billing/webhook",
            content=wh_body,
            headers={"Content-Type": "application/json", "X-Razorpay-Signature": wh_sig},
        )
        self.assertEqual(r_wh1.status_code, 200)
        self.assertEqual(get_user_credits_balance("usr_alice"), start_bal + 3.0)
        self.assertEqual(get_user_credits_balance("usr_bob"), bob_start_bal)
        inv1 = r_wh1.json()["invoice_number"]

        # Duplicate webhook delivery for the same payment is idempotent (still +3.0 credits)
        r_wh2 = client.post(
            "/api/billing/webhook",
            content=wh_body,
            headers={"Content-Type": "application/json", "X-Razorpay-Signature": wh_sig},
        )
        self.assertEqual(r_wh2.status_code, 200)
        self.assertEqual(get_user_credits_balance("usr_alice"), start_bal + 3.0)
        self.assertEqual(r_wh2.json()["invoice_number"], inv1)

        # Case B: Browser callback racing webhook concurrently
        order_b = create_razorpay_order(plan_id="single_pass", user_id="usr_alice", user_email="alice@example.com")
        oid_b = order_b["order_id"]
        pid_b = "pay_sim_race_002"
        results = []

        def run_browser_callback():
            results.append(
                process_successful_payment(
                    user_id="usr_alice",
                    plan_id="single_pass",
                    order_id=oid_b,
                    payment_id=pid_b,
                    signature="sig_sim_valid",
                )
            )

        def run_webhook():
            results.append(
                fulfill_razorpay_order(
                    order_id=oid_b,
                    payment_id=pid_b,
                    verified_amount_paise=29900,
                    verified_currency="INR",
                )
            )

        t1 = threading.Thread(target=run_browser_callback)
        t2 = threading.Thread(target=run_webhook)
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        self.assertEqual(len(results), 2)
        self.assertTrue(all(r[0] for r in results), f"Race results: {results}")
        # Balance increased by exactly 1.0 credit (from start_bal + 3.0 to start_bal + 4.0)
        self.assertEqual(get_user_credits_balance("usr_alice"), start_bal + 4.0)

        # Case C: Session-bound billing principal rejects cross-user spoofing and unauthenticated production calls
        from web.common import USER_SESSION_COOKIE, _generate_user_session_token
        alice_cookie = _generate_user_session_token("usr_alice", "alice@example.com")
        cookie_hdr = {"Cookie": f"{USER_SESSION_COOKIE}={alice_cookie}"}
        spoof_order = client.post(
            "/api/create-order",
            json={"plan_id": "single_pass", "user_id": "usr_bob", "email": "bob@example.com"},
            headers=cookie_hdr,
        )
        self.assertEqual(spoof_order.status_code, 403)
        self.assertIn("does not match authenticated session", spoof_order.json().get("detail", ""))

        spoof_verify = client.post(
            "/api/verify-payment",
            json={
                "order_id": oid_b,
                "payment_id": pid_b,
                "signature": "sig_sim_valid",
                "plan_id": "single_pass",
                "user_id": "usr_bob",
            },
            headers=cookie_hdr,
        )
        self.assertEqual(spoof_verify.status_code, 403)

        with patch.dict(os.environ, {"ENVIRONMENT": "production"}, clear=False):
            unauth_prod = client.post(
                "/api/create-order",
                json={"plan_id": "single_pass", "user_id": "usr_alice"},
            )
            self.assertEqual(unauth_prod.status_code, 401)


if __name__ == "__main__":
    unittest.main()
