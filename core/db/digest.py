"""Database persistence layer for Research Bouquet & Morning Digest dispatches and subscriber management."""

import base64
import hashlib
import hmac
import os
import time
import uuid
from datetime import datetime, timedelta, timezone
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
                      AND (is_subscriber = 1 OR (subscription_expires_at IS NOT NULL AND datetime(subscription_expires_at) > datetime('now')))
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
        if subscribe:
            # Re-subscribing clears a bounce pause, but never a spam-complaint pause (admin only).
            cursor.execute(
                f"""
                UPDATE user_accounts
                SET is_digest_subscribed = {p}, digest_paused_reason = NULL, digest_paused_at = NULL
                WHERE (digest_unsubscribe_token = {p} OR LOWER(email) = LOWER({p}))
                  AND COALESCE(digest_paused_reason, '') <> 'complained';
                """,
                (sub_val, val, val)
            )
        else:
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


DIGEST_EDITION_KINDS = ("MARKET_CLOSE", "FUND_NAV")


def _normalize_edition_kind(edition_kind: Optional[str]) -> str:
    kind = str(edition_kind or "MARKET_CLOSE").strip().upper()
    if kind not in DIGEST_EDITION_KINDS:
        raise ValueError(f"Unknown digest edition kind: {edition_kind!r}")
    return kind


def ensure_digest_edition_kind_column(cursor, is_pg: bool) -> None:
    """Migration v053: adds `edition_kind` to digest_dispatches; legacy rows become MARKET_CLOSE."""
    if is_pg:
        cursor.execute(
            "ALTER TABLE digest_dispatches ADD COLUMN IF NOT EXISTS edition_kind VARCHAR(32) NOT NULL DEFAULT 'MARKET_CLOSE';"
        )
    else:
        cursor.execute("PRAGMA table_info(digest_dispatches);")
        cols = {str(r[1]) for r in cursor.fetchall()}
        if "edition_kind" not in cols:
            cursor.execute(
                "ALTER TABLE digest_dispatches ADD COLUMN edition_kind VARCHAR(32) NOT NULL DEFAULT 'MARKET_CLOSE';"
            )
    cursor.execute(
        "UPDATE digest_dispatches SET edition_kind = 'MARKET_CLOSE' WHERE edition_kind IS NULL OR edition_kind = '';"
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_digest_dispatches_date_kind ON digest_dispatches (edition_date, edition_kind, status);"
    )


