"""Mailer delivery & open tracking: signed Resend webhook, per-recipient events, pauses, retention, panel."""
import base64
import hashlib
import hmac
import json
import os
import time
import unittest
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from fastapi.testclient import TestClient

from core.db import digest
from core.db.connection import get_connection, get_placeholder, init_db

IST = timezone(timedelta(hours=5, minutes=30))
SECRET = "whsec_" + base64.b64encode(b"test-webhook-secret-bytes-123456").decode()


def _sign(body: bytes, msg_id: str, ts: int, secret: str = SECRET) -> dict:
    key = base64.b64decode(secret.split("_", 1)[1])
    sig = base64.b64encode(hmac.new(key, f"{msg_id}.{ts}.".encode() + body, hashlib.sha256).digest()).decode()
    return {"svix-id": msg_id, "svix-timestamp": str(ts), "svix-signature": f"v1,{sig}"}


def _exec(sql, params=()):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(sql.replace("?", get_placeholder()), params)
    rows = cur.fetchall() if cur.description else []
    conn.commit()
    cur.close()
    conn.close()
    return rows


class MailerTrackingBase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_db()

    def setUp(self):
        self.uid = f"mt_{uuid.uuid4().hex[:10]}"
        self.email = f"{self.uid}@example.com"
        _exec(
            "INSERT INTO user_accounts (id, email, is_digest_subscribed, digest_unsubscribe_token) VALUES (?, ?, 1, ?)",
            (self.uid, self.email, f"tok_{self.uid}"),
        )
        self.msg = f"msg_{uuid.uuid4().hex[:12]}"
        self.dispatch = f"dsp_{uuid.uuid4().hex[:12]}"
        digest.record_recipient_sends(self.dispatch, "MARKET_CLOSE", "2026-11-12", [(self.uid, self.email, self.msg)])

    def tearDown(self):
        _exec("DELETE FROM digest_recipient_events WHERE user_id = ? OR dispatch_id = ?", (self.uid, self.dispatch))
        _exec("DELETE FROM user_accounts WHERE id = ?", (self.uid,))

    def _event(self, etype, bounce_type=None, msg=None):
        data = {"email_id": msg or self.msg, "to": [self.email], "created_at": "2026-11-12T14:05:00.000Z"}
        if bounce_type:
            data["bounce"] = {"type": bounce_type, "message": "mailbox unavailable"}
        return {"type": etype, "created_at": "2026-11-12T14:05:00.000Z", "data": data}

    def _apply(self, etype, **kw):
        return digest.apply_resend_event(self._event(etype, **kw), f"evt_{uuid.uuid4().hex}")

    def _sub_state(self):
        return _exec("SELECT is_digest_subscribed, digest_paused_reason FROM user_accounts WHERE id = ?", (self.uid,))[0]


class TestWebhookSignature(unittest.TestCase):

    def test_valid_signature_accepted_and_tampering_rejected(self):
        body = b'{"type":"email.delivered"}'
        now = int(time.time())
        headers = _sign(body, "msg_1", now)
        self.assertTrue(digest.verify_resend_webhook(body, headers, SECRET, now=now))
        self.assertFalse(digest.verify_resend_webhook(body + b" ", headers, SECRET, now=now))
        self.assertFalse(digest.verify_resend_webhook(body, headers, "whsec_" + base64.b64encode(b"other").decode(), now=now))
        self.assertFalse(digest.verify_resend_webhook(body, headers, "", now=now))
        self.assertFalse(digest.verify_resend_webhook(body, {}, SECRET, now=now))

    def test_stale_timestamp_rejected(self):
        body = b"{}"
        old = int(time.time()) - 3600
        self.assertFalse(digest.verify_resend_webhook(body, _sign(body, "m", old), SECRET))

    def test_endpoint_fails_closed_without_secret_and_writes_nothing(self):
        from web.main import app

        body = json.dumps({"type": "email.delivered", "data": {"email_id": "msg_x"}}).encode()
        headers = _sign(body, f"evt_{uuid.uuid4().hex}", int(time.time()))
        with TestClient(app) as client, \
             patch.dict(os.environ, {"RESEND_WEBHOOK_SECRET": ""}, clear=False), \
             patch("core.config.get_secret", return_value=None), \
             patch("core.db.digest.apply_resend_event") as apply_evt:
            resp = client.post("/api/webhooks/resend", content=body, headers=headers)
        self.assertEqual(resp.status_code, 401)
        apply_evt.assert_not_called()

    def test_endpoint_accepts_signed_event(self):
        from web.main import app

        body = json.dumps({"type": "email.opened", "data": {"email_id": "msg_unknown"}}).encode()
        headers = _sign(body, f"evt_{uuid.uuid4().hex}", int(time.time()))
        with TestClient(app) as client, \
             patch.dict(os.environ, {"RESEND_WEBHOOK_SECRET": SECRET}, clear=False), \
             patch("core.config.get_secret", return_value=None):
            resp = client.post("/api/webhooks/resend", content=body, headers=headers)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["status"], "UNKNOWN_MESSAGE")


