"""Database persistence layer for Research Bouquet & Morning Digest dispatches and subscriber management."""

import os
import uuid
import secrets
import logging
from typing import List, Dict, Any, Optional

from core.db.connection import get_db_connection, get_placeholder, init_db, is_postgres_connection

logger = logging.getLogger("equity_research.core.db.digest")


def _generate_unsubscribe_token() -> str:
    """Generates a secure, URL-safe random token for 1-click unsubscribe links."""
    return f"unsub_{secrets.token_urlsafe(32)}"


def get_active_digest_subscribers(only_active_pro: bool = False) -> List[Dict[str, Any]]:
    """
    Retrieves all registered users eligible for Research Bouquet digest emails.
    Filters out users who have unsubscribed.
    Branches SQL query between PostgreSQL and SQLite to prevent boolean=integer type mismatches:
      - PostgreSQL: WHERE is_digest_subscribed IS TRUE AND (is_subscriber IS TRUE OR subscription_expires_at > NOW())
      - SQLite: WHERE (is_digest_subscribed = 1 OR is_digest_subscribed IS NULL) AND (is_subscriber = 1 OR subscription_expires_at > datetime('now'))
    """
    init_db()
    conn = get_db_connection()
    cursor = conn.cursor()
    p = get_placeholder()

    try:
        is_pg = is_postgres_connection(conn)
        if is_pg:
            if only_active_pro:
                query = """
                    SELECT id, email, full_name, credits_balance, subscription_tier, 
                           is_subscriber, is_digest_subscribed, digest_unsubscribe_token, created_at
                    FROM user_accounts
                    WHERE is_digest_subscribed IS TRUE
                      AND (is_subscriber IS TRUE OR (subscription_expires_at IS NOT NULL AND subscription_expires_at > NOW()))
                      AND email IS NOT NULL AND email != ''
                """
            else:
                query = """
                    SELECT id, email, full_name, credits_balance, subscription_tier, 
                           is_subscriber, is_digest_subscribed, digest_unsubscribe_token, created_at
                    FROM user_accounts
                    WHERE (is_digest_subscribed IS TRUE OR is_digest_subscribed IS NULL)
                      AND email IS NOT NULL AND email != ''
                """
        else:
            if only_active_pro:
                query = """
                    SELECT id, email, full_name, credits_balance, subscription_tier, 
                           is_subscriber, is_digest_subscribed, digest_unsubscribe_token, created_at
                    FROM user_accounts
                    WHERE (is_digest_subscribed = 1 OR is_digest_subscribed IS NULL)
                      AND (is_subscriber = 1 OR (subscription_expires_at IS NOT NULL AND subscription_expires_at > datetime('now')))
                      AND email IS NOT NULL AND email != ''
                """
            else:
                query = """
                    SELECT id, email, full_name, credits_balance, subscription_tier, 
                           is_subscriber, is_digest_subscribed, digest_unsubscribe_token, created_at
                    FROM user_accounts
                    WHERE (is_digest_subscribed = 1 OR is_digest_subscribed IS NULL)
                      AND email IS NOT NULL AND email != ''
                """

        query += " ORDER BY created_at DESC;"
        cursor.execute(query)
        rows = cursor.fetchall()

        subscribers = []
        tokens_to_backfill = []

        for r in rows:
            uid = r[0]
            email = r[1]
            name = r[2] or email.split("@")[0].capitalize()
            bal = float(r[3] or 0.0)
            tier = r[4] or "free"
            is_sub = bool(r[5])
            is_digest_sub = bool(r[6] if r[6] is not None else True)
            token = r[7]

            if not token:
                token = _generate_unsubscribe_token()
                tokens_to_backfill.append((token, uid))

            subscribers.append({
                "id": uid,
                "email": email,
                "full_name": name,
                "credits_balance": bal,
                "subscription_tier": tier,
                "is_subscriber": is_sub,
                "is_digest_subscribed": is_digest_sub,
                "unsubscribe_token": token,
                "created_at": str(r[8]) if r[8] else ""
            })

        # Backfill tokens if any were generated
        if tokens_to_backfill:
            for tok, uid in tokens_to_backfill:
                cursor.execute(f"UPDATE user_accounts SET digest_unsubscribe_token = {p} WHERE id = {p};", (tok, uid))
            conn.commit()

        return subscribers
    except Exception as e:
        logger.error(f"Error fetching digest subscribers: {e}")
        return []
    finally:
        cursor.close()
        conn.close()


