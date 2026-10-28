"""Stateful Remediation Ledger Database Repository.

Tracks the full lifecycle of audit findings across continuous runs:
OPEN -> RE_EVALUATING -> RESOLVED

Provides:
- Deterministic deduplication via finding_hash.
- Verification attempt and failure pass counters.
- Dynamic age calculation (age_in_days) and progressive aging multipliers.
- Dual-binding database support for local SQLite and production PostgreSQL (Supabase / Render).
"""

import json
import hashlib
import logging
import os
import urllib.request
from decimal import Decimal
from datetime import datetime, date
from typing import Dict, Any, List, Optional

from core.db.connection import get_db_connection, is_postgres_connection, IST, now_ist_iso
from core.presentation.formatters import _coerce_datetime

logger = logging.getLogger("equity_research.core.db.remediation")


def _push_remediation_row_to_supabase_rest(cleaned_row: Dict[str, Any]) -> bool:
    """Mirrors a remediation ledger row to Supabase via PostgREST when local SQLite is primary."""
    from core.db.connection import _is_unit_test_runtime
    if not cleaned_row or _is_unit_test_runtime():
        return False
    try:
        from core.db.audit_logs import _get_supabase_rest_credentials, _build_ssl_context
        creds = _get_supabase_rest_credentials()
        if not creds:
            return False
        sb_url, sb_key = creds
        url = f"{sb_url}/rest/v1/audit_remediation_ledger?on_conflict=finding_hash"
        payload = {
            "finding_hash": cleaned_row.get("finding_hash"),
            "category": cleaned_row.get("category", "BACKEND_STABILITY"),
            "invariant_name": cleaned_row.get("invariant_name", "general_invariant"),
            "title": cleaned_row.get("title", ""),
            "description": cleaned_row.get("description", ""),
            "target_file_or_route": cleaned_row.get("target_file_or_route", "general"),
            "severity": cleaned_row.get("severity", "MEDIUM"),
            "status": cleaned_row.get("status", "OPEN"),
            "verification_attempts": int(cleaned_row.get("verification_attempts", 1)),
            "consecutive_failures": int(cleaned_row.get("consecutive_failures", 0)),
            "first_detected_at": cleaned_row.get("first_detected_at"),
            "last_verified_at": cleaned_row.get("last_verified_at"),
            "resolved_at": cleaned_row.get("resolved_at"),
            "remediation_notes": cleaned_row.get("remediation_notes") or "",
            "finding_metadata_json": cleaned_row.get("finding_metadata_json") or json.dumps(cleaned_row.get("metadata", {})),
        }
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
        logger.warning("Supabase REST remediation push notice for %s: %s", cleaned_row.get("finding_hash"), e)
        return False

SEVERITY_BASE_POINTS = {
    "CRITICAL": 15.0,
    "HIGH": 8.0,
    "MEDIUM": 4.0,
    "LOW": 1.0,
}


def compute_finding_hash(category: str, invariant_name: str, target: str) -> str:
    """Computes a deterministic SHA256 hash identifying a unique invariant violation."""
    raw = f"{str(category).strip().upper()}:{str(invariant_name).strip()}:{str(target).strip()}".encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:32]


def _clean_remediation_row(cursor, row: Any) -> Dict[str, Any]:
    """Normalizes an SQLite or psycopg2 row into a clean dictionary."""
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

    if "finding_metadata_json" in d and isinstance(d["finding_metadata_json"], str):
        try:
            d["metadata"] = json.loads(d["finding_metadata_json"])
        except Exception as e:
            logger.debug("Failed parsing finding_metadata_json: %s", e)
            d["metadata"] = {}
    elif "metadata" not in d:
        d["metadata"] = {}

    # Calculate age in days and progressive multiplier dynamically
    now_ist = datetime.now(IST)
    first_detected_str = d.get("first_detected_at")
    age_days = 0.0
    if first_detected_str:
        dt = _coerce_datetime(first_detected_str)
        if dt is not None:
            age_days = max(round((now_ist - dt).total_seconds() / 86400.0, 1), 0.0)

    d["age_in_days"] = age_days

    # Progressive aging multiplier:
    # 1.0x (<3 days), 1.5x (>=3 days), 2.0x (>=7 days)
    if age_days >= 7.0:
        aging_mult = 2.0
    elif age_days >= 3.0:
        aging_mult = 1.5
    else:
        aging_mult = 1.0

    d["aging_multiplier"] = aging_mult

    severity = str(d.get("severity", "MEDIUM")).upper()
    base_deduction = SEVERITY_BASE_POINTS.get(severity, 4.0)
    d["base_deduction"] = base_deduction
    d["effective_penalty"] = round(base_deduction * aging_mult, 1)

    return d


