"""
User Accounts, Credit Ledgers, and Monetization Persistence Module.

Provides dual-bound (PostgreSQL/SQLite) atomic transactions for:
- User profile retrieval and creation (linked to Supabase Auth UUIDs or emails)
- Credit balance queries and atomic usage deduction
- Top-up transaction records and subscription status tracking
- Audit ledger of credit consumption per ticker and action
"""

import time
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional, Tuple

from core.db.connection import (
    get_db_connection,
    get_placeholder,
    init_db,
    IST,
)
from core.db.reports import _format_timestamp

logger = logging.getLogger("equity_research.core.db.users")


def get_or_create_user(
    user_id: str,
    email: str,
    full_name: str = "",
    avatar_url: str = ""
) -> Dict[str, Any]:
    """
    Retrieves or creates a user account.
    Upon new account creation, grants 2.0 welcome research credits and logs an initial ledger event.
    """
    if not user_id or not email:
        return {}

    init_db()
    conn = get_db_connection()
    cursor = conn.cursor()
    p = get_placeholder()
    clean_email = email.strip().lower()
    clean_id = str(user_id).strip()

    try:
        # Check if user exists by ID or email
        cursor.execute(f"SELECT id, email, full_name, avatar_url, credits_balance, subscription_tier, subscription_expires_at, created_at, last_login_at FROM user_accounts WHERE id = {p} OR email = {p} LIMIT 1;", (clean_id, clean_email))
        row = cursor.fetchone()
        if row:
            db_id = row[0]
            # Check if this user ever received welcome credits
            cursor.execute(f"SELECT COUNT(*) FROM credit_transactions WHERE user_id = {p} AND pack_type = 'WELCOME_GRANT';", (db_id,))
            grant_row = cursor.fetchone()
            grant_count = grant_row[0] if grant_row else 0
            current_bal = float(row[4] or 0.0)

            if grant_count == 0 and current_bal < 2.0:
                # First-time welcome grant
                initial_credits = 2.0
                cursor.execute(f"UPDATE user_accounts SET credits_balance = credits_balance + {p} WHERE id = {p};", (initial_credits, db_id))
                tx_id = f"tx_welcome_{db_id[:12]}_{int(time.time())}"
                cursor.execute(
                    f"""
                    INSERT INTO credit_transactions (id, user_id, amount_inr, credits_added, payment_gateway, status, pack_type, invoice_number)
                    VALUES ({p}, {p}, 0.0, {p}, 'system_grant', 'success', 'WELCOME_GRANT', {p});
                    """,
                    (tx_id, db_id, initial_credits, f"INV-WELCOME-{int(time.time())}")
                )
                cursor.execute(
                    f"""
                    INSERT INTO credit_usage_ledger (user_id, ticker, action_type, credits_consumed, balance_after)
                    VALUES ({p}, 'PLATFORM', 'WELCOME_GRANT', 0.0, {p});
                    """,
                    (db_id, current_bal + initial_credits)
                )
                conn.commit()

            # Refresh updated row
            cursor.execute(f"SELECT id, email, full_name, avatar_url, credits_balance, subscription_tier, subscription_expires_at, created_at, last_login_at FROM user_accounts WHERE id = {p};", (db_id,))
            updated_row = cursor.fetchone() or row
            return _format_user_record(updated_row)

        # Create new user with 2 Welcome Credits
        initial_credits = 2.0
        cursor.execute(
            f"""
            INSERT INTO user_accounts (id, email, full_name, avatar_url, credits_balance, subscription_tier, created_at, last_login_at)
            VALUES ({p}, {p}, {p}, {p}, {p}, 'free', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP);
            """,
            (clean_id, clean_email, full_name, avatar_url, initial_credits)
        )

        # Log welcome grant transaction
        tx_id = f"tx_welcome_{clean_id[:12]}_{int(time.time())}"
        cursor.execute(
            f"""
            INSERT INTO credit_transactions (id, user_id, amount_inr, credits_added, payment_gateway, status, pack_type, invoice_number)
            VALUES ({p}, {p}, 0.0, {p}, 'system_grant', 'success', 'WELCOME_GRANT', {p});
            """,
            (tx_id, clean_id, initial_credits, f"INV-WELCOME-{int(time.time())}")
        )

        # Log initial ledger entry
        cursor.execute(
            f"""
            INSERT INTO credit_usage_ledger (user_id, ticker, action_type, credits_consumed, balance_after)
            VALUES ({p}, 'PLATFORM', 'WELCOME_GRANT', 0.0, {p});
            """,
            (clean_id, initial_credits)
        )
        conn.commit()

        logger.info(f"Created new user account: {clean_email} ({clean_id}) with {initial_credits} welcome credits.")
        return {
            "id": clean_id,
            "email": clean_email,
            "full_name": full_name or clean_email.split("@")[0],
            "avatar_url": avatar_url,
            "credits_balance": initial_credits,
            "subscription_tier": "free",
            "subscription_expires_at": None,
            "is_pro": False,
            "created_at": datetime.now(IST).strftime("%d-%b-%Y %H:%M IST"),
            "last_login_at": datetime.now(IST).strftime("%d-%b-%Y %H:%M IST")
        }
    except Exception as e:
        logger.error(f"Error in get_or_create_user for {email}: {e}")
        try:
            conn.rollback()
        except Exception:
            pass
        return {}
    finally:
        cursor.close()
        conn.close()


