"""Email addresses never reach log output; the paid audit worker reports that it is alive."""
import io
import logging
import os
import unittest
from unittest.mock import patch

os.environ.setdefault("TESTING", "1")

import core  # noqa: F401  (installs the masking record factory)
from core.log_privacy import mask_emails


def _capture(logger_name: str):
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(logging.Formatter("%(message)s"))
    log = logging.getLogger(logger_name)
    log.addHandler(handler)
    log.setLevel(logging.INFO)
    log.propagate = False
    return log, stream, handler


class TestMaskEmails(unittest.TestCase):
    def test_cases(self):
        for raw, want in [
            ("Dispatched email via Resend API to rahul.sharma@gmail.com (Subject: X)",
             "Dispatched email via Resend API to ra***@gmail.com (Subject: X)"),
            ("a@b.co", "a***@b.co"),
            ("to first.last+tag@mail.example.co.in and x9@yahoo.com",
             "to fi***@mail.example.co.in and x9***@yahoo.com"),
            ("Subject: Moatnomics Fund NAV Update (2026-11-12)", "Subject: Moatnomics Fund NAV Update (2026-11-12)"),
            ("@media rule, user@localhost, pkg@1.2.3", "@media rule, user@localhost, pkg@1.2.3"),
        ]:
            with self.subTest(raw=raw):
                self.assertEqual(mask_emails(raw), want)


class TestLogRecordsAreMasked(unittest.TestCase):
    def setUp(self):
        self.log, self.stream, self.handler = _capture("test.log_privacy")

    def tearDown(self):
        self.log.removeHandler(self.handler)

    def test_percent_args_masked(self):
        self.log.info("Dispatched email via Resend API to %s (Subject: %s)", "priya.nair@gmail.com", "Wrap")
        out = self.stream.getvalue()
        self.assertNotIn("priya.nair@gmail.com", out)
        self.assertIn("pr***@gmail.com", out)

    def test_fstring_masked(self):
        email = "rahul.sharma@outlook.com"
        self.log.info(f"Active session set for: {email} (Credits: 2)")
        out = self.stream.getvalue()
        self.assertNotIn(email, out)
        self.assertIn("ra***@outlook.com (Credits: 2)", out)

    def test_malformed_log_call_is_still_masked(self):
        with patch("sys.stderr", new_callable=io.StringIO) as err:
            self.log.info("Sent %s to %s", "only-one-arg-with rahul.sharma@gmail.com")
        out = self.stream.getvalue()
        self.assertNotIn("rahul.sharma@gmail.com", out)
        self.assertIn("ra***@gmail.com", out)
        self.assertIn("malformed log call", err.getvalue())
        self.assertNotIn("rahul", err.getvalue())

    def test_messages_without_email_untouched(self):
        self.log.info("Loaded %d NSE equity trading holidays.", 20)
        self.assertEqual(self.stream.getvalue().strip(), "Loaded 20 NSE equity trading holidays.")


class TestWorkerLogsLiveness(unittest.TestCase):
    def test_startup_and_status_lines(self):
        import scripts.run_paid_fund_audit_worker as worker

        clock = iter([0.0, 400.0, 400.0])
        with patch.object(worker, "setup_logging"), patch.object(worker, "init_db"), \
             patch.object(worker, "claim_fund_audit", return_value=None), \
             patch.object(worker, "sleep"), \
             patch.object(worker, "monotonic", side_effect=lambda: next(clock)), \
             patch("sys.argv", ["run_paid_fund_audit_worker.py", "--once"]), \
             self.assertLogs(worker.logger.name, level="INFO") as cm:
            worker.main()
        text = "\n".join(cm.output)
        self.assertIn("Paid fund audit worker started", text)
        self.assertIn("Paid fund audit worker alive: 0 job(s) done", text)


if __name__ == "__main__":
    unittest.main()
