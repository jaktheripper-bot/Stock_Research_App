"""Test suite for Email OTP authentication, session cookies, database isolation, and CSRF/origin protection."""

import os
os.environ["TESTING"] = "1"

import unittest
from fastapi.testclient import TestClient
from web.main import app
from core.auth.otp import create_email_otp, verify_email_otp
from core.db.connection import get_db_path, _INITIALIZED_DBS
from core.analysis.fundamentals import compute_pead_drift_band

class TestAuthAndIsolation(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    def test_database_isolation_routing(self):
        """Verify that get_db_path() resolves to test_reports.db under TESTING=1."""
        db_path = get_db_path()
        self.assertTrue(
            db_path.endswith("test_reports.db"),
            f"Expected db_path to end with test_reports.db, got {db_path}"
        )
        self.assertIn("reports.db", db_path or "")

    def test_otp_lifecycle_and_verification(self):
        """Test OTP generation, correct verification, and invalid code failure."""
        test_email = "investor_lifecycle@example.com"
        success, msg, code = create_email_otp(test_email)
        self.assertTrue(success, f"Failed to create OTP: {msg}")
        self.assertIsNotNone(code)
        self.assertEqual(len(code), 6)
        self.assertTrue(code.isdigit())

        # Verification with invalid code
        valid_bad, err = verify_email_otp(test_email, "000000")
        self.assertFalse(valid_bad)
        self.assertIn("Invalid", err)

        # Verification with correct code
        valid_good, ok_msg = verify_email_otp(test_email, code)
        self.assertTrue(valid_good)
        self.assertIn("verified", ok_msg.lower())

        # Second verification should fail (already consumed / deleted)
        valid_repeat, _ = verify_email_otp(test_email, code)
        self.assertFalse(valid_repeat)

    def test_otp_test_bypass_code_under_testing_env(self):
        """Verify that mock code 123456 bypasses verification in testing mode."""
        test_email = "bypass_tester@example.com"
        create_email_otp(test_email)
        valid, msg = verify_email_otp(test_email, "123456")
        self.assertTrue(valid)
        self.assertIn("verified", msg.lower())

    def test_api_auth_send_and_verify_otp(self):
        """Test the FastAPI /api/auth/send-otp and /api/auth/verify-otp flow."""
        email = "frontend_user@example.com"
        
        # 1. Send OTP
        resp_send = self.client.post("/api/auth/send-otp", json={"email": email})
        self.assertEqual(resp_send.status_code, 200)
        data_send = resp_send.json()
        self.assertTrue(data_send["success"])
        self.assertIn("test_code", data_send)

        # 2. Verify OTP with test bypass code
        resp_verify = self.client.post("/api/auth/verify-otp", json={
            "email": email,
            "code": "123456"
        })
        self.assertEqual(resp_verify.status_code, 200)
        data_verify = resp_verify.json()
        self.assertTrue(data_verify["success"])
        self.assertIn("user", data_verify)
        self.assertEqual(data_verify["user"]["email"], email)

        # Ensure session cookie was set in response
        self.assertIn("user_session_token", resp_verify.cookies)

        # 3. Access /api/auth/me using the returned session cookie
        cookies = {"user_session_token": resp_verify.cookies["user_session_token"]}
        resp_me = self.client.get("/api/auth/me", cookies=cookies)
        self.assertEqual(resp_me.status_code, 200)
        data_me = resp_me.json()
        self.assertTrue(data_me["authenticated"])
        self.assertEqual(data_me["user"]["email"], email)

        # 4. Sign out
        resp_out = self.client.post("/api/auth/signout", cookies=cookies)
        self.assertEqual(resp_out.status_code, 200)
        self.assertTrue(resp_out.json()["success"])

    def test_csrf_origin_validation_rejection(self):
        """Verify that state-mutating endpoints reject untrusted cross-origin requests."""
        # Unapproved origin on /api/create-order
        headers = {"Origin": "https://malicious-phishing-site.xyz"}
        resp_order = self.client.post("/api/create-order", json={"plan_id": "single"}, headers=headers)
        self.assertEqual(resp_order.status_code, 403)
        self.assertIn("Cross-origin request rejected", resp_order.json().get("detail", ""))

        # Unapproved origin on /api/premortem
        resp_pm = self.client.post(
            "/api/premortem",
            json={"ticker": "INFY", "failure_vector": "Margin Compression", "anti_thesis_notes": "Test anti thesis"},
            headers=headers
        )
        self.assertEqual(resp_pm.status_code, 403)
        self.assertIn("Cross-origin request rejected", resp_pm.json().get("detail", ""))

    def test_pead_drift_band_computation(self):
        """Verify PEAD drift band calculations for bullish and bearish vectors."""
        # Test bullish stock (price > 50-DMA)
        stock_bull = {"current_price": 1000.0}
        import pandas as pd
        df_bull = pd.DataFrame({"Close": [900.0] * 50})
        res_bull = compute_pead_drift_band(stock_bull, df_bull)
        self.assertTrue(res_bull["active"])
        self.assertEqual(res_bull["status"], "bullish")
        self.assertEqual(res_bull["vector"], "ACCUMULATION_DRIFT")
        self.assertGreater(res_bull["target_drift"], 1000.0)
        self.assertGreater(res_bull["upper_bound"], res_bull["target_drift"])

        # Test bearish stock (price < 50-DMA)
        stock_bear = {"current_price": 800.0}
        df_bear = pd.DataFrame({"Close": [950.0] * 50})
        res_bear = compute_pead_drift_band(stock_bear, df_bear)
        self.assertTrue(res_bear["active"])
        self.assertEqual(res_bear["status"], "bearish")
        self.assertEqual(res_bear["vector"], "COMPRESSION_DRIFT")
        self.assertLess(res_bear["target_drift"], 800.0)
        self.assertIn("Disposition Effect", res_bear["guidance"])


if __name__ == "__main__":
    unittest.main()
