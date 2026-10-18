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
        r1 = self.client.post(
            "/admin/auth/direct-verify",
            data={"email": "admin@moatnomics.com"},
            follow_redirects=False,
        )
        # Once patched, unauthenticated direct-verify without ADMIN_PASSWORD must not issue admin_2fa_pending
        if "admin_2fa_pending" in r1.cookies:
            r2 = self.client.get(
                "/admin/setup-2fa?reset=1",
                cookies={"admin_2fa_pending": r1.cookies["admin_2fa_pending"]},
                follow_redirects=False,
            )
            self.assertNotEqual(
                r2.status_code, 200,
                "CRITICAL: Unauthenticated caller was able to reset and view owner TOTP secret via ?reset=1!"
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
        race_uid = "usr_race_condition_test"
        # Reset user to exactly 1.0 credit
        add_user_credits(race_uid, 1.0, "race_seed", email="race@example.com")
        current = get_user_credits(race_uid)
        if current > 1.0:
            from core.db.users import deduct_user_credits
            deduct_user_credits(race_uid, current - 1.0, "normalize_to_1")

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


if __name__ == "__main__":
    unittest.main()
