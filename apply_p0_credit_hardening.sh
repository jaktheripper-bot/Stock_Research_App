#!/usr/bin/env bash
# P0 credit-grant integrity hardening (v3: isolated PostgreSQL integration tests,
# outcome-unknown handling, and complete release gates).
#
# Fixes:
# - Serializes PostgreSQL credit-cap checks across same-admin and same-target grants.
# - Resolves target identity before calculating the target's rolling 24-hour cap.
# - Fails closed when a recent grant-audit record is malformed, missing its amount,
#   non-finite, or negative.
# - Reports actual ticket-remedy grant outcomes.
# - Uses staged writes with rollback on write failure; does not claim cross-file atomicity.
# - Adds SQLite regression coverage, deterministic PostgreSQL lock-order coverage, and an opt-in
#   real PostgreSQL integration test that requires an explicitly named disposable database.
# - Never labels an authoritative-database interruption as a skipped grant: reconciliation is
#   required before a human retries the ticket action.
# - Synchronizes Living Docs (AGENTS.md Rule 3) and fixes the pytest boot-guard test.
#
# Usage:
#   bash apply_p0_credit_hardening.sh --check
#   bash apply_p0_credit_hardening.sh --apply
#   bash apply_p0_credit_hardening.sh --apply --with-tests
#
# Optional PostgreSQL integration test:
#   MOATNOMICS_TEST_POSTGRES_DSN='postgresql://.../moatnomics_test_credit' \
#   MOATNOMICS_PG_TEST_ACK=DISPOSABLE_DATABASE \
#     .venv/bin/python -m unittest \
#     tests.integration.test_postgres_credit_grant_concurrency

set -euo pipefail

MODE="check"
WITH_TESTS=0
REPO="${REPO:-$(git rev-parse --show-toplevel 2>/dev/null || pwd)}"

while (($#)); do
  case "$1" in
    --check) MODE="check"; shift ;;
    --apply) MODE="apply"; shift ;;
    --with-tests) WITH_TESTS=1; shift ;;
    --repo)
      [[ $# -ge 2 && -n "$2" ]] || {
        echo "ERROR: --repo requires a directory" >&2
        exit 2
      }
      REPO="$2"
      shift 2
      ;;
    *)
      echo "Usage: $0 [--check|--apply] [--with-tests] [--repo DIR]" >&2
      exit 2
      ;;
  esac
done

[[ -d "$REPO/.git" || -f "$REPO/.git" ]] || {
  echo "ERROR: not a Git checkout: $REPO" >&2
  exit 2
}

PY="$REPO/.venv/bin/python3"
[[ -x "$PY" ]] || PY="$(command -v python3)"

