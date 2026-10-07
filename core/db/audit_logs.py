"""Database Repository for Autonomous Project Audit Logs.

Supports dual-binding for local SQLite and production PostgreSQL (Supabase / Render).
Maintains permanent audit logs of all strategic, technical, and UI/UX audits.
"""

import json
import logging
from decimal import Decimal
from datetime import datetime, date
from typing import Optional, List, Dict, Any

from core.db.connection import get_db_connection, get_supabase_url

def is_supabase_enabled() -> bool:
    return bool(get_supabase_url())

logger = logging.getLogger(__name__)


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
            except Exception:
                d[target_field] = [] if "s" in target_field else {}
        elif target_field not in d:
            d[target_field] = [] if "s" in target_field else {}

    return d


def save_project_audit_log(audit: Dict[str, Any]) -> bool:
    """Inserts an autonomous project audit log into the database."""
    conn = get_db_connection()
    cursor = conn.cursor()
    use_pg = is_supabase_enabled()

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
                audit.get("audit_engine", "google-antigravity-sdk"),
            ))
        else:
            query = """
                INSERT OR REPLACE INTO project_audit_logs (
                    audit_id, overall_score, strategy_score, implementation_score, uiux_score,
                    status, tests_total, tests_passed, tests_failed,
                    endpoints_checked, endpoints_healthy,
                    critical_violations_json, recommendations_json, pillar_breakdown_json,
                    full_markdown_report, audit_engine, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'));
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
                audit.get("audit_engine", "google-antigravity-sdk"),
            ))
        conn.commit()
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
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT * FROM project_audit_logs ORDER BY id DESC LIMIT 1;")
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
    conn = get_db_connection()
    cursor = conn.cursor()
    use_pg = is_supabase_enabled()
    try:
        placeholder = "%s" if use_pg else "?"
        cursor.execute(f"SELECT * FROM project_audit_logs ORDER BY id DESC LIMIT {placeholder};", (limit,))
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
    conn = get_db_connection()
    cursor = conn.cursor()
    use_pg = is_supabase_enabled()
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
