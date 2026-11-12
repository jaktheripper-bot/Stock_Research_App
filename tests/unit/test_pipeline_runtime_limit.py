"""
Wall-clock limit for scheduled pipeline processes (PIPELINE_MAX_RUNTIME_SECONDS).

Render bills cron jobs per second of run time and only stops a run after 12 hours, so each Render
cron job sets a limit. At the limit the process must exit through the SIGTERM path (so held phase
leases are released) and, if it cannot unwind, be ended outright.
"""
import os
import re
import signal
import subprocess
import sys
import textwrap
import time
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]


class TestResolveMaxRuntime(unittest.TestCase):
    def _resolve(self, value):
        from scripts.run_scheduled_pipeline import MAX_RUNTIME_ENV, _resolve_max_runtime_seconds

        env = {k: v for k, v in os.environ.items() if k != MAX_RUNTIME_ENV}
        if value is not None:
            env[MAX_RUNTIME_ENV] = value
        with patch.dict(os.environ, env, clear=True):
            return _resolve_max_runtime_seconds()

    def test_unset_blank_and_zero_mean_no_limit(self):
        for value in (None, "", "   ", "0"):
            with self.subTest(value=value):
                self.assertEqual(self._resolve(value), 0)

    def test_valid_seconds_are_used(self):
        self.assertEqual(self._resolve("5400"), 5400)
        self.assertEqual(self._resolve(" 60 "), 60)

    def test_unreadable_or_negative_values_mean_no_limit(self):
        for value in ("90m", "1.5", "abc", "-5"):
            with self.subTest(value=value):
                self.assertEqual(self._resolve(value), 0)


class TestInstallRuntimeLimit(unittest.TestCase):
    def test_no_limit_starts_no_timers(self):
        from scripts.run_scheduled_pipeline import _install_runtime_limit

        self.assertEqual(_install_runtime_limit(0), [])
        self.assertEqual(_install_runtime_limit(-1), [])

    def test_limit_arms_soft_then_hard_timer(self):
        import scripts.run_scheduled_pipeline as pipeline

        timers = pipeline._install_runtime_limit(3600)
        try:
            self.assertEqual(len(timers), 2)
            self.assertEqual(timers[0].interval, 3600)
            self.assertEqual(timers[1].interval, 3600 + pipeline.MAX_RUNTIME_HARD_EXIT_GRACE_SECONDS)
            self.assertTrue(all(t.daemon and t.is_alive() for t in timers))
        finally:
            for t in timers:
                t.cancel()

    def test_soft_limit_sends_sigterm_and_hard_limit_ends_process(self):
        import scripts.run_scheduled_pipeline as pipeline

        with patch.object(pipeline, "MAX_RUNTIME_HARD_EXIT_GRACE_SECONDS", 0), \
                patch.object(pipeline.os, "kill") as kill, \
                patch.object(pipeline.os, "_exit") as hard_exit, \
                patch.object(pipeline, "flush_betterstack_logs"):
            # A 1-second limit is the smallest positive whole number of seconds.
            timers = pipeline._install_runtime_limit(1)
            for t in timers:
                t.join(timeout=10)
        kill.assert_called_once_with(os.getpid(), signal.SIGTERM)
        hard_exit.assert_called_once_with(pipeline.MAX_RUNTIME_HARD_EXIT_CODE)


class TestRuntimeLimitEndsARealProcess(unittest.TestCase):
    def test_process_exits_via_sigterm_path_and_runs_cleanup(self):
        """A run stuck past its limit exits 143 (128 + SIGTERM) and unwinds `finally` blocks."""
        script = textwrap.dedent("""
            import sys, time
            sys.path.insert(0, %r)
            import scripts.run_scheduled_pipeline as pipeline
            pipeline._install_termination_handler()
            pipeline._install_runtime_limit(1)
            try:
                time.sleep(60)
            finally:
                print("CLEANUP_RAN", flush=True)
        """ % str(ROOT))
        env = {**os.environ, "TESTING": "1"}
        started = time.monotonic()
        proc = subprocess.run(
            [sys.executable, "-c", script], cwd=str(ROOT), env=env,
            capture_output=True, text=True, timeout=45,
        )
        self.assertEqual(proc.returncode, 128 + int(signal.SIGTERM), proc.stderr[-800:])
        self.assertIn("CLEANUP_RAN", proc.stdout)
        self.assertLess(time.monotonic() - started, 40)


class TestRenderCronJobsSetALimit(unittest.TestCase):
    def test_every_render_cron_job_sets_a_limit_under_two_hours(self):
        text = (ROOT / "render.yaml").read_text()
        blocks = re.split(r"(?m)^  - type: ", text)[1:]
        crons = [b for b in blocks if b.split("\n", 1)[0].strip() == "cron"]
        self.assertEqual(len(crons), 6)
        for block in crons:
            name = re.search(r"(?m)^    name: (\S+)", block).group(1)
            with self.subTest(name=name):
                match = re.search(r'key: PIPELINE_MAX_RUNTIME_SECONDS\n\s+value: "(\d+)"', block)
                self.assertIsNotNone(match, f"{name} has no PIPELINE_MAX_RUNTIME_SECONDS")
                self.assertTrue(0 < int(match.group(1)) <= 7200)

    def test_sender_limits_exceed_their_wait_caps(self):
        """A sender must not be cut off while it is still allowed to wait for its phases."""
        from scripts.run_scheduled_pipeline import EDITION_FUND_NAV, EDITION_MARKET_CLOSE, SEND_WAIT_CAP_SECONDS

        text = (ROOT / "render.yaml").read_text()
        for name, kind in (("market-close-wrap-sender", EDITION_MARKET_CLOSE), ("fund-nav-update-sender", EDITION_FUND_NAV)):
            with self.subTest(name=name):
                block = text.split(f"name: {name}\n", 1)[1].split("  - type: ", 1)[0]
                limit = int(re.search(r'key: PIPELINE_MAX_RUNTIME_SECONDS\n\s+value: "(\d+)"', block).group(1))
                self.assertGreaterEqual(limit, SEND_WAIT_CAP_SECONDS[kind] + 600)


if __name__ == "__main__":
    unittest.main()
