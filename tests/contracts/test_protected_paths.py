"""The files that judge agent work can't be changed quietly.

Rule (from `reports/Why our audits missed issues.md`, recommendation 2): the agent that writes code
must not also own the tests and gates that grade it. Two enforcement points share one list,
`ci/protected_paths.txt`: a Claude Code hook that blocks edits, and a CI job that fails any commit
changing a protected file without a `Protected-Change-Approved:` trailer.
"""
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import check_protected_paths as cpp  # noqa: E402

HOOK_PATH = ROOT / ".claude" / "hooks" / "protect_paths.py"


def _load_hook():
    spec = importlib.util.spec_from_file_location("protect_paths_hook", HOOK_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestProtectedList(unittest.TestCase):
    def test_list_covers_the_judges(self):
        patterns = cpp.load_patterns()
        for path in (
            "tests/contracts/test_protected_paths.py",
            "tests/contracts/new_dir/test_new.py",
            "tests/security/test_wave1_hardening.py",
            "scripts/verify_reality_audit.py",
            "scripts/check_protected_paths.py",
            "ci/protected_paths.txt",
            ".github/workflows/ci.yml",
            "render.yaml",
            ".claude/settings.json",
            ".claude/hooks/protect_paths.py",
            str(ROOT / "render.yaml"),
            "./render.yaml",
        ):
            with self.subTest(path=path):
                self.assertTrue(cpp.is_protected(path, patterns))

    def test_ordinary_code_is_not_protected(self):
        patterns = cpp.load_patterns()
        for path in ("web/main.py", "tests/unit/test_x.py", "tests/contractsX/test.py", "docs/render.yaml.md", "/etc/render.yaml"):
            with self.subTest(path=path):
                self.assertFalse(cpp.is_protected(path, patterns))


@unittest.skipUnless(HOOK_PATH.exists(), "Claude Code hook not installed")
class TestClaudeHook(unittest.TestCase):
    def setUp(self):
        self.hook = _load_hook()
        self.patterns = cpp.load_patterns()

    def _decide(self, tool, unlocked=False, **tool_input):
        return self.hook.decide({"tool_name": tool, "tool_input": tool_input}, self.patterns, unlocked)

    def test_edits_to_protected_files_are_refused_until_unlocked(self):
        for tool, path in (("Edit", "render.yaml"), ("Write", "tests/contracts/test_new.py"),
                           ("Edit", str(ROOT / ".github/workflows/ci.yml"))):
            with self.subTest(path=path):
                self.assertIn("owner", self._decide(tool, file_path=path))
                self.assertIsNone(self._decide(tool, unlocked=True, file_path=path))

    def test_ordinary_edits_are_allowed(self):
        self.assertIsNone(self._decide("Edit", file_path="web/main.py"))

    def test_agent_cannot_unlock_itself(self):
        self.assertIsNotNone(self._decide("Write", unlocked=True, file_path=".claude/protected-unlock"))
        self.assertIsNotNone(self._decide("Bash", unlocked=True, command="./run.sh unlock-protected 30"))
        self.assertIsNotNone(self._decide("Bash", command="echo 9999999999 > .claude/protected-unlock"))

    def test_shell_writes_to_protected_files_are_refused(self):
        for command in ('sed -i "" s/a/b/ render.yaml', "echo x >> .github/workflows/ci.yml",
                        "rm tests/contracts/test_protected_paths.py", "git checkout -- scripts/verify_reality_audit.py",
                        "python3 -c \"open('render.yaml','w')\""):
            with self.subTest(command=command):
                self.assertIsNotNone(self._decide("Bash", command=command))

    def test_running_and_reading_protected_files_is_allowed(self):
        for command in ("python scripts/verify_reality_audit.py > /dev/null 2>&1", "cat render.yaml | grep branch",
                        "git diff --stat render.yaml", "python -m unittest tests.contracts.test_protected_paths",
                        "git commit -m x"):
            with self.subTest(command=command):
                self.assertIsNone(self._decide("Bash", command=command))

    def test_unlock_marker_must_be_in_the_future(self):
        with tempfile.TemporaryDirectory() as tmp:
            marker = Path(tmp) / "protected-unlock"
            with patch.object(self.hook, "UNLOCK_FILE", marker):
                self.assertFalse(self.hook._unlocked())
                marker.write_text(str(time.time() - 5))
                self.assertFalse(self.hook._unlocked())
                marker.write_text(str(time.time() + 600))
                self.assertTrue(self.hook._unlocked())

    def test_hook_is_wired_in_project_settings(self):
        settings = json.loads((ROOT / ".claude" / "settings.json").read_text())
        entries = settings["hooks"]["PreToolUse"]
        commands = [h["command"] for e in entries for h in e["hooks"] if "Bash" in e["matcher"] and "Edit" in e["matcher"]]
        self.assertTrue(any("protect_paths.py" in c for c in commands))


class TestCiCheck(unittest.TestCase):
    """Runs the CI check against a throwaway git repository."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name)
        self._git("init", "-q")
        self._git("config", "user.name", "Rahul Sharma")
        self._git("config", "user.email", "rahul@example.com")
        self._commit({"web/app.py": "a"}, "base")
        self.base = self._git("rev-parse", "HEAD").strip()
        self.root_patch = patch.object(cpp, "ROOT", self.repo)
        self.root_patch.start()

    def tearDown(self):
        self.root_patch.stop()
        self.tmp.cleanup()

    def _git(self, *args):
        return subprocess.run(["git", *args], cwd=self.repo, check=True, capture_output=True, text=True).stdout

    def _commit(self, files, message):
        for name, body in files.items():
            path = self.repo / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(body)
        self._git("add", "-A")
        self._git("commit", "-q", "-m", message)

    def _check(self):
        return cpp.check_range(f"{self.base}..HEAD", cpp.load_patterns())

    def test_unapproved_protected_change_fails(self):
        self._commit({"render.yaml": "x"}, "tweak deploy")
        summary, failures = self._check()
        self.assertEqual(len(failures), 1)
        self.assertIn("render.yaml", failures[0])
        self.assertIn("NOT APPROVED", "".join(summary))

    def test_approved_protected_change_passes_and_is_listed(self):
        self._commit({"tests/contracts/test_a.py": "x"}, "add contract\n\nProtected-Change-Approved: owner in chat 2026-11-15")
        summary, failures = self._check()
        self.assertEqual(failures, [])
        self.assertIn("tests/contracts/test_a.py", "".join(summary))

    def test_ordinary_change_passes_silently(self):
        self._commit({"web/app.py": "b"}, "fix")
        self.assertEqual(self._check(), ([], []))

    def test_unknown_base_checks_head_commit(self):
        self._commit({".github/workflows/ci.yml": "x"}, "ci")
        _, failures = cpp.check_range(f"{'0' * 40}..HEAD", cpp.load_patterns())
        self.assertEqual(len(failures), 1)

    def test_ci_runs_the_check_on_every_push(self):
        ci = (ROOT / ".github/workflows/ci.yml").read_text()
        self.assertIn("scripts/check_protected_paths.py --range", ci)
        self.assertIn("fetch-depth: 0", ci)


if __name__ == "__main__":
    unittest.main()
