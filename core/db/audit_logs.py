"""Database Repository for Autonomous Project Audit Logs.

Supports dual-binding for local SQLite and production PostgreSQL (Supabase / Render).
Maintains permanent audit logs of all strategic, technical, and UI/UX audits.
"""

import json
import logging
import os
import ssl
import time
import urllib.parse
import urllib.request
from decimal import Decimal
from datetime import datetime, date
from pathlib import Path
from typing import Optional, List, Dict, Any, Tuple

import certifi

from core.config import get_secret
from core.db.connection import get_db_connection, get_supabase_url, is_postgres_connection, is_postgres_active

def is_supabase_enabled() -> bool:
    return bool((get_supabase_url() and is_postgres_active()) or _get_supabase_rest_credentials())

logger = logging.getLogger(__name__)

_LAST_REMOTE_AUDIT_SYNC_TS: float = 0.0
_REMOTE_SYNC_COOLDOWN_SEC: float = 60.0


def _get_supabase_rest_credentials() -> Optional[Tuple[str, str]]:
    """Returns (supabase_url, service_role_key) when configured and not in unit test mode."""
    if os.environ.get("TESTING") == "1":
        return None
    sb_url = (get_secret("SUPABASE_URL") or os.environ.get("SUPABASE_URL") or "").strip().rstrip("/")
    sb_key = (
        get_secret("SUPABASE_SERVICE_ROLE_KEY")
        or os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
        or ""
    ).strip()
    if sb_url and sb_key and sb_url.startswith("https://"):
        return (sb_url, sb_key)
    return None


def _build_ssl_context() -> ssl.SSLContext:
    cafile = os.environ.get("SSL_CERT_FILE")
    if not cafile or not os.path.exists(cafile):
        cafile = certifi.where()
    try:
        return ssl.create_default_context(cafile=cafile)
    except Exception as ssl_err:
        logger.warning("Custom cafile notice in audit_logs: %s", ssl_err)
        return ssl.create_default_context(cafile=certifi.where())


def _push_audit_log_to_supabase_rest(
    audit: Dict[str, Any],
    critical_violations_json: str,
    recommendations_json: str,
    pillar_breakdown_json: str,
) -> bool:
    """Pushes a project audit log to Supabase via PostgREST when local SQLite is primary."""
    creds = _get_supabase_rest_credentials()
    if not creds:
        return False
    sb_url, sb_key = creds
    url = f"{sb_url}/rest/v1/project_audit_logs?on_conflict=audit_id"
    payload = {
        "audit_id": audit.get("audit_id"),
        "overall_score": float(audit.get("overall_score", 0.0)),
        "strategy_score": float(audit.get("strategy_score", 0.0)),
        "implementation_score": float(audit.get("implementation_score", 0.0)),
        "uiux_score": float(audit.get("uiux_score", 0.0)),
        "status": audit.get("status", "COMPLIANT"),
        "tests_total": int(audit.get("tests_total", 0)),
        "tests_passed": int(audit.get("tests_passed", 0)),
        "tests_failed": int(audit.get("tests_failed", 0)),
        "endpoints_checked": int(audit.get("endpoints_checked", 0)),
        "endpoints_healthy": int(audit.get("endpoints_healthy", 0)),
        "critical_violations_json": critical_violations_json,
        "recommendations_json": recommendations_json,
        "pillar_breakdown_json": pillar_breakdown_json,
        "full_markdown_report": audit.get("full_markdown_report", ""),
        "audit_engine": audit.get("audit_engine", "autonomous-auditor-engine"),
    }
    try:
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "apikey": sb_key,
                "Authorization": f"Bearer {sb_key}",
                "Content-Type": "application/json",
                "Prefer": "resolution=merge-duplicates,return=minimal",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10, context=_build_ssl_context()):
            pass
        return True
    except Exception as e:
        logger.warning("Supabase REST audit push notice for %s: %s", audit.get("audit_id"), e)
        return False