def record_digest_dispatch(
    edition_date: str,
    subject: str,
    recipients_count: int,
    delivered_count: int,
    failed_count: int,
    status: str = "COMPLETED",
    html_content: str = "",
    plain_text_content: str = "",
    dispatch_id: Optional[str] = None,
    edition_kind: str = "MARKET_CLOSE",
) -> str:
    """Records an executed or test research bouquet dispatch in the database."""
    kind = _normalize_edition_kind(edition_kind)  # raises on an unknown kind before touching the DB
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
                failed_count, status, html_content, plain_text_content, edition_kind
            )
            VALUES ({p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p});
            """,
            (
                did, str(edition_date), str(subject), int(recipients_count),
                int(delivered_count), int(failed_count), str(status),
                str(html_content), str(plain_text_content), kind
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


EMAILER_CONTENT_LABELS: Dict[str, Dict[str, str]] = {
    "equity_card": {"label": "Listed Equities (Discovery Cohort)", "icon": "📈"},
    "sovereign_curve": {"label": "Sovereign Par Curve & SDL Spreads", "icon": "🏛️"},
    "corporate_debt": {"label": "Corporate Debt & Credit Surveillance", "icon": "🏦"},
    "etf_matrix": {"label": "National ETF Liquidity & Tracking Matrix", "icon": "📊"},
    "reits_sgb": {"label": "REITs, InvITs & Sovereign Gold Parity", "icon": "🏢"},
    "mutual_fund": {"label": "Mutual Fund Look-Through Spotlight", "icon": "💼"},
    "msme_spotlight": {"label": "Unlisted MSME Forensic Spotlight", "icon": "🏭"},
    "terminal_cta": {"label": "Primary CTA (Open Research Terminal)", "icon": "🚀"},
    "contact_desk": {"label": "Support Desk Ticket Reply Link", "icon": "📩"},
    "unsubscribe_return": {"label": "Unsubscribe Confirmation Return", "icon": "↩️"},
    "resubscribe_return": {"label": "Re-subscribe Confirmation Return", "icon": "✅"},
}


def _format_dwell_brief(seconds: float) -> str:
    sec = int(round(max(0.0, float(seconds or 0.0))))
    if sec < 60:
        return f"{sec}s"
    mins = sec // 60
    rem = sec % 60
    if mins < 60:
        return f"{mins}m {rem:02d}s" if rem else f"{mins}m"
    hrs = mins // 60
    rem_m = mins % 60
    return f"{hrs}h {rem_m:02d}m"


def get_emailer_utm_analytics() -> Dict[str, Any]:
    """
    Aggregates empirical UTM click-through sessions, unique verified subscriber refs (`sub_ref`),
    per-edition attribution, and per-asset-pillar (`utm_content`) reading dwell time across
    `site_usage_events`. Zero fabricated metrics: returns 0 / 0.0% when no clicks exist.
    """
    import json

    init_db()
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            SELECT id, session_id, details, event_type
            FROM site_usage_events
            WHERE details LIKE '%moatnomics_digest%'
               OR details LIKE '%moatnomics_support%'
               OR details LIKE '%research_bouquet%'
               OR details LIKE '%email_digest%'
               OR details LIKE '%email_support%'
               OR traffic_source IN ('moatnomics_digest', 'moatnomics_support', 'Email Digest (Bouquet)', 'Support Desk Email')
            ORDER BY timestamp ASC;
            """
        )
        rows = cursor.fetchall()
    except Exception as e:
        logger.debug("Emailer UTM analytics query notice: %s", e)
        rows = []
    finally:
        cursor.close()
        conn.close()

    session_meta: Dict[str, Dict[str, Any]] = {}
    for r in rows:
        eid, sess_id, det_raw, ev_type = r
        eff_sess = str(sess_id).strip() if sess_id and str(sess_id).strip() else f"anon_{eid}"
        det: Dict[str, Any] = {}
        if det_raw:
            try:
                det = json.loads(det_raw) if isinstance(det_raw, str) else det_raw
                if not isinstance(det, dict):
                    det = {}
            except Exception as parse_err:
                logger.debug("Emailer UTM details JSON parse notice: %s", parse_err)
                det = {}

        src = str(det.get("utm_source") or "").strip()
        med = str(det.get("utm_medium") or "").strip()
        camp = str(det.get("utm_campaign") or "").strip()
        content = str(det.get("utm_content") or "").strip()
        term = str(det.get("utm_term") or "").strip()
        sub_ref = str(det.get("sub_ref") or det.get("sub_tk") or "").strip()
        if sub_ref in ("preview_token", "test_admin_token"):
            sub_ref = ""

        sm = session_meta.setdefault(
            eff_sess,
            {
                "source": src or "moatnomics_digest",
                "medium": med or "email_digest",
                "campaign": camp or "research_bouquet",
                "content": content,
                "term": term,
                "sub_ref": sub_ref,
                "dwell_sec": 0.0,
            },
        )
        if src and not sm.get("source"):
            sm["source"] = src
        if med and not sm.get("medium"):
            sm["medium"] = med
        if camp and (not sm.get("campaign") or sm["campaign"] == "research_bouquet"):
            sm["campaign"] = camp
        if content and not sm.get("content"):
            sm["content"] = content
        if term and not sm.get("term"):
            sm["term"] = term
        if sub_ref and not sm.get("sub_ref"):
            sm["sub_ref"] = sub_ref

        if str(ev_type or "").upper() == "PAGE_DWELL":
            try:
                sm["dwell_sec"] += float(det.get("dwell_seconds") or det.get("duration_seconds") or 0.0)
            except (TypeError, ValueError):
                pass

    edition_stats: Dict[str, Dict[str, Any]] = {}
    content_stats: Dict[str, Dict[str, Any]] = {}
    all_click_sessions = len(session_meta)
    all_unique_clickers = set()
    total_dwell_sec = 0.0

    for s_id, sm in session_meta.items():
        clicker_key = sm["sub_ref"] if sm.get("sub_ref") else f"sess:{s_id}"
        all_unique_clickers.add(clicker_key)
        dwell_val = float(sm.get("dwell_sec") or 0.0)
        total_dwell_sec += dwell_val

        camp_str = str(sm.get("campaign") or "research_bouquet")
        ed_key = ""
        if camp_str.startswith("research_bouquet_") and len(camp_str) >= len("research_bouquet_YYYY-MM-DD"):
            ed_key = camp_str[len("research_bouquet_") : len("research_bouquet_") + 10]
        if ed_key:
            eb = edition_stats.setdefault(ed_key, {"sessions": 0, "unique_clickers": set(), "dwell_sec": 0.0})
            eb["sessions"] += 1
            eb["unique_clickers"].add(clicker_key)
            eb["dwell_sec"] += dwell_val

        c_key = sm.get("content") or ("contact_desk" if sm.get("source") == "moatnomics_support" else "terminal_cta")
        cb = content_stats.setdefault(
            c_key,
            {"sessions": 0, "unique_clickers": set(), "dwell_sec": 0.0, "terms": {}},
        )
        cb["sessions"] += 1
        cb["unique_clickers"].add(clicker_key)
        cb["dwell_sec"] += dwell_val
        if sm.get("term"):
            t_k = sm["term"]
            cb["terms"][t_k] = cb["terms"].get(t_k, 0) + 1

    asset_breakdown: List[Dict[str, Any]] = []
    denom_sessions = max(1, all_click_sessions)
    for c_key, cb in sorted(content_stats.items(), key=lambda x: (x[1]["sessions"], x[1]["dwell_sec"]), reverse=True):
        meta_info = EMAILER_CONTENT_LABELS.get(
            c_key,
            {"label": c_key.replace("_", " ").title(), "icon": "🔗"},
        )
        s_cnt = cb["sessions"]
        avg_dw = round(cb["dwell_sec"] / max(1, s_cnt), 1)
        top_term = max(cb["terms"].items(), key=lambda x: x[1])[0] if cb["terms"] else "-"
        asset_breakdown.append(
            {
                "content_key": c_key,
                "label": meta_info["label"],
                "icon": meta_info["icon"],
                "click_sessions": s_cnt,
                "unique_clickers": len(cb["unique_clickers"]),
                "share_pct": round((s_cnt / denom_sessions) * 100.0, 1),
                "avg_dwell_seconds": avg_dw,
                "formatted_avg_dwell": _format_dwell_brief(avg_dw),
                "top_term": top_term,
            }
        )

    overall_avg_dwell = round(total_dwell_sec / max(1, all_click_sessions), 1) if all_click_sessions else 0.0

    return {
        "total_click_sessions": all_click_sessions,
        "unique_clickers_count": len(all_unique_clickers),
        "avg_dwell_seconds": overall_avg_dwell,
        "formatted_avg_dwell": _format_dwell_brief(overall_avg_dwell),
        "asset_breakdown": asset_breakdown,
        "edition_stats": {
            k: {
                "click_sessions": v["sessions"],
                "unique_clickers": len(v["unique_clickers"]),
                "avg_dwell_seconds": round(v["dwell_sec"] / max(1, v["sessions"]), 1),
                "formatted_avg_dwell": _format_dwell_brief(round(v["dwell_sec"] / max(1, v["sessions"]), 1)),
            }
            for k, v in edition_stats.items()
        },
    }


