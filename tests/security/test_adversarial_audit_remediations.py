import os
import unittest
from concurrent.futures import ThreadPoolExecutor
from fastapi.testclient import TestClient

os.environ["TESTING"] = "1"
from web.main import app
from core.billing.razorpay import verify_payment_signature
from core.db.users import add_user_credits, get_user_credits, unlock_ticker_for_user
from core.cortex.setu import SetuMatrixEngine


class TestAdversarialAuditRemediations(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    def test_crit01_admin_direct_verify_requires_secret_and_blocks_2fa_reset(self):
        """[CRIT-01] Verify unauthenticated caller cannot reset owner 2FA via direct-verify + ?reset=1."""
        # Half 1: Unauthenticated direct-verify without ADMIN_PASSWORD must not issue admin_2fa_pending
        r1 = self.client.post(
            "/admin/auth/direct-verify",
            data={"email": "admin@moatnomics.com"},
            follow_redirects=False,
        )
        self.assertNotIn(
            "admin_2fa_pending", r1.cookies,
            "CRITICAL: Unauthenticated direct-verify issued admin_2fa_pending cookie without password!"
        )

        # Half 2: Even with a valid pending 2FA token for an enrolled admin, unauthenticated ?reset=1 is blocked
        from web.common import _generate_pending_2fa_token
        from core.db.admin import add_admin_user, set_admin_totp_secret, enable_admin_totp

        admin_email = "owner_crit01@moatnomics.com"
        add_admin_user(admin_email, role="admin", invited_by="system")
        set_admin_totp_secret(admin_email, "JBSWY3DPEHPK3PXP")
        enable_admin_totp(admin_email)

        pending_token = _generate_pending_2fa_token(admin_email)
        r2 = self.client.get(
            "/admin/setup-2fa?reset=1",
            cookies={"admin_2fa_pending": pending_token},
            headers={"x-forwarded-for": "203.0.113.10"},
            follow_redirects=False,
        )
        self.assertEqual(
            r2.status_code, 303,
            "CRITICAL: Enrolled admin 2FA reset allowed without active authentication session!"
        )
        self.assertTrue(
            r2.headers.get("location", "").startswith("/admin/verify-2fa"),
            f"Expected redirect to /admin/verify-2fa, got {r2.headers.get('location')}"
        )

    def test_crit02_simulated_order_blocked_in_production_mode(self):
        """[CRIT-02] Verify order_sim_ / simulated_success is rejected when ENVIRONMENT=production."""
        old_env = os.environ.get("ENVIRONMENT")
        old_test = os.environ.get("TESTING")
        try:
            os.environ["ENVIRONMENT"] = "production"
            os.environ["TESTING"] = "0"
            is_valid = verify_payment_signature(
                order_id="order_sim_audit_check",
                payment_id="pay_sim_audit_check",
                signature="simulated_success",
            )
            self.assertFalse(
                is_valid,
                "CRITICAL: verify_payment_signature accepted order_sim_ in production mode!"
            )
        finally:
            if old_env is None:
                os.environ.pop("ENVIRONMENT", None)
            else:
                os.environ["ENVIRONMENT"] = old_env
            if old_test is not None:
                os.environ["TESTING"] = old_test

    def test_crit03_unauthenticated_unlock_and_synthesize_rejected(self):
        """[CRIT-03] Verify /api/synthesize and /api/dossier/unlock/{ticker} ignore unauthenticated payload.user_id."""
        victim_uid = "usr_victim_audit_test"
        add_user_credits(victim_uid, 5.0, "audit_seed", email="victim@example.com")
        before_credits = get_user_credits(victim_uid)

        resp = self.client.post(
            "/api/dossier/unlock/RELIANCE",
            json={"user_id": victim_uid},
        )
        after_credits = get_user_credits(victim_uid)
        self.assertEqual(
            before_credits, after_credits,
            "CRITICAL: Unauthenticated POST /api/dossier/unlock drained victim user's credits via payload.user_id!"
        )
        self.assertEqual(resp.status_code, 401)

    def test_crit04_api_v1_rejects_arbitrary_prefix_keys(self):
        """[CRIT-04] Verify /api/v1/reports/{ticker} rejects arbitrary sr_dev_ / usr_ strings in production."""
        old_test = os.environ.get("TESTING")
        try:
            os.environ["TESTING"] = "0"
            resp = self.client.get(
                "/api/v1/reports/TCS",
                headers={"X-API-Key": "sr_dev_unregistered_key"},
            )
            self.assertEqual(
                resp.status_code, 401,
                "CRITICAL: Public API v1 accepted arbitrary sr_dev_ prefix without database/HMAC validation!"
            )
        finally:
            if old_test is not None:
                os.environ["TESTING"] = old_test

    def test_crit05_admin_and_ingest_endpoints_require_auth(self):
        """[CRIT-05] Verify /api/admin/* and /api/debt/ingest reject unauthenticated requests."""
        for path, body in [
            ("/api/admin/run-fund-audit", {}),
            ("/api/admin/etfs/trigger-ingest", {}),
            ("/api/debt/ingest", {"isin": "INE999999999", "instrument_name": "Unauthorized Bond"}),
        ]:
            resp = self.client.post(path, json=body)
            self.assertIn(
                resp.status_code, (401, 403),
                f"CRITICAL: {path} allowed unauthenticated state mutation (status {resp.status_code})!"
            )

    def test_high01_concurrent_credit_deduction_atomicity(self):
        """[HIGH-01] Verify 8 concurrent unlock calls with 1.0 credit only succeed once."""
        from core.db.connection import get_db_connection, get_placeholder
        from core.db.users import get_or_create_user
        race_uid = "usr_race_condition_test"

        # Ensure user exists
        get_or_create_user(race_uid, "race@example.com", "Race Test User")

        # Clean prior race test unlocks and reset balance to exactly 1.0 credit
        conn = get_db_connection()
        c = conn.cursor()
        p = get_placeholder()
        c.execute(f"DELETE FROM user_unlocked_dossiers WHERE user_id = {p};", (race_uid,))
        c.execute(f"DELETE FROM credit_usage_ledger WHERE user_id = {p};", (race_uid,))
        c.execute(f"UPDATE user_accounts SET credits_balance = 1.0 WHERE id = {p};", (race_uid,))
        conn.commit()
        conn.close()

        tickers = [f"RACE_TICKER_{i}" for i in range(8)]
        with ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(lambda t: unlock_ticker_for_user(race_uid, t, cost=1.0), tickers))

        successes = [r for r in results if r.get("success") and not r.get("already_unlocked")]
        self.assertEqual(
            len(successes), 1,
            f"HIGH: Race condition allowed {len(successes)} dossier unlocks on a 1.0 credit balance!"
        )

    def test_med03_setu_matrix_handles_none_and_string_inputs(self):
        """[MED-03] Verify SetuMatrixEngine.evaluate does not raise TypeError when optional floats are None/str."""
        res = SetuMatrixEngine.evaluate(
            symbol="TCS",
            equity_fcf_yield_pct="4.5%",
            senior_debt_ytm_pct=None,
            mutual_fund_net_flow_cr=None,
            promoter_pledge_pct=None,
        )
        self.assertEqual(res.symbol, "TCS")

    def test_crit06_admin_pending_2fa_cookie_cannot_substitute_for_admin_session(self):
        """[CRIT-06] Verify admin_2fa_pending token cannot be substituted into admin_session cookie to bypass TOTP."""
        from web.common import _generate_pending_2fa_token, _validate_admin_token

        pending_tok = _generate_pending_2fa_token("admin@moatnomics.com")
        self.assertIsNone(
            _validate_admin_token(pending_tok),
            "CRITICAL: _validate_admin_token accepted an admin_2fa_pending token (2FA bypass via cookie substitution)!"
        )
        resp = self.client.post(
            "/api/admin/run-fund-audit",
            json={},
            cookies={"admin_session": pending_tok},
        )
        self.assertIn(resp.status_code, (401, 403))

    def test_high02_cross_user_order_intent_and_invoice_xss_escaping(self):
        """[HIGH-02] Verify one user cannot claim another user's Razorpay order intent and invoice HTML escapes XSS."""
        from core.billing.razorpay import _record_order_intent, process_successful_payment, generate_invoice_html

        _record_order_intent("order_sim_alice_999", "usr_alice", "single_pass", 19900)
        ok, _, _, msg = process_successful_payment(
            user_id="usr_bob",
            plan_id="single_pass",
            order_id="order_sim_alice_999",
            payment_id="pay_sim_999",
            signature="simulated_success",
        )
        self.assertFalse(ok, f"HIGH: usr_bob claimed usr_alice's order_id! msg={msg}")

        inv_html = generate_invoice_html(
            invoice_number="INV-<script>alert(1)</script>",
            user_email="<img src=x onerror=alert(1)>@example.com",
            plan_name="<b>Single Pass</b>",
            amount_inr=199.0,
            credits_added=1.0,
            payment_id="pay_<script>",
            date_str="2026-10-19",
        )
        self.assertNotIn("<script>", inv_html)
        self.assertNotIn("<img src=x", inv_html)
        self.assertIn("&lt;script&gt;", inv_html)

    def test_high03_debt_ingest_blocks_invalid_isin_and_coupon_bounds(self):
        """[HIGH-03] Verify /api/debt/ingest enforces Indian ISIN prefix and coupon sanity bounds."""
        from web.common import _generate_user_session_token
        from core.db.users import get_or_create_user

        get_or_create_user("usr_pentest_debt", "pentest@example.com", "Rahul Sharma")
        tok = _generate_user_session_token("usr_pentest_debt", "pentest@example.com")

        # 1. Invalid ISIN prefix (not starting with IN)
        r_bad_isin = self.client.post(
            "/api/debt/ingest",
            json={"isin": "XX0000000001", "coupon_rate": 8.5},
            cookies={"user_session_token": tok},
        )
        self.assertEqual(r_bad_isin.status_code, 400)

        # 2. Out-of-bounds coupon (> 30%)
        r_bad_coupon = self.client.post(
            "/api/debt/ingest",
            json={"isin": "INE999Z08011", "coupon_rate": 999.0},
            cookies={"user_session_token": tok},
        )
        self.assertEqual(r_bad_coupon.status_code, 400)

    def test_med04_rfc9116_security_txt_endpoint_and_zero_email_hygiene(self):
        """[MED-04] Verify /.well-known/security.txt and /security.txt conform to RFC 9116 and Directive 2."""
        for path in ("/.well-known/security.txt", "/security.txt"):
            r = self.client.get(path)
            self.assertEqual(r.status_code, 200)
            self.assertIn("Contact: https://moatnomics.com/contact", r.text)
            self.assertIn("Expires:", r.text)
            self.assertIn("Canonical: https://moatnomics.com/.well-known/security.txt", r.text)
            self.assertNotIn("@", r.text, "Directive 2 violation: email address exposed in security.txt")


if __name__ == "__main__":
    unittest.main()

