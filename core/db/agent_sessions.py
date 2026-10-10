"""Database Repository for Sitewide Autonomous Agent Sessions & Event Ledgers.

Supports dual-binding for SQLite and PostgreSQL (Supabase / Render).
Provides persistence for multi-turn conversations, tool traces, and proactive trigger events.
"""

import os
import json
import logging
from decimal import Decimal
from datetime import datetime, date, timezone
from typing import Optional, List, Dict, Any

from core.db.connection import get_db_connection, get_supabase_url

def is_supabase_enabled() -> bool:
    return bool(get_supabase_url())

logger = logging.getLogger(__name__)


def clean_row(cursor, row: Any) -> Dict[str, Any]:
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

    if "tool_calls_json" in d and isinstance(d["tool_calls_json"], str):
        try:
            d["tool_calls"] = json.loads(d["tool_calls_json"])
        except Exception:
            d["tool_calls"] = []
    if "metadata_json" in d and isinstance(d["metadata_json"], str):
        try:
            d["metadata"] = json.loads(d["metadata_json"])
        except Exception:
            d["metadata"] = {}

    return d


def create_or_get_agent_conversation(
    conversation_id: str,
    user_id: Optional[str] = None,
    agent_type: str = "equity_copilot",
    context_ticker: Optional[str] = None
) -> Dict[str, Any]:
    """Retrieves an existing conversation or initializes a new one."""
    conn = get_db_connection()
    cursor = conn.cursor()
    use_pg = is_supabase_enabled()

    try:
        placeholder = "%s" if use_pg else "?"
        cursor.execute(f"SELECT * FROM agent_conversations WHERE conversation_id = {placeholder};", (conversation_id,))
        row = cursor.fetchone()
        if row:
            return clean_row(cursor, row)

        if use_pg:
            query = """
                INSERT INTO agent_conversations (
                    conversation_id, user_id, agent_type, context_ticker, turn_count, total_tokens, created_at, updated_at
                ) VALUES (%s, %s, %s, %s, 0, 0, now(), now())
                RETURNING *;
            """
            cursor.execute(query, (conversation_id, user_id, agent_type, context_ticker))
            new_row = cursor.fetchone()
        else:
            query = """
                INSERT INTO agent_conversations (
                    conversation_id, user_id, agent_type, context_ticker, turn_count, total_tokens, created_at, updated_at
                ) VALUES (?, ?, ?, ?, 0, 0, datetime('now'), datetime('now'));
            """
            cursor.execute(query, (conversation_id, user_id, agent_type, context_ticker))
            cursor.execute("SELECT * FROM agent_conversations WHERE conversation_id = ?;", (conversation_id,))
            new_row = cursor.fetchone()

        conn.commit()
        return clean_row(cursor, new_row)
    except Exception as e:
        logger.error(f"Error in create_or_get_agent_conversation: {e}")
        conn.rollback()
        return {"conversation_id": conversation_id, "agent_type": agent_type, "error": str(e)}
    finally:
        cursor.close()
        conn.close()


def append_conversation_turn(
    conversation_id: str,
    sender_role: str,
    content: str,
    tool_calls: Optional[List[Dict[str, Any]]] = None
) -> bool:
    """Appends a dialogue turn to the conversation history and increments turn counter."""
    conn = get_db_connection()
    cursor = conn.cursor()
    use_pg = is_supabase_enabled()
    tool_calls_json = json.dumps(tool_calls or [])

    try:
        placeholder = "%s" if use_pg else "?"
        cursor.execute(f"SELECT COUNT(*) FROM agent_conversation_turns WHERE conversation_id = {placeholder};", (conversation_id,))
        count_row = cursor.fetchone()
        turn_index = (count_row[0] if count_row else 0) + 1

        if use_pg:
            cursor.execute("""
                INSERT INTO agent_conversation_turns (
                    conversation_id, turn_index, sender_role, content, tool_calls_json, created_at
                ) VALUES (%s, %s, %s, %s, %s, now());
            """, (conversation_id, turn_index, sender_role, content, tool_calls_json))
            cursor.execute("""
                UPDATE agent_conversations
                SET turn_count = turn_count + 1, updated_at = now()
                WHERE conversation_id = %s;
            """, (conversation_id,))
        else:
            cursor.execute("""
                INSERT INTO agent_conversation_turns (
                    conversation_id, turn_index, sender_role, content, tool_calls_json, created_at
                ) VALUES (?, ?, ?, ?, ?, datetime('now'));
            """, (conversation_id, turn_index, sender_role, content, tool_calls_json))
            cursor.execute("""
                UPDATE agent_conversations
                SET turn_count = turn_count + 1, updated_at = datetime('now')
                WHERE conversation_id = ?;
            """, (conversation_id,))

        conn.commit()
        return True
    except Exception as e:
        logger.error(f"Error appending conversation turn: {e}")
        conn.rollback()
        return False
    finally:
        cursor.close()
        conn.close()


