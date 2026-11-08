#!/usr/bin/env python3
"""Manifest-driven preflight/apply runner (Guide §7, B01/B02/B10 & P0 Release Gate, LP-01..LP-03).

Clones to an isolated scratch repo so check mode performs zero writes to target.
Supports both isolated SQLite unit runs and disposable PostgreSQL + separate-worker gates;
never certifies `release_gate_ready: true` when only SQLite tests ran.

Critical safeguards in v2:
1. Blocks silent history regression (LP-01): refuses to apply a manifest whose `base_commit`
   lags `HEAD` (`git diff target_tree` against an older base would erase post-base commits).
2. Fixes `--stage` multi-patch selection (LP-03): validates the requested stage name and includes
   all patches up through the final patch of that stage (never breaking after patch #1 of `W1`).
3. Supports `minimum_python` (`>= 3.12`) plus optional `exact_python` (LP-02).
4. Passes `MOATNOMICS_TEST_POSTGRES_DSN` + `MOATNOMICS_PG_TEST_ACK=DISPOSABLE_DATABASE` and
   executes `tests/integration/test_postgres_credit_grant_concurrency.py` when present (LP-03).
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
from urllib.parse import urlsplit

DEFAULT_REPO = Path(__file__).resolve().parents[1]

GIT_ENV_OVERRIDES = (
    "GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE",
    "GIT_COMMON_DIR", "GIT_OBJECT_DIRECTORY", "GIT_ALTERNATE_OBJECT_DIRECTORIES",
)


def clean_git_env(base_env=None):
    env = dict(base_env if base_env is not None else os.environ)
    for k in GIT_ENV_OVERRIDES:
        env.pop(k, None)
    return env


def run(cmd, cwd, env=None):
    return subprocess.run(cmd, cwd=cwd, env=clean_git_env(env), capture_output=True, text=True)


def sha256(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def validate_disposable_pg_url(pg_url: str) -> tuple[bool, str, str]:
    """Ensure the PostgreSQL URL is a valid disposable test database and return a redacted identity."""
    try:
        parts = urlsplit(pg_url)
    except ValueError:
        return False, "", "invalid PostgreSQL URL"
    if parts.scheme not in ("postgresql", "postgres") or not parts.hostname or not parts.path.strip("/"):
        return False, "", "PostgreSQL URL must include scheme, host and database name"
    db_name = parts.path.strip("/")
    if not any(token in db_name.lower() for token in ("test", "staging", "disposable", "ci", "sandbox")):
        return False, "", f"refusing to run destructive fault tests on non-test database '{db_name}'"
    redacted = f"{parts.scheme}://{parts.hostname}:{parts.port or 5432}/{db_name}"
    return True, redacted, ""


def check_version_bounds(
    actual_ver: list[int],
    *,
    minimum_python: str = "3.12",
    exact_python: str = "",
) -> list[str]:
    problems = []
    if minimum_python:
        min_want = [int(x) for x in minimum_python.split(".")]
        if tuple(actual_ver[:len(min_want)]) < tuple(min_want):
            problems.append(f"python {actual_ver} < minimum_python {minimum_python}")
    if exact_python:
        exact_want = [int(x) for x in exact_python.split(".")]
        if tuple(actual_ver[:len(exact_want)]) != tuple(exact_want):
            problems.append(f"python {actual_ver} != exact_python {exact_python}")
    return problems


def verify_python(
    py_bin: str,
    *,
    minimum_python: str = "3.12",
    exact_python: str = "",
    required_imports: list[str] = (),
) -> list[str]:
    problems = []
    code = (
        "import importlib.util, json, sys; "
        f"mods={list(required_imports)!r}; "
        "missing=[m for m in mods if importlib.util.find_spec(m) is None]; "
        "print(json.dumps({'ver': list(sys.version_info[:3]), 'missing': missing}))"
    )
    r = subprocess.run([py_bin, "-c", code], capture_output=True, text=True)
    if r.returncode != 0:
        return [f"interpreter {py_bin} failed: {r.stderr.strip()[:200]}"]
    info = json.loads(r.stdout)
    problems.extend(
        check_version_bounds(info["ver"], minimum_python=minimum_python, exact_python=exact_python)
    )
    if info["missing"]:
        problems.append(f"missing required packages: {info['missing']}")
    return problems


def select_manifest_patches(patches: list[dict], stage: str = "all") -> tuple[list[dict], list[str]]:
    """Order patches deterministically, validate `requires`, and include ALL patches up to the
    LAST patch matching `stage` (preventing early break on multi-patch stages such as W1).
    """
    ordered = sorted(patches, key=lambda p: p["order"])
    problems: list[str] = []
    seen: set[str] = set()
    for p in ordered:
        for req in p.get("requires", ()):
            if req not in seen:
                problems.append(f"{p['file']} requires {req} earlier in order")
        seen.add(p["file"])

    if stage == "all" or not ordered:
        return ordered, problems

    matching_indices = [idx for idx, p in enumerate(ordered) if p.get("stage") == stage]
    if not matching_indices:
        known = sorted({str(p.get("stage", "")) for p in ordered if p.get("stage")})
        problems.append(f"unknown stage {stage!r}; available stages: {known}")
        return [], problems

    cutoff = max(matching_indices)
    return ordered[: cutoff + 1], problems


def validate_base_commit_alignment(
    head: str,
    base_commit: str,
    *,
    is_ancestor: bool,
    has_patches: bool = True,
) -> list[str]:
    """Refuse to diff an older `base_commit` over an advanced `HEAD` when applying patches."""
    if head == base_commit:
        return []
    if is_ancestor:
        if not has_patches:
            return []
        return [
            f"HEAD {head[:12]} has advanced past manifest base_commit {base_commit[:12]}; "
            "regenerate patches/manifest on current HEAD before running preflight/apply so "
            "commits after base_commit are never reverted"
        ]
    return [f"HEAD {head[:12]} does not match or descend from base {base_commit[:12]}"]


def parse_pytest_counts(output: str) -> dict:
    def _num(pat):
        m = re.search(pat, output)
        return int(m.group(1)) if m else 0
    return {
        "passed": _num(r"(\d+)\s+passed"),
        "failed": _num(r"(\d+)\s+failed"),
        "errors": _num(r"(\d+)\s+errors?"),
        "skipped": _num(r"(\d+)\s+skipped"),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--checkout", default=str(DEFAULT_REPO), help="Target git checkout root.")
    ap.add_argument("--manifest", default="", help="JSON release manifest (defaults to <checkout>/release_manifest.json).")
    ap.add_argument("--patch-root", default="", help="Directory containing patch files (defaults to <checkout>).")
    ap.add_argument("--python", default=sys.executable, help="Explicit Python interpreter.")
    ap.add_argument("--strict-python", action="store_true", help="Enforce exact_python / required_python equality.")
    ap.add_argument("--stage", default="all", help="Filter up to stage name or 'all'.")
    ap.add_argument("--run-tests", action="store_true", help="Run isolated SQLite tests + AST audit.")
    ap.add_argument("--pg-test-url", default="", help="Disposable PostgreSQL URL for concurrency + worker gates.")
    ap.add_argument("--require-release-gate", action="store_true", help="Fail unless PostgreSQL + worker gates pass.")
    ap.add_argument("--allow-dirty-check", action="store_true", help="Allow check mode against committed HEAD even if working tree has local edits (never allowed with --apply).")
    ap.add_argument("--apply", action="store_true", help="Apply verified net diff to target checkout.")
    a = ap.parse_args()
    if os.path.sep in a.python or Path(a.python).exists():
        a.python = os.path.abspath(a.python)

    repo = Path(a.checkout).resolve()
    manifest_path = Path(a.manifest).resolve() if a.manifest else (repo / "release_manifest.json")
    root = Path(a.patch_root).resolve() if a.patch_root else repo
    m = json.loads(manifest_path.read_text(encoding="utf-8"))
    problems = []
    report = {
        "release_id": m["release_id"],
        "mode": "apply" if a.apply else "check",
        "selected_stage": a.stage,
        "sqlite_passed": False,
        "postgres_passed": False,
        "worker_reconcile_passed": False,
        "release_gate_ready": False,
    }

    min_py = m.get("minimum_python") or m.get("required_python", "3.12")
    exact_py = (m.get("exact_python") or m.get("required_python", "")) if a.strict_python else m.get("exact_python", "")
    problems.extend(
        verify_python(
            a.python,
            minimum_python=min_py,
            exact_python=exact_py,
            required_imports=m.get("required_imports", []),
        )
    )

    if a.pg_test_url:
        ok_pg, pg_redacted, pg_err = validate_disposable_pg_url(a.pg_test_url)
        if not ok_pg:
            problems.append(pg_err)
        else:
            report["postgres_target"] = pg_redacted
    elif a.require_release_gate:
        problems.append("--require-release-gate requires --pg-test-url (SQLite-only runs cannot certify release readiness)")

    top = run(["git", "rev-parse", "--show-toplevel"], repo).stdout.strip()
    if not top or Path(top).resolve() != repo:
        return finish(report, [*problems, "checkout is not a git top-level root"])

    status_pre = run(["git", "--no-optional-locks", "status", "--porcelain", "--untracked-files=normal"], repo).stdout.strip()
    report["working_tree_dirty"] = bool(status_pre)
    if status_pre and (a.apply or not a.allow_dirty_check):
        problems.append("target checkout has uncommitted or untracked files")
    head = run(["git", "rev-parse", "HEAD"], repo).stdout.strip()
    branch = run(["git", "rev-parse", "--abbrev-ref", "HEAD"], repo).stdout.strip()
    target_tree = run(["git", "rev-parse", f"{head}^{{tree}}"], repo).stdout.strip()
    report.update(head=head, branch=branch, target_tree=target_tree)

    selected_patches, stage_problems = select_manifest_patches(m.get("patches", []), a.stage)
    problems.extend(stage_problems)

    anc = run(["git", "merge-base", "--is-ancestor", m["base_commit"], head], repo)
    problems.extend(
        validate_base_commit_alignment(
            head,
            m["base_commit"],
            is_ancestor=(anc.returncode == 0),
            has_patches=bool(selected_patches),
        )
    )
    if branch != m["expected_branch"]:
        problems.append(f"branch {branch} != expected {m['expected_branch']}")

    for p in selected_patches:
        f = root / p["file"]
        if not f.is_file():
            problems.append(f"missing patch: {p['file']}")
        elif sha256(f) != p["sha256"]:
            problems.append(f"sha256 mismatch: {p['file']}")
    if problems:
        return finish(report, problems)

    tmp = Path(tempfile.mkdtemp(prefix="moat-preflight-"))
    scratch = tmp / "repo"
    try:
        r_clone = run(["git", "clone", "--quiet", "--no-checkout", "--no-hardlinks", "--", str(repo), str(scratch)], tmp)
        if r_clone.returncode != 0:
            return finish(report, [f"scratch clone failed: {r_clone.stderr.strip()}"])
        checkout_ref = m["base_commit"] if selected_patches else head
        run(["git", "-c", "core.hooksPath=/dev/null", "checkout", "--quiet", "--detach", checkout_ref], scratch)

        applied = []
        for p in selected_patches:
            patch_path = root / p["file"]
            r_app = run(["git", "apply", "--index", "--whitespace=error", str(patch_path)], scratch)
            if r_app.returncode != 0:
                return finish(report, [f"apply failed ({p['file']}): {r_app.stderr.strip()[:300]}"])
            applied.append({"file": p["file"], "sha256": p["sha256"]})

        net_patch = tmp / "verified-net.patch"
        if selected_patches:
            chk = run(["git", "diff", "--cached", "--check", m["base_commit"]], scratch)
            if chk.returncode != 0:
                return finish(report, [f"git diff --check failed: {chk.stdout.strip()[:200]}"])

            output_tree = run(["git", "write-tree"], scratch).stdout.strip()
            net_diff = subprocess.run(
                ["git", "diff", "--cached", "--binary", target_tree],
                cwd=scratch, env=clean_git_env(), capture_output=True,
            ).stdout
            net_patch.write_bytes(net_diff)
            report.update(applied_patches=applied, output_tree_hash=output_tree, net_patch_bytes=len(net_diff))

            if not net_diff:
                return finish(report, ["selected manifest produced an empty diff against target tree"])

            r_check = run(["git", "apply", "--check", "--whitespace=error", str(net_patch)], repo)
            if r_check.returncode != 0:
                return finish(report, [f"target preflight apply --check failed: {r_check.stderr.strip()[:300]}"])
        else:
            report.update(applied_patches=[], output_tree_hash=target_tree, net_patch_bytes=0)
            if a.apply:
                return finish(report, ["--apply requested on baseline verification manifest with zero patches"])

        if a.run_tests or a.pg_test_url:
            test_home, test_tmp = tmp / "home", tmp / "tmp"
            test_home.mkdir()
            test_tmp.mkdir()
            base_test_env = {
                "PATH": "/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin",
                "HOME": str(test_home),
                "TMPDIR": str(test_tmp),
                "PYTHONPATH": str(scratch),
                "TESTING": "1",
                "SKIP_DOTENV_IN_SUBPROCESS": "1",
                "ENABLE_BACKGROUND_SCHEDULERS": "0",
                "ENABLE_DURABLE_FUND_AUDITS": "0",
                "ADMIN_PASSWORD": "test_admin_pwd_default",
            }
            sqlite_env = {
                **base_test_env,
                "FORCE_LOCAL_SQLITE": "1",
                "TEST_DB_PATH": str(test_tmp / "tests.db"),
            }
            existing_tests = [
                arg for arg in m["test_command"]
                if not arg.startswith("tests/") or (scratch / arg).exists()
            ]
            t_res = subprocess.run([a.python, *existing_tests], cwd=scratch, env=sqlite_env, capture_output=True, text=True)
            counts = parse_pytest_counts(t_res.stdout + "\n" + t_res.stderr)
            report["sqlite_tests"] = {
                "rc": t_res.returncode,
                "selected": [x for x in existing_tests if x.startswith("tests/")],
                **counts,
            }
            if t_res.returncode != 0 or counts["passed"] == 0 or counts["failed"] > 0 or counts["errors"] > 0:
                return finish(report, ["isolated SQLite test suite failed or ran zero tests"])

            audit_script = scratch / "scripts" / "verify_reality_audit.py"
            if audit_script.is_file():
                a_env = {**sqlite_env, "TEST_DB_PATH": str(test_tmp / "audit.db")}
                a_res = subprocess.run([a.python, str(audit_script)], cwd=scratch, env=a_env, capture_output=True, text=True)
                report["reality_audit_rc"] = a_res.returncode
                if a_res.returncode != 0:
                    return finish(report, ["verify_reality_audit.py failed"])
            report["sqlite_passed"] = True

            if a.pg_test_url:
                pg_env = {
                    **base_test_env,
                    "FORCE_LOCAL_SQLITE": "0",
                    "SUPABASE_DB_URL": a.pg_test_url,
                    "MOATNOMICS_TEST_POSTGRES_DSN": a.pg_test_url,
                    "MOATNOMICS_PG_TEST_ACK": "DISPOSABLE_DATABASE",
                    "ENABLE_DURABLE_FUND_AUDITS": "1",
                }
                candidate_pg_suites = [
                    "tests/unit/test_p0_credit_and_db_containment.py",
                    "tests/integration/test_postgres_credit_grant_concurrency.py",
                    "tests/unit/test_release_fund_audit.py",
                ]
                active_pg_suites = [s for s in candidate_pg_suites if (scratch / s).is_file()]
                pg_cmd = [a.python, "-m", "pytest", "-q", *active_pg_suites]
                pg_res = subprocess.run(pg_cmd, cwd=scratch, env=pg_env, capture_output=True, text=True)
                pg_counts = parse_pytest_counts(pg_res.stdout + "\n" + pg_res.stderr)
                report["postgres_tests"] = {"rc": pg_res.returncode, "selected": active_pg_suites, **pg_counts}
                if pg_res.returncode != 0 or pg_counts["passed"] == 0 or pg_counts["failed"] > 0 or pg_counts["errors"] > 0:
                    return finish(report, ["disposable PostgreSQL concurrency/fault suite failed"])
                report["postgres_passed"] = True

                worker_script = scratch / "scripts" / "run_paid_fund_audit_worker.py"
                if worker_script.is_file():
                    w_res = subprocess.run(
                        [a.python, "-m", "scripts.run_paid_fund_audit_worker", "--reconcile-only"],
                        cwd=scratch, env=pg_env, capture_output=True, text=True,
                    )
                    report["worker_reconcile_rc"] = w_res.returncode
                    if w_res.returncode != 0:
                        return finish(report, [f"separate worker --reconcile-only failed on PostgreSQL: {w_res.stderr.strip()[:200]}"])
                    report["worker_reconcile_passed"] = True
                    report["release_gate_ready"] = True
                elif a.require_release_gate:
                    return finish(report, ["scripts/run_paid_fund_audit_worker.py not yet present in checkout; release gate incomplete"])

        if a.apply:
            head_now = run(["git", "rev-parse", "HEAD"], repo).stdout.strip()
            status_now = run(["git", "--no-optional-locks", "status", "--porcelain", "--untracked-files=normal"], repo).stdout.strip()
            if head_now != head or status_now:
                return finish(report, ["target checkout changed during verification; aborting apply"])
            r_apply = run(["git", "apply", "--whitespace=error", str(net_patch)], repo)
            if r_apply.returncode != 0:
                return finish(report, [f"apply failed: {r_apply.stderr.strip()[:300]}"])
            report["applied_to_target"] = True
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    return finish(report, problems)


def finish(report, problems):
    report["problems"] = problems
    report["ok"] = not problems
    print(json.dumps(report, indent=2))
    return 0 if not problems else 1


if __name__ == "__main__":
    sys.exit(main())

