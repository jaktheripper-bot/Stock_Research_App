"""
Consolidated Auth, Security, Admin Remediation & Production Hardening Suite
===========================================================================
Unifies:
1. Email OTP authentication, session cookies, database isolation, and CSRF/origin protection
2. Admin direct remedial credit granting, atomic DB transactions, audit logging & ticket updates
3. Render production configuration, worker concurrency, and secret key boot guards
"""
import asyncio
import os
from pathlib import Path
import unittest
from unittest.mock import patch
import uuid

os.environ["TESTING"] = "1"

from fastapi import FastAPI
from fastapi.testclient import TestClient

from core.analysis.fundamentals import compute_pead_drift_band
from core.auth.otp import create_email_otp, verify_email_otp
from core.db.admin import (
    admin_grant_user_credits,
    get_admin_audit_logs,
)
from core.db.connection import get_db_path, init_db
from core.db.support import create_support_ticket, get_support_tickets
from core.db.users import (
    get_all_billables,
    get_or_create_user,
    get_user_by_email,
    get_user_credits_balance,
)
from web.main import (
    ADMIN_COOKIE_NAME,
    _generate_admin_token,
    _generate_user_session_token,
    app,
    lifespan,
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


# ==============================================================================
# 1. User Authentication, Session Cookies & CSRF Origin Isolation
# ==============================================================================
class TestAuthAndIsolation(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    def test_database_isolation_routing(self):
        db_path = get_db_path()
        self.assertTrue(
            db_path.endswith("test_reports.db"),
            f"Expected db_path to end with test_reports.db, got {db_path}"
        )
        self.assertIn("reports.db", db_path or "")

    def test_otp_lifecycle_and_verification(self):
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
        test_email = "bypass_tester@example.com"
        create_email_otp(test_email)
        valid, msg = verify_email_otp(test_email, "123456")
        self.assertTrue(valid)
        self.assertIn("verified", msg.lower())

    def test_api_auth_send_and_verify_otp(self):
        email = "frontend_user@example.com"

        resp_send = self.client.post("/api/auth/send-otp", json={"email": email})
        self.assertEqual(resp_send.status_code, 200)
        data_send = resp_send.json()
        self.assertTrue(data_send["success"])
        self.assertIn("test_code", data_send)

        resp_verify = self.client.post("/api/auth/verify-otp", json={
            "email": email,
            "code": "123456"
        })
        self.assertEqual(resp_verify.status_code, 200)
        data_verify = resp_verify.json()
        self.assertTrue(data_verify["success"])
        self.assertIn("user", data_verify)
        self.assertEqual(data_verify["user"]["email"], email)
        self.assertIn("user_session_token", resp_verify.cookies)

        cookies = {"user_session_token": resp_verify.cookies["user_session_token"]}
        resp_me = self.client.get("/api/auth/me", cookies=cookies)
        self.assertEqual(resp_me.status_code, 200)
        data_me = resp_me.json()
        self.assertTrue(data_me["authenticated"])
        self.assertEqual(data_me["user"]["email"], email)

        resp_out = self.client.post("/api/auth/signout", cookies=cookies)
        self.assertEqual(resp_out.status_code, 200)
        self.assertTrue(resp_out.json()["success"])

    def test_csrf_origin_validation_rejection(self):
        headers = {"Origin": "https://malicious-phishing-site.xyz"}
        resp_order = self.client.post("/api/create-order", json={"plan_id": "single"}, headers=headers)
        self.assertEqual(resp_order.status_code, 403)
        self.assertIn("Cross-origin request rejected", resp_order.json().get("detail", ""))

        resp_pm = self.client.post(
            "/api/premortem",
            json={"ticker": "INFY", "failure_vector": "Margin Compression", "anti_thesis_notes": "Test anti thesis"},
            headers=headers
        )
        self.assertEqual(resp_pm.status_code, 403)
        self.assertIn("Cross-origin request rejected", resp_pm.json().get("detail", ""))

    def test_pead_drift_band_computation(self):
        import pandas as pd
        stock_bull = {"current_price": 1000.0}
        df_bull = pd.DataFrame({"Close": [900.0] * 50})
        res_bull = compute_pead_drift_band(stock_bull, df_bull)
        self.assertTrue(res_bull["active"])
        self.assertEqual(res_bull["status"], "bullish")
        self.assertEqual(res_bull["vector"], "ACCUMULATION_DRIFT")
        self.assertGreater(res_bull["target_drift"], 1000.0)
        self.assertGreater(res_bull["upper_bound"], res_bull["target_drift"])

        stock_bear = {"current_price": 800.0}
        df_bear = pd.DataFrame({"Close": [950.0] * 50})
        res_bear = compute_pead_drift_band(stock_bear, df_bear)
        self.assertTrue(res_bear["active"])
        self.assertEqual(res_bear["status"], "bearish")
        self.assertEqual(res_bear["vector"], "COMPRESSION_DRIFT")
        self.assertLess(res_bear["target_drift"], 800.0)
        self.assertIn("Disposition Effect", res_bear["guidance"])


# ==============================================================================
# 2. Admin Credit Grants & Atomic Ledger Transactions
# ==============================================================================
class TestAdminCreditGrant(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_db()
        cls.client = TestClient(app)
        cls.admin_email = "lyndnpnto@gmail.com"
        cls.admin_cookie = _generate_admin_token(cls.admin_email, "owner")

    def setUp(self):
        self.unique_suffix = uuid.uuid4().hex[:8]
        self.test_user_email = f"remedy_user_{self.unique_suffix}@example.com"
        self.user_record = get_or_create_user(
            user_id=f"usr_test_{self.unique_suffix}",
            email=self.test_user_email,
            full_name="Remedy Test User"
        )
        self.assertEqual(float(self.user_record.get("credits_balance", 0.0)), 2.0)

    def test_admin_grant_user_credits_atomic_db_transaction(self):
        initial_balance = get_user_credits_balance(self.user_record["id"])
        self.assertEqual(initial_balance, 2.0)

        res = admin_grant_user_credits(
            admin_email=self.admin_email,
            target_user_identifier=self.test_user_email,
            credits_amount=2.0,
            reason_code="TASK_REMEDY",
            admin_note="Compensating for failed synthesis retry on INFY",
            task_ticker="INFY"
        )

        self.assertTrue(res.get("success"), f"Grant failed: {res.get('error')}")
        self.assertEqual(res.get("credits_added"), 2.0)
        self.assertEqual(res.get("old_balance"), 2.0)
        self.assertEqual(res.get("new_balance"), 4.0)

        updated_user = get_user_by_email(self.test_user_email)
        self.assertIsNotNone(updated_user)
        self.assertEqual(float(updated_user["credits_balance"]), 4.0)

        billables = get_all_billables(limit=100, exclude_tests=False)
        grant_tx = next((b for b in billables if b["customer_email"] == self.test_user_email and "ADMIN_GRANT" in b["pack_type"]), None)
        self.assertIsNotNone(grant_tx, "Expected credit_transactions entry for admin grant.")
        self.assertEqual(grant_tx["amount_inr"], 0.0, "Remedial credits must strictly have 0.0 INR value.")
        self.assertEqual(grant_tx["base_amount_inr"], 0.0)
        self.assertEqual(grant_tx["tax_gst_inr"], 0.0)
        self.assertEqual(grant_tx["nature"], "FREE_GRANT", "Transaction nature must be classified as FREE_GRANT.")
        self.assertEqual(grant_tx["credits_added"], 2.0)

        audit_logs = get_admin_audit_logs(limit=20)
        grant_log = next((l for l in audit_logs if l["action"] == "GRANT_USER_CREDITS" and l["target_id"] == self.user_record["id"]), None)
        self.assertIsNotNone(grant_log, "Expected admin_audit_log entry for GRANT_USER_CREDITS.")
        self.assertEqual(grant_log["admin_email"], self.admin_email)
        details = grant_log.get("details_parsed", {})
        self.assertEqual(details.get("credits_granted"), 2.0)
        self.assertEqual(details.get("reason_code"), "TASK_REMEDY")
        self.assertEqual(details.get("task_ticker"), "INFY")
        self.assertEqual(details.get("nature"), "FREE_GRANT")

    def test_admin_grant_with_ticket_auto_resolution(self):
        ticket_res = create_support_ticket(
            user_email=self.test_user_email,
            subject="Synthesis failed on TCS",
            message="Credits deducted but synthesis timed out",
            user_name="Remedy Test User",
            category="synthesis_error"
        )
        self.assertTrue(ticket_res.get("success"))
        ticket_id = ticket_res["ticket_id"]

        res = admin_grant_user_credits(
            admin_email=self.admin_email,
            target_user_identifier=self.test_user_email,
            credits_amount=1.0,
            reason_code="TASK_REMEDY",
            admin_note="Restored 1.0 credit after timeout review",
            ticket_id=ticket_id,
            task_ticker="TCS",
            resolve_ticket=True
        )
        self.assertTrue(res.get("success"))
        self.assertEqual(res.get("new_balance"), 3.0)

        tickets = get_support_tickets(status="all", exclude_tests=False)
        target_ticket = next((t for t in tickets if t["ticket_id"] == ticket_id), None)
        self.assertIsNotNone(target_ticket)
        self.assertEqual(target_ticket["status"], "resolved")
        self.assertIn("[Admin Credits Granted: +1.0", target_ticket["admin_notes"])
        self.assertIn("Restored 1.0 credit after timeout review", target_ticket["admin_notes"])

    def test_support_ticket_query_parameterization_and_exclusion(self):
        """Verifies support tickets and open count queries function correctly under test exclusion filters without SQL placeholder crashes."""
        from core.db.support import get_open_tickets_count, create_support_ticket, get_support_tickets
        # Create a test-flagged ticket
        test_tkt = create_support_ticket(
            user_email="qa_runner@test.com",
            subject="Synthetic QA Ticket",
            message="Auto generated test run",
            user_name="QA Bot"
        )
        self.assertTrue(test_tkt.get("success"))

        # Create a genuine user ticket
        genuine_email = f"investor_{uuid.uuid4().hex[:6]}@domain.org"
        real_tkt = create_support_ticket(
            user_email=genuine_email,
            subject="Real Account Inquiry",
            message="Need assist on sovereign bond yields",
            user_name="Real Investor"
        )
        self.assertTrue(real_tkt.get("success"))

        # Verify exclude_tests=True includes genuine ticket and excludes test ticket
        tickets = get_support_tickets(exclude_tests=True)
        ticket_emails = [t["user_email"] for t in tickets]
        self.assertIn(genuine_email, ticket_emails)
        self.assertNotIn("qa_runner@test.com", ticket_emails)

        # Verify get_open_tickets_count excludes test tickets
        open_count = get_open_tickets_count(exclude_tests=True)
        self.assertGreaterEqual(open_count, 1)

        # Verify status filtering works cleanly without psycopg2 % interpolation crash
        open_tickets = get_support_tickets(status="open", exclude_tests=True)
        self.assertTrue(any(t["ticket_id"] == real_tkt["ticket_id"] for t in open_tickets))

    def test_admin_grant_validation_rejections(self):
        ghost_email = f"ghost_user_{uuid.uuid4().hex[:8]}@example.com"
        res_nonexistent = admin_grant_user_credits(
            admin_email=self.admin_email,
            target_user_identifier=ghost_email,
            credits_amount=2.0
        )
        self.assertFalse(res_nonexistent.get("success"))
        self.assertIn("not found", res_nonexistent.get("error", "").lower())

        res_zero = admin_grant_user_credits(
            admin_email=self.admin_email,
            target_user_identifier=self.test_user_email,
            credits_amount=0.0
        )
        self.assertFalse(res_zero.get("success"))

        res_neg = admin_grant_user_credits(
            admin_email=self.admin_email,
            target_user_identifier=self.test_user_email,
            credits_amount=-5.0
        )
        self.assertFalse(res_neg.get("success"))

    def test_endpoint_unauthorized_rejection(self):
        res = self.client.post(
            "/admin/users/grant-credits",
            json={"user_email": self.test_user_email, "credits": 2.0},
            headers={"Accept": "application/json"}
        )
        self.assertEqual(res.status_code, 403)

        res_form = self.client.post(
            "/admin/users/grant-credits",
            data={"user_email": self.test_user_email, "credits": 2.0}
        )
        self.assertEqual(res_form.status_code, 403)

    def test_endpoint_authenticated_json_ajax_success(self):
        payload = {
            "user_email": self.test_user_email,
            "credits": 2.0,
            "reason": "TASK_REMEDY",
            "admin_note": "Sequence diagram verification grant",
            "task_ticker": "INFY"
        }
        res = self.client.post(
            "/admin/users/grant-credits",
            json=payload,
            cookies={ADMIN_COOKIE_NAME: self.admin_cookie},
            headers={"Accept": "application/json"}
        )
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertTrue(data.get("success"))
        self.assertEqual(data.get("new_balance"), 4.0)
        self.assertEqual(data.get("credits_added"), 2.0)
        self.assertEqual(data.get("user_email"), self.test_user_email)
        self.assertIn(f"Successfully granted 2.0 credits to {self.test_user_email}", data.get("message"))

    def test_endpoint_authenticated_form_post_redirect(self):
        form_data = {
            "user_email": self.test_user_email,
            "credits": "1.5",
            "reason": "GOODWILL_COMPENSATION",
            "admin_note": "Goodwill top-up",
            "tab": "users"
        }
        res = self.client.post(
            "/admin/users/grant-credits",
            data=form_data,
            cookies={ADMIN_COOKIE_NAME: self.admin_cookie},
            follow_redirects=False
        )
        self.assertEqual(res.status_code, 303)
        location = res.headers.get("location", "")
        self.assertIn("tab=users", location)
        self.assertIn("Successfully+granted+1.5+credits", location)
        self.assertEqual(get_user_credits_balance(self.user_record["id"]), 3.5)


# ==============================================================================
# 3. Render Production Hardening & Secret Guards
# ==============================================================================
class TestRenderHardening(unittest.TestCase):
    def test_render_yaml_configuration(self):
        render_yaml_path = PROJECT_ROOT / "render.yaml"
        self.assertTrue(render_yaml_path.exists(), "render.yaml file does not exist")

        with open(render_yaml_path, "r", encoding="utf-8") as f:
            content = f.read()

        self.assertRegex(content, r"startCommand:\s*.*--workers 2", "render.yaml startCommand must configure --workers 2")

        required_secrets = ["SECRET_KEY", "ADMIN_API_KEY", "ADMIN_PASSWORD"]
        for sec in required_secrets:
            pattern = rf"- key:\s*{sec}\s*\n\s*sync:\s*false"
            self.assertRegex(content, pattern, f"Secret {sec} in render.yaml must be declared with sync: false")

    def test_production_boot_guard_rejects_missing_secret_key(self):
        test_app = FastAPI()

        with patch.dict(os.environ, {"ENVIRONMENT": "production", "SECRET_KEY": "stock_research_user_session_salt_2026"}):
            with self.assertRaises(RuntimeError) as ctx:
                async def run_boot():
                    async with lifespan(test_app):
                        pass
                asyncio.run(run_boot())
            self.assertIn("CRITICAL PRODUCTION BOOT FAILURE", str(ctx.exception))

        with patch.dict(os.environ, {"ENVIRONMENT": "production", "SECRET_KEY": "too_short_key_12345"}):
            with self.assertRaises(RuntimeError) as ctx:
                async def run_boot():
                    async with lifespan(test_app):
                        pass
                asyncio.run(run_boot())
            self.assertIn("shorter than 32 characters", str(ctx.exception))

        with patch.dict(os.environ, {"ENVIRONMENT": "production", "SECRET_KEY": ""}):
            with self.assertRaises(RuntimeError) as ctx:
                async def run_boot():
                    async with lifespan(test_app):
                        pass
                asyncio.run(run_boot())
            self.assertIn("missing, insecure", str(ctx.exception))

    def test_production_boot_guard_accepts_valid_secret_key(self):
        test_app = FastAPI()
        valid_key = "a" * 32

        with patch.dict(os.environ, {"ENVIRONMENT": "production", "SECRET_KEY": valid_key, "TESTING": "1"}):
            async def run_boot():
                async with lifespan(test_app):
                    pass
            asyncio.run(run_boot())

    def test_resolve_app_base_url_local_and_production(self):
        from web.main import resolve_app_base_url
        from starlette.datastructures import Headers

        class MockRequest:
            def __init__(self, headers=None, url_scheme="http", netloc="localhost:8000"):
                self.headers = Headers(headers or {})
                self.url = type("URL", (), {"scheme": url_scheme, "netloc": netloc})()

        # Local development
        req_local = MockRequest(headers={"host": "localhost:8000"})
        self.assertEqual(resolve_app_base_url(req_local), "http://localhost:8000")

        # Reverse proxy on Render / custom domain
        req_prod = MockRequest(headers={"x-forwarded-proto": "https", "x-forwarded-host": "moatnomics.com"})
        self.assertEqual(resolve_app_base_url(req_prod), "https://moatnomics.com")

        # Production fallback if internal loopback header sent
        with patch.dict(os.environ, {"ENVIRONMENT": "production", "CANONICAL_DOMAIN": "https://moatnomics.com"}):
            req_loopback = MockRequest(headers={"host": "127.0.0.1:10000"})
            self.assertEqual(resolve_app_base_url(req_loopback), "https://moatnomics.com")

    def test_public_auth_google_clean_redirect_and_cookie(self):
        client = TestClient(app)
        # 1. Default redirect produces clean /auth/callback target
        r = client.get("/auth/google", headers={"host": "moatnomics.com", "x-forwarded-proto": "https"}, follow_redirects=False)
        self.assertEqual(r.status_code, 303)
        loc = r.headers.get("location", "")
        self.assertIn("redirect_to=https%3A//moatnomics.com/auth/callback", loc)
        self.assertNotIn("next%3D", loc)
        self.assertNotIn("oauth_next", r.cookies)

        # 2. Custom redirect sets oauth_next cookie
        r2 = client.get(
            "/auth/google?redirect=/opportunities",
            headers={"host": "moatnomics.com", "x-forwarded-proto": "https"},
            follow_redirects=False
        )
        self.assertEqual(r2.status_code, 303)
        self.assertIn("redirect_to=https%3A//moatnomics.com/auth/callback", r2.headers.get("location", ""))
        self.assertEqual(r2.cookies.get("oauth_next", "").strip('"'), "/opportunities")

    def test_get_google_oauth_url_canonical_fallback(self):
        from core.auth.supabase_auth import get_google_oauth_url
        with patch.dict(os.environ, {"CANONICAL_DOMAIN": "https://moatnomics.com"}):
            oauth_url = get_google_oauth_url()
            self.assertIn("redirect_to=https://moatnomics.com/auth/callback", oauth_url)

    def test_public_auth_callback_token_exchange_and_root_code_forwarder(self):
        import base64
        import json
        client = TestClient(app)

        # 1. Root code forwarder forwards ?code=... to /auth/callback?code=...
        r_root_code = client.get("/?code=sb-test-code-999", follow_redirects=False)
        self.assertEqual(r_root_code.status_code, 303)
        self.assertIn("/auth/callback?code=sb-test-code-999", r_root_code.headers.get("location", ""))

        # 2. Public auth callback without code/token returns client-side hash handler HTML
        r_empty = client.get("/auth/callback", follow_redirects=False)
        self.assertEqual(r_empty.status_code, 200)
        self.assertIn("Verifying Identity...", r_empty.text)

        # 3. Defensive error param handling redirects to /?err=...
        r_err = client.get("/auth/callback?error=access_denied&error_description=User+cancelled+flow", follow_redirects=False)
        self.assertEqual(r_err.status_code, 303)
        self.assertIn("/?err=User%20cancelled%20flow", r_err.headers.get("location", ""))

        # 4. Public auth callback with access_token successfully sets session cookie and localStorage
        payload = base64.urlsafe_b64encode(json.dumps({
            "email": "verified_oauth_user@example.com",
            "user_metadata": {"full_name": "Verified User"}
        }).encode()).decode().rstrip("=")
        jwt_token = f"header.{payload}.sig"

        r_token = client.get(f"/auth/callback?access_token={jwt_token}", follow_redirects=False)
        self.assertEqual(r_token.status_code, 200)
        self.assertIn("Welcome, Verified User!", r_token.text)
        self.assertIn("localStorage.setItem('sr_user'", r_token.text)
        set_cookies = r_token.headers.get_list("set-cookie")
        self.assertTrue(any("user_session_token=" in c for c in set_cookies))

        # 5. Already authenticated user visiting callback without tokens redirects to destination
        token_str = [c for c in set_cookies if "user_session_token=" in c][0].split(";", 1)[0].split("=", 1)[1]
        r_authed = client.get("/auth/callback?next=/opportunities", cookies={"user_session_token": token_str}, follow_redirects=False)
        self.assertEqual(r_authed.status_code, 303)
        self.assertEqual(r_authed.headers.get("location"), "/opportunities")

        # 6. HTML and XSS sanitization on full_name
        payload_xss = base64.urlsafe_b64encode(json.dumps({
            "email": "xss_tester@example.com",
            "user_metadata": {"full_name": "<script>alert('xss')</script>"}
        }).encode()).decode().rstrip("=")
        jwt_xss = f"header.{payload_xss}.sig"
        r_xss = client.get(f"/auth/callback?access_token={jwt_xss}", follow_redirects=False)
        self.assertEqual(r_xss.status_code, 200)
        self.assertNotIn("<script>alert('xss')</script>", r_xss.text)
        self.assertIn("&lt;script&gt;alert(&#x27;xss&#x27;)&lt;/script&gt;", r_xss.text)

        # 7. Protocol-relative open redirect mitigation (//evil.com -> /)
        r_open = client.get(f"/auth/callback?access_token={jwt_token}&next=//evil.com", follow_redirects=False)
        self.assertEqual(r_open.status_code, 200)
        self.assertIn('window.location.replace("/")', r_open.text)
        self.assertNotIn("//evil.com", r_open.text)

        # 8. Authenticated open redirect mitigation
        r_open_auth = client.get("/auth/callback?next=//evil.com", cookies={"user_session_token": token_str}, follow_redirects=False)
        self.assertEqual(r_open_auth.status_code, 303)
        self.assertEqual(r_open_auth.headers.get("location"), "/")

    def test_es256_jwks_verification_and_sql_fallback_url_resolution(self):
        import base64
        import json
        import time
        from cryptography.hazmat.primitives.asymmetric import ec
        from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature
        from cryptography.hazmat.primitives import hashes
        import core.auth.supabase_auth as sb_auth

        # Generate ephemeral EC P-256 keypair and populate _JWKS_CACHE
        priv_key = ec.generate_private_key(ec.SECP256R1())
        pub_nums = priv_key.public_key().public_numbers()
        x_b64 = base64.urlsafe_b64encode(pub_nums.x.to_bytes(32, "big")).decode().rstrip("=")
        y_b64 = base64.urlsafe_b64encode(pub_nums.y.to_bytes(32, "big")).decode().rstrip("=")

        jwk_entry = {
            "kty": "EC",
            "crv": "P-256",
            "alg": "ES256",
            "kid": "test-kid-es256",
            "x": x_b64,
            "y": y_b64,
        }
        sb_auth._JWKS_CACHE["keys"] = [jwk_entry]
        sb_auth._JWKS_CACHE["fetched_at"] = time.time()
        sb_auth._JWKS_CACHE["url"] = "https://omswdxrtzrvlszkidssh.supabase.co"

        header_b64 = base64.urlsafe_b64encode(
            json.dumps({"alg": "ES256", "kid": "test-kid-es256", "typ": "JWT"}).encode()
        ).decode().rstrip("=")
        payload_b64 = base64.urlsafe_b64encode(
            json.dumps({
                "email": "es256_verified@moatnomics.com",
                "exp": int(time.time()) + 3600,
                "user_metadata": {"full_name": "Rahul Sharma"},
            }).encode()
        ).decode().rstrip("=")

        signing_input = f"{header_b64}.{payload_b64}".encode("ascii")
        der_sig = priv_key.sign(signing_input, ec.ECDSA(hashes.SHA256()))
        r_int, s_int = decode_dss_signature(der_sig)
        raw_sig = r_int.to_bytes(32, "big") + s_int.to_bytes(32, "big")
        sig_b64 = base64.urlsafe_b64encode(raw_sig).decode().rstrip("=")

        valid_es256_jwt = f"{header_b64}.{payload_b64}.{sig_b64}"
        tampered_es256_jwt = f"{header_b64}.{payload_b64}." + base64.urlsafe_b64encode(b"\x01" * 64).decode().rstrip("=")

        # Verify in non-test (production) mode with empty SUPABASE_ANON_KEY
        with patch.dict(os.environ, {"TESTING": "0", "SUPABASE_ANON_KEY": ""}):
            email, name = sb_auth.verify_supabase_access_token(valid_es256_jwt)
            self.assertEqual(email, "es256_verified@moatnomics.com")
            self.assertEqual(name, "Rahul Sharma")

            # Tampered signature must be rejected in production mode
            with patch("core.auth.supabase_auth.requests.get") as mock_get:
                mock_get.return_value.status_code = 401
                bad_email, _ = sb_auth.verify_supabase_access_token(tampered_es256_jwt)
                self.assertIsNone(bad_email)


# ==============================================================================
# 5. Database Dual-Binding & SQLite Transparent Failover
# ==============================================================================
class TestDatabaseDualBindingFailover(unittest.TestCase):
    def test_init_db_transparent_sqlite_failover_when_postgres_unreachable(self):
        """Verifies that when SUPABASE_DB_URL is set to an unreachable host, init_db()
        transparently falls back to SQLite without raising 'near EXISTS: syntax error'."""
        import tempfile
        import sqlite3
        from core.db.connection import (
            init_db,
            is_postgres_connection,
            get_placeholder,
            _PG_AVAILABLE,
        )
        import core.db.connection as conn_mod

        # Create temporary clean SQLite database file
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tf:
            temp_db_path = tf.name

        old_testing = os.environ.pop("TESTING", None)
        old_test_sb = os.environ.pop("TEST_SUPABASE", None)
        old_sb_url = os.environ.get("SUPABASE_DB_URL")
        old_db_path = os.environ.get("DB_PATH")

        try:
            # Point to unreachable PostgreSQL URL and fresh SQLite path
            os.environ["SUPABASE_DB_URL"] = "postgresql://invalid_user:invalid_pass@127.0.0.1:5432/invalid_db"
            os.environ["DB_PATH"] = temp_db_path
            conn_mod._CACHED_SUPABASE_URL = "postgresql://invalid_user:invalid_pass@127.0.0.1:5432/invalid_db"
            conn_mod._SUPABASE_URL_RESOLVED = True
            conn_mod._PG_AVAILABLE = None  # Reset availability state

            # Test connection inspector on pure SQLite connection
            s_conn = sqlite3.connect(":memory:")
            self.assertFalse(is_postgres_connection(s_conn))
            s_conn.close()

            # Execute init_db(force=True) on fresh database - MUST NOT raise OperationalError
            init_db(force=True)

            # Placeholder must be '?' for SQLite, not '%s'
            self.assertEqual(get_placeholder(), "?")

            # Verify that all 27 migrations successfully created core tables in SQLite
            verify_conn = sqlite3.connect(temp_db_path)
            cursor = verify_conn.cursor()
            cursor.execute("SELECT count(*) FROM schema_migrations;")
            migration_count = cursor.fetchone()[0]
            self.assertGreaterEqual(migration_count, 27)

            # Verify reports table exists and has baseline columns
            cursor.execute("PRAGMA table_info(reports);")
            columns = [c[1] for c in cursor.fetchall()]
            self.assertIn("baseline_price", columns)
            self.assertIn("baseline_pe", columns)
            self.assertIn("baseline_mcap", columns)
            self.assertIn("latest_announcement", columns)
            verify_conn.close()
        finally:
            if old_testing is not None:
                os.environ["TESTING"] = old_testing
            if old_test_sb is not None:
                os.environ["TEST_SUPABASE"] = old_test_sb
            if old_sb_url is not None:
                os.environ["SUPABASE_DB_URL"] = old_sb_url
            else:
                os.environ.pop("SUPABASE_DB_URL", None)
            if old_db_path is not None:
                os.environ["DB_PATH"] = old_db_path
            else:
                os.environ.pop("DB_PATH", None)
            conn_mod._CACHED_SUPABASE_URL = None
            conn_mod._SUPABASE_URL_RESOLVED = False
            conn_mod._PG_AVAILABLE = None
            if os.path.exists(temp_db_path):
                os.remove(temp_db_path)

# ==============================================================================
# 5. Razorpay HMAC-SHA256 Signature Verification & Simulation Boundary
# ==============================================================================
class TestRazorpaySignatureVerification(unittest.TestCase):
    def test_missing_or_empty_arguments(self):
        from core.billing.razorpay import verify_payment_signature
        self.assertFalse(verify_payment_signature("", "pay_123", "sig_123"))
        self.assertFalse(verify_payment_signature("order_123", "", "sig_123"))
        self.assertFalse(verify_payment_signature("order_123", "pay_123", ""))
        self.assertFalse(verify_payment_signature(None, "pay_123", "sig_123"))

    def test_simulated_orders_in_testing_environment(self):
        from core.billing.razorpay import verify_payment_signature
        with patch.dict(os.environ, {"TESTING": "1", "ENVIRONMENT": "development"}, clear=False):
            with patch("core.billing.razorpay.get_razorpay_keys", return_value=("", "", False)):
                self.assertTrue(verify_payment_signature("order_sim_123", "pay_sim_123", "sig_sim_abc"))
                self.assertTrue(verify_payment_signature("order_sim_123", "pay_sim_123", "simulated_success"))
                self.assertFalse(verify_payment_signature("order_sim_123", "pay_sim_123", "invalid_sig"))

    def test_simulated_orders_blocked_in_production_or_render(self):
        from core.billing.razorpay import verify_payment_signature
        # Blocked in production
        with patch.dict(os.environ, {"ENVIRONMENT": "production", "TESTING": "1"}, clear=False):
            with patch("core.billing.razorpay.get_razorpay_keys", return_value=("", "", False)):
                self.assertFalse(verify_payment_signature("order_sim_123", "pay_sim_123", "sig_sim_abc"))

        # Blocked on Render
        with patch.dict(os.environ, {"RENDER": "true", "TESTING": "1"}, clear=False):
            with patch("core.billing.razorpay.get_razorpay_keys", return_value=("", "", False)):
                self.assertFalse(verify_payment_signature("order_sim_123", "pay_sim_123", "sig_sim_abc"))

    def test_simulated_orders_blocked_when_key_secret_configured(self):
        from core.billing.razorpay import verify_payment_signature
        with patch.dict(os.environ, {"TESTING": "1", "ENVIRONMENT": "development"}, clear=False):
            with patch("core.billing.razorpay.get_razorpay_keys", return_value=("rzp_key", "rzp_secret", False)):
                self.assertFalse(verify_payment_signature("order_sim_123", "pay_sim_123", "sig_sim_abc"))

    def test_simulated_orders_blocked_outside_testing(self):
        from core.billing.razorpay import verify_payment_signature
        with patch.dict(os.environ, {"TESTING": "0", "ENVIRONMENT": "development"}, clear=False):
            with patch("core.billing.razorpay.get_razorpay_keys", return_value=("", "", False)):
                self.assertFalse(verify_payment_signature("order_sim_123", "pay_sim_123", "sig_sim_abc"))

    def test_real_hmac_sha256_cryptographic_verification(self):
        import hashlib
        import hmac
        from core.billing.razorpay import verify_payment_signature

        order_id = "order_live_9876543210"
        payment_id = "pay_live_1234567890"
        mock_secret = "secret_key_moatnomics_test_2026"

        msg = f"{order_id}|{payment_id}".encode("utf-8")
        valid_sig = hmac.new(mock_secret.encode("utf-8"), msg, hashlib.sha256).hexdigest()

        with patch("core.billing.razorpay.get_razorpay_keys", return_value=("rzp_live_key", mock_secret, True)):
            # Valid signature passes
            self.assertTrue(verify_payment_signature(order_id, payment_id, valid_sig))
            self.assertTrue(verify_payment_signature(order_id, payment_id, f"  {valid_sig}  "))

            # Tampered signature fails
            self.assertFalse(verify_payment_signature(order_id, payment_id, "tampered_signature_hex"))

            # Tampered payment_id fails
            self.assertFalse(verify_payment_signature(order_id, "pay_live_other", valid_sig))

            # Tampered order_id fails
            self.assertFalse(verify_payment_signature("order_live_other", payment_id, valid_sig))

    def test_real_order_fails_without_key_secret(self):
        from core.billing.razorpay import verify_payment_signature
        with patch("core.billing.razorpay.get_razorpay_keys", return_value=("", "", False)):
            self.assertFalse(verify_payment_signature("order_real_123", "pay_real_123", "sig_123"))


# ==============================================================================
# 6. /api/synthesize Verified Session Cookie & Ignored Client user_id
# ==============================================================================
class TestSynthesizeSessionAuth(unittest.TestCase):
    def setUp(self):
        from web.main import app
        from starlette.testclient import TestClient
        self.client = TestClient(app)

    def test_synthesize_unauthenticated_rejected_401(self):
        """Unauthenticated requests must be rejected with 401 and AUTHENTICATION_REQUIRED."""
        resp = self.client.post(
            "/api/synthesize",
            json={"ticker": "INFY", "user_id": "spoofed_user_123"}
        )
        self.assertEqual(resp.status_code, 401)
        data = resp.json().get("detail", {})
        self.assertEqual(data.get("error"), "AUTHENTICATION_REQUIRED")
        self.assertIn("Please sign in to synthesize a dossier", data.get("message", ""))

    def test_synthesize_ignores_client_supplied_user_id(self):
        """The endpoint must ignore client-supplied user_id and strictly resolve from verified session."""
        web_user = {
            "id": "usr_verified_session_789",
            "email": "verified_session@example.com",
            "credits_balance": 10.0,
            "subscription_tier": "free"
        }
        with patch("web.routers.dossier._get_current_web_user", return_value=web_user):
            with patch("web.routers.dossier.clean_ticker", return_value="INFY"):
                with patch("web.routers.dossier.resolve_canonical_symbol", return_value="INFY"):
                    with patch("web.routers.dossier.get_report_by_ticker_sync", return_value={"report_text": "Sample report"}):
                        resp = self.client.post(
                            "/api/synthesize",
                            json={"ticker": "INFY", "user_id": "attacker_spoofed_victim_id", "force_refresh": False}
                        )
                        self.assertEqual(resp.status_code, 200)
                        data = resp.json()
                        self.assertTrue(data.get("success"))
                        self.assertTrue(data.get("already_exists"))

    def test_synthesize_admin_authenticated_without_web_user(self):
        """An authenticated admin without a web user can synthesize using clean_uid='admin_console'."""
        admin_session = {"email": "admin@moatnomics.com", "role": "super_admin"}
        with patch("web.routers.dossier._get_current_web_user", return_value=None):
            with patch("web.routers.dossier._is_admin_authenticated", return_value=admin_session):
                with patch("web.routers.dossier.clean_ticker", return_value="TCS"):
                    with patch("web.routers.dossier.resolve_canonical_symbol", return_value="TCS"):
                        with patch("web.routers.dossier.get_report_by_ticker_sync", return_value={"report_text": "TCS report"}):
                            resp = self.client.post(
                                "/api/synthesize",
                                json={"ticker": "TCS"}
                            )
                            self.assertEqual(resp.status_code, 200)
                            data = resp.json()
                            self.assertTrue(data.get("success"))
                            self.assertTrue(data.get("already_exists"))

    def test_synthesize_unrecognized_ticker_preflight_404(self):
        """Unrecognized ticker must fail pre-flight validation with 404 UNRECOGNIZED_TICKER before charging credits."""
        web_user = {
            "id": "usr_verified_session_789",
            "email": "verified_session@example.com",
            "credits_balance": 10.0,
            "subscription_tier": "free"
        }
        with patch("web.routers.dossier._get_current_web_user", return_value=web_user):
            with patch("web.routers.dossier.clean_ticker", return_value="TOTALLYFAKETICKER"):
                with patch("web.routers.dossier.resolve_canonical_symbol", return_value="TOTALLYFAKETICKER"):
                    with patch("web.routers.dossier.resolve_bse_scrip_code", return_value=None):
                        with patch("web.routers.dossier.get_latest_report", return_value={}):
                            resp = self.client.post(
                                "/api/synthesize",
                                json={"ticker": "TOTALLYFAKETICKER"}
                            )
                            self.assertEqual(resp.status_code, 404)
                            data = resp.json()
                            detail = data.get("detail", {})
                            self.assertEqual(detail.get("error"), "UNRECOGNIZED_TICKER")
                            self.assertIn("not found in the BSE/NSE scrip master", detail.get("message", ""))
                            self.assertIn("suggestions", detail)


# ==============================================================================
# 7. /api/dossier/unlock/{ticker} Session Cookie & Auth Contract
# ==============================================================================
class TestDossierUnlockSessionAuth(unittest.TestCase):
    def setUp(self):
        from web.main import app
        from starlette.testclient import TestClient
        self.client = TestClient(app)

    def test_dossier_unlock_unauthenticated_rejected_401(self):
        """Unauthenticated unlock requests must return 401 with AUTH_REQUIRED code."""
        resp = self.client.post("/api/dossier/unlock/INFY")
        self.assertEqual(resp.status_code, 401)
        data = resp.json()
        self.assertEqual(data.get("status"), "error")
        self.assertEqual(data.get("code"), "AUTH_REQUIRED")
        self.assertEqual(data.get("message"), "Sign in required to unlock dossiers.")

    def test_dossier_unlock_spoofed_user_id_rejected(self):
        """Passing spoofed user_id in payload without verified session cookie must be rejected with 401."""
        resp = self.client.post(
            "/api/dossier/unlock/INFY",
            json={"user_id": "usr_victim_account"}
        )
        self.assertEqual(resp.status_code, 401)
        data = resp.json()
        self.assertEqual(data.get("status"), "error")
        self.assertEqual(data.get("code"), "AUTH_REQUIRED")

    def test_dossier_unlock_authenticated_session_success(self):
        """Authenticated session uses web_user id to unlock dossier."""
        web_user = {
            "id": "usr_verified_777",
            "email": "verified_777@example.com",
            "credits_balance": 5.0,
            "subscription_tier": "free"
        }
        with patch("web.main._get_current_web_user", return_value=web_user):
            with patch("web.routers.dossier.get_user_by_id", return_value=web_user):
                with patch("web.main.unlock_ticker_for_user", return_value=(True, 4.0, "Dossier unlocked successfully")):
                    resp = self.client.post(
                        "/api/dossier/unlock/INFY",
                        json={"user_id": "spoofed_ignored_id"}
                    )
                    self.assertEqual(resp.status_code, 200)
                    data = resp.json()
                    self.assertTrue(data.get("success"))
                    self.assertEqual(data.get("new_balance"), 4.0)


# ==============================================================================
# 8. /api/v1/reports/{ticker} Developer API Key & Boundary Validation
# ==============================================================================
class TestApiV1DeveloperAuth(unittest.TestCase):
    def setUp(self):
        from web.main import app
        from starlette.testclient import TestClient
        self.client = TestClient(app)

    def test_unauthenticated_request_rejected_401(self):
        """Unauthenticated request to Developer API must return 401."""
        resp = self.client.get("/api/v1/reports/INFY")
        self.assertEqual(resp.status_code, 401)
        self.assertIn("Valid API key required", resp.json().get("detail", ""))

    def test_testing_mode_mock_dev_key_accepted(self):
        """In testing mode (TESTING=1), sr_dev_* and usr_* keys are accepted."""
        resp1 = self.client.get(
            "/api/v1/reports/INFY",
            headers={"Authorization": "Bearer sr_dev_unit_test_key_101"}
        )
        self.assertEqual(resp1.status_code, 200)
        self.assertTrue(resp1.json()["success"])

        resp2 = self.client.get(
            "/api/v1/reports/INFY",
            headers={"X-API-Key": "usr_test_client_key_202"}
        )
        self.assertEqual(resp2.status_code, 200)
        self.assertTrue(resp2.json()["success"])

    def test_testing_mode_invalid_key_rejected_401(self):
        """In testing mode, random non-matching keys without sr_dev_/usr_ prefix return 401."""
        resp = self.client.get(
            "/api/v1/reports/INFY",
            headers={"Authorization": "Bearer non_dev_random_key_999"}
        )
        self.assertEqual(resp.status_code, 401)

    def test_production_mode_simulation_key_rejected_401(self):
        """In production mode (TESTING=0), sr_dev_* simulation keys must be strictly rejected."""
        orig_testing = os.environ.get("TESTING")
        try:
            os.environ["TESTING"] = "0"
            resp = self.client.get(
                "/api/v1/reports/INFY",
                headers={"Authorization": "Bearer sr_dev_test_simulation_token"}
            )
            self.assertEqual(resp.status_code, 401)
        finally:
            if orig_testing is not None:
                os.environ["TESTING"] = orig_testing
            else:
                os.environ.pop("TESTING", None)

    def test_production_mode_expected_api_key_accepted(self):
        """In production mode (TESTING=0), verified expected API key succeeds via timing-safe HMAC."""
        orig_testing = os.environ.get("TESTING")
        orig_admin_key = os.environ.get("ADMIN_API_KEY")
        try:
            os.environ["TESTING"] = "0"
            os.environ["ADMIN_API_KEY"] = "prod_canonical_developer_key_456"
            resp = self.client.get(
                "/api/v1/reports/INFY",
                headers={"Authorization": "Bearer prod_canonical_developer_key_456"}
            )
            self.assertEqual(resp.status_code, 200)
            self.assertTrue(resp.json()["success"])
        finally:
            if orig_testing is not None:
                os.environ["TESTING"] = orig_testing
            else:
                os.environ.pop("TESTING", None)
            if orig_admin_key is not None:
                os.environ["ADMIN_API_KEY"] = orig_admin_key
            else:
                os.environ.pop("ADMIN_API_KEY", None)


class TestUserProfileApiAuth(unittest.TestCase):
    """Verifies IDOR protection and role-based access control on /api/user/{user_id}."""

    @classmethod
    def setUpClass(cls):
        init_db()
        cls.client = TestClient(app)
        cls.user_a = get_or_create_user("usr_profile_auth_a", "alice@example.com", "Alice Tester")
        cls.user_b = get_or_create_user("usr_profile_auth_b", "bob@example.com", "Bob Tester")
        cls.token_a = _generate_user_session_token(cls.user_a["id"], cls.user_a["email"])
        cls.token_b = _generate_user_session_token(cls.user_b["id"], cls.user_b["email"])
        cls.admin_token = _generate_admin_token("admin@example.com", "owner")

    def test_unauthenticated_request_rejected_403(self):
        """Unauthenticated requests cannot fetch any user profile."""
        res = self.client.get(f"/api/user/{self.user_a['id']}")
        self.assertEqual(res.status_code, 403)
        self.assertIn("cannot inspect another user's profile", res.json().get("detail", ""))

    def test_user_cannot_inspect_another_user_profile_403(self):
        """User A is forbidden from inspecting User B's profile (IDOR defense)."""
        res = self.client.get(
            f"/api/user/{self.user_b['id']}",
            cookies={"user_session_token": self.token_a}
        )
        self.assertEqual(res.status_code, 403)
        self.assertIn("cannot inspect another user's profile", res.json().get("detail", ""))

    def test_user_can_inspect_own_profile_200(self):
        """User A can successfully inspect their own profile."""
        res = self.client.get(
            f"/api/user/{self.user_a['id']}",
            cookies={"user_session_token": self.token_a}
        )
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data.get("status"), "success")
        self.assertIn("user", data)
        self.assertEqual(data["user"]["id"], self.user_a["id"])
        self.assertEqual(data["user"]["email"], "alice@example.com")

    def test_admin_can_inspect_any_user_profile_200(self):
        """Authenticated admin can inspect any registered user profile."""
        res = self.client.get(
            f"/api/user/{self.user_a['id']}",
            cookies={ADMIN_COOKIE_NAME: self.admin_token}
        )
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data.get("status"), "success")
        self.assertEqual(data["user"]["id"], self.user_a["id"])

    def test_admin_inspect_nonexistent_user_returns_404(self):
        """Non-existent user profile query by admin returns 404 Not Found."""
        res = self.client.get(
            "/api/user/usr_nonexistent_profile_9999",
            cookies={ADMIN_COOKIE_NAME: self.admin_token}
        )
        self.assertEqual(res.status_code, 404)
        self.assertEqual(res.json().get("detail"), "User not found")


if __name__ == "__main__":
    unittest.main()


