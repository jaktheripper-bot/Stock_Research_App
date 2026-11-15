"""Checks changes to protected files (the tests, gates and config that judge the agents' work).

The list lives in `ci/protected_paths.txt`. Two callers:

- CI: `python scripts/check_protected_paths.py --range <base>..<head>` fails when a commit in the
  range changes a protected file without the `Protected-Change-Approved:` trailer, and writes a
  summary of every protected change it saw (approved or not) for the owner to review.
- The Claude Code hook imports `is_protected()` so both enforcement points share one list.

This is a guard against an agent quietly changing what judges it. It cannot stop a determined
bypass on its own; its job is to make every such change visible and attributable.
"""

from __future__ import annotations

import argparse
import fnmatch
import os
import subprocess
import sys
from pathlib import Path
from typing import Iterable, List, Tuple

ROOT = Path(__file__).resolve().parent.parent
LIST_FILE = ROOT / "ci" / "protected_paths.txt"
APPROVAL_TRAILER = "Protected-Change-Approved:"
EMPTY_SHA = "0" * 40


def load_patterns(list_file: Path = LIST_FILE) -> List[str]:
    patterns = []
    for line in list_file.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            patterns.append(line)
    return patterns


def _normalise(path: str) -> str:
    """Repo-relative POSIX path for `path`, or "" when it lies outside the repository."""
    candidate = Path(path)
    if candidate.is_absolute():
        try:
            candidate = candidate.resolve().relative_to(ROOT.resolve())
        except ValueError:
            return ""
    text = candidate.as_posix()
    while text.startswith("./"):
        text = text[2:]
    return text


def _matches(path: str, pattern: str) -> bool:
    if pattern.endswith("/**"):
        prefix = pattern[:-3]
        return path == prefix or path.startswith(prefix + "/")
    return fnmatch.fnmatchcase(path, pattern)


def is_protected(path: str, patterns: Iterable[str] | None = None) -> bool:
    rel = _normalise(path)
    if not rel:
        return False
    return any(_matches(rel, p) for p in (patterns if patterns is not None else load_patterns()))


def _git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, check=True, capture_output=True, text=True).stdout


def commits_in_range(rev_range: str) -> List[str]:
    base, _, head = rev_range.partition("..")
    known_base = bool(base) and base != EMPTY_SHA and subprocess.run(
        ["git", "cat-file", "-e", f"{base}^{{commit}}"], cwd=ROOT, capture_output=True
    ).returncode == 0
    if not known_base:
        # New branch, force-push, or shallow history: check the head commit only.
        return [_git("rev-parse", head or "HEAD").strip()]
    return [c for c in _git("rev-list", "--reverse", rev_range).split() if c]


def changed_files(commit: str) -> List[str]:
    out = _git("diff-tree", "--no-commit-id", "--name-only", "-r", "--root", commit)
    return [line for line in out.splitlines() if line]


def commit_message(commit: str) -> str:
    return _git("log", "-1", "--format=%B", commit)


def check_range(rev_range: str, patterns: List[str]) -> Tuple[List[str], List[str]]:
    """Returns (summary lines, failure lines) for every commit in `rev_range`."""
    summary, failures = [], []
    for commit in commits_in_range(rev_range):
        touched = [f for f in changed_files(commit) if is_protected(f, patterns)]
        if not touched:
            continue
        message = commit_message(commit)
        approval = next((l.strip() for l in message.splitlines() if l.strip().startswith(APPROVAL_TRAILER)), "")
        subject = message.splitlines()[0] if message else ""
        status = approval or "NOT APPROVED"
        summary.append(f"- `{commit[:7]}` {subject}\n  - {status}\n" + "".join(f"  - `{f}`\n" for f in touched))
        if not approval:
            failures.append(f"{commit[:7]} changes protected files without '{APPROVAL_TRAILER}': {', '.join(touched)}")
    return summary, failures


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--range", required=True, help="git revision range, e.g. <before>..<after>")
    args = parser.parse_args(argv)

    patterns = load_patterns()
    summary, failures = check_range(args.range, patterns)

    report = "## Protected files\n\n" + ("".join(summary) if summary else "No protected files changed.\n")
    print(report)
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_path:
        with open(summary_path, "a", encoding="utf-8") as fh:
            fh.write(report + "\n")
    for failure in failures:
        print(f"::error::{failure}")
    if failures:
        print(
            "\nProtected files decide whether the agents' work passes. Changing them needs the owner's "
            f"approval, recorded as a '{APPROVAL_TRAILER} <who, where, date>' line in the commit message."
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