def record_or_update_finding(
    finding: Dict[str, Any],
    conn: Optional[Any] = None,
    cursor: Optional[Any] = None,
    commit: bool = True
) -> Dict[str, Any]:
    """Records a new finding or updates an existing one with failed verification passes."""
    owns_conn = False
    if conn is None:
        conn = get_db_connection()
        cursor = conn.cursor()
        owns_conn = True
    elif cursor is None:
        cursor = conn.cursor()

    use_pg = is_postgres_connection(conn)

    category = str(finding.get("category", "BACKEND_STABILITY")).strip().upper()
    invariant_name = str(finding.get("invariant_name", "general_invariant")).strip()
    target = str(finding.get("target_file_or_route", "general")).strip()
    title = str(finding.get("title", f"Defect in {invariant_name}")).strip()[:255]
    desc = str(finding.get("description", "")).strip()
    severity = str(finding.get("severity", "MEDIUM")).strip().upper()
    notes = finding.get("remediation_notes") or ""
    metadata_json = json.dumps(finding.get("metadata", {}))

    finding_hash = finding.get("finding_hash") or compute_finding_hash(category, invariant_name, target)

    try:
        # Check if record already exists
        cursor.execute("SELECT id, status, verification_attempts, consecutive_failures FROM audit_remediation_ledger WHERE finding_hash = ?;" if not use_pg else "SELECT id, status, verification_attempts, consecutive_failures FROM audit_remediation_ledger WHERE finding_hash = %s;", (finding_hash,))
        existing = cursor.fetchone()

        if existing:
            row_id, old_status, old_attempts, old_failures = existing[0], existing[1], existing[2], existing[3]
            new_attempts = int(old_attempts or 0) + 1
            new_failures = (int(old_failures or 0) + 1) if old_status != "RESOLVED" else 1

            if use_pg:
                update_sql = """
                    UPDATE audit_remediation_ledger
                    SET title = %s, description = %s, severity = %s,
                        status = 'OPEN',
                        verification_attempts = %s,
                        consecutive_failures = %s,
                        last_verified_at = now(),
                        resolved_at = NULL,
                        remediation_notes = %s,
                        finding_metadata_json = %s
                    WHERE finding_hash = %s;
                """
                cursor.execute(update_sql, (title, desc, severity, new_attempts, new_failures, notes, metadata_json, finding_hash))
            else:
                now_ts = now_ist_iso()
                update_sql = """
                    UPDATE audit_remediation_ledger
                    SET title = ?, description = ?, severity = ?,
                        status = 'OPEN',
                        verification_attempts = ?,
                        consecutive_failures = ?,
                        last_verified_at = ?,
                        resolved_at = NULL,
                        remediation_notes = ?,
                        finding_metadata_json = ?
                    WHERE finding_hash = ?;
                """
                cursor.execute(update_sql, (title, desc, severity, new_attempts, new_failures, now_ts, notes, metadata_json, finding_hash))
        else:
            if use_pg:
                insert_sql = """
                    INSERT INTO audit_remediation_ledger (
                        finding_hash, category, invariant_name, title, description,
                        target_file_or_route, severity, status, verification_attempts,
                        consecutive_failures, first_detected_at, last_verified_at,
                        resolved_at, remediation_notes, finding_metadata_json
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, 'OPEN', 1, 1, now(), now(), NULL, %s, %s);
                """
                cursor.execute(insert_sql, (finding_hash, category, invariant_name, title, desc, target, severity, notes, metadata_json))
            else:
                now_ts = now_ist_iso()
                insert_sql = """
                    INSERT INTO audit_remediation_ledger (
                        finding_hash, category, invariant_name, title, description,
                        target_file_or_route, severity, status, verification_attempts,
                        consecutive_failures, first_detected_at, last_verified_at,
                        resolved_at, remediation_notes, finding_metadata_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, 'OPEN', 1, 1, ?, ?, NULL, ?, ?);
                """
                cursor.execute(insert_sql, (finding_hash, category, invariant_name, title, desc, target, severity, now_ts, now_ts, notes, metadata_json))

        if commit:
            conn.commit()

        # Fetch and return normalized record
        cursor.execute("SELECT * FROM audit_remediation_ledger WHERE finding_hash = ?;" if not use_pg else "SELECT * FROM audit_remediation_ledger WHERE finding_hash = %s;", (finding_hash,))
        updated_row = cursor.fetchone()
        cleaned = _clean_remediation_row(cursor, updated_row)
        if not use_pg and commit:
            _push_remediation_row_to_supabase_rest(cleaned)
        return cleaned
    except Exception as e:
        logger.error(f"Error recording or updating remediation finding {finding_hash}: {e}")
        if commit:
            try:
                conn.rollback()
            except Exception as rb_err:
                logger.debug(f"Rollback notice for {finding_hash}: {rb_err}")
        return {}
    finally:
        if owns_conn:
            try:
                cursor.close()
            except Exception as c_err:
                logger.debug(f"Cursor close notice: {c_err}")
            try:
                conn.close()
            except Exception as conn_err:
                logger.debug(f"Conn close notice: {conn_err}")


