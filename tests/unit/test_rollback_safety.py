"""`./run.sh rollback` force-pushes production, so it must be confirmed by a person, must not
destroy uncommitted work, and must test the commit it is about to restore."""
import io
import unittest
from unittest.mock import MagicMock, patch

from ci import checkpoint_manager as cm

SHA = "a" * 40
LEDGER = [{"tag": "checkpoint_x", "commit_sha": SHA}]


def _git_calls(run_cmd_mock):
    return [" ".join(c.args[0]) for c in run_cmd_mock.call_args_list]


class TestRollbackSafety(unittest.TestCase):
    def _run(self, *, status="", isatty=True, typed=(), tests_pass=True, force=False):
        stdin = MagicMock()
        stdin.isatty.return_value = isatty
        answers = iter(typed)
        with patch.object(cm, "load_ledger", return_value=LEDGER), \
             patch.object(cm, "get_git_info", return_value=("b" * 40, "dev", status)), \
             patch.object(cm, "run_cmd") as run_cmd, \
             patch.object(cm, "verify_commit_passes_tests", return_value=tests_pass) as verify, \
             patch.object(cm, "DB_FILE", MagicMock(exists=MagicMock(return_value=False))), \
             patch.object(cm.sys, "stdin", stdin), \
             patch("builtins.input", side_effect=lambda: next(answers)), \
             patch("sys.stdout", new_callable=io.StringIO) as out:
            try:
                cm.rollback_to_checkpoint(target_tag="checkpoint_x", force=force, restore_db=False)
                exited = False
            except SystemExit:
                exited = True
        return _git_calls(run_cmd), verify, out.getvalue(), exited

    def test_non_interactive_run_changes_nothing_even_with_force(self):
        calls, verify, out, exited = self._run(isatty=False, force=True)
        self.assertTrue(exited)
        self.assertEqual(calls, [])
        verify.assert_not_called()
        self.assertIn("interactive terminal", out)

    def test_uncommitted_changes_block_rollback(self):
        calls, _, out, exited = self._run(status=" M web/main.py")
        self.assertTrue(exited)
        self.assertEqual(calls, [])
        self.assertIn("Uncommitted changes", out)

    def test_wrong_confirmation_changes_nothing(self):
        calls, verify, _, _ = self._run(typed=["yes"])
        self.assertEqual(calls, [])
        verify.assert_not_called()

    def test_failing_target_commit_stops_rollback(self):
        calls, verify, out, _ = self._run(typed=["checkpoint_x", "no"], tests_pass=False)
        verify.assert_called_once_with(SHA)
        self.assertEqual(calls, [])
        self.assertIn("does not pass its own tests", out)

    def test_confirmed_and_passing_rollback_proceeds(self):
        calls, verify, _, _ = self._run(typed=["checkpoint_x"])
        verify.assert_called_once_with(SHA)
        self.assertIn(f"git reset --hard {SHA}", calls)
        self.assertIn("git push origin main --force", calls)


if __name__ == "__main__":
    unittest.main()
