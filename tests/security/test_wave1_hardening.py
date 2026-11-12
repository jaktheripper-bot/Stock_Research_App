"""
Wave 1 of the 12 Nov security audit (P0-01, P0-02, P0-03, P0-05, P0-07, P0-09):
- no admin-API "user exists" fallback when verifying a sign-in token; `exp` is required;
- the OAuth callback's `next` value can't break out of its <script> or point off-site;
- workflow_dispatch inputs never reach shell text;
- the admin lookup fails closed on database errors;
- thesis saves and analytics events take identity only from the session cookie;
- .dockerignore keeps secrets and local databases out of images.
"""
import base64
import json
import os
import re
import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

os.environ.setdefault("TESTING", "1")

ROOT = Path(__file__).resolve().parents[2]


def _b64(obj) -> str:
    return base64.urlsafe_b64encode(json.dumps(obj).encode()).decode().rstrip("=")


def _unsigned_token(header, claims) -> str:
    return f"{_b64(header)}.{_b64(claims)}." + base64.urlsafe_b64encode(b"\x01" * 64).decode().rstrip("=")


class TestTokenVerification(unittest.TestCase):
    def _verify(self, token, anon_key):
        from core.auth import supabase_auth as sb

        cfg = {"url": "https://example.supabase.co", "anon_key": anon_key}
        resp_401 = MagicMock(status_code=401)
        with patch.dict(os.environ, {"TESTING": "0"}), \
             patch.object(sb, "get_supabase_auth_config", return_value=cfg), \
             patch.object(sb.requests, "get", return_value=resp_401) as mock_get:
            result = sb.verify_supabase_access_token(token)
        return result, [c.args[0] for c in mock_get.call_args_list]

    def test_forged_token_with_service_key_config_is_rejected(self):
        token = _unsigned_token({"alg": "HS256"}, {"sub": "victim-uuid", "email": "victim@example.com",
                                                   "exp": int(time.time()) + 600})
        (email, _), urls = self._verify(token, anon_key="sb_secret_example")
        self.assertIsNone(email)
        self.assertFalse(any("/auth/v1/admin/" in u for u in urls), urls)

    def test_token_without_exp_is_rejected(self):
        token = _unsigned_token({"alg": "ES256"}, {"sub": "x", "email": "a@example.com"})
        (email, _), urls = self._verify(token, anon_key="public-anon")
        self.assertIsNone(email)
        self.assertEqual(urls, [])

    def test_no_admin_lookup_code_remains(self):
        src = (ROOT / "core/auth/supabase_auth.py").read_text()
        self.assertNotIn("/auth/v1/admin/users", src)


class TestSafeNextPath(unittest.TestCase):
    def test_cases(self):
        from web.routers.auth_billing import _safe_next_path

        for raw, want in [
            ("/dossier/INFY", "/dossier/INFY"),
            (None, "/"),
            ("https://evil.example", "/"),
            ("//evil.example", "/"),
            ("/\\evil.example", "/"),
            ("/ok\nSet-Cookie: x", "/"),
            ("/" + "a" * 600, "/"),
        ]:
            with self.subTest(raw=raw):
                self.assertEqual(_safe_next_path(raw), want)

    def test_callback_page_cannot_be_broken_out_of(self):
        from fastapi.testclient import TestClient
        from web.main import app

        payload = "');alert(document.cookie)//</script><script>alert(1)</script>"
        res = TestClient(app).get("/auth/callback", params={"next": payload})
        self.assertEqual(res.status_code, 200)
        self.assertNotIn("alert(", res.text)
        self.assertNotIn("<script>alert", res.text)
        self.assertIn('encodeURIComponent("/")', res.text)

    def test_valid_next_is_json_encoded(self):
        from fastapi.testclient import TestClient
        from web.main import app

        res = TestClient(app).get("/auth/callback", params={"next": "/dossier/INFY?tab=x'y"})
        self.assertIn('encodeURIComponent("/dossier/INFY?tab=x\'y")', res.text)


