"""Claude Code PreToolUse hook: agents may not change the files that judge their work.

The protected list is `ci/protected_paths.txt` (shared with the CI check). An edit is allowed only
while the owner has unlocked it from their own terminal with `./run.sh unlock-protected <minutes>`;
that writes `.claude/protected-unlock`, which no agent tool call may create, change or delete.

Bash commands are checked heuristically: a command is refused when it names a protected file and
also writes (a redirect into it, sed -i, tee, rm, mv, cp, git checkout/restore, write_text ...).
Running a protected script or test is allowed. CI is the backstop for anything this misses.
"""
import json
import os
import re
import sys
import time
from pathlib import Path

ROOT = Path(os.environ.get("CLAUDE_PROJECT_DIR") or Path(__file__).resolve().parents[2])
sys.path.insert(0, str(ROOT / "scripts"))

UNLOCK_FILE = ROOT / ".claude" / "protected-unlock"
UNLOCK_NAMES = ("protected-unlock", "unlock-protected")
WRITE_HINTS = re.compile(
    r"\btee\b|\bsed\b[^|;&]*\s-i|\bperl\b[^|;&]*\s-i|\brm\b|\bmv\b|\bcp\b|\btruncate\b|\bchmod\b|"
    r"\bln\b|\bdd\b|\bpatch\b|\bgit\s+(?:checkout|restore|rm|mv|apply|am|stash|reset|clean)\b|"
    r"write_text|write_bytes|\.write\(|open\([^)]*['\"][wax+]"
)
REDIRECT = re.compile(r"(?<![0-9&])>>?\s*(['\"]?)([^\s;&|'\"]+)\1")

ASK_OWNER = (
    "Protected files (ci/protected_paths.txt) decide whether agent work passes, so agents may not "
    "change them on their own. Explain in chat exactly what you want to change and why, and wait. "
    "If the owner agrees, they run `./run.sh unlock-protected 30` in their own terminal; then retry, "
    "and add 'Protected-Change-Approved: <who, where, date>' to the commit message."
)
SELF_UNLOCK = "Only the owner may unlock protected files, from their own terminal."


def _unlocked() -> bool:
    try:
        return float(UNLOCK_FILE.read_text().strip()) > time.time()
    except (OSError, ValueError):
        return False


def _deny(reason: str) -> None:
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }
    }))
    sys.exit(0)


def _protected_literals(patterns):
    """The fixed text of each pattern, for spotting protected paths inside shell commands."""
    out = []
    for p in patterns:
        literal = p[:-3] + "/" if p.endswith("/**") else p
        literal = re.split(r"[*?\[]", literal)[0]
        if literal:
            out.append(literal)
    return out


def decide(payload: dict, patterns, unlocked: bool):
    """Returns a denial reason, or None to allow."""
    from check_protected_paths import is_protected

    tool = payload.get("tool_name", "")
    tool_input = payload.get("tool_input") or {}

    if tool in ("Edit", "Write", "NotebookEdit", "MultiEdit"):
        path = tool_input.get("file_path") or tool_input.get("notebook_path") or ""
        if Path(path).name == UNLOCK_FILE.name:
            return SELF_UNLOCK
        if not unlocked and is_protected(path, patterns):
            return ASK_OWNER
        return None

    if tool == "Bash":
        command = tool_input.get("command") or ""
        if any(name in command for name in UNLOCK_NAMES):
            return SELF_UNLOCK
        if unlocked:
            return None
        for match in REDIRECT.finditer(command):
            if is_protected(match.group(2), patterns):
                return ASK_OWNER
        if WRITE_HINTS.search(command) and any(lit in command for lit in _protected_literals(patterns)):
            return ASK_OWNER
    return None


def main() -> None:
    from check_protected_paths import load_patterns

    reason = decide(json.load(sys.stdin), load_patterns(), _unlocked())
    if reason:
        _deny(reason)


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception as err:  # A broken hook must say so loudly rather than quietly allow edits.
        print(f"protect_paths hook error: {err}", file=sys.stderr)
        sys.exit(2)