def get_digest_dispatch_history(limit: int = 15) -> List[Dict[str, Any]]:
    """Retrieves chronological dispatch history for the Admin Console enriched with UTM click & CTR metrics."""
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
    except Exception as e:
        logger.error(f"Error fetching digest dispatch history: {e}")
        return []
    finally:
        cursor.close()
        conn.close()

    utm_analytics = get_emailer_utm_analytics()
    ed_map = utm_analytics.get("edition_stats", {})

    history: List[Dict[str, Any]] = []
    for r in rows:
        ed_date = str(r[1] or "")[:10]
        delivered = int(r[4] or 0)
        status_str = str(r[6] or "")
        ed_stat = ed_map.get(ed_date, {}) if status_str != "TEST_SENT" else {}
        click_sessions = int(ed_stat.get("click_sessions", 0))
        unique_clickers = int(ed_stat.get("unique_clickers", 0))
        ctr_pct = (
            min(100.0, round((unique_clickers / max(1, delivered)) * 100.0, 1))
            if delivered > 0 and unique_clickers > 0
            else 0.0
        )
        history.append(
            {
                "id": r[0],
                "edition_date": r[1],
                "subject": r[2],
                "recipients_count": r[3],
                "delivered_count": delivered,
                "failed_count": r[5],
                "status": status_str,
                "created_at": str(r[7])[:19] if r[7] else "",
                "click_sessions": click_sessions,
                "unique_clickers": unique_clickers,
                "ctr_pct": ctr_pct,
                "avg_dwell_seconds": ed_stat.get("avg_dwell_seconds", 0.0),
                "formatted_avg_dwell": ed_stat.get("formatted_avg_dwell", "0s"),
            }
        )
    return history