(
  cd "$REPO"

  # Do not overwrite pre-existing edits in files this script owns.
  TARGETS=(
    core/db/admin.py
    web/routers/admin.py
    web/templates/admin.html
    tests/unit/test_p0_credit_and_db_containment.py
    tests/integration/test_postgres_credit_grant_concurrency.py
    tests/security/test_auth_and_security.py
    docs/MASTER_ENGINEERING_MANUAL.md
    .antigravity/docs/ARCHITECTURE.md
  )

  for path in "${TARGETS[@]}"; do
    if [[ -e "$path" && -n "$(git status --porcelain -- "$path")" ]]; then
      echo "ERROR: refusing to overwrite existing changes in $path" >&2
      exit 3
    fi
  done

  "$PY" - "$REPO" "$MODE" <<'PY'
from __future__ import annotations

import os
import pathlib
import sys
import tempfile

repo = pathlib.Path(sys.argv[1]).resolve()
mode = sys.argv[2]

staged: dict[pathlib.Path, str] = {}


def current(rel: str) -> str:
    path = repo / rel
    if path in staged:
        return staged[path]
    if not path.is_file():
        raise SystemExit(f"ERROR: missing target file: {rel}")
    return path.read_text(encoding="utf-8")


def replace_once(rel: str, old: str, new: str) -> None:
    text = current(rel)
    count = text.count(old)
    if count != 1:
        raise SystemExit(
            f"ERROR: expected exactly one match in {rel}; found {count}.\n"
            f"Anchor: {old[:180]!r}"
        )
    staged[repo / rel] = text.replace(old, new, 1)


def replace_between(rel: str, start: str, end: str, replacement: str) -> None:
    text = current(rel)
    if text.count(start) != 1 or text.count(end) != 1:
        raise SystemExit(f"ERROR: ambiguous replacement anchors in {rel}")
    left = text.index(start)
    right = text.index(end, left)
    if right <= left:
        raise SystemExit(f"ERROR: invalid replacement range in {rel}")
    staged[repo / rel] = text[:left] + replacement + text[right:]


# ---------------------------------------------------------------------------
# 1. Ledger: lock actor, resolve+lock target, then inspect recent history.
# ---------------------------------------------------------------------------
replace_between(
    "core/db/admin.py",
    '''        if owns_conn and not use_pg:
            cursor.execute("BEGIN IMMEDIATE")

        # Enforce 24-hour cumulative target and actor grant limits from admin_audit_log
''',
    '''        old_balance = float(user_row[3] or 0.0)
''',
    '''        if owns_conn and not use_pg:
            cursor.execute("BEGIN IMMEDIATE")

        # Lock order is actor -> target. The actor advisory lock serializes the
        # per-actor cap across different target accounts; FOR UPDATE serializes
        # the per-target cap across different administrators.
        if use_pg:
            cursor.execute(
                "SELECT pg_advisory_xact_lock(193759, hashtext(%s))",
                (clean_admin,),
            )

        # Resolve and lock the canonical target before inspecting the rolling
        # history. This prevents a user_id/email alias from bypassing the cap.
        lock_user = " FOR UPDATE" if use_pg else ""
        cursor.execute(
            f"""
            SELECT id, email, full_name, credits_balance
            FROM user_accounts
            WHERE LOWER(email) = LOWER({p}) OR id = {p}
            LIMIT 1{lock_user};
            """,
            (clean_target, clean_target),
        )
        user_row = cursor.fetchone()

        if not user_row:
            should_auto_provision = (
                auto_provision
                or clean_target == clean_admin
                or clean_target in get_authorized_bootstrap_emails()
            )
            if should_auto_provision and (
                "@" in clean_target or clean_target.startswith("usr_")
            ):
                import re

                generated_id = (
                    f"usr_{re.sub(r'[^a-zA-Z0-9]', '_', clean_target)[:32]}"
                )
                generated_email = (
                    clean_target
                    if "@" in clean_target
                    else f"{clean_target}@user.local"
                )
                generated_name = (
                    clean_target.split("@")[0].replace(".", " ").title()
                    if "@" in clean_target
                    else "Investor"
                )
                cursor.execute(
                    f"""
                    INSERT INTO user_accounts
                        (id, email, full_name, credits_balance, subscription_tier)
                    VALUES ({p}, {p}, {p}, 0.0, 'free')
                    ON CONFLICT DO NOTHING;
                    """,
                    (generated_id, generated_email, generated_name),
                )
                cursor.execute(
                    f"""
                    SELECT id, email, full_name, credits_balance
                    FROM user_accounts
                    WHERE id = {p} OR LOWER(email) = LOWER({p})
                    LIMIT 1{lock_user};
                    """,
                    (generated_id, generated_email),
                )
                user_row = cursor.fetchone()

        if not user_row:
            if owns_conn:
                conn.rollback()
            return {
                "success": False,
                "error": (
                    f"User '{target_user_identifier}' not found in registered accounts."
                ),
            }

        resolved_uid = str(user_row[0] or "").strip().lower()
        resolved_email = str(user_row[1] or "").strip().lower()

        # Read after both applicable locks. PostgreSQL READ COMMITTED obtains a
        # fresh statement snapshot here after any preceding lock wait.
        if use_pg:
            cursor.execute(
                """
                SELECT details, admin_email
                FROM admin_audit_log
                WHERE action = 'GRANT_USER_CREDITS'
                  AND created_at >= statement_timestamp() - INTERVAL '24 hours'
                """
            )
        else:
            # datetime(created_at) normalizes legacy UTC, IST-offset, and plain
            # SQLite values before comparison. The broad textual prefilter keeps
            # the indexed scan bounded without deciding eligibility by itself.
            cursor.execute(
                """
                SELECT details, admin_email
                FROM admin_audit_log
                WHERE action = 'GRANT_USER_CREDITS'
                  AND created_at >= datetime('now', '-36 hours')
                  AND datetime(created_at) >= datetime('now', '-24 hours')
                """
            )

        actor_24h_total = 0.0
        target_24h_total = 0.0
        integrity_error = None

        for details_raw, row_admin in cursor.fetchall():
            try:
                details = json.loads(details_raw)
            except (TypeError, ValueError) as exc:
                integrity_error = "malformed audit details"
                logger.error(
                    "Credit grant history integrity failure: malformed audit JSON: %s",
                    exc,
                )
                break

            if not isinstance(details, dict):
                integrity_error = "non-object audit details"
                logger.error(
                    "Credit grant history integrity failure: audit details are not an object."
                )
                break

            raw_amount = details.get("credits_granted")
            if isinstance(raw_amount, bool) or raw_amount is None:
                integrity_error = "missing or boolean audit amount"
                logger.error(
                    "Credit grant history integrity failure: missing or invalid credits_granted."
                )
                break

            try:
                granted = float(raw_amount)
            except (TypeError, ValueError):
                integrity_error = "non-numeric credits_granted"
                logger.error(
                    "Credit grant history integrity failure: non-numeric credits_granted."
                )
                break

            if not math.isfinite(granted) or granted < 0:
                integrity_error = "non-finite or negative audit amount"
                logger.error(
                    "Credit grant history integrity failure: invalid credits_granted=%r.",
                    raw_amount,
                )
                break

            row_uid = str(details.get("user_id") or "").strip().lower()
            row_email = str(details.get("user_email") or "").strip().lower()
            if (
                (resolved_uid and row_uid == resolved_uid)
                or (resolved_email and row_email == resolved_email)
            ):
                target_24h_total += granted
            if str(row_admin or "").strip().lower() == clean_admin:
                actor_24h_total += granted

        if integrity_error:
            if owns_conn:
                conn.rollback()
            return {
                "success": False,
                "error": (
                    "Credit grant history failed integrity validation. "
                    "No credits were granted."
                ),
            }

        if target_24h_total + credits_val > MAX_TARGET_DAILY_CREDIT_GRANT + 1e-6:
            if owns_conn:
                conn.rollback()
            return {
                "success": False,
                "error": (
                    f"24h target grant limit exceeded "
                    f"({target_24h_total:.1f} already granted; "
                    f"max {MAX_TARGET_DAILY_CREDIT_GRANT:.1f}/24h)."
                ),
            }

        if actor_24h_total + credits_val > MAX_ACTOR_DAILY_CREDIT_GRANT + 1e-6:
            if owns_conn:
                conn.rollback()
            return {
                "success": False,
                "error": (
                    f"24h administrator grant limit exceeded "
                    f"({actor_24h_total:.1f} already granted; "
                    f"max {MAX_ACTOR_DAILY_CREDIT_GRANT:.1f}/24h)."
                ),
            }

        user_id = user_row[0]
        user_email = user_row[1]
        user_name = user_row[2] or "Investor"
''',
)

replace_once(
    "core/db/admin.py",
    "0.0, 0.0, '', now());",
    "0.0, 0.0, '', statement_timestamp());",
)
replace_once(
    "core/db/admin.py",
    "VALUES ({p}, {p}, {p}, 0.0, {p}, now());",
    "VALUES ({p}, {p}, {p}, 0.0, {p}, statement_timestamp());",
)
replace_once(
    "core/db/admin.py",
    "VALUES ({p}, {p}, 'GRANT_USER_CREDITS', 'user', {p}, {p}, {p}, {p}, now());",
    "VALUES ({p}, {p}, 'GRANT_USER_CREDITS', 'user', {p}, {p}, {p}, {p}, statement_timestamp());",
)

# ---------------------------------------------------------------------------
# 2. Ticket reply: validate before side effects and surface the true outcome.
# ---------------------------------------------------------------------------
replace_once(
    "web/routers/admin.py",
    '''    MAX_SINGLE_ADMIN_CREDIT_GRANT,
)
from core.db.telemetry import purge_test_telemetry''',
    '''    MAX_SINGLE_ADMIN_CREDIT_GRANT,
)
from core.db.connection import AuthoritativeDatabaseUnavailable
from core.db.telemetry import purge_test_telemetry''',
)

replace_once(
    "web/routers/admin.py",
    '''    clean_reply = str(reply_message or "").strip()
    if not clean_reply:
        err_msg = "Reply message cannot be empty."
        if is_ajax:
            return JSONResponse(status_code=400, content={"success": False, "error": err_msg})
        return RedirectResponse(url=f"/admin?tab=tickets&err={urllib.parse.quote_plus(err_msg)}", status_code=303)
''',
    '''    clean_reply = str(reply_message or "").strip()
    if not clean_reply:
        err_msg = "Reply message cannot be empty."
        if is_ajax:
            return JSONResponse(status_code=400, content={"success": False, "error": err_msg})
        return RedirectResponse(
            url=f"/admin?tab=tickets&err={urllib.parse.quote_plus(err_msg)}",
            status_code=303,
        )

    remedial_credits_to_grant = 0.0
    raw_remedial_credits = (
        "" if grant_remedial_credits is None else str(grant_remedial_credits).strip()
    )
    if raw_remedial_credits not in ("", "0", "0.0", "0.00"):
        try:
            remedial_credits_to_grant = parse_strict_credit_amount(
                grant_remedial_credits,
                max_allowed=MAX_SINGLE_ADMIN_CREDIT_GRANT,
            )
        except ValueError as exc:
            err_msg = f"Invalid remedial credits amount: {exc}"
            if is_ajax:
                return JSONResponse(
                    status_code=400,
                    content={"success": False, "error": err_msg},
                )
            return RedirectResponse(
                url=f"/admin?tab=tickets&err={urllib.parse.quote_plus(err_msg)}",
                status_code=303,
            )
''',
)

replace_between(
    "web/routers/admin.py",
    '''    # 4. Handle optional remedial credits grant
''',
    '''    # 5. Record admin audit log
''',
    '''    # 4. Handle optional remedial credits grant
    credits_granted = 0.0
    grant_error = None
    if remedial_credits_to_grant > 0:
        try:
            grant_result = admin_grant_user_credits(
                admin_email=admin_email,
                target_user_identifier=ticket.get("user_email"),
                credits_amount=remedial_credits_to_grant,
                reason_code="TASK_REMEDY",
                admin_note=f"Remedial grant from ticket response {canonical_tid}",
                ticket_id=canonical_tid,
                resolve_ticket=False,
                auto_provision=True,
                ip_address=client_ip,
                user_agent=request.headers.get("user-agent", ""),
            )
            if grant_result.get("success"):
                credits_granted = float(
                    grant_result.get("credits_added") or remedial_credits_to_grant
                )
            else:
                grant_error = str(
                    grant_result.get("error") or "Remedial credit grant was rejected."
                )
                logger.warning(
                    "Remedial credit grant rejected for ticket %s: %s",
                    canonical_tid,
                    grant_error,
                )
        except AuthoritativeDatabaseUnavailable:
            # Fail closed on authoritative database outage; preserve 503 response
            raise
        except Exception as exc:
            grant_error = str(exc)
            logger.error(
                "Remedial credit grant failed for ticket %s: %s",
                canonical_tid,
                exc,
            )

''',
)

replace_once(
    "web/routers/admin.py",
    '''        details={
            "recipient_email": ticket.get("user_email"),
            "new_status": new_status,
            "email_dispatched": email_dispatched,
            "email_configured": email_configured,
            "email_status_text": email_status_text,
            "credits_granted": credits_granted,
            "reply_preview": clean_reply[:100]
        },
''',
    '''        details={
            "recipient_email": ticket.get("user_email"),
            "new_status": new_status,
            "email_dispatched": email_dispatched,
            "email_configured": email_configured,
            "email_status_text": email_status_text,
            "credits_granted": credits_granted,
            "grant_error": grant_error,
            "reply_preview": clean_reply[:100],
        },
''',
)

replace_once(
    "web/routers/admin.py",
    '''            "email_status_text": email_status_text,
            "message": f"Response recorded for {ticket.get('user_email')} (Status: {new_status.upper()}). Outgoing Email: {email_status_text}."
''',
    '''            "email_status_text": email_status_text,
            "credits_granted": credits_granted,
            "grant_error": grant_error,
            "message": (
                f"Response recorded for {ticket.get('user_email')} "
                f"(Status: {new_status.upper()}). Outgoing Email: {email_status_text}."
                + (
                    f" Granted +{credits_granted} remedial credits."
                    if credits_granted > 0
                    else (
                        f" Remedial credit status: {grant_error}"
                        if grant_error
                        else ""
                    )
                )
            ),
''',
)

replace_once(
    "web/routers/admin.py",
    '''    if credits_granted > 0:
        msg += f"+(+{credits_granted}+credits+granted)"
    return RedirectResponse(url=f"/admin?tab=tickets&msg={msg}", status_code=303)
''',
    '''    if credits_granted > 0:
        msg += f"+(+{credits_granted}+credits+granted)"
    elif grant_error:
        msg += f"+(credit+grant+status:+{urllib.parse.quote_plus(grant_error)})"
    return RedirectResponse(url=f"/admin?tab=tickets&msg={msg}", status_code=303)
''',
)

# ---------------------------------------------------------------------------
# 3. UI: limits match server policy and rejected grants are visible.
# ---------------------------------------------------------------------------
replace_once(
    "web/templates/admin.html",
    '''<input type="number" step="any" min="0" max="100" name="grant_remedial_credits" id="replyRemedialCredits" value="0.0" class="admin-input" style="width: 100%; box-sizing: border-box; font-size: 16px; padding: 5px 8px;" placeholder="0.0">''',
    '''<input type="number" step="0.01" min="0" max="10" name="grant_remedial_credits" id="replyRemedialCredits" value="0.0" class="admin-input" style="width: 100%; box-sizing: border-box; font-size: 16px; padding: 5px 8px;" placeholder="0.0 (max 10.0)">''',
)

replace_once(
    "web/templates/admin.html",
    '''        if (window.showToast) {
          window.showToast(`Reply sent & ticket ${res.ticket_id} marked ${effectiveStatus.toUpperCase()}`, 'success');
        }''',
    '''        if (window.showToast) {
          if (res.grant_error) {
            window.showToast(
              `Reply sent (${effectiveStatus.toUpperCase()}); remedial credit status: ${res.grant_error}`,
              'warning'
            );
          } else {
            const creditSuffix = Number(res.credits_granted) > 0
              ? ` (+${res.credits_granted} credits)`
              : '';
            window.showToast(
              `Reply sent & ticket ${res.ticket_id} marked ${effectiveStatus.toUpperCase()}${creditSuffix}`,
              'success'
            );
          }
        }''',
)

# ---------------------------------------------------------------------------
# 4. SQLite regressions: identity, malformed history, ticket outcome.
# ---------------------------------------------------------------------------
replace_once(
    "tests/unit/test_p0_credit_and_db_containment.py",
    '''import tempfile
import threading
import unittest
from unittest.mock import patch''',
    '''import tempfile
import threading
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from unittest.mock import patch''',
)

insertion_anchor = '''    def test_admin_copilot_proposal_binding_one_time_consumption_and_tamper_rejection(self):'''
new_tests = r'''
    @staticmethod
    def _wrap_conn_with_audit_read_latency(delay_sec: float = 0.05):
        """Inject latency on admin_audit_log reads to expose any check-then-insert race."""
        import core.db.admin as adm_mod

        orig_get_conn = adm_mod.get_db_connection

        class _LatencyCursor:
            def __init__(self, cur):
                self._cur = cur

            def execute(self, sql, *args, **kwargs):
                res = self._cur.execute(sql, *args, **kwargs)
                if "FROM admin_audit_log" in str(sql):
                    time.sleep(delay_sec)
                return res

            def __getattr__(self, name):
                return getattr(self._cur, name)

        class _LatencyConn:
            def __init__(self, conn):
                self._conn = conn

            def cursor(self, *args, **kwargs):
                return _LatencyCursor(self._conn.cursor(*args, **kwargs))

            def __getattr__(self, name):
                return getattr(self._conn, name)

        return patch.object(adm_mod, "get_db_connection", side_effect=lambda: _LatencyConn(orig_get_conn()))

    def test_concurrent_grants_share_target_cap_across_id_and_email(self):
        starting_balance = get_user_credits_balance("usr_alice")
        barrier = threading.Barrier(2)

        def grant(actor, target):
            barrier.wait(timeout=5)
            return admin_grant_user_credits(actor, target, 6.0)

        with self._wrap_conn_with_audit_read_latency(0.05), ThreadPoolExecutor(max_workers=2) as pool:
            first = pool.submit(grant, "owner@example.com", "usr_alice")
            second = pool.submit(grant, "other-admin@example.com", "alice@example.com")
            results = [first.result(timeout=10), second.result(timeout=10)]

        self.assertEqual(sum(result["success"] for result in results), 1, results)
        rejected = next(result for result in results if not result["success"])
        self.assertIn("24h target grant limit exceeded", rejected["error"])
        self.assertEqual(get_user_credits_balance("usr_alice"), starting_balance + 6.0)

    def test_concurrent_grants_share_actor_cap_across_targets(self):
        get_or_create_user("usr_carol", "carol@example.com", "Carol")
        get_or_create_user("usr_dan", "dan@example.com", "Dan")
        actor = "owner@example.com"
        for target in ("usr_alice", "usr_bob"):
            self.assertTrue(admin_grant_user_credits(actor, target, 10.0)["success"])
        targets = ("usr_carol", "usr_dan")
        starting_total = sum(get_user_credits_balance(target) for target in targets)
        barrier = threading.Barrier(2)

        def grant(target):
            barrier.wait(timeout=5)
            return admin_grant_user_credits(actor, target, 4.0)

        with self._wrap_conn_with_audit_read_latency(0.05), ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(grant, targets))

        self.assertEqual(sum(result["success"] for result in results), 1, results)
        rejected = next(result for result in results if not result["success"])
        self.assertIn("24h administrator grant limit exceeded", rejected["error"])
        self.assertEqual(sum(get_user_credits_balance(target) for target in targets), starting_total + 4.0)

    def test_postgres_grant_cap_locks_actor_and_target_before_reading_audit_history(self):
        """PostgreSQL path must take the actor advisory lock and the target FOR UPDATE lock BEFORE reading admin_audit_log."""
        executed_sql = []

        class _FakePgCursor:
            def execute(self, sql, params=None):
                norm = " ".join(str(sql).split())
                executed_sql.append((norm, params))
                self._last = norm

            def fetchone(self):
                if "FROM user_accounts" in self._last:
                    return ("usr_alice", "alice@example.com", "Alice Sharma", 2.0)
                return None

            def fetchall(self):
                if "FROM admin_audit_log" in self._last:
                    return [(json.dumps({"user_id": "usr_alice", "user_email": "alice@example.com", "credits_granted": 6.0}), "other@example.com")]
                return []

            def close(self):
                pass

        class _FakePgConn:
            def cursor(self):
                return _FakePgCursor()

            def commit(self):
                pass

            def rollback(self):
                pass

            def close(self):
                pass

        with patch("core.db.admin.is_postgres_connection", return_value=True):
            res = admin_grant_user_credits(
                "owner@example.com",
                "alice@example.com",
                6.0,
                connection=_FakePgConn(),
            )
        self.assertFalse(res["success"])
        self.assertIn("24h target grant limit exceeded", res["error"])
        queries = [q for q, _ in executed_sql]
        adv_idx = next((i for i, q in enumerate(queries) if "pg_advisory_xact_lock(193759, hashtext(%s))" in q), -1)
        usr_idx = next((i for i, q in enumerate(queries) if "FROM user_accounts" in q and "FOR UPDATE" in q), -1)
        aud_idx = next((i for i, q in enumerate(queries) if "FROM admin_audit_log" in q and "statement_timestamp()" in q), -1)
        self.assertGreaterEqual(adv_idx, 0, f"Missing pg_advisory_xact_lock in: {queries}")
        self.assertGreater(usr_idx, adv_idx, f"user_accounts FOR UPDATE must follow advisory lock: {queries}")
        self.assertGreater(aud_idx, usr_idx, f"admin_audit_log read must follow both locks: {queries}")

    def _insert_grant_audit(self, audit_id, details, created_at=None, admin="other@example.com"):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO admin_audit_log
                    (id, admin_email, action, details, created_at)
                VALUES (?, ?, 'GRANT_USER_CREDITS', ?, COALESCE(?, datetime('now')))
                """,
                (audit_id, admin, details, created_at),
            )
            conn.commit()

    def test_credit_grant_history_fails_closed_on_invalid_recent_amounts(self):
        original_balance = get_user_credits_balance("usr_alice")
        invalid_details = (
            "{not-json",
            json.dumps({}),
            json.dumps({"credits_granted": "NaN"}),
            json.dumps({"credits_granted": -1}),
        )

        for index, details in enumerate(invalid_details):
            with self.subTest(details=details):
                with sqlite3.connect(self.db_path) as conn:
                    conn.execute(
                        "DELETE FROM admin_audit_log WHERE action = 'GRANT_USER_CREDITS'"
                    )
                    conn.commit()

                self._insert_grant_audit(f"aud_invalid_{index}", details)
                result = admin_grant_user_credits(
                    "owner@example.com",
                    "alice@example.com",
                    1.0,
                )
                self.assertFalse(result["success"])
                self.assertIn("history failed integrity validation", result["error"])
                self.assertEqual(
                    get_user_credits_balance("usr_alice"),
                    original_balance,
                )

    def test_email_identity_and_ist_boundary_control_target_cap(self):
        from core.db.connection import IST

        now_ist = datetime.now(IST)
        old_timestamp = (now_ist - timedelta(hours=25)).isoformat(
            sep=" ", timespec="seconds"
        )
        recent_timestamp = (now_ist - timedelta(hours=2)).isoformat(
            sep=" ", timespec="seconds"
        )

        self._insert_grant_audit(
            "aud_expired_bob",
            json.dumps(
                {
                    "user_id": "usr_bob",
                    "user_email": "bob@example.com",
                    "credits_granted": 9.0,
                }
            ),
            old_timestamp,
        )
        self._insert_grant_audit(
            "aud_prior_alice_id",
            json.dumps(
                {
                    "user_id": "usr_legacy_alice",
                    "user_email": "alice@example.com",
                    "credits_granted": 7.0,
                }
            ),
            recent_timestamp,
        )

        self.assertTrue(
            admin_grant_user_credits(
                "owner@example.com", "usr_bob", 5.0
            )["success"]
        )
        result = admin_grant_user_credits(
            "owner@example.com", "usr_alice", 4.0
        )
        self.assertFalse(result["success"])
        self.assertIn("24h target grant limit exceeded", result["error"])

    def test_ticket_reply_reports_rejected_remedial_grant_truthfully(self):
        from core.db.support import create_support_ticket
        from web.common import ADMIN_COOKIE_NAME, _generate_admin_token

        self._insert_grant_audit(
            "aud_alice_cap",
            json.dumps(
                {
                    "user_id": "usr_prior_alice",
                    "user_email": "alice@example.com",
                    "credits_granted": 10.0,
                }
            ),
        )
        ticket = create_support_ticket(
            "alice@example.com",
            "Credit issue",
            "Please review",
            user_name="Alice Sharma",
        )
        cookie = _generate_admin_token("owner@example.com", "owner")
        client = TestClient(app, raise_server_exceptions=False)
        response = client.post(
            "/api/admin/tickets/reply",
            data={
                "ticket_id": ticket["ticket_id"],
                "reply_message": "We investigated the issue.",
                "dispatch_email": "off",
                "grant_remedial_credits": "1.0",
            },
            headers={
                "Cookie": f"{ADMIN_COOKIE_NAME}={cookie}",
                "Origin": "http://testserver",
                "Accept": "application/json",
                "X-Requested-With": "XMLHttpRequest",
            },
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["credits_granted"], 0.0)
        self.assertIn("24h target grant limit exceeded", body["grant_error"])
'''
replace_once(
    "tests/unit/test_p0_credit_and_db_containment.py",
    insertion_anchor,
    new_tests + "\n" + insertion_anchor,
)

# ---------------------------------------------------------------------------
# 5. Real PostgreSQL integration test. It is opt-in to prevent accidental use
#    of a production DSN; CI must supply a disposable test database.
# ---------------------------------------------------------------------------
pg_test = r'''"""
Real PostgreSQL checks for P0 admin-credit serialization.

This suite intentionally skips unless MOATNOMICS_TEST_POSTGRES_DSN is set.
Never point that variable at a production database.
"""
import json
import os
import threading
import unittest
import uuid
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
from urllib.parse import urlparse
import re


POSTGRES_DSN = os.environ.get("MOATNOMICS_TEST_POSTGRES_DSN", "").strip()


@unittest.skipUnless(POSTGRES_DSN, "MOATNOMICS_TEST_POSTGRES_DSN is not configured")
class TestPostgresCreditGrantConcurrency(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        parsed_dsn = urlparse(POSTGRES_DSN)
        database_name = parsed_dsn.path.lstrip("/")
        if not re.fullmatch(r"moatnomics_test_[a-z0-9_]+", database_name):
            raise RuntimeError(
                "Refusing PostgreSQL integration test: database name must match "
                "moatnomics_test_<purpose>."
            )
        if os.environ.get("MOATNOMICS_PG_TEST_ACK") != "DISPOSABLE_DATABASE":
            raise RuntimeError(
                "Refusing PostgreSQL integration test without "
                "MOATNOMICS_PG_TEST_ACK=DISPOSABLE_DATABASE."
            )

        import core.db.connection as db
        from core.db.connection import init_db

        cls.env = patch.dict(
            os.environ,
            {
                "TESTING": "1",
                "TEST_SUPABASE": "1",
                "SUPABASE_DB_URL": POSTGRES_DSN,
                "FORCE_LOCAL_SQLITE": "0",
            },
            clear=False,
        )
        cls.env.start()
        db._DB_INITIALIZED = False
        db._INITIALIZED_DBS.clear()
        db._SUPABASE_URL_RESOLVED = False
        db._PG_AVAILABLE = None
        init_db(force=True)

        from core.db.connection import get_db_connection, is_postgres_connection

        probe = get_db_connection()
        try:
            if not is_postgres_connection(probe):
                raise RuntimeError(
                    "PostgreSQL integration test resolved a non-PostgreSQL connection; "
                    "check TEST_SUPABASE / SUPABASE_DB_URL."
                )
        finally:
            probe.close()

    @classmethod
    def tearDownClass(cls):
        cls.env.stop()
        import core.db.connection as db

        db._DB_INITIALIZED = False
        db._INITIALIZED_DBS.clear()
        db._SUPABASE_URL_RESOLVED = False
        db._PG_AVAILABLE = None

    def setUp(self):
        from core.db.connection import get_db_connection

        suffix = uuid.uuid4().hex[:12]
        self.actor = f"admin_{suffix}@example.test"
        self.other_actor = f"other_{suffix}@example.test"
        self.alice_id = f"usr_alice_{suffix}"
        self.bob_id = f"usr_bob_{suffix}"
        self.carol_id = f"usr_carol_{suffix}"
        self.dan_id = f"usr_dan_{suffix}"
        self.alice_email = f"alice_{suffix}@example.test"
        self.bob_email = f"bob_{suffix}@example.test"
        self.carol_email = f"carol_{suffix}@example.test"
        self.dan_email = f"dan_{suffix}@example.test"

        conn = get_db_connection()
        try:
            cur = conn.cursor()
            cur.execute(
                """
                INSERT INTO user_accounts
                    (id, email, full_name, credits_balance, subscription_tier)
                VALUES
                    (%s, %s, 'Alice Sharma', 0, 'free'),
                    (%s, %s, 'Bob Verma', 0, 'free'),
                    (%s, %s, 'Carol Sen', 0, 'free'),
                    (%s, %s, 'Dan Joshi', 0, 'free')
                """,
                (
                    self.alice_id,
                    self.alice_email,
                    self.bob_id,
                    self.bob_email,
                    self.carol_id,
                    self.carol_email,
                    self.dan_id,
                    self.dan_email,
                ),
            )
            conn.commit()
        finally:
            conn.close()

    def _concurrent_grants(self, calls):
        from core.db.admin import admin_grant_user_credits

        barrier = threading.Barrier(len(calls))

        def grant(actor, target, amount):
            barrier.wait(timeout=10)
            return admin_grant_user_credits(actor, target, amount)

        with ThreadPoolExecutor(max_workers=len(calls)) as pool:
            futures = [pool.submit(grant, *call) for call in calls]
            return [future.result(timeout=30) for future in futures]

    def tearDown(self):
        """Remove every row created by this test, even when an assertion fails."""
        from core.db.connection import get_db_connection

        conn = get_db_connection()
        try:
            cur = conn.cursor()
            ids = (self.alice_id, self.bob_id, self.carol_id, self.dan_id)
            cur.execute(
                "DELETE FROM admin_audit_log WHERE target_id IN (%s, %s, %s, %s)", ids
            )
            cur.execute(
                "DELETE FROM credit_usage_ledger WHERE user_id IN (%s, %s, %s, %s)", ids
            )
            cur.execute(
                "DELETE FROM credit_transactions WHERE user_id IN (%s, %s, %s, %s)", ids
            )
            cur.execute("DELETE FROM user_accounts WHERE id IN (%s, %s, %s, %s)", ids)
            conn.commit()
        finally:
            conn.close()

    def _account_counts(self, user_id):
        from core.db.connection import get_db_connection

        conn = get_db_connection()
        try:
            cur = conn.cursor()
            cur.execute(
                "SELECT credits_balance FROM user_accounts WHERE id = %s", (user_id,)
            )
            balance = float(cur.fetchone()[0])
            cur.execute("SELECT COUNT(*) FROM credit_transactions WHERE user_id = %s", (user_id,))
            transactions = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM credit_usage_ledger WHERE user_id = %s", (user_id,))
            ledger_rows = cur.fetchone()[0]
            cur.execute(
                "SELECT COUNT(*) FROM admin_audit_log "
                "WHERE action = 'GRANT_USER_CREDITS' AND target_id = %s",
                (user_id,),
            )
            audit_rows = cur.fetchone()[0]
            return balance, transactions, ledger_rows, audit_rows
        finally:
            conn.close()

    def test_target_cap_serializes_across_two_administrators(self):
        results = self._concurrent_grants(
            (
                (self.actor, self.alice_email, 6.0),
                (self.other_actor, self.alice_id, 6.0),
            )
        )
        self.assertEqual(sum(bool(item["success"]) for item in results), 1, results)
        self.assertIn(
            "24h target grant limit exceeded",
            next(item["error"] for item in results if not item["success"]),
        )
        self.assertEqual(self._account_counts(self.alice_id), (6.0, 1, 1, 1))

    def test_actor_cap_serializes_across_two_targets(self):
        from core.db.admin import admin_grant_user_credits

        self.assertTrue(
            admin_grant_user_credits(self.actor, self.alice_id, 10.0)["success"]
        )
        self.assertTrue(
            admin_grant_user_credits(self.actor, self.bob_id, 10.0)["success"]
        )

        results = self._concurrent_grants(
            (
                (self.actor, self.carol_id, 4.0),
                (self.actor, self.dan_id, 4.0),
            )
        )
        self.assertEqual(sum(bool(item["success"]) for item in results), 1, results)
        self.assertIn(
            "24h administrator grant limit exceeded",
            next(item["error"] for item in results if not item["success"]),
        )
        alice = self._account_counts(self.alice_id)
        bob = self._account_counts(self.bob_id)
        carol = self._account_counts(self.carol_id)
        dan = self._account_counts(self.dan_id)
        self.assertEqual(alice[0], 10.0)
        self.assertEqual(bob[0], 10.0)
        self.assertEqual(carol[0] + dan[0], 4.0)
        self.assertEqual(alice[1] + bob[1] + carol[1] + dan[1], 3)
        self.assertEqual(alice[2] + bob[2] + carol[2] + dan[2], 3)
        self.assertEqual(alice[3] + bob[3] + carol[3] + dan[3], 3)


if __name__ == "__main__":
    unittest.main()
'''
pg_path = repo / "tests/integration/test_postgres_credit_grant_concurrency.py"
staged[pg_path] = pg_test


# ---------------------------------------------------------------------------
# 6. pytest boot-guard test isolation + Living Docs (AGENTS.md Rule 3).
# ---------------------------------------------------------------------------
replace_once(
    "tests/security/test_auth_and_security.py",
    """        with patch.dict(os.environ, {"ENVIRONMENT": "production", "SECRET_KEY": valid_key, "TESTING": "1"}):
            async def run_boot():
                async with lifespan(test_app):
                    pass
            asyncio.run(run_boot())

    def test_resolve_app_base_url_local_and_production(self):""",
    """        with patch.dict(os.environ, {"ENVIRONMENT": "production", "SECRET_KEY": valid_key, "TESTING": "1"}), patch(
            "web.main.init_db"
        ):
            async def run_boot():
                async with lifespan(test_app):
                    pass
            asyncio.run(run_boot())

    def test_resolve_app_base_url_local_and_production(self):""",
)

replace_once(
    "docs/MASTER_ENGINEERING_MANUAL.md",
    "admin credit grants (`admin_grant_user_credits`, `parse_strict_credit_amount`) enforce `10.0` single/24h per-target and `25.0` 24h per-actor caps and single-use server-stored `admin_action_proposals` (`proposal_id`).",
    "admin credit grants (`admin_grant_user_credits`, `parse_strict_credit_amount`) serialize PostgreSQL grants via `pg_advisory_xact_lock(193759, hashtext(clean_admin))` and `user_accounts ... FOR UPDATE` before a `statement_timestamp()` 24h audit read (timezone-normalized `datetime(created_at)` on SQLite; malformed, missing, non-finite or negative recent audit amounts fail closed), enforce `10.0` single/24h per-target (canonical `user_id` or `email`) and `25.0` 24h per-actor caps, report the true outcome of ticket-reply remedial grants (`admin_reply_ticket`), and consume single-use server-stored `admin_action_proposals` (`proposal_id`).",
)

replace_once(
    ".antigravity/docs/ARCHITECTURE.md",
    "`MAX_ACTOR_DAILY_CREDIT_GRANT = 25.0`), and single-use TTL-bounded Copilot action proposals",
    "`MAX_ACTOR_DAILY_CREDIT_GRANT = 25.0`, serialized on PostgreSQL by `pg_advisory_xact_lock(193759, hashtext(clean_admin))` + `user_accounts ... FOR UPDATE` before a `statement_timestamp()` audit read, failing closed on invalid recent audit amounts, with `datetime(created_at)` normalization on SQLite), and single-use TTL-bounded Copilot action proposals",
)

if mode == "check":
    print(
        f"DRY-RUN PASS: {len(staged)} files staged; "
        "no repository files modified."
    )
    raise SystemExit(0)

# Stage every replacement first. If a replacement fails, nothing has been written.
temporary_files: list[tuple[pathlib.Path, pathlib.Path]] = []
original_contents: dict[pathlib.Path, bytes | None] = {}
written: list[pathlib.Path] = []

try:
    for path, content in staged.items():
        original_contents[path] = path.read_bytes() if path.exists() else None
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary_name = tempfile.mkstemp(
            prefix=f".{path.name}.",
            suffix=".tmp",
            dir=path.parent,
        )
        temporary = pathlib.Path(temporary_name)
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        temporary_files.append((path, temporary))

    for destination, temporary in temporary_files:
        os.replace(temporary, destination)
        written.append(destination)

except Exception as exc:
    # Best-effort rollback. A power loss cannot make a multi-file filesystem
    # update atomic; this prevents ordinary write failures from leaving a
    # partial patch behind.
    for path in reversed(written):
        previous = original_contents[path]
        if previous is None:
            try:
                path.unlink()
            except FileNotFoundError:
                pass
        else:
            path.write_bytes(previous)
    raise SystemExit(f"ERROR: write failed; rollback attempted: {exc}") from exc
finally:
    for _, temporary in temporary_files:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass

print(f"APPLIED: updated {len(staged)} files.")
PY
)

