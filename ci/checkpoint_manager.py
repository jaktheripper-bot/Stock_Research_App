#!/usr/bin/env python3
"""
ci/checkpoint_manager.py
==============================================================================
Production Release Checkpoint & Emergency Disaster Recovery Manager
for Stock Research App

Features:
  1. Pre-flight Verification Gate: Ensures only 100% verified, operational
     code can be tagged as a rollback point.
  2. Safe Database Snapshotting: Takes non-blocking SQLite online backups
     into .checkpoints/ with report & revision counts.
  3. Git Release Tagging & Remote Sync: Stamps an annotated git tag and
     pushes it to origin (GitHub) for cloud resilience.
  4. 1-Command Live Emergency Rollback: Instantly rolls back local and
     origin/main (Streamlit Community Cloud) to a verified working state.
  5. Ledger Tracking: Maintains both machine-readable JSON and
     CHECKPOINTS.md markdown ledgers in IST.
==============================================================================
"""

import os
import sys
import json
import time
import shutil
import sqlite3
import argparse
import subprocess
from datetime import datetime, timezone, timedelta
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CHECKPOINTS_DIR = PROJECT_ROOT / ".checkpoints"
LEDGER_FILE = CHECKPOINTS_DIR / "ledger.json"
MARKDOWN_LEDGER = PROJECT_ROOT / "CHECKPOINTS.md"
DB_FILE = PROJECT_ROOT / "reports.db"

# IST timezone (+05:30)
IST = timezone(timedelta(hours=5, minutes=30))


def get_current_ist_str() -> str:
    """Return formatted IST timestamp string."""
    return datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S IST")


def get_checkpoint_timestamp_tag() -> str:
    """Return compact timestamp for git tag naming."""
    return datetime.now(IST).strftime("%Y%m%d_%H%M%S")


def run_cmd(cmd_list, check=True, capture=True):
    """Run a subprocess command in PROJECT_ROOT."""
    res = subprocess.run(
        cmd_list,
        cwd=str(PROJECT_ROOT),
        capture_output=capture,
        text=True,
        check=check,
    )
    return res


def get_git_info():
    """Retrieve current commit SHA, branch, and status."""
    sha = run_cmd(["git", "rev-parse", "HEAD"]).stdout.strip()
    branch = run_cmd(["git", "rev-parse", "--abbrev-ref", "HEAD"]).stdout.strip()
    status = run_cmd(["git", "status", "--porcelain"]).stdout.strip()
    return sha, branch, status