def get_conversation_turns(conversation_id: str, limit: int = 50) -> List[Dict[str, Any]]:
    """Retrieves chronological dialogue turns for a conversation."""
    conn = get_db_connection()
    cursor = conn.cursor()
    use_pg = is_supabase_enabled()

    try:
        placeholder = "%s" if use_pg else "?"
        cursor.execute(f"""
            SELECT * FROM agent_conversation_turns
            WHERE conversation_id = {placeholder}
            ORDER BY turn_index ASC
            LIMIT {limit};
        """, (conversation_id,))
        rows = cursor.fetchall()
        return [clean_row(cursor, r) for r in rows]
    except Exception as e:
        logger.error(f"Error fetching conversation turns: {e}")
        return []
    finally:
        cursor.close()
        conn.close()


def record_autonomous_event(
    event_type: str,
    ticker: Optional[str],
    trigger_source: str,
    action_taken: str,
    summary: str,
    metadata: Optional[Dict[str, Any]] = None
) -> str:
    """Records an autonomous trigger or background watcher event into the ledger."""
    conn = get_db_connection()
    cursor = conn.cursor()
    use_pg = is_supabase_enabled()
    event_id = f"EVT-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}-{os.urandom(3).hex()}"
    metadata_json = json.dumps(metadata or {})

    try:
        if use_pg:
            cursor.execute("""
                INSERT INTO autonomous_event_ledger (
                    event_id, event_type, ticker, trigger_source, action_taken, summary, metadata_json, created_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, now());
            """, (event_id, event_type, ticker, trigger_source, action_taken, summary, metadata_json))
        else:
            cursor.execute("""
                INSERT INTO autonomous_event_ledger (
                    event_id, event_type, ticker, trigger_source, action_taken, summary, metadata_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now'));
            """, (event_id, event_type, ticker, trigger_source, action_taken, summary, metadata_json))
        conn.commit()
        return event_id
    except Exception as e:
        logger.error(f"Error recording autonomous event: {e}")
        conn.rollback()
        return ""
    finally:
        cursor.close()
        conn.close()


def get_recent_autonomous_events(
    limit: int = 25, 
    event_type: Optional[str] = None,
    include_test_events: bool = False
) -> List[Dict[str, Any]]:
    """Retrieves recent autonomous trigger actions from the event ledger."""
    conn = get_db_connection()
    cursor = conn.cursor()
    use_pg = is_supabase_enabled()

    try:
        base_filter = """
            (ticker IS NULL OR (ticker NOT LIKE '%TEST%' AND ticker NOT LIKE '%UNITTEST%'))
            AND (trigger_source IS NULL OR trigger_source NOT IN ('unit_test', 'TEST_SUITE_ROTATION'))
        """
        if event_type:
            placeholder = "%s" if use_pg else "?"
            if include_test_events:
                cursor.execute(f"""
                    SELECT * FROM autonomous_event_ledger
                    WHERE event_type = {placeholder}
                    ORDER BY id DESC LIMIT {limit};
                """, (event_type,))
            else:
                cursor.execute(f"""
                    SELECT * FROM autonomous_event_ledger
                    WHERE event_type = {placeholder} AND {base_filter}
                    ORDER BY id DESC LIMIT {limit};
                """, (event_type,))
        else:
            if include_test_events:
                cursor.execute(f"""
                    SELECT * FROM autonomous_event_ledger 
                    ORDER BY id DESC LIMIT {limit};
                """)
            else:
                cursor.execute(f"""
                    SELECT * FROM autonomous_event_ledger 
                    WHERE {base_filter}
                    ORDER BY id DESC LIMIT {limit};
                """)
        rows = cursor.fetchall()
        return [clean_row(cursor, r) for r in rows]
    except Exception as e:
        logger.error(f"Error fetching autonomous events: {e}")
        return []
    finally:
        cursor.close()
        conn.close()