def sync_remote_audits_to_local(limit: int = 30, force: bool = False) -> Dict[str, Any]:
    """Pulls remote Supabase project_audit_logs and audit_remediation_ledger into local SQLite and audits/."""
    global _LAST_REMOTE_AUDIT_SYNC_TS
    now = time.time()
    if not force and (now - _LAST_REMOTE_AUDIT_SYNC_TS) < _REMOTE_SYNC_COOLDOWN_SEC:
        return {"synced": False, "reason": "cooldown"}

    creds = _get_supabase_rest_credentials()
    if not creds:
        return {"synced": False, "reason": "unconfigured"}

    conn = get_db_connection()
    if is_postgres_connection(conn):
        conn.close()
        return {"synced": False, "reason": "already_postgres"}

    sb_url, sb_key = creds
    ssl_ctx = _build_ssl_context()
    headers = {
        "apikey": sb_key,
        "Authorization": f"Bearer {sb_key}",
        "Accept": "application/json",
    }

    synced_audits = 0
    synced_files = 0
    synced_findings = 0
    latest_audit_id = None
    latest_overall_score = 100.0

    cursor = conn.cursor()
    try:
        logs_url = f"{sb_url}/rest/v1/project_audit_logs?select=*&order=id.desc&limit={int(limit)}"
        req_logs = urllib.request.Request(logs_url, headers=headers)
        with urllib.request.urlopen(req_logs, timeout=10, context=ssl_ctx) as resp:
            remote_logs = json.loads(resp.read().decode("utf-8")) or []

        audits_dir = Path(__file__).resolve().parent.parent.parent / "audits"
        audits_dir.mkdir(parents=True, exist_ok=True)

        # Insert oldest first so local auto-increment IDs follow chronological order
        for r in reversed(remote_logs):
            audit_id = r.get("audit_id")
            if not audit_id:
                continue
            latest_audit_id = audit_id
            latest_overall_score = float(r.get("overall_score", 0.0))
            created_str = str(r.get("created_at") or "")[:19].replace("T", " ").strip()
            if not created_str:
                created_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            cursor.execute(
                """
                INSERT INTO project_audit_logs (
                    audit_id, overall_score, strategy_score, implementation_score, uiux_score,
                    status, tests_total, tests_passed, tests_failed,
                    endpoints_checked, endpoints_healthy,
                    critical_violations_json, recommendations_json, pillar_breakdown_json,
                    full_markdown_report, audit_engine, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT (audit_id) DO UPDATE SET
                    overall_score = EXCLUDED.overall_score,
                    strategy_score = EXCLUDED.strategy_score,
                    implementation_score = EXCLUDED.implementation_score,
                    uiux_score = EXCLUDED.uiux_score,
                    status = EXCLUDED.status,
                    tests_total = EXCLUDED.tests_total,
                    tests_passed = EXCLUDED.tests_passed,
                    tests_failed = EXCLUDED.tests_failed,
                    endpoints_checked = EXCLUDED.endpoints_checked,
                    endpoints_healthy = EXCLUDED.endpoints_healthy,
                    critical_violations_json = EXCLUDED.critical_violations_json,
                    recommendations_json = EXCLUDED.recommendations_json,
                    pillar_breakdown_json = EXCLUDED.pillar_breakdown_json,
                    full_markdown_report = EXCLUDED.full_markdown_report,
                    audit_engine = EXCLUDED.audit_engine,
                    created_at = EXCLUDED.created_at;
                """,
                (
                    audit_id,
                    float(r.get("overall_score", 0.0)),
                    float(r.get("strategy_score", 0.0)),
                    float(r.get("implementation_score", 0.0)),
                    float(r.get("uiux_score", 0.0)),
                    r.get("status", "COMPLIANT"),
                    int(r.get("tests_total", 0)),
                    int(r.get("tests_passed", 0)),
                    int(r.get("tests_failed", 0)),
                    int(r.get("endpoints_checked", 0)),
                    int(r.get("endpoints_healthy", 0)),
                    r.get("critical_violations_json") or "[]",
                    r.get("recommendations_json") or "[]",
                    r.get("pillar_breakdown_json") or "{}",
                    r.get("full_markdown_report") or "",
                    r.get("audit_engine") or "autonomous-auditor-engine",
                    created_str,
                ),
            )
            synced_audits += 1

            md_report = r.get("full_markdown_report") or ""
            if md_report and audit_id.startswith("AUD-"):
                file_suffix = audit_id[4:].replace("-", "_")
                md_path = audits_dir / f"project_audit_{file_suffix}.md"
                if force or not md_path.exists():
                    md_path.write_text(md_report, encoding="utf-8")
                    synced_files += 1

        rem_url = f"{sb_url}/rest/v1/audit_remediation_ledger?select=*&order=id.asc&limit=200"
        req_rem = urllib.request.Request(rem_url, headers=headers)
        with urllib.request.urlopen(req_rem, timeout=10, context=ssl_ctx) as resp_rem:
            remote_findings = json.loads(resp_rem.read().decode("utf-8")) or []

        for f in remote_findings:
            f_hash = f.get("finding_hash")
            if not f_hash:
                continue
            first_dt = str(f.get("first_detected_at") or "")[:19].replace("T", " ").strip() or datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            last_dt = str(f.get("last_verified_at") or "")[:19].replace("T", " ").strip() or first_dt
            res_raw = f.get("resolved_at")
            res_dt = str(res_raw)[:19].replace("T", " ").strip() if res_raw else None

            cursor.execute(
                """
                INSERT INTO audit_remediation_ledger (
                    finding_hash, category, invariant_name, title, description,
                    target_file_or_route, severity, status, verification_attempts,
                    consecutive_failures, first_detected_at, last_verified_at,
                    resolved_at, remediation_notes, finding_metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT (finding_hash) DO UPDATE SET
                    category = EXCLUDED.category,
                    invariant_name = EXCLUDED.invariant_name,
                    title = EXCLUDED.title,
                    description = EXCLUDED.description,
                    target_file_or_route = EXCLUDED.target_file_or_route,
                    severity = EXCLUDED.severity,
                    status = EXCLUDED.status,
                    verification_attempts = EXCLUDED.verification_attempts,
                    consecutive_failures = EXCLUDED.consecutive_failures,
                    first_detected_at = EXCLUDED.first_detected_at,
                    last_verified_at = EXCLUDED.last_verified_at,
                    resolved_at = EXCLUDED.resolved_at,
                    remediation_notes = EXCLUDED.remediation_notes,
                    finding_metadata_json = EXCLUDED.finding_metadata_json;
                """,
                (
                    f_hash,
                    f.get("category", "BACKEND_STABILITY"),
                    f.get("invariant_name", "general_invariant"),
                    f.get("title", ""),
                    f.get("description", ""),
                    f.get("target_file_or_route", "general"),
                    f.get("severity", "MEDIUM"),
                    f.get("status", "OPEN"),
                    int(f.get("verification_attempts", 1)),
                    int(f.get("consecutive_failures", 0)),
                    first_dt,
                    last_dt,
                    res_dt,
                    f.get("remediation_notes") or "",
                    f.get("finding_metadata_json") or "{}",
                ),
            )
            synced_findings += 1

        conn.commit()
        _LAST_REMOTE_AUDIT_SYNC_TS = now
    except Exception as sync_err:
        logger.warning("Remote Supabase audit sync notice: %s", sync_err)
        try:
            conn.rollback()
        except Exception as rb_err:
            logger.warning("Rollback notice during remote audit sync: %s", rb_err)
    finally:
        cursor.close()
        conn.close()

    if latest_audit_id:
        try:
            from core.audit.project_auditor import write_remediation_action_plan
            from core.db.remediation import get_open_remediation_findings, get_remediation_summary_stats
            write_remediation_action_plan(
                latest_audit_id,
                latest_overall_score,
                get_open_remediation_findings(),
                get_remediation_summary_stats(),
                [],
            )
        except Exception as plan_err:
            logger.warning("Remediation action plan sync notice: %s", plan_err)

    return {
        "synced": True,
        "synced_audits": synced_audits,
        "synced_files": synced_files,
        "synced_findings": synced_findings,
        "latest_audit_id": latest_audit_id,
    }


