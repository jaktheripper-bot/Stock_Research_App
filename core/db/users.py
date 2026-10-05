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

        # Fetch user profile to enrich invoice
        cursor.execute(f"SELECT email, full_name FROM user_accounts WHERE id = {p};", (clean_id,))
        acc_info = cursor.fetchone()
        cust_email = acc_info[0] if acc_info else f"{clean_id}@stockresearch.ai"
        cust_name = acc_info[1] if acc_info else "Investor"

        # Compute GST breakdown (Inclusive of 18% GST, SAC 998314)
        amt = float(amount_inr)
        if amt > 0:
            base_amt = round(amt / 1.18, 2)
            gst_amt = round(amt - base_amt, 2)
        else:
            base_amt = 0.0
            gst_amt = 0.0

        # Determine gateway and simulation flag
        is_simulation_order = bool(
            (gateway_order_id and str(gateway_order_id).startswith(("order_sim_", "order_test_"))) or
            (gateway_payment_id and str(gateway_payment_id).startswith(("pay_sim_", "pay_test_")))
        )
        effective_gateway = "simulation" if is_simulation_order else "razorpay"

        # Insert Transaction with complete tax & customer audit trail
        try:
            cursor.execute(
                f"""
                INSERT INTO credit_transactions (
                    id, user_id, amount_inr, credits_added, payment_gateway,
                    gateway_order_id, gateway_payment_id, status, pack_type, invoice_number,
                    customer_email, customer_name, base_amount_inr, tax_gst_inr, sac_code
                )
                VALUES ({p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, '998314');
                """,
                (tx_id, clean_id, amt, credits_to_add, effective_gateway, gateway_order_id, gateway_payment_id, status, pack_type, inv_num, cust_email, cust_name, base_amt, gst_amt)
            )
        except Exception:
            # Fallback for earlier schema if columns not yet committed
            cursor.execute(
                f"""
                INSERT INTO credit_transactions (id, user_id, amount_inr, credits_added, payment_gateway, gateway_order_id, gateway_payment_id, status, pack_type, invoice_number)
                VALUES ({p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p});
                """,
                (tx_id, clean_id, amt, credits_to_add, effective_gateway, gateway_order_id, gateway_payment_id, status, pack_type, inv_num)
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
        logger.info(f"Added {credits_to_add} credits to user {clean_id} (Pack: {pack_type}, INR: ₹{amt}). New balance: {new_balance}")
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


def get_all_billables(status: Optional[str] = None, limit: int = 100, offset: int = 0, exclude_tests: bool = True) -> List[Dict[str, Any]]:
    """
    Retrieves all purchases, invoices, and returns for administrative billing audit.
    Includes tax breakdown (Base + GST 18%), SAC code, and gateway IDs.
    Filters out synthetic test orders by default.
    """
    init_db()
    conn = get_db_connection()
    cursor = conn.cursor()
    p = get_placeholder()
    try:
        where_conditions = []
        params = []
        if status:
            where_conditions.append(f"t.status = {p}")
            params.append(status.lower())
        if exclude_tests:
            where_conditions.append("(t.customer_email IS NULL OR (t.customer_email NOT LIKE '%@example.com' AND t.customer_email NOT LIKE '%@test.com' AND t.customer_email NOT LIKE '%@pytest.com'))")
            where_conditions.append("(t.user_id NOT LIKE 'test_%' AND t.user_id NOT IN ('guest_web_user', 'testclient', 'test_admin', 'test_user'))")
            where_conditions.append("(t.gateway_order_id IS NULL OR (t.gateway_order_id NOT LIKE 'order_test_%' AND t.gateway_order_id NOT LIKE 'order_sim_%'))")
            where_conditions.append("(t.gateway_payment_id IS NULL OR (t.gateway_payment_id NOT LIKE 'pay_test_%' AND t.gateway_payment_id NOT LIKE 'pay_sim_%'))")
            where_conditions.append("t.payment_gateway != 'simulation'")

        where_clause = f"WHERE {' AND '.join(where_conditions)}" if where_conditions else ""

        query = f"""
            SELECT 
                t.id, t.user_id, t.amount_inr, t.credits_added, t.payment_gateway,
                t.gateway_order_id, t.gateway_payment_id, t.status, t.pack_type, t.invoice_number,
                t.created_at,
                COALESCE(t.customer_email, u.email, t.user_id) as email,
                COALESCE(t.customer_name, u.full_name, 'Investor') as name,
                COALESCE(t.base_amount_inr, 0.0),
                COALESCE(t.tax_gst_inr, 0.0),
                COALESCE(t.sac_code, '998314'),
                COALESCE(t.refund_amount_inr, 0.0),
                t.refund_reason,
                t.gateway_refund_id,
                t.refunded_at
            FROM credit_transactions t
            LEFT JOIN user_accounts u ON t.user_id = u.id
            {where_clause}
            ORDER BY t.created_at DESC
            LIMIT {limit} OFFSET {offset};
        """
        cursor.execute(query, tuple(params))
        rows = cursor.fetchall()
        billables = []
        for r in rows:
            amt = float(r[2] or 0.0)
            base = float(r[13] or 0.0)
            gst = float(r[14] or 0.0)
            if amt > 0 and base == 0.0 and gst == 0.0:
                base = round(amt / 1.18, 2)
                gst = round(amt - base, 2)

            # Classify transaction nature (Verified Cash vs Free Token Grant vs Simulation)
            g_ord = (r[5] or "").lower()
            g_pay = (r[6] or "").lower()
            gw = (r[4] or "").lower()
            pack = (r[8] or "").upper()
            st = (r[7] or "success").lower()

            if "sim" in g_ord or "sim" in g_pay or gw == "simulation" or "order_test" in g_ord:
                nature = "SIMULATION"
                nature_label = "🧪 Sandbox Test"
            elif pack == "WELCOME_GRANT" or (amt == 0.0 and (gw == "system_grant" or "grant" in pack or "free" in pack)):
                nature = "FREE_GRANT"
                nature_label = "🎁 Free Grant (₹0)"
            elif amt > 0 and st in ("success", "paid"):
                nature = "VERIFIED_PAID"
                nature_label = "💳 Paid Order"
            else:
                nature = "PROMO"
                nature_label = "🎟️ Free Token"

            billables.append({
                "id": r[0],
                "user_id": r[1],
                "amount_inr": amt,
                "credits_added": float(r[3] or 0.0),
                "gateway": r[4] or "razorpay",
                "gateway_order_id": r[5] or "",
                "gateway_payment_id": r[6] or "",
                "status": st,
                "pack_type": r[8],
                "invoice_number": r[9] or f"INV-{r[0]}",
                "date": _format_timestamp(r[10]),
                "customer_email": r[11],
                "customer_name": r[12],
                "base_amount_inr": base,
                "tax_gst_inr": gst,
                "sac_code": r[15] or "998314",
                "refund_amount_inr": float(r[16] or 0.0),
                "refund_reason": r[17] or "",
                "gateway_refund_id": r[18] or "",
                "refunded_at": _format_timestamp(r[19]) if r[19] else None,
                "nature": nature,
                "nature_label": nature_label,
            })
        return billables
    except Exception as e:
        logger.error(f"Error fetching all billables: {e}")
        return []
    finally:
        cursor.close()
        conn.close()


def get_revenue_analytics_summary(days: int = None, start_date = None, end_date = None, exclude_tests: bool = True) -> Dict[str, Any]:
    """
    Computes institutional revenue summary, GST collected, returns/refunds,
    and circulating credit liabilities across a selectable time window.
    Strictly distinguishes genuine, bank-cleared revenue (Razorpay)
    from promotional welcome grants, free test tokens, and sandbox checkout simulations.
    """
    init_db()
    conn = get_db_connection()
    cursor = conn.cursor()
    from core.db.telemetry import _build_telemetry_time_filter, get_supabase_url
    supabase_url = get_supabase_url()

    summary = {
        "gross_revenue_inr": 0.0,
        "net_revenue_inr": 0.0,
        "tax_gst_collected_inr": 0.0,
        "refunded_amount_inr": 0.0,
        "paid_orders_count": 0,
        "paid_credits_issued": 0.0,
        "refunded_orders_count": 0,
        "welcome_grants_count": 0,
        "free_credits_issued": 0.0,
        "credits_in_circulation": 0.0,
        "active_subscribers_count": 0
    }

    try:
        time_filter = _build_telemetry_time_filter(supabase_url, days=days, start_date=start_date, end_date=end_date, exclude_tests=False)
        time_filter_tx = time_filter.replace("timestamp", "created_at")
        if exclude_tests:
            time_filter_tx += " AND (customer_email IS NULL OR (customer_email NOT LIKE '%@example.com' AND customer_email NOT LIKE '%@test.com' AND customer_email NOT LIKE '%@pytest.com')) AND (user_id IS NULL OR (user_id NOT LIKE 'test_%' AND user_id NOT IN ('guest_web_user', 'testclient', 'test_admin', 'test_user'))) AND (gateway_order_id IS NULL OR (gateway_order_id NOT LIKE 'order_test_%' AND gateway_order_id NOT LIKE 'order_sim_%')) AND (gateway_payment_id IS NULL OR (gateway_payment_id NOT LIKE 'pay_test_%' AND gateway_payment_id NOT LIKE 'pay_sim_%')) AND payment_gateway != 'simulation'"

        # 1. Total paid revenue, GST, order count, and separate paid vs free token accounting
        cursor.execute(f"""
            SELECT 
                COUNT(CASE WHEN amount_inr > 0 AND status = 'success' 
                           AND payment_gateway != 'simulation'
                           AND (gateway_payment_id IS NULL OR (gateway_payment_id NOT LIKE 'pay_sim_%' AND gateway_payment_id NOT LIKE 'pay_test_%'))
                           AND (gateway_order_id IS NULL OR (gateway_order_id NOT LIKE 'order_sim_%' AND gateway_order_id NOT LIKE 'order_test_%'))
                           THEN 1 END) as paid_orders,
                COALESCE(SUM(CASE WHEN amount_inr > 0 AND status = 'success' 
                           AND payment_gateway != 'simulation'
                           AND (gateway_payment_id IS NULL OR (gateway_payment_id NOT LIKE 'pay_sim_%' AND gateway_payment_id NOT LIKE 'pay_test_%'))
                           AND (gateway_order_id IS NULL OR (gateway_order_id NOT LIKE 'order_sim_%' AND gateway_order_id NOT LIKE 'order_test_%'))
                           THEN amount_inr ELSE 0 END), 0.0) as gross_rev,
                COUNT(CASE WHEN status IN ('refunded', 'reversed') THEN 1 END) as refund_count,
                COALESCE(SUM(refund_amount_inr), 0.0) as refund_sum,
                COUNT(CASE WHEN pack_type = 'WELCOME_GRANT' 
                           OR (amount_inr = 0 AND (payment_gateway = 'system_grant' OR pack_type LIKE '%GRANT%' OR pack_type LIKE '%FREE%'))
                           THEN 1 END) as welcome_grants,
                COALESCE(SUM(CASE WHEN pack_type = 'WELCOME_GRANT' 
                           OR (amount_inr = 0 AND (payment_gateway = 'system_grant' OR pack_type LIKE '%GRANT%' OR pack_type LIKE '%FREE%'))
                           THEN credits_added ELSE 0 END), 0.0) as free_credits,
                COALESCE(SUM(CASE WHEN amount_inr > 0 AND status = 'success' 
                           AND payment_gateway != 'simulation'
                           AND (gateway_payment_id IS NULL OR (gateway_payment_id NOT LIKE 'pay_sim_%' AND gateway_payment_id NOT LIKE 'pay_test_%'))
                           AND (gateway_order_id IS NULL OR (gateway_order_id NOT LIKE 'order_sim_%' AND gateway_order_id NOT LIKE 'order_test_%'))
                           THEN credits_added ELSE 0 END), 0.0) as paid_credits
            FROM credit_transactions
            WHERE {time_filter_tx};
        """)
        row = cursor.fetchone()
        if row:
            gross = float(row[1] or 0.0)
            refund_sum = float(row[3] or 0.0)
            summary["paid_orders_count"] = int(row[0] or 0)
            summary["gross_revenue_inr"] = gross
            summary["refunded_orders_count"] = int(row[2] or 0)
            summary["refunded_amount_inr"] = refund_sum
            summary["welcome_grants_count"] = int(row[4] or 0)
            summary["free_credits_issued"] = float(row[5] or 0.0)
            summary["paid_credits_issued"] = float(row[6] or 0.0)

            # 18% GST calculation (Price inclusive of GST)
            if gross > 0:
                summary["net_revenue_inr"] = round((gross - refund_sum) / 1.18, 2)
                summary["tax_gst_collected_inr"] = round((gross - refund_sum) - summary["net_revenue_inr"], 2)

        # 2. Credits in circulation across all users (unearned revenue liability)
        try:
            cursor.execute("SELECT SUM(credits_balance), COUNT(CASE WHEN subscription_tier IN ('pro_monthly', 'pro_annual') THEN 1 END) FROM user_accounts;")
            c_row = cursor.fetchone()
            if c_row:
                summary["credits_in_circulation"] = float(c_row[0] or 0.0)
                summary["active_subscribers_count"] = int(c_row[1] or 0)
        except Exception:
            pass

    except Exception as e:
        logger.error(f"Error computing revenue analytics summary: {e}")
    finally:
        cursor.close()
        conn.close()

    return summary


def process_refund(
    transaction_id: str,
    refund_amount: Optional[float] = None,
    reason: str = "Customer requested return within policy",
    admin_notes: str = ""
) -> Tuple[bool, str]:
    """
    Processes a return / refund for an existing purchase transaction.
    - Sets transaction status to 'refunded' with immutable audit fields
    - Deducts the equivalent credits from the user's credit balance
    - Logs a reversal ledger entry for SEBI / accounting audit trail
    """
    if not transaction_id:
        return False, "Transaction ID required."

    init_db()
    conn = get_db_connection()
    cursor = conn.cursor()
    p = get_placeholder()
    tx_clean = str(transaction_id).strip()

    try:
        cursor.execute(
            f"SELECT id, user_id, amount_inr, credits_added, status, invoice_number FROM credit_transactions WHERE id = {p};",
            (tx_clean,)
        )
        tx = cursor.fetchone()
        if not tx:
            return False, f"Transaction {tx_clean} not found."

        if tx[4] == "refunded":
            return False, f"Transaction {tx_clean} is already marked as refunded."

        user_id = tx[1]
        orig_amount = float(tx[2] or 0.0)
        credits_to_reverse = float(tx[3] or 0.0)
        actual_refund_amt = float(refund_amount) if refund_amount is not None else orig_amount

        # Update credit_transactions
        now_val = "CURRENT_TIMESTAMP"
        cursor.execute(
            f"""
            UPDATE credit_transactions
            SET status = 'refunded',
                refund_amount_inr = {p},
                refund_reason = {p},
                refunded_at = CURRENT_TIMESTAMP
            WHERE id = {p};
            """,
            (actual_refund_amt, f"{reason} | Notes: {admin_notes}", tx_clean)
        )

        # Adjust user balance
        cursor.execute(f"SELECT credits_balance FROM user_accounts WHERE id = {p};", (user_id,))
        u_row = cursor.fetchone()
        current_bal = float(u_row[0] or 0.0) if u_row else 0.0
        new_bal = max(0.0, round(current_bal - credits_to_reverse, 2))

        cursor.execute(f"UPDATE user_accounts SET credits_balance = {p} WHERE id = {p};", (new_bal, user_id))

        # Log reversal entry in credit_usage_ledger
        cursor.execute(
            f"""
            INSERT INTO credit_usage_ledger (user_id, ticker, action_type, credits_consumed, balance_after)
            VALUES ({p}, 'BILLING', 'REFUND_REVERSAL', {p}, {p});
            """,
            (user_id, credits_to_reverse, new_bal)
        )

        conn.commit()
        logger.info(f"Processed refund for tx {tx_clean} (User: {user_id}, Amount: ₹{actual_refund_amt}). Adjusted balance: {new_bal}")
        return True, f"Successfully processed refund of ₹{actual_refund_amt:.2f} for Invoice {tx[5]}. Reversal ledger committed."
    except Exception as e:
        logger.error(f"Error processing refund for {transaction_id}: {e}")
        try:
            conn.rollback()
        except Exception:
            pass
        return False, f"Database error during refund: {e}"
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