def has_edition_been_dispatched(edition_date: str, edition_kind: str = "MARKET_CLOSE") -> bool:
    """
    Idempotency guard: returns True if a broadcast of `edition_kind` for `edition_date` has
    already been recorded with status COMPLETED or PARTIAL in `digest_dispatches`.
    """
    if not edition_date or not str(edition_date).strip():
        return False

    clean_date = str(edition_date).strip()
    init_db()
    conn = get_db_connection()
    cursor = conn.cursor()
    p = get_placeholder()
    try:
        cursor.execute(
            f"""
            SELECT 1 FROM digest_dispatches
            WHERE edition_date = {p}
              AND edition_kind = {p}
              AND status IN ('COMPLETED', 'PARTIAL')
            LIMIT 1;
            """,
            (clean_date, _normalize_edition_kind(edition_kind)),
        )
        return cursor.fetchone() is not None
    except Exception as e:
        logger.error(f"Failed checking digest dispatch status for {clean_date}: {e}")
        return False
    finally:
        cursor.close()
        conn.close()



# --- Mailer delivery & open tracking (migration v054) -------------------------------------
# Per-recipient Resend events for the Market Close Wrap and Fund NAV Update. Rows are personal
# data: kept 90 days, then rolled into permanent per-edition totals. Clicks stay in
# site_usage_events (UTM links) and are not duplicated here.

RECIPIENT_EVENT_TYPES = (
    "sent", "delivered", "delivery_delayed", "bounced_hard", "bounced_soft", "complained", "opened",
)
RECIPIENT_EVENT_RETENTION_DAYS = 90
SOFT_BOUNCE_PAUSE_STREAK = 3
WEBHOOK_TOLERANCE_SECONDS = 300
_IST = timezone(timedelta(hours=5, minutes=30))