def clean_audit_row(cursor, row: Any) -> Dict[str, Any]:
    """Converts a sqlite3.Row, tuple, or psycopg2 dict into a pure Python dictionary."""
    if not row:
        return {}
    if hasattr(row, "keys"):
        d = dict(row)
    elif cursor and cursor.description:
        cols = [c[0] for c in cursor.description]
        d = dict(zip(cols, row))
    else:
        d = dict(row)

    for k, v in list(d.items()):
        if isinstance(v, Decimal):
            d[k] = float(v)
        elif isinstance(v, (datetime, date)):
            d[k] = str(v)

    for json_field, target_field in [
        ("critical_violations_json", "critical_violations"),
        ("recommendations_json", "recommendations"),
        ("pillar_breakdown_json", "pillar_breakdown"),
    ]:
        if json_field in d and isinstance(d[json_field], str):
            try:
                d[target_field] = json.loads(d[json_field])
            except Exception as e:
                logger.debug("Failed parsing %s: %s", json_field, e)
                d[target_field] = [] if "s" in target_field else {}
        elif target_field not in d:
            d[target_field] = [] if "s" in target_field else {}

    return d


def save_project_audit_log(audit: Dict[str, Any]) -> bool:
    """Inserts an autonomous project audit log into the database."""
    conn = get_db_connection()
    cursor = conn.cursor()
    use_pg = is_postgres_connection(conn)

    critical_violations_json = json.dumps(audit.get("critical_violations", []))
    recommendations_json = json.dumps(audit.get("recommendations", []))
    pillar_breakdown_json = json.dumps(audit.get("pillar_breakdown", {}))

    try:
        if use_pg:
            query = """
                INSERT INTO project_audit_logs (
                    audit_id, overall_score, strategy_score, implementation_score, uiux_score,
                    status, tests_total, tests_passed, tests_failed,
                    endpoints_checked, endpoints_healthy,
                    critical_violations_json, recommendations_json, pillar_breakdown_json,
                    full_markdown_report, audit_engine, created_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, now())
                ON CONFLICT (audit_id) DO UPDATE SET
                    overall_score = EXCLUDED.overall_score,
                    strategy_score = EXCLUDED.strategy_score,
                    implementation_score = EXCLUDED.implementation_score,
                    uiux_score = EXCLUDED.uiux_score,
                    status = EXCLUDED.status,
                    tests_total = EXCLUDED.tests_total,
                    tests_passed = EXCLUDED.tests_passed,
                    tests_failed = EXCLUDED.tests_failed,
                    endpoints_checked = EXCLUDED.endpoints_checked,
                    endpoints_healthy = EXCLUDED.endpoints_healthy,
                    critical_violations_json = EXCLUDED.critical_violations_json,
                    recommendations_json = EXCLUDED.recommendations_json,
                    pillar_breakdown_json = EXCLUDED.pillar_breakdown_json,
                    full_markdown_report = EXCLUDED.full_markdown_report,
                    audit_engine = EXCLUDED.audit_engine,
                    created_at = now();
            """
            cursor.execute(query, (
                audit.get("audit_id"),
                audit.get("overall_score", 0.0),
                audit.get("strategy_score", 0.0),
                audit.get("implementation_score", 0.0),
                audit.get("uiux_score", 0.0),
                audit.get("status", "COMPLIANT"),
                audit.get("tests_total", 0),
                audit.get("tests_passed", 0),
                audit.get("tests_failed", 0),
                audit.get("endpoints_checked", 0),
                audit.get("endpoints_healthy", 0),
                critical_violations_json,
                recommendations_json,
                pillar_breakdown_json,
                audit.get("full_markdown_report", ""),
                audit.get("audit_engine", "autonomous-auditor-engine"),
            ))
        else:
            query = """
                INSERT INTO project_audit_logs (
                    audit_id, overall_score, strategy_score, implementation_score, uiux_score,
                    status, tests_total, tests_passed, tests_failed,
                    endpoints_checked, endpoints_healthy,
                    critical_violations_json, recommendations_json, pillar_breakdown_json,
                    full_markdown_report, audit_engine, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
                ON CONFLICT (audit_id) DO UPDATE SET
                    overall_score = EXCLUDED.overall_score,
                    strategy_score = EXCLUDED.strategy_score,
                    implementation_score = EXCLUDED.implementation_score,
                    uiux_score = EXCLUDED.uiux_score,
                    status = EXCLUDED.status,
                    tests_total = EXCLUDED.tests_total,
                    tests_passed = EXCLUDED.tests_passed,
                    tests_failed = EXCLUDED.tests_failed,
                    endpoints_checked = EXCLUDED.endpoints_checked,
                    endpoints_healthy = EXCLUDED.endpoints_healthy,
                    critical_violations_json = EXCLUDED.critical_violations_json,
                    recommendations_json = EXCLUDED.recommendations_json,
                    pillar_breakdown_json = EXCLUDED.pillar_breakdown_json,
                    full_markdown_report = EXCLUDED.full_markdown_report,
                    audit_engine = EXCLUDED.audit_engine,
                    created_at = datetime('now');
            """
            cursor.execute(query, (
                audit.get("audit_id"),
                audit.get("overall_score", 0.0),
                audit.get("strategy_score", 0.0),
                audit.get("implementation_score", 0.0),
                audit.get("uiux_score", 0.0),
                audit.get("status", "COMPLIANT"),
                audit.get("tests_total", 0),
                audit.get("tests_passed", 0),
                audit.get("tests_failed", 0),
                audit.get("endpoints_checked", 0),
                audit.get("endpoints_healthy", 0),
                critical_violations_json,
                recommendations_json,
                pillar_breakdown_json,
                audit.get("full_markdown_report", ""),
                audit.get("audit_engine", "autonomous-auditor-engine"),
            ))
        conn.commit()
        if not use_pg:
            _push_audit_log_to_supabase_rest(
                audit,
                critical_violations_json,
                recommendations_json,
                pillar_breakdown_json,
            )
        return True
    except Exception as e:
        logger.error(f"Error saving project audit log: {e}")
        conn.rollback()
        return False
    finally:
        cursor.close()
        conn.close()