if [[ "$MODE" == "apply" && "$WITH_TESTS" == "1" ]]; then
  (
    cd "$REPO"

    TESTING=1 FORCE_LOCAL_SQLITE=1 \
      ADMIN_PASSWORD=test_admin_pwd_default \
      "$PY" -m pytest -q \
      tests/unit/test_p0_credit_and_db_containment.py

    TESTING=1 FORCE_LOCAL_SQLITE=1 \
      ADMIN_PASSWORD=test_admin_pwd_default \
      "$PY" -m pytest -q tests/security/test_auth_and_security.py \
      -k "production_boot_guard"

    TESTING=1 FORCE_LOCAL_SQLITE=1 \
      "$PY" scripts/verify_reality_audit.py

    TESTING=1 FORCE_LOCAL_SQLITE=1 \
      "$PY" scripts/run_project_audit.py --quick

    if [[ -n "${MOATNOMICS_TEST_POSTGRES_DSN:-}" ]]; then
      MOATNOMICS_PG_TEST_ACK="${MOATNOMICS_PG_TEST_ACK:-}" \
        "$PY" -m pytest -q tests/integration/test_postgres_credit_grant_concurrency.py
    else
      echo "SKIPPED: postgres-concurrency (MOATNOMICS_TEST_POSTGRES_DSN not configured)"
    fi

    TESTING=1 FORCE_LOCAL_SQLITE=1 \
      "$PY" -m unittest discover -s tests
  )
fi