get_digest_subscribers = get_active_digest_subscribers


def get_subscriber_by_token(token: str) -> Optional[Dict[str, Any]]:
    """Resolves subscriber by their unique unsubscribe token."""
    if not token or not str(token).strip():
        return None

    clean_token = str(token).strip()
    init_db()
    conn = get_db_connection()
    cursor = conn.cursor()
    p = get_placeholder()

    try:
        cursor.execute(
            f"""
            SELECT id, email, full_name, subscription_tier, is_digest_subscribed, digest_unsubscribe_token
            FROM user_accounts
            WHERE digest_unsubscribe_token = {p}
            LIMIT 1;
            """,
            (clean_token,)
        )
        r = cursor.fetchone()
        if not r:
            return None

        return {
            "id": r[0],
            "email": r[1],
            "full_name": r[2] or r[1].split("@")[0].capitalize(),
            "subscription_tier": r[3] or "free",
            "is_digest_subscribed": bool(r[4] if r[4] is not None else True),
            "unsubscribe_token": r[5]
        }
    except Exception as e:
        logger.error(f"Error resolving subscriber by token: {e}")
        return None
    finally:
        cursor.close()
        conn.close()


def set_user_digest_subscription(token_or_email: str, subscribe: bool) -> bool:
    """Updates user's digest subscription status using either their token or email."""
    if not token_or_email or not str(token_or_email).strip():
        return False

    val = str(token_or_email).strip()
    init_db()
    conn = get_db_connection()
    cursor = conn.cursor()
    p = get_placeholder()

    try:
        sub_val = bool(subscribe) if is_postgres_connection(conn) else (1 if subscribe else 0)
        cursor.execute(
            f"""
            UPDATE user_accounts 
            SET is_digest_subscribed = {p}
            WHERE digest_unsubscribe_token = {p} OR LOWER(email) = LOWER({p});
            """,
            (sub_val, val, val)
        )
        conn.commit()
        affected = cursor.rowcount
        return affected > 0
    except Exception as e:
        logger.error(f"Error setting digest subscription: {e}")
        return False
    finally:
        cursor.close()
        conn.close()


def record_digest_dispatch(
    edition_date: str,
    subject: str,
    recipients_count: int,
    delivered_count: int,
    failed_count: int,
    status: str = "COMPLETED",
    html_content: str = "",
    plain_text_content: str = "",
    dispatch_id: Optional[str] = None
) -> str:
    """Records an executed or test research bouquet dispatch in the database."""
    init_db()
    conn = get_db_connection()
    cursor = conn.cursor()
    p = get_placeholder()

    did = dispatch_id or f"dsp_{uuid.uuid4().hex[:12]}"
    try:
        cursor.execute(
            f"""
            INSERT INTO digest_dispatches (
                id, edition_date, subject, recipients_count, delivered_count, 
                failed_count, status, html_content, plain_text_content
            )
            VALUES ({p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p});
            """,
            (
                did, str(edition_date), str(subject), int(recipients_count),
                int(delivered_count), int(failed_count), str(status),
                str(html_content), str(plain_text_content)
            )
        )
        conn.commit()
        return did
    except Exception as e:
        logger.error(f"Error recording digest dispatch: {e}")
        return did
    finally:
        cursor.close()
        conn.close()


def get_digest_dispatch_history(limit: int = 15) -> List[Dict[str, Any]]:
    """Retrieves chronological dispatch history for the Admin Console."""
    init_db()
    conn = get_db_connection()
    cursor = conn.cursor()
    p = get_placeholder()

    try:
        cursor.execute(
            f"""
            SELECT id, edition_date, subject, recipients_count, delivered_count, 
                   failed_count, status, created_at
            FROM digest_dispatches
            ORDER BY created_at DESC
            LIMIT {p};
            """,
            (int(limit),)
        )
        rows = cursor.fetchall()
        return [
            {
                "id": r[0],
                "edition_date": r[1],
                "subject": r[2],
                "recipients_count": r[3],
                "delivered_count": r[4],
                "failed_count": r[5],
                "status": r[6],
                "created_at": str(r[7])[:19] if r[7] else ""
            }
            for r in rows
        ]
    except Exception as e:
        logger.error(f"Error fetching digest dispatch history: {e}")
        return []
    finally:
        cursor.close()
        conn.close()