def get_latest_project_audit_log() -> Optional[Dict[str, Any]]:
    """Retrieves the most recent project audit log."""
    sync_remote_audits_to_local(limit=20)
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT * FROM project_audit_logs ORDER BY created_at DESC, id DESC LIMIT 1;")
        row = cursor.fetchone()
        if not row:
            return None
        return clean_audit_row(cursor, row)
    except Exception as e:
        logger.error(f"Error fetching latest audit log: {e}")
        return None
    finally:
        cursor.close()
        conn.close()


def get_project_audit_history(limit: int = 10) -> List[Dict[str, Any]]:
    """Retrieves recent audit logs in reverse chronological order."""
    sync_remote_audits_to_local(limit=max(limit, 20))
    conn = get_db_connection()
    cursor = conn.cursor()
    use_pg = is_postgres_connection(conn)
    try:
        placeholder = "%s" if use_pg else "?"
        cursor.execute(f"SELECT * FROM project_audit_logs ORDER BY created_at DESC, id DESC LIMIT {placeholder};", (limit,))
        rows = cursor.fetchall()
        return [clean_audit_row(cursor, r) for r in rows]
    except Exception as e:
        logger.error(f"Error fetching audit history: {e}")
        return []
    finally:
        cursor.close()
        conn.close()


def get_project_audit_by_id(audit_id: str) -> Optional[Dict[str, Any]]:
    """Retrieves a specific audit log by its unique audit_id."""
    sync_remote_audits_to_local(limit=30)
    conn = get_db_connection()
    cursor = conn.cursor()
    use_pg = is_postgres_connection(conn)
    try:
        placeholder = "%s" if use_pg else "?"
        cursor.execute(f"SELECT * FROM project_audit_logs WHERE audit_id = {placeholder};", (audit_id,))
        row = cursor.fetchone()
        if not row:
            return None
        return clean_audit_row(cursor, row)
    except Exception as e:
        logger.error(f"Error fetching audit by id {audit_id}: {e}")
        return None
    finally:
        cursor.close()
        conn.close()