def ensure_digest_tracking_tables(cursor, is_pg: bool) -> None:
    """Migration v054: per-recipient events, permanent per-edition totals, subscriber pause fields."""
    id_col = "SERIAL PRIMARY KEY" if is_pg else "INTEGER PRIMARY KEY AUTOINCREMENT"
    ts = "TIMESTAMP WITH TIME ZONE" if is_pg else "TEXT"
    cursor.execute(f"""
        CREATE TABLE IF NOT EXISTS digest_recipient_events (
            id {id_col},
            webhook_event_id VARCHAR(128) UNIQUE,
            dispatch_id VARCHAR(64),
            edition_kind VARCHAR(32),
            edition_date VARCHAR(32),
            user_id VARCHAR(128),
            email VARCHAR(320),
            resend_message_id VARCHAR(128),
            event_type VARCHAR(32) NOT NULL,
            raw_reason TEXT,
            occurred_at {ts} NOT NULL
        );
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_dre_message ON digest_recipient_events (resend_message_id);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_dre_edition ON digest_recipient_events (edition_date, edition_kind, event_type);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_dre_user ON digest_recipient_events (user_id, occurred_at);")
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS digest_edition_totals (
            edition_date VARCHAR(32) NOT NULL,
            edition_kind VARCHAR(32) NOT NULL,
            event_type VARCHAR(32) NOT NULL,
            event_count INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (edition_date, edition_kind, event_type)
        );
    """)
    if is_pg:
        cursor.execute("ALTER TABLE user_accounts ADD COLUMN IF NOT EXISTS digest_paused_reason VARCHAR(32);")
        cursor.execute("ALTER TABLE user_accounts ADD COLUMN IF NOT EXISTS digest_paused_at TIMESTAMP WITH TIME ZONE;")
    else:
        cursor.execute("PRAGMA table_info(user_accounts);")
        cols = {str(r[1]) for r in cursor.fetchall()}
        if "digest_paused_reason" not in cols:
            cursor.execute("ALTER TABLE user_accounts ADD COLUMN digest_paused_reason VARCHAR(32);")
        if "digest_paused_at" not in cols:
            cursor.execute("ALTER TABLE user_accounts ADD COLUMN digest_paused_at TEXT;")


def _now_ist_iso() -> str:
    return datetime.now(_IST).isoformat()


def _to_ist_iso(value: Optional[str]) -> str:
    if not value:
        return _now_ist_iso()
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(_IST).isoformat()
    except ValueError:
        return _now_ist_iso()


def record_recipient_sends(dispatch_id: str, edition_kind: str, edition_date: str, rows) -> int:
    """Records one `sent` row per recipient accepted by Resend. Returns rows written."""
    kind = _normalize_edition_kind(edition_kind)
    payload = [(r[0], r[1], r[2]) for r in rows or [] if r and r[1]]
    if not payload:
        return 0
    conn = get_db_connection()
    cursor = conn.cursor()
    p = get_placeholder()
    now = _now_ist_iso()
    try:
        for user_id, email, message_id in payload:
            cursor.execute(
                f"""INSERT INTO digest_recipient_events
                    (dispatch_id, edition_kind, edition_date, user_id, email, resend_message_id, event_type, occurred_at)
                    VALUES ({p}, {p}, {p}, {p}, {p}, {p}, 'sent', {p});""",
                (dispatch_id, kind, str(edition_date), str(user_id) if user_id is not None else None,
                 str(email), str(message_id or "") or None, now),
            )
        conn.commit()
        return len(payload)
    except Exception as e:
        conn.rollback()
        logger.error("Failed recording %d recipient sends for %s: %s", len(payload), dispatch_id, e)
        return 0
    finally:
        cursor.close()
        conn.close()


def verify_resend_webhook(raw_body: bytes, headers: Dict[str, str], secret: Optional[str], now: Optional[float] = None) -> bool:
    """Verifies a Resend (Svix) webhook signature over the raw body; rejects stale timestamps."""
    if not secret or raw_body is None:
        return False
    h = {str(k).lower(): str(v) for k, v in (headers or {}).items()}
    msg_id, msg_ts, sig_header = h.get("svix-id"), h.get("svix-timestamp"), h.get("svix-signature")
    if not (msg_id and msg_ts and sig_header):
        return False
    try:
        ts_int = int(msg_ts)
    except ValueError:
        return False
    if abs((now if now is not None else time.time()) - ts_int) > WEBHOOK_TOLERANCE_SECONDS:
        return False
    key_part = secret.split("_", 1)[1] if secret.startswith("whsec_") else secret
    try:
        key = base64.b64decode(key_part)
    except Exception as key_err:
        logger.warning("RESEND_WEBHOOK_SECRET is not valid base64; rejecting webhook: %s", key_err)
        return False
    signed = f"{msg_id}.{msg_ts}.".encode("utf-8") + raw_body
    expected = base64.b64encode(hmac.new(key, signed, hashlib.sha256).digest()).decode("ascii")
    for part in sig_header.split():
        version, _, sig = part.partition(",")
        if version == "v1" and hmac.compare_digest(sig, expected):
            return True
    return False