def get_user_by_id(user_id: str) -> Optional[Dict[str, Any]]:
    """Retrieves user profile and credit balance by user ID."""
    if not user_id:
        return None
    init_db()
    conn = get_db_connection()
    cursor = conn.cursor()
    p = get_placeholder()
    try:
        cursor.execute(
            f"SELECT id, email, full_name, avatar_url, credits_balance, subscription_tier, subscription_expires_at, created_at, last_login_at FROM user_accounts WHERE id = {p};",
            (str(user_id).strip(),)
        )
        row = cursor.fetchone()
        return _format_user_record(row) if row else None
    except Exception as e:
        logger.error(f"Error fetching user by ID {user_id}: {e}")
        return None
    finally:
        cursor.close()
        conn.close()


def get_user_by_email(email: str) -> Optional[Dict[str, Any]]:
    """Retrieves user profile and credit balance by email address."""
    if not email:
        return None
    init_db()
    conn = get_db_connection()
    cursor = conn.cursor()
    p = get_placeholder()
    try:
        cursor.execute(
            f"SELECT id, email, full_name, avatar_url, credits_balance, subscription_tier, subscription_expires_at, created_at, last_login_at FROM user_accounts WHERE email = {p};",
            (email.strip().lower(),)
        )
        row = cursor.fetchone()
        return _format_user_record(row) if row else None
    except Exception as e:
        logger.error(f"Error fetching user by email {email}: {e}")
        return None
    finally:
        cursor.close()
        conn.close()


def get_user_credits_balance(user_id: str) -> float:
    """Returns the current credit balance of the user (or 0.0 if not found)."""
    user = get_user_by_id(user_id)
    return float(user.get("credits_balance", 0.0)) if user else 0.0