class TestRecipientEventsAndPauses(MailerTrackingBase):

    def test_events_map_to_dispatch_and_are_idempotent(self):
        evt = self._event("email.delivered")
        self.assertEqual(digest.apply_resend_event(evt, "evt_dup_" + self.uid), "RECORDED")
        self.assertEqual(digest.apply_resend_event(evt, "evt_dup_" + self.uid), "DUPLICATE")
        rows = _exec(
            "SELECT dispatch_id, edition_kind, edition_date, event_type FROM digest_recipient_events WHERE user_id = ? AND event_type = 'delivered'",
            (self.uid,),
        )
        self.assertEqual(rows, [(self.dispatch, "MARKET_CLOSE", "2026-11-12", "delivered")])
        self.assertEqual(self._apply("email.opened"), "RECORDED")
        self.assertEqual(self._apply("email.sent"), "IGNORED_TYPE")
        self.assertEqual(self._apply("email.delivered", msg="msg_not_ours"), "UNKNOWN_MESSAGE")

    def test_hard_bounce_pauses_and_user_resubscribe_clears_it(self):
        self._apply("email.bounced", bounce_type="Permanent")
        subscribed, reason = self._sub_state()
        self.assertFalse(bool(subscribed))
        self.assertEqual(reason, "bounced_hard")
        self.assertTrue(digest.set_user_digest_subscription(f"tok_{self.uid}", True))
        subscribed, reason = self._sub_state()
        self.assertTrue(bool(subscribed))
        self.assertIsNone(reason)

    def test_spam_complaint_pause_only_admin_can_clear(self):
        self._apply("email.complained")
        self.assertEqual(self._sub_state()[1], "complained")
        self.assertFalse(digest.set_user_digest_subscription(f"tok_{self.uid}", True))
        self.assertEqual(self._sub_state()[1], "complained")
        self.assertIn(self.uid, [s["user_id"] for s in digest.get_paused_digest_subscribers()])
        self.assertTrue(digest.resume_digest_subscriber(self.uid))
        subscribed, reason = self._sub_state()
        self.assertTrue(bool(subscribed))
        self.assertIsNone(reason)
        self.assertFalse(digest.resume_digest_subscriber(self.uid))  # nothing left to resume

    def test_soft_bounces_pause_only_after_three_in_a_row(self):
        self._apply("email.bounced", bounce_type="Transient")
        self._apply("email.bounced", bounce_type="Transient")
        self.assertIsNone(self._sub_state()[1])
        self._apply("email.delivered")  # a delivery resets the streak
        self._apply("email.bounced", bounce_type="Transient")
        self._apply("email.bounced", bounce_type="Transient")
        self.assertIsNone(self._sub_state()[1])
        self._apply("email.bounced", bounce_type="Transient")
        self.assertEqual(self._sub_state()[1], "bounced_soft_x3")


class TestRetention(MailerTrackingBase):

    def test_rows_older_than_90_days_roll_into_totals(self):
        old_date = f"2001-01-{uuid.uuid4().int % 28 + 1:02d}"
        old_ts = (datetime.now(IST) - timedelta(days=91)).isoformat()
        new_ts = (datetime.now(IST) - timedelta(days=89)).isoformat()
        for ts, etype in ((old_ts, "delivered"), (old_ts, "opened"), (new_ts, "delivered")):
            _exec(
                "INSERT INTO digest_recipient_events (dispatch_id, edition_kind, edition_date, user_id, email, event_type, occurred_at) VALUES (?, 'FUND_NAV', ?, ?, ?, ?, ?)",
                (self.dispatch, old_date, self.uid, self.email, etype, ts),
            )
        try:
            res = digest.purge_expired_recipient_events()
            self.assertGreaterEqual(res["deleted_rows"], 2)
            left = _exec("SELECT event_type FROM digest_recipient_events WHERE edition_date = ?", (old_date,))
            self.assertEqual(left, [("delivered",)])
            totals = dict(_exec(
                "SELECT event_type, event_count FROM digest_edition_totals WHERE edition_date = ? AND edition_kind = 'FUND_NAV'",
                (old_date,),
            ))
            self.assertEqual(totals, {"delivered": 1, "opened": 1})
        finally:
            _exec("DELETE FROM digest_edition_totals WHERE edition_date = ?", (old_date,))
            _exec("DELETE FROM digest_recipient_events WHERE edition_date = ?", (old_date,))