def _classify_resend_event(event: Dict[str, Any]) -> Optional[str]:
    etype = str(event.get("type") or "")
    data = event.get("data") or {}
    if etype == "email.bounced":
        bounce = data.get("bounce") or {}
        btype = str(bounce.get("type") or bounce.get("subType") or "").lower()
        return "bounced_soft" if btype in ("transient", "temporary", "soft", "undetermined") else "bounced_hard"
    return {
        "email.sent": None,  # our own `sent` row already exists
        "email.delivered": "delivered",
        "email.delivery_delayed": "delivery_delayed",
        "email.complained": "complained",
        "email.opened": "opened",
    }.get(etype)


def apply_resend_event(event: Dict[str, Any], webhook_event_id: str) -> str:
    """Stores one verified Resend webhook event and applies pause rules.

    Returns: RECORDED, DUPLICATE, IGNORED_TYPE, UNKNOWN_MESSAGE or ERROR."""
    event_type = _classify_resend_event(event or {})
    if not event_type:
        return "IGNORED_TYPE"
    data = (event or {}).get("data") or {}
    message_id = str(data.get("email_id") or data.get("id") or "")
    if not message_id:
        return "UNKNOWN_MESSAGE"
    conn = get_db_connection()
    cursor = conn.cursor()
    p = get_placeholder()
    try:
        cursor.execute(f"SELECT 1 FROM digest_recipient_events WHERE webhook_event_id = {p};", (webhook_event_id,))
        if cursor.fetchone():
            return "DUPLICATE"
        cursor.execute(
            f"""SELECT dispatch_id, edition_kind, edition_date, user_id, email FROM digest_recipient_events
                WHERE resend_message_id = {p} AND event_type = 'sent' LIMIT 1;""",
            (message_id,),
        )
        sent = cursor.fetchone()
        if not sent:
            logger.warning("Resend event %s for unknown message %s ignored.", event_type, message_id)
            return "UNKNOWN_MESSAGE"
        dispatch_id, kind, edition_date, user_id, email = sent
        bounce = data.get("bounce") or {}
        reason = str(bounce.get("message") or bounce.get("subType") or "")[:500] or None
        cursor.execute(
            f"""INSERT INTO digest_recipient_events
                (webhook_event_id, dispatch_id, edition_kind, edition_date, user_id, email, resend_message_id,
                 event_type, raw_reason, occurred_at)
                VALUES ({p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p});""",
            (webhook_event_id, dispatch_id, kind, edition_date, user_id, email, message_id,
             event_type, reason, _to_ist_iso(event.get("created_at") or data.get("created_at"))),
        )
        pause_reason = None
        if event_type in ("bounced_hard", "complained"):
            pause_reason = event_type
        elif event_type == "bounced_soft" and user_id:
            cursor.execute(
                f"""SELECT event_type FROM digest_recipient_events
                    WHERE user_id = {p} AND event_type IN ('delivered', 'bounced_soft', 'bounced_hard')
                    ORDER BY occurred_at DESC, id DESC LIMIT {SOFT_BOUNCE_PAUSE_STREAK};""",
                (user_id,),
            )
            recent = [r[0] for r in cursor.fetchall()]
            if len(recent) == SOFT_BOUNCE_PAUSE_STREAK and all(r == "bounced_soft" for r in recent):
                pause_reason = "bounced_soft_x3"
        if pause_reason and user_id:
            off = False if is_postgres_connection(conn) else 0
            cursor.execute(
                f"""UPDATE user_accounts SET is_digest_subscribed = {p}, digest_paused_reason = {p}, digest_paused_at = {p}
                    WHERE CAST(id AS TEXT) = {p} AND COALESCE(digest_paused_reason, '') <> 'complained';""",
                (off, pause_reason, _now_ist_iso(), str(user_id)),
            )
            logger.warning("Paused research emails for subscriber %s (%s).", user_id, pause_reason)
        conn.commit()
        return "RECORDED"
    except Exception as e:
        conn.rollback()
        logger.error("Failed applying Resend event %s (%s): %s", webhook_event_id, event_type, e)
        return "ERROR"
    finally:
        cursor.close()
        conn.close()


