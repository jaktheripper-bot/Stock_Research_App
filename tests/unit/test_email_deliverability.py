"""
Inbox placement signals for the research emails (Task 7):
- RFC 2369 / RFC 8058 List-Unsubscribe + List-Unsubscribe-Post headers on every subscriber send,
- a token-only one-click POST handler at the same URL,
- a dedicated "Moatnomics Research" sender, separate from the Service Desk address,
- a "move to Primary" hint in both the HTML and plain-text footers.
"""
import json
import os
import unittest
from unittest.mock import patch

os.environ.setdefault("TESTING", "1")


class _Resp:
    status = 200

    def read(self):
        return b'{"id": "re_msg_1"}'

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class TestListUnsubscribeHeaders(unittest.TestCase):
    def test_header_format(self):
        from core.notify import list_unsubscribe_headers

        h = list_unsubscribe_headers("tok_abc")
        self.assertRegex(h["List-Unsubscribe"], r"^<https://[^>]+/api/notifications/unsubscribe\?token=tok_abc>$")
        self.assertEqual(h["List-Unsubscribe-Post"], "List-Unsubscribe=One-Click")

    def test_token_is_url_encoded(self):
        from core.notify import list_unsubscribe_headers

        self.assertIn("token=a%2Bb%26c", list_unsubscribe_headers("a+b&c")["List-Unsubscribe"])

    def test_no_token_no_headers(self):
        from core.notify import list_unsubscribe_headers

        for tok in (None, "", "   "):
            self.assertEqual(list_unsubscribe_headers(tok), {})

    def test_headers_reach_the_resend_payload(self):
        from core import notify

        payloads = []

        def fake_urlopen(req, context=None, timeout=None):
            payloads.append(json.loads(req.data.decode()))
            return _Resp()

        with patch.dict(os.environ, {"RESEND_API_KEY": "re_test"}, clear=False), \
             patch("core.notify._is_live_email_dispatch_allowed", return_value=True), \
             patch("urllib.request.urlopen", side_effect=fake_urlopen):
            notify._send_via_resend("a@x.com", "b@y.com", "S", "T", headers=notify.list_unsubscribe_headers("t1"))
            notify._send_via_resend("a@x.com", "b@y.com", "S", "T")
        self.assertEqual(payloads[0]["headers"]["List-Unsubscribe-Post"], "List-Unsubscribe=One-Click")
        self.assertNotIn("headers", payloads[1])


class TestResearchDispatch(unittest.TestCase):
    def test_each_subscriber_gets_own_headers_and_research_sender(self):
        from core import notify

        bouquet = {"edition_date": "2026-11-13", "subject": "Moatnomics Fund NAV Update", "formatted_date": "13 Nov"}
        subs = [
            {"id": "u1", "email": "a@example.com", "full_name": "Rahul Sharma", "unsubscribe_token": "tok1"},
            {"id": "u2", "email": "b@example.com", "full_name": "Priya Nair", "unsubscribe_token": "tok2"},
        ]
        calls = []

        def fake_send(sender, to, subj, text, html=None, tags=None, headers=None):
            calls.append((sender, to, headers))
            return "re_x"

        with patch.dict(os.environ, {"RESEND_API_KEY": "re_test", "SMTP_FROM": "Moatnomics Service Desk <desk@moatnomics.com>"}, clear=False), \
             patch("core.notify._get_cfg", side_effect=lambda k: {"RESEND_API_KEY": "re_test", "SMTP_FROM": "Moatnomics Service Desk <desk@moatnomics.com>"}.get(k)), \
             patch("core.analysis.research_bouquet.compile_research_bouquet", return_value=bouquet), \
             patch("core.analysis.research_bouquet.render_bouquet_html", return_value="<p>x</p>"), \
             patch("core.analysis.research_bouquet.render_bouquet_text", return_value="x"), \
             patch("core.db.digest.has_edition_been_dispatched", return_value=False), \
             patch("core.db.digest.get_digest_subscribers", return_value=subs), \
             patch("core.db.digest.record_digest_dispatch", return_value="dsp_1"), \
             patch("core.db.digest.record_recipient_sends"), \
             patch("core.notify._send_via_resend", side_effect=fake_send):
            notify.dispatch_research_bouquet(edition_date="2026-11-13", edition_kind="FUND_NAV")

        self.assertEqual(len(calls), 2)
        for (sender, to, headers), tok in zip(calls, ("tok1", "tok2")):
            self.assertEqual(sender, notify.RESEARCH_FROM_DEFAULT)
            self.assertIn(f"token={tok}>", headers["List-Unsubscribe"])

    def test_research_sender_override_and_default(self):
        from core import notify

        with patch("core.notify._get_cfg", return_value=None):
            self.assertEqual(notify.research_sender(), "Moatnomics Research <research@moatnomics.com>")
        with patch("core.notify._get_cfg", side_effect=lambda k: "Desk <x@moatnomics.com>" if k == "RESEARCH_FROM" else None):
            self.assertEqual(notify.research_sender(), "Desk <x@moatnomics.com>")