def deduct_user_credits(
    user_id: str,
    ticker: str,
    action_type: str,
    amount: float = 1.0
) -> Tuple[bool, float, str]:
    """
    Atomically checks balance and deducts credits for an action.
    Handles Pro subscription entitlements (e.g. unlimited surgical refreshes and PDF exports).
    Returns (success: bool, new_balance: float, message: str).
    """
    if not user_id:
        return False, 0.0, "Authentication required to perform this action."

    init_db()
    conn = get_db_connection()
    cursor = conn.cursor()
    p = get_placeholder()
    clean_id = str(user_id).strip()

    try:
        cursor.execute(
            f"SELECT id, credits_balance, subscription_tier, subscription_expires_at FROM user_accounts WHERE id = {p};",
            (clean_id,)
        )
        row = cursor.fetchone()
        if not row:
            return False, 0.0, "User account not found."

        current_balance = float(row[1] or 0.0)
        sub_tier = (row[2] or "free").lower()
        sub_expires = row[3]

        is_pro_active = False
        if sub_tier in ("pro_monthly", "pro_annual"):
            if sub_expires is None:
                is_pro_active = True
            else:
                now = datetime.now(timezone.utc)
                if isinstance(sub_expires, str):
                    try:
                        exp_dt = datetime.fromisoformat(sub_expires.replace("Z", "+00:00"))
                        is_pro_active = exp_dt > now
                    except Exception:
                        is_pro_active = True
                elif hasattr(sub_expires, "tzinfo"):
                    is_pro_active = sub_expires > now
                else:
                    is_pro_active = True

        # Pro Tier Entitlements: Surgical updates & PDF exports are uncapped / free
        if is_pro_active and action_type in ("SURGICAL_REFRESH", "PDF_EXPORT"):
            cursor.execute(
                f"""
                INSERT INTO credit_usage_ledger (user_id, ticker, action_type, credits_consumed, balance_after)
                VALUES ({p}, {p}, {p}, 0.0, {p});
                """,
                (clean_id, ticker.upper(), action_type, current_balance)
            )
            conn.commit()
            return True, current_balance, "Action covered under active Pro subscription (0 credits consumed)."

        # Standard Credit Deduction Check
        cost = float(amount)
        if current_balance < cost:
            return False, current_balance, f"Insufficient research credits ({current_balance:.1f} available, {cost:.2f} required). Please top up via UPI/Card."

        new_balance = round(current_balance - cost, 2)
        cursor.execute(
            f"UPDATE user_accounts SET credits_balance = {p} WHERE id = {p};",
            (new_balance, clean_id)
        )
        cursor.execute(
            f"""
            INSERT INTO credit_usage_ledger (user_id, ticker, action_type, credits_consumed, balance_after)
            VALUES ({p}, {p}, {p}, {p}, {p});
            """,
            (clean_id, ticker.upper(), action_type, cost, new_balance)
        )
        conn.commit()
        logger.info(f"Deducted {cost} credits from {clean_id} for {action_type} on {ticker}. New balance: {new_balance}")
        return True, new_balance, f"Success: {cost:.2f} credit(s) consumed. Remaining balance: {new_balance:.1f}."
    except Exception as e:
        logger.error(f"Error deducting credits for user {user_id}: {e}")
        try:
            conn.rollback()
        except Exception:
            pass
        return False, 0.0, f"Database transaction error: {e}"
    finally:
        cursor.close()
        conn.close()


def add_user_credits(
    user_id: str,
    amount_inr: float,
    credits_added: float,
    pack_type: str,
    gateway_order_id: Optional[str] = None,
    gateway_payment_id: Optional[str] = None,
    status: str = "success",
    invoice_number: Optional[str] = None
) -> Tuple[bool, float]:
    """
    Records a payment transaction and credits research units or upgrades the subscription tier.
    Returns (success: bool, new_balance: float).
    """
    if not user_id:
        return False, 0.0

    init_db()
    clean_id = str(user_id).strip()
    if not get_user_by_id(clean_id):
        get_or_create_user(clean_id, f"{clean_id}@stockresearch.ai", "Guest Investor")

    conn = get_db_connection()
    cursor = conn.cursor()
    p = get_placeholder()

    try:
        cursor.execute(f"SELECT credits_balance, subscription_tier FROM user_accounts WHERE id = {p};", (clean_id,))
        row = cursor.fetchone()
        if not row:
            return False, 0.0

        current_balance = float(row[0] or 0.0)
        credits_to_add = float(credits_added)
        new_balance = round(current_balance + credits_to_add, 2)
        tx_id = f"tx_{int(time.time())}_{clean_id[:8]}"
        inv_num = invoice_number or f"INV-{int(time.time())}"

        # Insert Transaction
        cursor.execute(
            f"""
            INSERT INTO credit_transactions (id, user_id, amount_inr, credits_added, payment_gateway, gateway_order_id, gateway_payment_id, status, pack_type, invoice_number)
            VALUES ({p}, {p}, {p}, {p}, 'razorpay', {p}, {p}, {p}, {p}, {p});
            """,
            (tx_id, clean_id, amount_inr, credits_to_add, gateway_order_id, gateway_payment_id, status, pack_type, inv_num)
        )

        # Handle Subscriptions (Pro Monthly / Annual)
        normalized_pack = pack_type.upper()
        now_dt = datetime.now(timezone.utc)
        if "PRO_MONTHLY" in normalized_pack:
            exp_date = now_dt + timedelta(days=30)
            cursor.execute(
                f"UPDATE user_accounts SET credits_balance = {p}, subscription_tier = 'pro_monthly', subscription_expires_at = {p} WHERE id = {p};",
                (new_balance, exp_date.isoformat(), clean_id)
            )
        elif "PRO_ANNUAL" in normalized_pack:
            exp_date = now_dt + timedelta(days=365)
            cursor.execute(
                f"UPDATE user_accounts SET credits_balance = {p}, subscription_tier = 'pro_annual', subscription_expires_at = {p} WHERE id = {p};",
                (new_balance, exp_date.isoformat(), clean_id)
            )
        else:
            cursor.execute(
                f"UPDATE user_accounts SET credits_balance = {p} WHERE id = {p};",
                (new_balance, clean_id)
            )

        # Record Ledger Event
        cursor.execute(
            f"""
            INSERT INTO credit_usage_ledger (user_id, ticker, action_type, credits_consumed, balance_after)
            VALUES ({p}, 'BILLING', {p}, {p}, {p});
            """,
            (clean_id, f"TOPUP_{pack_type}", -credits_to_add, new_balance)
        )

        conn.commit()
        logger.info(f"Added {credits_to_add} credits to user {clean_id} (Pack: {pack_type}, INR: ₹{amount_inr}). New balance: {new_balance}")
        return True, new_balance
    except Exception as e:
        logger.error(f"Error adding credits to user {user_id}: {e}")
        try:
            conn.rollback()
        except Exception:
            pass
        return False, 0.0
    finally:
        cursor.close()
        conn.close()