def resume_digest_subscriber(user_id: str) -> bool:
    """Admin action: clears any pause (including spam complaints) and re-enables both emails."""
    conn = get_db_connection()
    cursor = conn.cursor()
    p = get_placeholder()
    try:
        on = True if is_postgres_connection(conn) else 1
        cursor.execute(
            f"""UPDATE user_accounts SET is_digest_subscribed = {p}, digest_paused_reason = NULL, digest_paused_at = NULL
                WHERE CAST(id AS TEXT) = {p} AND digest_paused_reason IS NOT NULL;""",
            (on, str(user_id)),
        )
        conn.commit()
        return (cursor.rowcount or 0) > 0
    except Exception as e:
        conn.rollback()
        logger.error("Failed resuming digest subscriber %s: %s", user_id, e)
        return False
    finally:
        cursor.close()
        conn.close()


def get_paused_digest_subscribers(limit: int = 200) -> List[Dict[str, Any]]:
    """Subscribers paused by bounce/complaint rules, newest first."""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            f"""SELECT id, email, digest_paused_reason, digest_paused_at FROM user_accounts
                WHERE digest_paused_reason IS NOT NULL ORDER BY digest_paused_at DESC LIMIT {int(limit)};"""
        )
        return [
            {"user_id": str(r[0]), "email": r[1], "reason": r[2], "paused_at": str(r[3] or "")}
            for r in cursor.fetchall()
        ]
    except Exception as e:
        logger.error("Failed loading paused digest subscribers: %s", e)
        return []
    finally:
        cursor.close()
        conn.close()


def purge_expired_recipient_events(retention_days: int = RECIPIENT_EVENT_RETENTION_DAYS, now: Optional[datetime] = None) -> Dict[str, int]:
    """Rolls per-recipient rows older than `retention_days` into digest_edition_totals, then deletes them."""
    cutoff = ((now or datetime.now(_IST)) - timedelta(days=int(retention_days))).isoformat()
    conn = get_db_connection()
    is_pg = is_postgres_connection(conn)
    cursor = conn.cursor()
    p = get_placeholder()
    older = f"occurred_at < {p}" if is_pg else f"datetime(occurred_at) < datetime({p})"
    try:
        cursor.execute(
            f"""SELECT edition_date, edition_kind, event_type, COUNT(*) FROM digest_recipient_events
                WHERE {older} GROUP BY edition_date, edition_kind, event_type;""",
            (cutoff,),
        )
        groups = cursor.fetchall()
        for edition_date, kind, etype, n in groups:
            cursor.execute(
                f"""INSERT INTO digest_edition_totals (edition_date, edition_kind, event_type, event_count)
                    VALUES ({p}, {p}, {p}, {p})
                    ON CONFLICT (edition_date, edition_kind, event_type)
                    DO UPDATE SET event_count = digest_edition_totals.event_count + EXCLUDED.event_count;""",
                (edition_date, kind, etype, int(n)),
            )
        cursor.execute(f"DELETE FROM digest_recipient_events WHERE {older};", (cutoff,))
        deleted = cursor.rowcount or 0
        conn.commit()
        return {"rolled_up_groups": len(groups), "deleted_rows": int(deleted)}
    except Exception as e:
        conn.rollback()
        logger.error("Recipient event retention failed: %s", e)
        raise
    finally:
        cursor.close()
        conn.close()


MAILER_SCHEDULE = {
    # kind: (scheduled IST time, weekdays sent; FUND_NAV covers the prior trading day)
    "MARKET_CLOSE": ("19:30", (0, 1, 2, 3, 4)),
    "FUND_NAV": ("07:30", (0, 1, 2, 3, 4)),
}
LATE_AFTER_MINUTES = 15


def _scheduled_send_at(kind: str, edition_date: str) -> datetime:
    hhmm, _ = MAILER_SCHEDULE[kind]
    d = datetime.strptime(edition_date, "%Y-%m-%d")
    if kind == "FUND_NAV":
        d = d + timedelta(days=1)  # sent the morning after the NAV date
    h, m = (int(x) for x in hhmm.split(":"))
    return d.replace(hour=h, minute=m, tzinfo=_IST)