def prune_old_project_audit_logs(keep_last: int = 90, max_age_days: int = 45) -> Dict[str, int]:
    """Prunes project_audit_logs retaining the keep_last newest runs and removes audit files older than max_age_days."""
    conn = get_db_connection()
    cursor = conn.cursor()
    use_pg = is_postgres_connection(conn)
    deleted_db_rows = 0
    try:
        placeholder = "%s" if use_pg else "?"
        cursor.execute(f"SELECT id FROM project_audit_logs ORDER BY id DESC LIMIT 1 OFFSET {placeholder};", (keep_last,))
        row = cursor.fetchone()
        if row:
            cutoff_id = row[0]
            cursor.execute(f"DELETE FROM project_audit_logs WHERE id <= {placeholder};", (cutoff_id,))
            deleted_db_rows = cursor.rowcount
            conn.commit()
            logger.info("Pruned %d old project audit logs from database (retaining %d newest runs).", deleted_db_rows, keep_last)
    except Exception as e:
        logger.error("Error pruning old project audit logs from database: %s", e)
        try:
            conn.rollback()
        except Exception as rb_err:
            logger.debug("Rollback notice in prune_old_project_audit_logs: %s", rb_err)
    finally:
        cursor.close()
        conn.close()

    deleted_files = 0
    try:
        import time
        from pathlib import Path
        audits_dir = Path(__file__).resolve().parent.parent.parent / "audits"
        if audits_dir.exists():
            cutoff_time = time.time() - (max_age_days * 86400)
            for f in audits_dir.glob("project_audit_*.md"):
                if f.is_file() and f.stat().st_mtime < cutoff_time:
                    try:
                        f.unlink()
                        deleted_files += 1
                    except Exception as fe:
                        logger.debug("Failed unlinking old audit file %s: %s", f, fe)
            if deleted_files > 0:
                logger.info("Pruned %d markdown dossiers from audits/ older than %d days.", deleted_files, max_age_days)
    except Exception as file_err:
        logger.warning("Error pruning old audit files: %s", file_err)

    return {"deleted_db_rows": deleted_db_rows, "deleted_files": deleted_files}