def record_findings_batch(findings: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Records or updates multiple findings in a single atomic database transaction."""
    if not findings:
        return []
    conn = get_db_connection()
    use_pg = is_postgres_connection(conn)
    cursor = conn.cursor()
    results = []
    try:
        for finding in findings:
            res = record_or_update_finding(finding, conn=conn, cursor=cursor, commit=False)
            if res:
                results.append(res)
        conn.commit()
        if not use_pg:
            for r in results:
                _push_remediation_row_to_supabase_rest(r)
        return results
    except Exception as e:
        logger.error(f"Error in record_findings_batch: {e}")
        try:
            conn.rollback()
        except Exception as rb_err:
            logger.debug(f"Rollback notice: {rb_err}")
        return []
    finally:
        try:
            cursor.close()
        except Exception as c_err:
            logger.debug(f"Cursor close notice: {c_err}")
        try:
            conn.close()
        except Exception as conn_err:
            logger.debug(f"Conn close notice: {conn_err}")


def get_open_remediation_findings() -> List[Dict[str, Any]]:
    """Returns all currently active (OPEN or RE_EVALUATING) remediation findings."""
    conn = get_db_connection()
    use_pg = is_postgres_connection(conn)
    cursor = conn.cursor()
    try:
        cursor.execute("""
            SELECT * FROM audit_remediation_ledger
            WHERE status IN ('OPEN', 'RE_EVALUATING')
            ORDER BY first_detected_at ASC;
        """)
        rows = cursor.fetchall()
        cleaned = [_clean_remediation_row(cursor, r) for r in rows]
        # Sort by effective_penalty DESC, then age_in_days DESC
        cleaned.sort(key=lambda x: (x.get("effective_penalty", 0.0), x.get("age_in_days", 0.0)), reverse=True)
        return cleaned
    except Exception as e:
        logger.error(f"Error fetching open remediation findings: {e}")
        return []
    finally:
        try:
            cursor.close()
        except Exception as c_err:
            logger.debug(f"Cursor close notice: {c_err}")
        try:
            conn.close()
        except Exception as conn_err:
            logger.debug(f"Conn close notice: {conn_err}")


def mark_finding_re_evaluating(finding_hash: str) -> bool:
    """Sets a finding's status to RE_EVALUATING as part of the Verify First cycle."""
    conn = get_db_connection()
    use_pg = is_postgres_connection(conn)
    cursor = conn.cursor()
    use_pg = is_postgres_connection(conn)
    try:
        if use_pg:
            cursor.execute(
                "UPDATE audit_remediation_ledger SET status = 'RE_EVALUATING', last_verified_at = now() WHERE finding_hash = %s;",
                (finding_hash,),
            )
        else:
            cursor.execute(
                "UPDATE audit_remediation_ledger SET status = 'RE_EVALUATING', last_verified_at = ? WHERE finding_hash = ?;",
                (now_ist_iso(), finding_hash),
            )
        conn.commit()
        if not use_pg:
            cursor.execute("SELECT * FROM audit_remediation_ledger WHERE finding_hash = ?;", (finding_hash,))
            row = cursor.fetchone()
            if row:
                _push_remediation_row_to_supabase_rest(_clean_remediation_row(cursor, row))
        return True
    except Exception as e:
        logger.error(f"Error marking finding {finding_hash} RE_EVALUATING: {e}")
        try:
            conn.rollback()
        except Exception as rb_err:
            logger.debug(f"Rollback notice for {finding_hash}: {rb_err}")
        return False
    finally:
        try:
            cursor.close()
        except Exception as c_err:
            logger.debug(f"Cursor close notice: {c_err}")
        try:
            conn.close()
        except Exception as conn_err:
            logger.debug(f"Conn close notice: {conn_err}")


def mark_finding_resolved(finding_hash: str, notes: Optional[str] = None) -> bool:
    """Marks an invariant violation as RESOLVED and records the resolution timestamp."""
    conn = get_db_connection()
    use_pg = is_postgres_connection(conn)
    cursor = conn.cursor()
    use_pg = is_postgres_connection(conn)
    try:
        if use_pg:
            sql = """
                UPDATE audit_remediation_ledger
                SET status = 'RESOLVED',
                    resolved_at = now(),
                    consecutive_failures = 0,
                    verification_attempts = verification_attempts + 1,
                    remediation_notes = COALESCE(%s, remediation_notes)
                WHERE finding_hash = %s;
            """
            cursor.execute(sql, (notes, finding_hash))
        else:
            sql = """
                UPDATE audit_remediation_ledger
                SET status = 'RESOLVED',
                    resolved_at = ?,
                    consecutive_failures = 0,
                    verification_attempts = verification_attempts + 1,
                    remediation_notes = COALESCE(?, remediation_notes)
                WHERE finding_hash = ?;
            """
            cursor.execute(sql, (now_ist_iso(), notes, finding_hash))
        conn.commit()
        if not use_pg:
            cursor.execute("SELECT * FROM audit_remediation_ledger WHERE finding_hash = ?;", (finding_hash,))
            row = cursor.fetchone()
            if row:
                _push_remediation_row_to_supabase_rest(_clean_remediation_row(cursor, row))
        logger.info(f"Remediation finding {finding_hash} successfully marked RESOLVED.")
        return True
    except Exception as e:
        logger.error(f"Error marking finding {finding_hash} RESOLVED: {e}")
        try:
            conn.rollback()
        except Exception as rb_err:
            logger.debug(f"Rollback notice for {finding_hash}: {rb_err}")
        return False
    finally:
        try:
            cursor.close()
        except Exception as c_err:
            logger.debug(f"Cursor close notice: {c_err}")
        try:
            conn.close()
        except Exception as conn_err:
            logger.debug(f"Conn close notice: {conn_err}")


def get_all_remediation_findings(limit: int = 100, status_filter: Optional[str] = None) -> List[Dict[str, Any]]:
    """Retrieves remediation ledger entries with optional status filtering."""
    conn = get_db_connection()
    use_pg = is_postgres_connection(conn)
    cursor = conn.cursor()
    use_pg = is_postgres_connection(conn)
    try:
        if status_filter:
            sql = "SELECT * FROM audit_remediation_ledger WHERE status = ? ORDER BY first_detected_at DESC LIMIT ?;" if not use_pg else "SELECT * FROM audit_remediation_ledger WHERE status = %s ORDER BY first_detected_at DESC LIMIT %s;"
            cursor.execute(sql, (status_filter, limit))
        else:
            sql = "SELECT * FROM audit_remediation_ledger ORDER BY first_detected_at DESC LIMIT ?;" if not use_pg else "SELECT * FROM audit_remediation_ledger ORDER BY first_detected_at DESC LIMIT %s;"
            cursor.execute(sql, (limit,))
        rows = cursor.fetchall()
        return [_clean_remediation_row(cursor, r) for r in rows]
    except Exception as e:
        logger.error(f"Error querying remediation findings: {e}")
        return []
    finally:
        try:
            cursor.close()
        except Exception as c_err:
            logger.debug(f"Cursor close notice: {c_err}")
        try:
            conn.close()
        except Exception as conn_err:
            logger.debug(f"Conn close notice: {conn_err}")


def get_remediation_summary_stats() -> Dict[str, Any]:
    """Computes high-level triage statistics across the remediation ledger."""
    open_findings = get_open_remediation_findings()
    all_findings = get_all_remediation_findings(limit=500)

    total_open = len(open_findings)
    critical_open = sum(1 for f in open_findings if f.get("severity") == "CRITICAL")
    high_open = sum(1 for f in open_findings if f.get("severity") == "HIGH")
    medium_open = sum(1 for f in open_findings if f.get("severity") == "MEDIUM")
    low_open = sum(1 for f in open_findings if f.get("severity") == "LOW")

    aging_over_3d = sum(1 for f in open_findings if f.get("age_in_days", 0.0) >= 3.0)
    aging_over_7d = sum(1 for f in open_findings if f.get("age_in_days", 0.0) >= 7.0)

    resolved_total = sum(1 for f in all_findings if f.get("status") == "RESOLVED")
    total_penalty = sum(f.get("effective_penalty", 0.0) for f in open_findings)

    return {
        "total_open": total_open,
        "critical_open": critical_open,
        "high_open": high_open,
        "medium_open": medium_open,
        "low_open": low_open,
        "aging_over_3d": aging_over_3d,
        "aging_over_7d": aging_over_7d,
        "resolved_total": resolved_total,
        "total_penalty": round(total_penalty, 1),
    }
