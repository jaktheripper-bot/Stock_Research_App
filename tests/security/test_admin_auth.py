"""
tests/security/test_admin_auth.py
=================================
Admin Authentication, RFC 6238 TOTP 2FA, Role Management & Audit Ledger
"""
import os
os.environ["TESTING"] = "1"
import unittest
from fastapi.testclient import TestClient
from core.auth.totp import generate_totp_secret, get_totp_code, verify_totp_code, get_totp_uri
from core.db.admin import (
    get_admin_user, list_admin_users, add_admin_user, remove_admin_user,
    update_admin_role, set_admin_totp_secret, enable_admin_totp,
    record_admin_audit, get_admin_audit_logs
)
from web.main import app, ADMIN_COOKIE_NAME, ADMIN_2FA_PENDING_COOKIE, _generate_admin_token

class TestAdminAuthSuite(unittest.TestCase):
    def setUp(self):
        os.environ["ADMIN_PASSWORD"] = "test_admin_auth_pwd_2026"
        self.admin_pwd = "test_admin_auth_pwd_2026"
        self.client = TestClient(app)

    
    
        generate_totp_secret,
        get_totp_code,
        verify_totp_code,
        get_totp_uri,
        get_admin_user,
        list_admin_users,
        add_admin_user,
        remove_admin_user,
        update_admin_role,
        set_admin_totp_secret,
        enable_admin_totp,
        record_admin_audit,
        get_admin_audit_logs,
    
    
    
    
    def test_totp_generation_and_verification(self):
        """Verify RFC 6238 TOTP generates and verifies 6-digit codes correctly."""
        secret = generate_totp_secret()
        self.assertEqual(len(secret), 32)
        self.assertTrue(secret.isalnum())
    
        # Code generation
        code = get_totp_code(secret)
        self.assertEqual(len(code), 6)
        self.assertTrue(code.isdigit())
    
        # Verification passes for correct code
        self.assertTrue(verify_totp_code(secret, code))
    
        # Verification fails for invalid code
        self.assertFalse(verify_totp_code(secret, "999999" if code != "999999" else "000000"))
        self.assertFalse(verify_totp_code(secret, ""))
        self.assertFalse(verify_totp_code(secret, "123"))
    
        # URI contains account and secret
        uri = get_totp_uri(secret, "lyndnpnto@gmail.com")
        self.assertTrue(uri.startswith("otpauth://totp/"))
        self.assertIn(secret, uri)
        self.assertIn("lyndnpnto%40gmail.com", uri or "lyndnpnto@gmail.com")
    
    
    def test_admin_whitelist_and_seeding(self):
        """Verify root owner account is seeded and team management works."""
        owner = get_admin_user("lyndnpnto@gmail.com")
        self.assertIsNotNone(owner)
        self.assertEqual(owner["role"], "owner")
        self.assertEqual(owner["email"].lower(), "lyndnpnto@gmail.com")
    
        # Ensure test isolation by clearing any leftover test admin
        remove_admin_user("test_admin@example.com", requesting_email="lyndnpnto@gmail.com")

        # Add a new admin
        ok, msg = add_admin_user("test_admin@example.com", role="admin", invited_by="lyndnpnto@gmail.com")
        self.assertTrue(ok)
        admin = get_admin_user("test_admin@example.com")
        self.assertIsNotNone(admin)
        self.assertEqual(admin["role"], "admin")
    
        # Update role
        ok, msg = update_admin_role("test_admin@example.com", "viewer", requesting_email="lyndnpnto@gmail.com")
        self.assertTrue(ok)
        self.assertEqual(get_admin_user("test_admin@example.com")["role"], "viewer")
    
        # Remove admin
        ok, msg = remove_admin_user("test_admin@example.com", requesting_email="lyndnpnto@gmail.com")
        self.assertTrue(ok)
        self.assertIsNone(get_admin_user("test_admin@example.com"))
    
        # Owner cannot be removed
        ok, msg = remove_admin_user("lyndnpnto@gmail.com", requesting_email="other@example.com")
        self.assertFalse(ok)
    
    
    def test_admin_audit_trail_logging(self):
        """Verify immutable audit ledger logs events correctly."""
        record_admin_audit(
            admin_email="lyndnpnto@gmail.com",
            action="test_action_event",
            target_type="test_target",
            target_id="12345",
            details={"reason": "unit_test"},
            ip_address="127.0.0.1"
        )
    
        logs = get_admin_audit_logs(limit=20)
        matched = [l for l in logs if l.get("action") == "test_action_event"]
        self.assertTrue(len(matched) > 0)
        self.assertEqual(matched[0]["admin_email"], "lyndnpnto@gmail.com")
        self.assertEqual(matched[0]["target_id"], "12345")
    
    
    def test_admin_web_flow(self):
        """Verify admin login challenge, 2FA setup, and dashboard access."""
        # 1. Unauthenticated request to /admin shows login form
        res = self.client.get("/admin")
        self.assertEqual(res.status_code, 200)
        self.assertIn("Executive Administrator Portal", res.text)
        self.assertIn("Sign In with Google", res.text)
    
        # 2. Direct verify initiation for whitelisted owner
        res2 = self.client.post(
            "/admin/auth/direct-verify",
            data={"email": "lyndnpnto@gmail.com", "password": self.admin_pwd},
            follow_redirects=False
        )
        self.assertEqual(res2.status_code, 303)
        self.assertIn(ADMIN_2FA_PENDING_COOKIE, res2.cookies)
    
        pending_cookie = res2.cookies[ADMIN_2FA_PENDING_COOKIE]
    
        # 3. Setup 2FA
        res_setup = self.client.get("/admin/setup-2fa", cookies={ADMIN_2FA_PENDING_COOKIE: pending_cookie})
        self.assertEqual(res_setup.status_code, 200)
        self.assertIn("Set Up Google Authenticator", res_setup.text)
    
        # Retrieve secret from db
        owner = get_admin_user("lyndnpnto@gmail.com")
        secret = owner["totp_secret"]
        self.assertIsNotNone(secret)
    
        # Submit valid 6-digit code
        valid_code = get_totp_code(secret)
        res_confirm = self.client.post(
            "/admin/setup-2fa",
            data={"code": valid_code},
            cookies={ADMIN_2FA_PENDING_COOKIE: pending_cookie},
            follow_redirects=False
        )
        self.assertEqual(res_confirm.status_code, 303)
        self.assertIn(ADMIN_COOKIE_NAME, res_confirm.cookies)
    
        admin_session_cookie = res_confirm.cookies[ADMIN_COOKIE_NAME]
    
        # 4. Access dashboard with authenticated session
        res_dash = self.client.get("/admin", cookies={ADMIN_COOKIE_NAME: admin_session_cookie})
        self.assertEqual(res_dash.status_code, 200)
        self.assertIn("Executive Telemetry & Site Usage Hub", res_dash.text)
        self.assertIn("lyndnpnto@gmail.com", res_dash.text)
        self.assertIn("OWNER", res_dash.text)
        self.assertIn("2FA ACTIVE", res_dash.text)
    
    
    def test_telemetry_attribution_and_custom_date_range(self):
        """Verify UTM and referrer attribution, custom date range filtering, and test data purge."""
        from web.main import _generate_admin_token
    
        admin_cookie = _generate_admin_token("lyndnpnto@gmail.com", "owner")
    
        # 1. Send client-side telemetry with UTM campaign and custom referrer
        telemetry_payload = {
            "event_type": "page_view",
            "ticker": "INFY",
            "session_id": "sess_test_12345",
            "referrer": "https://twitter.com/i/web/status/123",
            "utm_source": "twitter",
            "utm_campaign": "q3_results",
            "details": {"path": "/dossier/INFY"}
        }
        res_tel = self.client.post("/api/telemetry/event", json=telemetry_payload)
        self.assertEqual(res_tel.status_code, 200)
        self.assertIn(res_tel.json()["status"], ("ok", "filtered"))
    
        # 2. Access admin console with custom date range
        res_custom = self.client.get(
            "/admin?window=custom&start_date=2026-09-01&end_date=2026-10-05&tab=traffic",
            cookies={ADMIN_COOKIE_NAME: admin_cookie}
        )
        self.assertEqual(res_custom.status_code, 200)
        self.assertIn("2026-09-01", res_custom.text)
        self.assertIn("2026-10-05", res_custom.text)
        self.assertIn("Traffic Channels", res_custom.text)
    
        # 3. Test data purge endpoint requires authentication
        res_unauth = self.client.post("/admin/telemetry/purge-test-data")
        self.assertIn(res_unauth.status_code, (401, 303))
    
        # 4. Trigger purge with authenticated owner
        res_purge = self.client.post(
            "/admin/telemetry/purge-test-data",
            cookies={ADMIN_COOKIE_NAME: admin_cookie},
            follow_redirects=False
        )
        self.assertEqual(res_purge.status_code, 303)
        self.assertIn("tab=telemetry", res_purge.headers["location"])
    
        # 5. Verify audit log entry was created
        audit_logs = get_admin_audit_logs(limit=10)
        self.assertTrue(any(log.get("action") == "PURGE_TEST_DATA" for log in audit_logs))
    
    
    def test_admin_owner_auto_bootstrap(self):
        """Verify authorized owner email auto-bootstraps and cannot be locked out, removed, or downgraded."""
        # 1. Primary owner email exists and is owner
        owner_primary = get_admin_user("lyndnpnto@gmail.com")
        self.assertIsNotNone(owner_primary)
        self.assertEqual(owner_primary["role"], "owner")
        self.assertEqual(owner_primary["email"], "lyndnpnto@gmail.com")
    
        # 2. Random unauthorized email is NOT authorized
        unauth = get_admin_user("unauthorized_stranger@example.com")
        self.assertIsNone(unauth)
    
        # 3. Direct verify initiation succeeds for owner email
        res1 = self.client.post(
            "/admin/auth/direct-verify",
            data={"email": "lyndnpnto@gmail.com", "password": self.admin_pwd},
            follow_redirects=False
        )
        self.assertEqual(res1.status_code, 303)
        self.assertIn(ADMIN_2FA_PENDING_COOKIE, res1.cookies)
    
        # 4. Direct verify fails for unauthorized email
        res3 = self.client.post(
            "/admin/auth/direct-verify",
            data={"email": "unauthorized_stranger@example.com", "password": self.admin_pwd},
            follow_redirects=False
        )
        self.assertEqual(res3.status_code, 303)
        self.assertIn("Access+Denied", res3.headers["location"])
    
        # 5. Owner account cannot be removed or downgraded
        ok_rem1, _ = remove_admin_user("lyndnpnto@gmail.com", requesting_email="other@example.com")
        self.assertFalse(ok_rem1)
    
        ok_down1, _ = update_admin_role("lyndnpnto@gmail.com", "admin", requesting_email="other@example.com")
        self.assertFalse(ok_down1)
    
    
    def test_admin_dev_login_and_next_url(self):
        """Verify one-click dev-login route sets admin session and preserves next_url."""
        # 1. Dev login with destination URL
        res = self.client.post("/admin/auth/dev-login", data={"next_url": "/admin?tab=tickets"}, follow_redirects=False)
        self.assertEqual(res.status_code, 303)
        self.assertEqual(res.headers.get("location"), "/admin?tab=tickets")
        self.assertIn(ADMIN_COOKIE_NAME, res.cookies)
    
        # 2. Access dashboard with the session cookie
        dash_res = self.client.get("/admin?tab=tickets", cookies={ADMIN_COOKIE_NAME: res.cookies[ADMIN_COOKIE_NAME]})
        self.assertEqual(dash_res.status_code, 200)
        self.assertIn("Executive Telemetry & Site Usage Hub", dash_res.text)
    
    
    def test_admin_2fa_local_bypass_code_and_next_url(self):
        """Verify 000000 bypass on localhost preserves next_url destination."""
        # 1. Direct verify with next_url
        res_init = self.client.post(
            "/admin/auth/direct-verify",
            data={"email": "lyndnpnto@gmail.com", "password": self.admin_pwd, "next_url": "/admin?tab=tickets"},
            follow_redirects=False
        )
        self.assertEqual(res_init.status_code, 303)
        self.assertIn("/admin/verify-2fa?next=", res_init.headers["location"])
        pending_cookie = res_init.cookies[ADMIN_2FA_PENDING_COOKIE]
    
        # 2. Verify with emergency code 000000
        res_verify = self.client.post(
            "/admin/verify-2fa",
            data={"code": "000000", "next_url": "/admin?tab=tickets"},
            cookies={ADMIN_2FA_PENDING_COOKIE: pending_cookie},
            follow_redirects=False
        )
        self.assertEqual(res_verify.status_code, 303)
        self.assertEqual(res_verify.headers.get("location"), "/admin?tab=tickets")
        self.assertIn(ADMIN_COOKIE_NAME, res_verify.cookies)

    def test_admin_direct_verify_password_enforcement_and_alias(self):
        """Verify strict timing-safe ADMIN_PASSWORD enforcement and /admin/login alias."""
        # 1. Reject invalid password
        res_bad = self.client.post(
            "/admin/auth/direct-verify",
            data={"email": "lyndnpnto@gmail.com", "password": "wrong_password_attempt"},
            follow_redirects=False
        )
        self.assertEqual(res_bad.status_code, 303)
        self.assertIn("Invalid+admin+credentials", res_bad.headers.get("location", ""))
        self.assertNotIn("admin_2fa_pending", res_bad.cookies)

        # 2. Reject empty password
        res_empty = self.client.post(
            "/admin/auth/direct-verify",
            data={"email": "lyndnpnto@gmail.com", "password": ""},
            follow_redirects=False
        )
        self.assertEqual(res_empty.status_code, 303)
        self.assertIn("Invalid+admin+credentials", res_empty.headers.get("location", ""))
        self.assertNotIn("admin_2fa_pending", res_empty.cookies)

        # 3. Reject when ADMIN_PASSWORD is unset in environment
        old_pwd = os.environ.pop("ADMIN_PASSWORD", None)
        try:
            res_unset = self.client.post(
                "/admin/auth/direct-verify",
                data={"email": "lyndnpnto@gmail.com", "password": "any"},
                follow_redirects=False
            )
            self.assertEqual(res_unset.status_code, 303)
            self.assertIn("Invalid+admin+credentials", res_unset.headers.get("location", ""))
        finally:
            if old_pwd:
                os.environ["ADMIN_PASSWORD"] = old_pwd

        # 4. /admin/login redirect alias preserving error params
        res_login = self.client.get("/admin/login?error=Invalid+admin+credentials", follow_redirects=False)
        self.assertEqual(res_login.status_code, 303)
        self.assertIn("/admin?err=Invalid+admin+credentials", res_login.headers.get("location", ""))

    def test_admin_dev_login_proxy_and_production_isolation(self):
        """Verify _is_local_dev_request rejects X-Forwarded-For proxies, production, and Render environments."""
        from web.routers.admin import _is_local_dev_request
        from unittest.mock import patch, MagicMock

        # 1. Dev login route rejects requests carrying X-Forwarded-For header
        res_proxy = self.client.post(
            "/admin/auth/dev-login",
            data={"next_url": "/admin"},
            headers={"X-Forwarded-For": "203.0.113.50"},
            follow_redirects=False
        )
        self.assertEqual(res_proxy.status_code, 403)
        self.assertIn("Direct dev login only allowed on local environments.", res_proxy.text)

        # 2. Dev login route rejects in production environment
        with patch.dict(os.environ, {"ENVIRONMENT": "production"}):
            res_prod = self.client.post(
                "/admin/auth/dev-login",
                data={"next_url": "/admin"},
                follow_redirects=False
            )
            self.assertEqual(res_prod.status_code, 403)

        # 3. Dev login route rejects in Render environment
        with patch.dict(os.environ, {"RENDER": "true"}):
            res_render = self.client.post(
                "/admin/auth/dev-login",
                data={"next_url": "/admin"},
                follow_redirects=False
            )
            self.assertEqual(res_render.status_code, 403)

        # 4. Direct unit test of _is_local_dev_request matrix
        # 4a. External client IP
        mock_req = MagicMock()
        mock_req.client.host = "198.51.100.1"
        mock_req.headers = {}
        mock_req.url.hostname = "localhost"
        self.assertFalse(_is_local_dev_request(mock_req))

        # 4b. Spoofed localhost host header with proxy header
        mock_req = MagicMock()
        mock_req.client.host = "127.0.0.1"
        mock_req.headers = {"x-forwarded-for": "198.51.100.1"}
        mock_req.url.hostname = "localhost"
        self.assertFalse(_is_local_dev_request(mock_req))

        # 4c. Non-local hostname
        mock_req = MagicMock()
        mock_req.client.host = "127.0.0.1"
        mock_req.headers = {}
        mock_req.url.hostname = "evil-domain.com"
        self.assertFalse(_is_local_dev_request(mock_req))

        # 4d. Legitimate direct local connection (127.0.0.1 and ::1)
        mock_req = MagicMock()
        mock_req.client.host = "127.0.0.1"
        mock_req.headers = {}
        mock_req.url.hostname = "localhost"
        self.assertTrue(_is_local_dev_request(mock_req))

        mock_req.client.host = "::1"
        self.assertTrue(_is_local_dev_request(mock_req))


    
    
    