def get_mailer_panel(days: int = 14, today: Optional[datetime] = None) -> List[Dict[str, Any]]:
    """One row per (edition date, kind) for the admin digest tab: timeliness + delivery funnel.

    Counts are None (shown as "—") when no tracking data exists, never zero-filled."""
    today_ist = (today or datetime.now(_IST)).astimezone(_IST)
    dates = [(today_ist - timedelta(days=i)).strftime("%Y-%m-%d") for i in range(int(days))]
    conn = get_db_connection()
    is_pg = is_postgres_connection(conn)
    cursor = conn.cursor()
    p = get_placeholder()
    rows: List[Dict[str, Any]] = []
    try:
        placeholders = ", ".join([p] * len(dates))
        cursor.execute(
            f"""SELECT edition_date, edition_kind, status, recipients_count, delivered_count, failed_count, created_at
                FROM digest_dispatches WHERE edition_date IN ({placeholders})
                  AND status IN ('COMPLETED', 'PARTIAL') ORDER BY created_at ASC;""",
            tuple(dates),
        )
        sends = {}
        for d, k, status, rc, dc, fc, created in cursor.fetchall():
            sends.setdefault((str(d), str(k or "MARKET_CLOSE")), (status, rc, dc, fc, created))
        cursor.execute(
            f"""SELECT edition_date, edition_kind, event_type, COUNT(DISTINCT COALESCE(user_id, email))
                FROM digest_recipient_events WHERE edition_date IN ({placeholders})
                GROUP BY edition_date, edition_kind, event_type;""",
            tuple(dates),
        )
        funnel: Dict[tuple, Dict[str, int]] = {}
        for d, k, et, n in cursor.fetchall():
            funnel.setdefault((str(d), str(k)), {})[str(et)] = int(n)
        cursor.execute(
            f"""SELECT edition_date, edition_kind, event_type, event_count FROM digest_edition_totals
                WHERE edition_date IN ({placeholders});""",
            tuple(dates),
        )
        for d, k, et, n in cursor.fetchall():
            bucket = funnel.setdefault((str(d), str(k)), {})
            bucket[str(et)] = bucket.get(str(et), 0) + int(n)
    except Exception as e:
        logger.error("Failed building mailer panel: %s", e)
        return []
    finally:
        cursor.close()
        conn.close()

    now = today_ist
    for d in dates:
        weekday = datetime.strptime(d, "%Y-%m-%d").weekday()
        for kind in ("MARKET_CLOSE", "FUND_NAV"):
            due_at = _scheduled_send_at(kind, d)
            send = sends.get((d, kind))
            if weekday not in MAILER_SCHEDULE[kind][1]:
                timeliness = "NOT_DUE"
            elif send:
                sent_at = send[4]
                try:
                    sent_dt = sent_at if isinstance(sent_at, datetime) else datetime.fromisoformat(str(sent_at).replace("Z", "+00:00"))
                    if sent_dt.tzinfo is None:
                        sent_dt = sent_dt.replace(tzinfo=timezone.utc)
                    late = sent_dt.astimezone(_IST) > due_at + timedelta(minutes=LATE_AFTER_MINUTES)
                    timeliness = "LATE" if late else "ON_TIME"
                except ValueError:
                    timeliness = "SENT"
            elif now < due_at:
                timeliness = "UPCOMING"
            else:
                timeliness = "NOT_SENT"
            ev = funnel.get((d, kind))
            rows.append({
                "edition_date": d,
                "edition_kind": kind,
                "scheduled_at": due_at.strftime("%Y-%m-%d %H:%M IST"),
                "timeliness": timeliness,
                "status": send[0] if send else None,
                "recipients": int(send[1]) if send and send[1] is not None else None,
                "accepted": int(send[2]) if send and send[2] is not None else None,
                "delivered": ev.get("delivered") if ev else None,
                "bounced": (ev.get("bounced_hard", 0) + ev.get("bounced_soft", 0)) if ev else None,
                "complaints": ev.get("complained") if ev else None,
                "opens": ev.get("opened") if ev else None,
            })
    return rows