class TestFooterHint(unittest.TestCase):
    def test_primary_hint_in_both_formats(self):
        from core.analysis import research_bouquet as rb

        bouquet = {"edition_date": "2026-11-13", "formatted_date": "13 Nov 2026", "subject": "S"}
        sub = {"email": "a@example.com", "full_name": "Rahul Sharma", "unsubscribe_token": "tok1"}
        html_out = rb.render_bouquet_html(bouquet, subscriber=sub)
        text_out = rb.render_bouquet_text(bouquet, subscriber=sub)
        self.assertIn(rb.PRIMARY_TAB_HINT, html_out)
        self.assertIn(rb.PRIMARY_TAB_HINT, text_out)
        self.assertIn(rb.build_unsubscribe_url("tok1"), html_out)


class TestOneClickEndpoint(unittest.TestCase):
    def _post(self, url, found=None, saved=True):
        from fastapi.testclient import TestClient
        from web.main import app

        with patch("core.db.digest.get_subscriber_by_token", return_value=found) as lookup, \
             patch("core.db.digest.set_user_digest_subscription", return_value=saved) as setter:
            res = TestClient(app).post(url, data={"List-Unsubscribe": "One-Click"})
        return res, lookup, setter

    def test_valid_token_unsubscribes(self):
        res, _, setter = self._post("/api/notifications/unsubscribe?token=tok1", found={"email": "a@example.com"})
        self.assertEqual(res.status_code, 200)
        setter.assert_called_once_with("tok1", subscribe=False)

    def test_email_address_is_never_accepted(self):
        res, lookup, setter = self._post("/api/notifications/unsubscribe?token=a@example.com", found=None)
        self.assertEqual(res.status_code, 404)
        setter.assert_not_called()

    def test_missing_token(self):
        res, _, setter = self._post("/api/notifications/unsubscribe")
        self.assertEqual(res.status_code, 400)
        setter.assert_not_called()

    def test_storage_failure_is_500(self):
        res, _, _ = self._post("/api/notifications/unsubscribe?token=tok1", found={"email": "a@example.com"}, saved=False)
        self.assertEqual(res.status_code, 500)


class TestTokenOnlyLinks(unittest.TestCase):
    """GET unsubscribe / resubscribe accept only the secret token, never an email address."""

    def _get(self, path, found):
        from fastapi.testclient import TestClient
        from web.main import app

        with patch("core.db.digest.get_subscriber_by_token", return_value=found), \
             patch("core.db.digest.set_user_digest_subscription", return_value=True) as setter:
            res = TestClient(app).get(path, headers={"Accept": "application/json"})
        return res, setter

    def test_email_parameter_is_ignored(self):
        for path in ("/api/notifications/unsubscribe?email=a@example.com",
                     "/api/notifications/resubscribe?email=a@example.com"):
            with self.subTest(path=path):
                res, setter = self._get(path, found={"email": "a@example.com"})
                self.assertEqual(res.status_code, 400)
                setter.assert_not_called()

    def test_email_passed_as_token_is_rejected(self):
        for path in ("/api/notifications/unsubscribe?token=a@example.com",
                     "/api/notifications/resubscribe?token=a@example.com"):
            with self.subTest(path=path):
                res, setter = self._get(path, found=None)
                self.assertEqual(res.status_code, 404)
                setter.assert_not_called()

    def test_valid_token_still_works(self):
        for path, subscribe in (("/api/notifications/unsubscribe?token=tok1", False),
                                ("/api/notifications/resubscribe?token=tok1", True)):
            with self.subTest(path=path):
                res, setter = self._get(path, found={"email": "a@example.com"})
                self.assertEqual(res.status_code, 200)
                setter.assert_called_once_with("tok1", subscribe=subscribe)


if __name__ == "__main__":
    unittest.main()
