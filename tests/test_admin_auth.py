"""
tests/test_admin_auth.py
==============================================================================
Test Suite for Admin Google OAuth, RFC 6238 TOTP 2FA, Roles & Audit Ledger.
==============================================================================
"""

import pytest
from fastapi.testclient import TestClient

from core.auth.totp import (
    generate_totp_secret,
    get_totp_code,
    verify_totp_code,
    get_totp_uri,
)
from core.db.admin import (
    get_admin_user,
    list_admin_users,
    add_admin_user,
    remove_admin_user,
    update_admin_role,
    set_admin_totp_secret,
    enable_admin_totp,
    record_admin_audit,
    get_admin_audit_logs,
)
from web.main import app, ADMIN_COOKIE_NAME, ADMIN_2FA_PENDING_COOKIE


@pytest.fixture
def client():
    return TestClient(app)


def test_totp_generation_and_verification():
    """Verify RFC 6238 TOTP generates and verifies 6-digit codes correctly."""
    secret = generate_totp_secret()
    assert len(secret) == 32
    assert secret.isalnum()

    # Code generation
    code = get_totp_code(secret)
    assert len(code) == 6
    assert code.isdigit()

    # Verification passes for correct code
    assert verify_totp_code(secret, code) is True

    # Verification fails for invalid code
    assert verify_totp_code(secret, "999999" if code != "999999" else "000000") is False
    assert verify_totp_code(secret, "") is False
    assert verify_totp_code(secret, "123") is False

    # URI contains account and secret
    uri = get_totp_uri(secret, "lyndnpnto@gmail.com")
    assert uri.startswith("otpauth://totp/")
    assert secret in uri
    assert "lyndnpnto%40gmail.com" in uri or "lyndnpnto@gmail.com" in uri


def test_admin_whitelist_and_seeding():
    """Verify root owner account is seeded and team management works."""
    owner = get_admin_user("lyndnpnto@gmail.com")
    assert owner is not None
    assert owner["role"] == "owner"
    assert owner["email"].lower() == "lyndnpnto@gmail.com"

    # Add a new admin
    ok, msg = add_admin_user("test_admin@example.com", role="admin", invited_by="lyndnpnto@gmail.com")
    assert ok is True
    admin = get_admin_user("test_admin@example.com")
    assert admin is not None
    assert admin["role"] == "admin"

    # Update role
    ok, msg = update_admin_role("test_admin@example.com", "viewer", requesting_email="lyndnpnto@gmail.com")
    assert ok is True
    assert get_admin_user("test_admin@example.com")["role"] == "viewer"

    # Remove admin
    ok, msg = remove_admin_user("test_admin@example.com", requesting_email="lyndnpnto@gmail.com")
    assert ok is True
    assert get_admin_user("test_admin@example.com") is None

    # Owner cannot be removed
    ok, msg = remove_admin_user("lyndnpnto@gmail.com", requesting_email="other@example.com")
    assert ok is False


def test_admin_audit_trail_logging():
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
    assert len(matched) > 0
    assert matched[0]["admin_email"] == "lyndnpnto@gmail.com"
    assert matched[0]["target_id"] == "12345"


def test_admin_web_flow(client):
    """Verify admin login challenge, 2FA setup, and dashboard access."""
    # 1. Unauthenticated request to /admin shows login form
    res = client.get("/admin")
    assert res.status_code == 200
    assert "Executive Administrator Portal" in res.text
    assert "Sign In with Google" in res.text

    # 2. Direct verify initiation for whitelisted owner
    res2 = client.post("/admin/auth/direct-verify", data={"email": "lyndnpnto@gmail.com"}, follow_redirects=False)
    assert res2.status_code == 303
    assert ADMIN_2FA_PENDING_COOKIE in res2.cookies

    pending_cookie = res2.cookies[ADMIN_2FA_PENDING_COOKIE]

    # 3. Setup 2FA
    res_setup = client.get("/admin/setup-2fa", cookies={ADMIN_2FA_PENDING_COOKIE: pending_cookie})
    assert res_setup.status_code == 200
    assert "Set Up Google Authenticator" in res_setup.text

    # Retrieve secret from db
    owner = get_admin_user("lyndnpnto@gmail.com")
    secret = owner["totp_secret"]
    assert secret is not None

    # Submit valid 6-digit code
    valid_code = get_totp_code(secret)
    res_confirm = client.post(
        "/admin/setup-2fa",
        data={"code": valid_code},
        cookies={ADMIN_2FA_PENDING_COOKIE: pending_cookie},
        follow_redirects=False
    )
    assert res_confirm.status_code == 303
    assert ADMIN_COOKIE_NAME in res_confirm.cookies

    admin_session_cookie = res_confirm.cookies[ADMIN_COOKIE_NAME]

    # 4. Access dashboard with authenticated session
    res_dash = client.get("/admin", cookies={ADMIN_COOKIE_NAME: admin_session_cookie})
    assert res_dash.status_code == 200
    assert "Executive Telemetry & Site Usage Hub" in res_dash.text
    assert "lyndnpnto@gmail.com" in res_dash.text
    assert "OWNER" in res_dash.text
    assert "2FA ACTIVE" in res_dash.text


def test_telemetry_attribution_and_custom_date_range(client):
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
    res_tel = client.post("/api/telemetry/event", json=telemetry_payload)
    assert res_tel.status_code == 200
    assert res_tel.json()["status"] == "ok"

    # 2. Access admin console with custom date range
    res_custom = client.get(
        "/admin?window=custom&start_date=2026-09-01&end_date=2026-10-05&tab=traffic",
        cookies={ADMIN_COOKIE_NAME: admin_cookie}
    )
    assert res_custom.status_code == 200
    assert "2026-09-01" in res_custom.text
    assert "2026-10-05" in res_custom.text
    assert "Traffic Channels" in res_custom.text

    # 3. Test data purge endpoint requires authentication
    res_unauth = client.post("/admin/telemetry/purge-test-data")
    assert res_unauth.status_code in (401, 303)

    # 4. Trigger purge with authenticated owner
    res_purge = client.post(
        "/admin/telemetry/purge-test-data",
        cookies={ADMIN_COOKIE_NAME: admin_cookie},
        follow_redirects=False
    )
    assert res_purge.status_code == 303
    assert "tab=telemetry" in res_purge.headers["location"]

    # 5. Verify audit log entry was created
    audit_logs = get_admin_audit_logs(limit=10)
    assert any(log["action"] == "PURGE_TEST_DATA" for log in audit_logs)