def get_user_transactions(user_id: str, limit: int = 20) -> List[Dict[str, Any]]:
    """Retrieves recent credit purchase transactions for a user."""
    if not user_id:
        return []
    init_db()
    conn = get_db_connection()
    cursor = conn.cursor()
    p = get_placeholder()
    try:
        cursor.execute(
            f"""
            SELECT id, amount_inr, credits_added, payment_gateway, gateway_payment_id, status, pack_type, invoice_number, created_at
            FROM credit_transactions
            WHERE user_id = {p}
            ORDER BY created_at DESC
            LIMIT {limit};
            """,
            (str(user_id).strip(),)
        )
        rows = cursor.fetchall()
        return [
            {
                "id": r[0],
                "amount_inr": float(r[1]),
                "credits_added": float(r[2]),
                "gateway": r[3],
                "payment_id": r[4],
                "status": r[5],
                "pack_type": r[6],
                "invoice_number": r[7],
                "date": _format_timestamp(r[8])
            }
            for r in rows
        ]
    except Exception as e:
        logger.error(f"Error fetching user transactions for {user_id}: {e}")
        return []
    finally:
        cursor.close()
        conn.close()


def get_user_usage_history(user_id: str, limit: int = 30) -> List[Dict[str, Any]]:
    """Retrieves credit consumption ledger history for a user."""
    if not user_id:
        return []
    init_db()
    conn = get_db_connection()
    cursor = conn.cursor()
    p = get_placeholder()
    try:
        cursor.execute(
            f"""
            SELECT ticker, action_type, credits_consumed, balance_after, created_at
            FROM credit_usage_ledger
            WHERE user_id = {p}
            ORDER BY created_at DESC
            LIMIT {limit};
            """,
            (str(user_id).strip(),)
        )
        rows = cursor.fetchall()
        return [
            {
                "ticker": r[0],
                "action": r[1],
                "credits_consumed": float(r[2]),
                "balance_after": float(r[3]),
                "date": _format_timestamp(r[4])
            }
            for r in rows
        ]
    except Exception as e:
        logger.error(f"Error fetching usage ledger for {user_id}: {e}")
        return []
    finally:
        cursor.close()
        conn.close()


def _format_user_record(row) -> Dict[str, Any]:
    """Helper to convert a database row into a structured user profile dictionary."""
    sub_tier = (row[5] or "free").lower()
    sub_expires = row[6]
    is_pro = False
    if sub_tier in ("pro_monthly", "pro_annual"):
        if sub_expires is None:
            is_pro = True
        else:
            now = datetime.now(timezone.utc)
            if isinstance(sub_expires, str):
                try:
                    exp_dt = datetime.fromisoformat(sub_expires.replace("Z", "+00:00"))
                    is_pro = exp_dt > now
                except Exception:
                    is_pro = True
            elif hasattr(sub_expires, "tzinfo"):
                is_pro = sub_expires > now
            else:
                is_pro = True

    return {
        "id": row[0],
        "email": row[1],
        "full_name": row[2] or row[1].split("@")[0],
        "avatar_url": row[3] or "",
        "credits_balance": float(row[4] or 0.0),
        "subscription_tier": sub_tier,
        "subscription_expires_at": _format_timestamp(sub_expires) if sub_expires else None,
        "is_pro": is_pro,
        "created_at": _format_timestamp(row[7]),
        "last_login_at": _format_timestamp(row[8])
    }