class TestWorkflowInputs(unittest.TestCase):
    def test_inputs_never_inside_run_scripts(self):
        for name in ("scheduled_pipeline.yml", "subscription_renewal_reminder.yml"):
            text = (ROOT / ".github/workflows" / name).read_text()
            for block in re.findall(r"run: \|\n((?:\s{10,}.*\n?)+)", text):
                with self.subTest(workflow=name):
                    self.assertNotIn("${{", block)
            self.assertIn('INPUT_DATE: ${{ inputs.date }}', text)
            self.assertIn("^[0-9]{4}-[0-9]{2}-[0-9]{2}$", text)

    def test_ci_workflows_are_read_only(self):
        for name in ("ci.yml", "p0_release_gate.yml"):
            text = (ROOT / ".github/workflows" / name).read_text()
            with self.subTest(workflow=name):
                self.assertRegex(text, r"(?m)^permissions:\n  contents: read$")


class TestAdminLookupFailsClosed(unittest.TestCase):
    def test_db_error_returns_none_even_for_owner_email(self):
        from core.db import admin as admin_db

        owner = sorted(admin_db.get_authorized_bootstrap_emails())[0]
        with patch.object(admin_db, "init_db", side_effect=RuntimeError("pool exhausted")), \
             self.assertLogs(admin_db.logger.name, level="ERROR"):
            self.assertIsNone(admin_db.get_admin_user(owner))

    def test_failed_bootstrap_persist_returns_none(self):
        from core.db import admin as admin_db

        owner = sorted(admin_db.get_authorized_bootstrap_emails())[0]
        empty_cursor = MagicMock()
        empty_cursor.fetchone.return_value = None
        first_conn = MagicMock()
        first_conn.cursor.return_value = empty_cursor
        with patch.object(admin_db, "init_db"), \
             patch.object(admin_db, "get_db_connection", side_effect=[first_conn, RuntimeError("write failed")]):
            self.assertIsNone(admin_db.get_admin_user(owner))


class TestIdentityFromSessionOnly(unittest.TestCase):
    def _client(self):
        from fastapi.testclient import TestClient
        from web.main import app
        return TestClient(app)

    def test_anonymous_victim_user_id_is_refused(self):
        for path, body in (
            ("/api/countercase", {"ticker": "INFY", "failure_vector": "x", "anti_thesis_notes": "y"}),
            ("/api/thesis-checkpoint", {"ticker": "INFY", "decision": "HOLD", "rationale": "y"}),
        ):
            with self.subTest(path=path), \
                 patch("web.routers.markets._get_current_web_user", return_value=None), \
                 patch("core.db.users.save_user_thesis_entry") as saver:
                res = self._client().post(path, json={**body, "user_id": "usr_victim"})
                self.assertEqual(res.status_code, 401)
                saver.assert_not_called()

    def test_signed_in_user_writes_own_ledger_only(self):
        with patch("web.routers.markets._get_current_web_user", return_value={"id": "usr_me"}), \
             patch("web.routers.markets.record_usage_event"), \
             patch("core.db.users.save_user_thesis_entry") as saver:
            res = self._client().post("/api/countercase", json={
                "ticker": "INFY", "failure_vector": "x", "anti_thesis_notes": "y", "user_id": "usr_victim"})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(saver.call_args.kwargs["user_id"], "usr_me")

    def test_telemetry_ignores_body_identity(self):
        seen = {}

        def capture(**kw):
            seen.update(kw)
            return True

        with patch("web.routers.auth_billing._get_current_web_user", return_value=None), \
             patch("web.routers.auth_billing.is_excluded_telemetry_event", side_effect=capture):
            self._client().post("/api/telemetry/event", json={
                "event_type": "PAGE_DWELL", "user_id": "usr_victim", "user_email": "victim@example.com"})
        self.assertEqual(seen.get("user_id"), "")
        self.assertEqual(seen.get("user_email"), "")


class TestDockerIgnore(unittest.TestCase):
    def test_secrets_and_databases_excluded(self):
        lines = set((ROOT / ".dockerignore").read_text().split())
        for entry in (".env", ".env.*", "*.db", "*.db-*", "backups/", "scratch/", ".git/"):
            with self.subTest(entry=entry):
                self.assertIn(entry, lines)
        for needed in ("web/", "core/", "scripts/", "data/", "requirements.txt"):
            self.assertNotIn(needed, lines)


if __name__ == "__main__":
    unittest.main()