class TestMailerPanel(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        init_db()

    def test_timeliness_classification_and_dash_for_missing_data(self):
        fri = datetime(2031, 3, 14, 23, 0, tzinfo=IST)  # a Friday, far from real data
        dates = ("2031-03-14", "2031-03-13", "2031-03-12")
        ids = []
        sends = {
            ("2031-03-13", "MARKET_CLOSE"): "2031-03-13T19:31:00+05:30",  # on time
            ("2031-03-12", "MARKET_CLOSE"): "2031-03-12T20:10:00+05:30",  # late
        }
        try:
            for (d, k), created in sends.items():
                did = f"dsp_{uuid.uuid4().hex[:12]}"
                ids.append(did)
                _exec(
                    "INSERT INTO digest_dispatches (id, edition_date, subject, recipients_count, delivered_count, failed_count, status, edition_kind, created_at) VALUES (?, ?, 's', 5, 5, 0, 'COMPLETED', ?, ?)",
                    (did, d, k, created),
                )
            rows = {(r["edition_date"], r["edition_kind"]): r for r in digest.get_mailer_panel(days=3, today=fri)}
            self.assertEqual(rows[("2031-03-13", "MARKET_CLOSE")]["timeliness"], "ON_TIME")
            self.assertEqual(rows[("2031-03-12", "MARKET_CLOSE")]["timeliness"], "LATE")
            self.assertEqual(rows[("2031-03-14", "MARKET_CLOSE")]["timeliness"], "NOT_SENT")  # 23:00 Fri, none sent
            self.assertEqual(rows[("2031-03-14", "FUND_NAV")]["timeliness"], "UPCOMING")      # due Sat 07:30
            self.assertIsNone(rows[("2031-03-13", "MARKET_CLOSE")]["delivered"])               # no webhook data: "—"
            self.assertEqual(rows[("2031-03-13", "MARKET_CLOSE")]["recipients"], 5)
        finally:
            for did in ids:
                _exec("DELETE FROM digest_dispatches WHERE id = ?", (did,))

    def test_weekend_editions_are_not_due(self):
        sun = datetime(2031, 3, 16, 23, 0, tzinfo=IST)
        rows = {(r["edition_date"], r["edition_kind"]): r for r in digest.get_mailer_panel(days=2, today=sun)}
        self.assertEqual(rows[("2031-03-16", "MARKET_CLOSE")]["timeliness"], "NOT_DUE")
        self.assertEqual(rows[("2031-03-15", "FUND_NAV")]["timeliness"], "NOT_DUE")


class TestSendPath(unittest.TestCase):

    def test_send_via_resend_returns_message_id_and_sends_tags(self):
        from core import notify

        captured = {}

        class _Resp:
            status = 200

            def read(self):
                return b'{"id": "re_msg_123"}'

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

        def fake_urlopen(req, context=None, timeout=None):
            captured.setdefault("payloads", []).append(json.loads(req.data.decode()))
            return _Resp()

        with patch.dict(os.environ, {"RESEND_API_KEY": "re_test"}, clear=False), \
             patch("core.notify._is_live_email_dispatch_allowed", return_value=True), \
             patch("urllib.request.urlopen", side_effect=fake_urlopen):
            mid = notify._send_via_resend("a@x.com", "b@y.com", "S", "T", tags={"edition_kind": "FUND_NAV", "edition_date": "2026-11-12"})
            ok = notify._dispatch_via_resend("a@x.com", "b@y.com", "S", "T")
        self.assertEqual(mid, "re_msg_123")
        self.assertIs(ok, True)  # existing callers keep a plain bool
        self.assertIn({"name": "edition_date", "value": "2026-11-12"}, captured["payloads"][0]["tags"])
        self.assertNotIn("tags", captured["payloads"][1])  # untagged callers send no tags

    def test_failed_send_returns_none_and_false(self):
        from core import notify

        with patch.dict(os.environ, {"RESEND_API_KEY": "re_test"}, clear=False), \
             patch("core.notify._is_live_email_dispatch_allowed", return_value=True), \
             patch("urllib.request.urlopen", side_effect=OSError("down")):
            self.assertIsNone(notify._send_via_resend("a@x.com", "b@y.com", "S", "T"))
            self.assertIs(notify._dispatch_via_resend("a@x.com", "b@y.com", "S", "T"), False)


class TestMigrationV054(unittest.TestCase):

    def test_v054_is_idempotent_on_sqlite(self):
        import sqlite3

        conn = sqlite3.connect(":memory:")
        cur = conn.cursor()
        cur.execute("CREATE TABLE user_accounts (id TEXT PRIMARY KEY, email TEXT)")
        digest.ensure_digest_tracking_tables(cur, is_pg=False)
        digest.ensure_digest_tracking_tables(cur, is_pg=False)
        cur.execute("PRAGMA table_info(user_accounts)")
        cols = {r[1] for r in cur.fetchall()}
        self.assertTrue({"digest_paused_reason", "digest_paused_at"} <= cols)
        cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = {r[0] for r in cur.fetchall()}
        self.assertTrue({"digest_recipient_events", "digest_edition_totals"} <= tables)
        conn.close()


if __name__ == "__main__":
    unittest.main()