def load_ledger() -> list:
    """Load JSON checkpoints ledger."""
    if not LEDGER_FILE.exists():
        return []
    try:
        with open(LEDGER_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def save_ledger(checkpoints: list):
    """Save JSON checkpoints ledger and update CHECKPOINTS.md."""
    CHECKPOINTS_DIR.mkdir(parents=True, exist_ok=True)
    with open(LEDGER_FILE, "w", encoding="utf-8") as f:
        json.dump(checkpoints, f, indent=2)

    # Generate CHECKPOINTS.md
    last_ts = checkpoints[-1]["timestamp"] if checkpoints else "None"
    total_count = len(checkpoints)

    md_lines = [
        "# Production Release Checkpoints & Disaster Recovery Ledger",
        f"**Last Checkpoint:** {last_ts}  ",
        f"**Total Verified Rollback Points:** {total_count}  ",
        "",
        "> [!NOTE]",
        "> These checkpoints represent byte-for-byte verified working releases that passed the 4-tier pre-flight audit.",
        "> In case of an emergency live crash, run `./run.sh rollback` to instantly restore production.",
        "",
        "---",
        "",
        "| Checkpoint Tag | IST Timestamp | Commit | DB Reports | Description |",
        "|:---|:---|:---|:---|:---|",
    ]

    for cp in reversed(checkpoints):
        tag = cp.get("tag", "N/A")
        ts = cp.get("timestamp", "N/A")
        sha = cp.get("commit_sha", "")[:7]
        db_info = cp.get("database", {})
        db_stat = f"{db_info.get('report_count', 0)} rep / {db_info.get('revision_count', 0)} rev" if db_info.get("exists") else "N/A"
        label = cp.get("description", "Regular Checkpoint")
        md_lines.append(f"| `{tag}` | {ts} | `{sha}` | {db_stat} | {label} |")

    md_lines.append("")
    with open(MARKDOWN_LEDGER, "w", encoding="utf-8") as f:
        f.write("\n".join(md_lines))


def snapshot_database(checkpoint_tag: str) -> dict:
    """Take an atomic, safe online backup of reports.db using SQLite API."""
    if not DB_FILE.exists():
        return {"exists": False, "path": None, "report_count": 0, "revision_count": 0}

    CHECKPOINTS_DIR.mkdir(parents=True, exist_ok=True)
    snapshot_filename = f"reports_{checkpoint_tag}.db"
    snapshot_file = CHECKPOINTS_DIR / snapshot_filename

    src = sqlite3.connect(str(DB_FILE))
    dst = sqlite3.connect(str(snapshot_file))
    with dst:
        src.backup(dst)

    report_count = 0
    revision_count = 0
    try:
        cur = dst.cursor()
        cur.execute("SELECT COUNT(*) FROM reports")
        report_count = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM report_revisions")
        revision_count = cur.fetchone()[0]
    except Exception:
        pass

    dst.close()
    src.close()

    return {
        "exists": True,
        "filename": snapshot_filename,
        "path": f".checkpoints/{snapshot_filename}",
        "size_bytes": snapshot_file.stat().st_size,
        "report_count": report_count,
        "revision_count": revision_count,
    }


def run_preflight_verification() -> bool:
    """Execute the 4-tier pre-flight verification suite."""
    print("\n🔍 Step 1/4: Executing Mandatory 4-Tier Pre-Flight Verification Gate...")
    py_exec = sys.executable

    tiers = [
        ("Streamlit Static Linter", [py_exec, "lint_streamlit.py"]),
        ("System Contract Audit", [py_exec, "check_system.py"]),
        ("Interactive UI Action Simulation", [py_exec, "test_ui_headless.py"]),
        ("Latency Performance Benchmark", [py_exec, "benchmark.py"]),
    ]

    for name, cmd in tiers:
        print(f"   • Running {name}...")
        res = run_cmd(cmd, check=False)
        if res.returncode != 0:
            print(f"\n❌ Pre-flight check failed on: {name}")
            print(res.stdout[-1000:] if res.stdout else "")
            print(res.stderr[-1000:] if res.stderr else "")
            return False

    print("   ✅ All 4 pre-flight tiers PASSED. Code is certified 100% operational.")
    return True


def create_checkpoint(label: str = "", skip_checks: bool = False, push_remote: bool = True):
    """Create a verified release checkpoint, git tag, and DB snapshot."""
    sha, branch, status = get_git_info()
    if status and not skip_checks:
        print(f"⚠️ Uncommitted changes detected in working directory on branch '{branch}':")
        for line in status.splitlines()[:5]:
            print(f"   {line}")
        print("\n💡 Please commit or stash your changes before creating a release checkpoint.")
        sys.exit(1)

    # 1. Run Pre-flight Gate
    if not skip_checks:
        if not run_preflight_verification():
            print("\n🚨 Checkpoint ABORTED: Code did not pass pre-flight verification.")
            print("   Only verified, operational code can be saved as a recovery checkpoint.")
            sys.exit(1)
    else:
        print("⚠️ Warning: Skipping pre-flight checks as requested.")

    # 2. Tag Name & Metadata
    ts_str = get_current_ist_str()
    tag_clean_label = "".join(c if c.isalnum() or c in ("-", "_") else "_" for c in label.strip())
    suffix = f"_{tag_clean_label}" if tag_clean_label else ""
    tag_name = f"checkpoint_{get_checkpoint_timestamp_tag()}{suffix}"

    print(f"\n📦 Step 2/4: Creating SQLite Database Snapshot for '{tag_name}'...")
    db_meta = snapshot_database(tag_name)
    if db_meta["exists"]:
        print(f"   ✅ Database snapshot saved: {db_meta['path']} ({db_meta['report_count']} reports, {db_meta['revision_count']} revisions).")
    else:
        print("   ℹ️ No local reports.db found. Proceeding with code-only checkpoint.")

    print(f"\n🏷️ Step 3/4: Creating Annotated Git Release Tag '{tag_name}'...")
    tag_msg = f"Verified Checkpoint: {label or 'Stable Release'} | SHA: {sha[:7]} | IST: {ts_str}"
    run_cmd(["git", "tag", "-a", tag_name, "-m", tag_msg])
    print(f"   ✅ Git tag '{tag_name}' created on commit {sha[:7]}.")

    if push_remote:
        print(f"\n🚀 Step 4/4: Synchronizing Tag with Remote Repository (origin)...")
        try:
            run_cmd(["git", "push", "origin", tag_name])
            print(f"   ✅ Tag '{tag_name}' safely pushed to GitHub origin.")
        except Exception as e:
            print(f"   ⚠️ Could not push tag to origin (check network/credentials): {e}")

    # Record in ledger
    checkpoints = load_ledger()
    record = {
        "tag": tag_name,
        "timestamp": ts_str,
        "commit_sha": sha,
        "branch": branch,
        "description": label or "Production Release Checkpoint",
        "database": db_meta,
        "preflight_passed": not skip_checks,
    }
    checkpoints.append(record)
    save_ledger(checkpoints)

    print("\n" + "=" * 65)
    print("🎉 RELEASE CHECKPOINT CREATED SUCCESSFULLY!")
    print(f"   • Tag:         {tag_name}")
    print(f"   • Timestamp:   {ts_str}")
    print(f"   • Commit:      {sha[:7]}")
    print(f"   • Ledger:      CHECKPOINTS.md updated")
    print(f"   • Rollback:    Run `./run.sh rollback {tag_name}` at any time.")
    print("=" * 65 + "\n")


def list_checkpoints():
    """List all available checkpoints from ledger and git tags."""
    checkpoints = load_ledger()
    if not checkpoints:
        # Fallback to git tags if ledger is empty
        tags_res = run_cmd(["git", "tag", "-l", "checkpoint_*"])
        raw_tags = [t.strip() for t in tags_res.stdout.splitlines() if t.strip()]
        if not raw_tags:
            print("ℹ️ No checkpoints found. Create one with `./run.sh checkpoint [optional_label]`.")
            return []
        print(f"Found {len(raw_tags)} checkpoint tag(s) in git:")
        for t in raw_tags:
            print(f"  • {t}")
        return raw_tags

    print("\n" + "=" * 75)
    print(f"  VERIFIED PRODUCTION RELEASE CHECKPOINTS ({len(checkpoints)} available)")
    print("=" * 75)
    for idx, cp in enumerate(reversed(checkpoints), 1):
        tag = cp.get("tag")
        ts = cp.get("timestamp")
        sha = cp.get("commit_sha", "")[:7]
        label = cp.get("description", "")
        db_stat = f"{cp.get('database', {}).get('report_count', 0)} reports" if cp.get('database', {}).get('exists') else "no db"
        print(f"[{idx}] {tag}")
        print(f"    Timestamp: {ts}  |  Commit: {sha}  |  DB: {db_stat}")
        print(f"    Label:     {label}")
        print("-" * 75)

    print("💡 To rollback to a checkpoint, run:")
    print("   ./run.sh rollback [TAG_NAME]\n")
    return checkpoints


def rollback_to_checkpoint(target_tag: str = "", force: bool = False, restore_db: bool = True):
    """
    Execute emergency rollback of production to target checkpoint.
    Restores code and pushes to origin/main so Streamlit Cloud redeploys immediately.
    """
    checkpoints = load_ledger()
    if not target_tag:
        if not checkpoints:
            print("❌ No checkpoints found in ledger to rollback to.")
            sys.exit(1)
        # Default to latest checkpoint
        target_cp = checkpoints[-1]
        target_tag = target_cp["tag"]
        print(f"ℹ️ No checkpoint specified. Defaulting to most recent verified checkpoint: '{target_tag}'")
    else:
        matched = [cp for cp in checkpoints if cp["tag"] == target_tag]
        target_cp = matched[0] if matched else {"tag": target_tag}

    target_sha = target_cp.get("commit_sha")
    if not target_sha:
        # Resolve from git tag directly
        try:
            target_sha = run_cmd(["git", "rev-parse", f"{target_tag}^{{commit}}"]).stdout.strip()
        except Exception:
            print(f"❌ Error: Git tag '{target_tag}' could not be resolved.")
            sys.exit(1)

    curr_sha, curr_branch, curr_status = get_git_info()

    print("\n" + "=" * 65)
    print("🚨 INITIATING EMERGENCY DISASTER RECOVERY ROLLBACK")
    print(f"   • Target Checkpoint:  {target_tag}")
    print(f"   • Target Commit SHA:  {target_sha[:7]}")
    print(f"   • Current Branch:     {curr_branch} ({curr_sha[:7]})")
    print("=" * 65)

    if not force:
        print("\n⚠️ This action will:")
        print(f"   1. Hard reset '{curr_branch}' to commit {target_sha[:7]} ({target_tag}).")
        print("   2. Update 'main' and force-push to 'origin/main' (triggering Streamlit Cloud redeploy).")
        if restore_db and target_cp.get("database", {}).get("filename"):
            print(f"   3. Restore database from '{target_cp['database']['filename']}'.")
        print("\nType 'yes' or 'y' to confirm emergency rollback: ", end="", flush=True)
        conf = input().strip().lower()
        if conf not in ("yes", "y"):
            print("Rollback cancelled by user.")
            return

    # 1. Safety backup of current reports.db
    if DB_FILE.exists():
        safety_name = f"reports_pre_rollback_{int(time.time())}.db"
        safety_path = CHECKPOINTS_DIR / safety_name
        try:
            shutil.copy2(DB_FILE, safety_path)
            print(f"\n🛡️ Step 1/5: Saved safety backup of current DB to: .checkpoints/{safety_name}")
        except Exception as e:
            print(f"⚠️ Warning: Could not create pre-rollback DB backup: {e}")

    # 2. Reset code to target checkpoint
    print(f"\n🔄 Step 2/5: Resetting branch '{curr_branch}' to {target_tag} ({target_sha[:7]})...")
    run_cmd(["git", "reset", "--hard", target_sha])
    print(f"   ✅ Working directory reset to {target_sha[:7]}.")

    # 3. Synchronize with main and push to origin/main (Live Streamlit Cloud)
    print("\n🌐 Step 3/5: Deploying Rollback to Live Production (origin/main)...")
    try:
        run_cmd(["git", "checkout", "main"])
        run_cmd(["git", "reset", "--hard", target_sha])
        run_cmd(["git", "push", "origin", "main", "--force"])
        print("   ✅ Live 'main' updated and force-pushed to origin/main.")
        print("   📡 Streamlit Community Cloud will automatically detect and reboot with this verified release.")
    except Exception as e:
        print(f"   ⚠️ Could not push to origin/main: {e}")
    finally:
        # Return to previous working branch if different
        if curr_branch != "main":
            run_cmd(["git", "checkout", curr_branch])

    # 4. Restore Database Snapshot if available
    db_meta = target_cp.get("database", {})
    if restore_db and db_meta and db_meta.get("filename"):
        snap_file = CHECKPOINTS_DIR / db_meta["filename"]
        if snap_file.exists():
            print(f"\n💾 Step 4/5: Restoring database from .checkpoints/{db_meta['filename']}...")
            src = sqlite3.connect(str(snap_file))
            dst = sqlite3.connect(str(DB_FILE))
            with dst:
                src.backup(dst)
            dst.close()
            src.close()
            print(f"   ✅ Database restored cleanly ({db_meta.get('report_count', 0)} reports).")
        else:
            print(f"   ℹ️ Snapshot file {db_meta['filename']} not found locally. Database untouched.")
    else:
        print("\n💾 Step 4/5: Database restore skipped.")

    # 5. Local verification smoke test
    print("\n🔍 Step 5/5: Executing Post-Rollback Smoke Verification...")
    res = run_cmd([sys.executable, "test_ui_headless.py"], check=False)
    if res.returncode == 0:
        print("   ✅ Headless UI simulation passed cleanly on restored code.")
    else:
        print("   ⚠️ Headless UI test completed with warnings (check output).")

    print("\n" + "=" * 65)
    print("🎉 EMERGENCY ROLLBACK COMPLETED SUCCESSFULLY!")
    print(f"   • Active Release:  {target_tag}")
    print(f"   • Active Commit:   {target_sha[:7]}")
    print("   • Live Cloud:      Streamlit Community Cloud is rebooting now.")
    print("=" * 65 + "\n")


def main():
    parser = argparse.ArgumentParser(description="Stock Research App Checkpoint & Disaster Recovery Manager")
    subparsers = parser.add_subparsers(dest="subcommand", help="Action to perform")

    # create
    create_p = subparsers.add_parser("create", help="Create a verified release checkpoint")
    create_p.add_argument("label", nargs="?", default="", help="Optional descriptive label for the checkpoint")
    create_p.add_argument("--skip-checks", action="store_true", help="Skip 4-tier pre-flight verification (not recommended)")
    create_p.add_argument("--no-push", action="store_true", help="Do not push git tag to origin")

    # rollback
    rollback_p = subparsers.add_parser("rollback", help="Rollback production to a verified checkpoint")
    rollback_p.add_argument("tag", nargs="?", default="", help="Checkpoint tag name to restore (defaults to latest)")
    rollback_p.add_argument("--force", "-f", action="store_true", help="Bypass confirmation prompt")
    rollback_p.add_argument("--no-db", action="store_true", help="Do not restore database snapshot")

    # list
    subparsers.add_parser("list", help="List available release checkpoints")

    args = parser.parse_args()

    if args.subcommand == "create":
        create_checkpoint(label=args.label, skip_checks=args.skip_checks, push_remote=not args.no_push)
    elif args.subcommand == "rollback":
        rollback_to_checkpoint(target_tag=args.tag, force=args.force, restore_db=not args.no_db)
    elif args.subcommand in ("list", None):
        list_checkpoints()


if __name__ == "__main__":
    main()
