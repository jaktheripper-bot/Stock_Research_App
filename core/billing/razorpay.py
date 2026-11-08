"""
Razorpay Payment Gateway Integration & Order Processing Engine.

Handles:
- Razorpay Orders REST API dispatch (UPI, Cards, NetBanking)
- Cryptographic HMAC-SHA256 signature verification
- Instant simulated sandbox mode when keys are pending setup
- Credit balance updates and SEBI-compliant invoice receipt generation
"""

import os
import hmac
import hashlib
import json
import time
import uuid
import logging
import requests
from datetime import datetime, timedelta
from typing import Dict, Any, Tuple, Optional
from urllib.parse import quote

logger = logging.getLogger("equity_research.core.billing")

# Load environment variables from .env
try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception as e:
    logger.debug("dotenv load notice: %s", e)

try:
    import razorpay
except ImportError:
    razorpay = None

from core.config import get_secret
from core.billing.pricing import (
    get_plan_by_id,
    INVOICE_SERVICE_DESCRIPTION,
    INVOICE_SAC_CODE,
    INVOICE_DISCLAIMER,
)
from core.db import add_user_credits, get_user_by_id
from core.db.connection import (
    AuthoritativeDatabaseUnavailable,
    IST,
    get_db_connection,
    init_db,
    is_hosted_production_runtime,
    is_postgres_connection,
)


class RazorpayAuthError(Exception):
    """Raised when Razorpay returns authentication 401 failure."""
    pass


class RazorpayAPIError(Exception):
    """Raised when Razorpay returns 5xx or bad gateway error."""
    pass


def get_razorpay_keys() -> Tuple[str, str, bool]:
    """
    Retrieves Razorpay API credentials from environment or secrets.
    Returns (key_id, key_secret, is_live).
    """
    key_id = get_secret("RAZORPAY_KEY_ID")
    key_secret = get_secret("RAZORPAY_KEY_SECRET")

    key_id = (key_id or "").strip()
    key_secret = (key_secret or "").strip()
    is_live = bool(key_id and key_secret and not key_id.startswith("rzp_test_"))
    return key_id, key_secret, is_live


def get_razorpay_client() -> Optional[Any]:
    """Returns an authenticated razorpay.Client instance if SDK is available and keys exist."""
    key_id, key_secret, _ = get_razorpay_keys()
    if razorpay and key_id and key_secret:
        try:
            return razorpay.Client(auth=(key_id, key_secret))
        except Exception as e:
            logger.error(f"Failed to initialize Razorpay client: {e}")
            return None
    return None


def is_razorpay_configured() -> bool:
    """Returns True if live or test Razorpay keys are configured."""
    key_id, key_secret, _ = get_razorpay_keys()
    return bool(key_id and key_secret)


def _record_order_intent(
    order_id: str,
    user_id: str,
    plan_id: Optional[str],
    amount_paise: int,
    *,
    user_email: str = "",
    currency: str = "INR",
    credits: Optional[float] = None,
    is_simulated: Optional[bool] = None,
) -> None:
    """Persists the authoritative order intent in billing_order_intents before returning order to client."""
    clean_order = str(order_id or "").strip()
    if not clean_order:
        return
    resolved_plan_id = str(plan_id or "single_pass").strip()
    resolved_credits = credits
    if resolved_credits is None:
        plan_obj = get_plan_by_id(resolved_plan_id)
        resolved_credits = float(plan_obj.get("credits") or 1.0)
    resolved_sim = clean_order.startswith("order_sim_") if is_simulated is None else bool(is_simulated)

    init_db()
    conn = get_db_connection()
    cur = conn.cursor()
    p = "%s" if is_postgres_connection(conn) else "?"
    try:
        cur.execute(
            f"""
            INSERT INTO billing_order_intents (
                order_id, user_id, user_email, plan_id, amount_paise, currency,
                credits, is_simulated, status, created_at_epoch
            )
            VALUES ({p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, 'CREATED', {p})
            ON CONFLICT (order_id) DO NOTHING
            """,
            (
                clean_order,
                str(user_id or "").strip(),
                str(user_email or "").strip().lower(),
                resolved_plan_id,
                int(amount_paise),
                str(currency or "INR").strip().upper(),
                float(resolved_credits),
                1 if resolved_sim else 0,
                int(time.time()),
            ),
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
        conn.close()


def create_razorpay_order(
    plan_id: Optional[str] = None,
    amount_paise: Optional[int] = None,
    currency: str = "INR",
    receipt: Optional[str] = None,
    user_id: str = "guest_web_user",
    user_email: str = "investor@example.com"
) -> Dict[str, Any]:
    """
    Creates an order via Razorpay Orders API / SDK and persists a durable billing_order_intents record.
    """
    clean_uid = str(user_id or "").strip()
    if not clean_uid or clean_uid == "guest_web_user":
        raise ValueError("Authenticated user account is required to create a billing order.")
    if not plan_id:
        raise ValueError("A valid plan_id is required.")
    plan = get_plan_by_id(plan_id)
    if not plan:
        raise ValueError(f"Invalid plan ID: {plan_id}")

    expected_paise = int(plan["amount_paise"])
    if amount_paise is not None and int(amount_paise) != expected_paise:
        raise ValueError("Requested amount does not match the selected plan price.")
    amount_paise = expected_paise

    clean_currency = str(currency or "INR").strip().upper()
    if clean_currency != "INR":
        raise ValueError("Only INR billing orders are supported.")

    key_id, key_secret, is_live = get_razorpay_keys()
    receipt_id = receipt or f"rcpt_{int(time.time())}_{clean_uid[:8]}"

    # Live or Test API Call via Official Razorpay SDK / REST
    if key_id and key_secret:
        notes = {
            "user_id": clean_uid,
            "user_email": user_email,
            "plan_id": plan["id"],
            "service": INVOICE_SERVICE_DESCRIPTION,
            "credits": str(plan["credits"]),
        }

        # Try official SDK first
        client = get_razorpay_client()
        if client:
            try:
                order_data = client.order.create({
                    "amount": amount_paise,
                    "currency": clean_currency,
                    "receipt": receipt_id,
                    "notes": notes
                })
                order_data["order_id"] = order_data["id"]
                order_data["key_id"] = key_id
                order_data["is_simulated"] = False
                order_data["plan"] = plan
                _record_order_intent(
                    order_data["id"],
                    clean_uid,
                    plan["id"],
                    amount_paise,
                    user_email=user_email,
                    currency=clean_currency,
                    credits=float(plan["credits"]),
                    is_simulated=False,
                )
                return order_data
            except AuthoritativeDatabaseUnavailable:
                raise
            except Exception as e:
                err_str = str(e)
                logger.error(f"Razorpay SDK order.create error: {err_str}")
                if "401" in err_str or "auth" in err_str.lower():
                    raise RazorpayAuthError("Razorpay authentication failed. Invalid API credentials.")
                raise RazorpayAPIError(f"Razorpay API Error: {err_str}")

        # Fallback to direct REST API
        try:
            url = "https://api.razorpay.com/v1/orders"
            payload = {
                "amount": amount_paise,
                "currency": clean_currency,
                "receipt": receipt_id,
                "notes": notes
            }
            resp = requests.post(url, json=payload, auth=(key_id, key_secret), timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                data["order_id"] = data["id"]
                data["key_id"] = key_id
                data["is_simulated"] = False
                data["plan"] = plan
                _record_order_intent(
                    data["id"],
                    clean_uid,
                    plan["id"],
                    amount_paise,
                    user_email=user_email,
                    currency=clean_currency,
                    credits=float(plan["credits"]),
                    is_simulated=False,
                )
                return data
            elif resp.status_code == 401:
                raise RazorpayAuthError("Razorpay authentication failed. Invalid API credentials.")
            else:
                raise RazorpayAPIError(f"Razorpay API Error {resp.status_code}: {resp.text}")
        except (RazorpayAuthError, AuthoritativeDatabaseUnavailable):
            raise
        except Exception as e:
            logger.error(f"Failed to call Razorpay REST API: {e}")
            raise RazorpayAPIError(f"Razorpay order dispatch failed: {e}")

    # Fallback Seamless Sandbox Simulation Order strictly restricted to explicit TESTING=1 mode
    if is_hosted_production_runtime() or os.environ.get("TESTING") != "1":
        raise RazorpayAuthError("Razorpay API credentials are required in non-test environments.")

    simulated_order_id = f"order_sim_{int(time.time())}_{uuid.uuid4().hex[:8]}"
    _record_order_intent(
        simulated_order_id,
        clean_uid,
        plan["id"],
        amount_paise,
        user_email=user_email,
        currency=clean_currency,
        credits=float(plan["credits"]),
        is_simulated=True,
    )
    return {
        "id": simulated_order_id,
        "order_id": simulated_order_id,
        "amount": amount_paise,
        "amount_inr": amount_paise / 100.0,
        "currency": clean_currency,
        "key_id": key_id or "rzp_test_simulated_key",
        "receipt": receipt_id,
        "status": "created",
        "is_simulated": True,
        "plan": plan,
        "notes": {
            "user_id": clean_uid,
            "user_email": user_email,
            "plan_id": plan["id"],
        }
    }


def verify_payment_signature(order_id: str, payment_id: str, signature: str) -> bool:
    """Cryptographically verifies the Razorpay HMAC-SHA256 payment signature."""
    if not order_id or not payment_id or not signature:
        return False

    is_prod = is_hosted_production_runtime()
    is_testing = os.environ.get("TESTING") == "1"

    _, key_secret, *_ = get_razorpay_keys()
    if order_id.startswith("order_sim_"):
        if is_prod or key_secret or not is_testing:
            logger.error("Blocked simulated order_id=%s in non-test/production environment.", order_id)
            return False
        return signature.startswith("sig_sim_") or signature == "simulated_success"

    if not key_secret:
        logger.error("Cannot verify payment signature: RAZORPAY_KEY_SECRET is not configured.")
        return False

    try:
        msg = f"{order_id}|{payment_id}".encode("utf-8")
        expected_sig = hmac.new(key_secret.encode("utf-8"), msg, hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected_sig, signature.strip())
    except Exception as e:
        logger.error("Signature verification exception: %s", e)
        return False


def verify_webhook_signature(raw_body: bytes, signature: str) -> bool:
    """Cryptographically verifies Razorpay X-Razorpay-Signature header using RAZORPAY_WEBHOOK_SECRET."""
    webhook_secret = (get_secret("RAZORPAY_WEBHOOK_SECRET") or "").strip()
    if not webhook_secret or not raw_body or not signature:
        return False
    expected = hmac.new(webhook_secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature.strip())


def fulfill_razorpay_order(
    *,
    order_id: str,
    payment_id: str,
    claimed_user_id: Optional[str] = None,
    claimed_plan_id: Optional[str] = None,
    verified_amount_paise: Optional[int] = None,
    verified_currency: Optional[str] = None,
) -> Tuple[bool, float, str, str]:
    """
    Single atomic fulfilment path shared by browser callback and server-to-server webhook.
    Matches captured payment strictly against the persisted `billing_order_intents` record,
    locks the intent and user row in one transaction, and credits the account once.
    """
    clean_order_id = str(order_id or "").strip()
    clean_payment_id = str(payment_id or "").strip()
    if not clean_order_id or not clean_payment_id:
        return False, 0.0, "", "Missing order_id or payment_id."

    init_db()
    conn = get_db_connection()
    cur = conn.cursor()
    use_pg = is_postgres_connection(conn)
    p = "%s" if use_pg else "?"

    try:
        if not use_pg:
            cur.execute("BEGIN IMMEDIATE")

        lock_sql = " FOR UPDATE" if use_pg else ""
        cur.execute(
            f"""
            SELECT order_id, user_id, user_email, plan_id, amount_paise, currency,
                   credits, is_simulated, status, gateway_payment_id, invoice_number
            FROM billing_order_intents
            WHERE order_id = {p}{lock_sql}
            """,
            (clean_order_id,),
        )
        intent = cur.fetchone()
        if not intent:
            conn.rollback()
            return False, 0.0, "", "Order intent not found."

        (
            _,
            owner_user_id,
            owner_email,
            intent_plan_id,
            intent_amount_paise,
            intent_currency,
            intent_credits,
            intent_simulated,
            intent_status,
            existing_payment_id,
            existing_invoice,
        ) = intent

        # Verify caller/claim consistency against stored order intent
        if claimed_user_id and claimed_user_id != "guest_web_user" and claimed_user_id != owner_user_id:
            conn.rollback()
            return False, 0.0, "", "Order belongs to a different user account."
        if claimed_plan_id and claimed_plan_id != intent_plan_id:
            conn.rollback()
            return False, 0.0, "", "Order plan mismatch."
        expected_plan = get_plan_by_id(intent_plan_id)
        if expected_plan and int(intent_amount_paise) != int(expected_plan["amount_paise"]):
            conn.rollback()
            return False, 0.0, "", "Order amount does not match the selected plan price."
        if verified_amount_paise is not None and int(verified_amount_paise) != int(intent_amount_paise):
            conn.rollback()
            return False, 0.0, "", "Captured payment amount does not match order amount."
        if verified_currency is not None and str(verified_currency).strip().upper() != str(intent_currency).strip().upper():
            conn.rollback()
            return False, 0.0, "", "Captured payment currency does not match order currency."

        # Lock user account row
        cur.execute(
            f"SELECT credits_balance, email, full_name, subscription_tier, subscription_expires_at FROM user_accounts WHERE id = {p}{lock_sql}",
            (owner_user_id,),
        )
        user_row = cur.fetchone()
        if not user_row:
            conn.rollback()
            return False, 0.0, "", "Order owner account not found."
        current_balance = float(user_row[0] or 0.0)
        cust_email = user_row[1] or owner_email
        cust_name = user_row[2] or "Investor"
        raw_exp = user_row[4]

        # Idempotent replay handling: if order intent was already fulfilled
        if intent_status == "FULFILLED":
            conn.rollback()
            if existing_payment_id and existing_payment_id != clean_payment_id:
                return False, current_balance, "", "Order was already fulfilled by a different payment ID."
            return True, current_balance, existing_invoice or "", "Payment already processed (idempotent replay). Balance preserved."

        # Also check if gateway_payment_id was already used on any other order
        cur.execute(
            f"SELECT order_id FROM billing_order_intents WHERE gateway_payment_id = {p}",
            (clean_payment_id,),
        )
        dup_pay = cur.fetchone()
        if dup_pay and dup_pay[0] != clean_order_id:
            conn.rollback()
            return False, current_balance, "", "Payment ID is already bound to another order."

        now_epoch = int(time.time())
        inv_number = f"INV-{datetime.now(IST).strftime('%Y%m')}-{now_epoch % 100000:05d}-{uuid.uuid4().hex[:4].upper()}"
        credits_to_add = float(intent_credits)
        new_balance = round(current_balance + credits_to_add, 2)
        amount_inr = round(float(intent_amount_paise) / 100.0, 2)
        effective_gateway = "simulation" if intent_simulated else "razorpay"
        pack_type = str(intent_plan_id).upper()
        tx_id = f"tx_{now_epoch}_{owner_user_id[:8]}_{uuid.uuid4().hex[:6]}"

        # 1. Mark order intent FULFILLED
        cur.execute(
            f"""
            UPDATE billing_order_intents
            SET status = 'FULFILLED',
                gateway_payment_id = {p},
                invoice_number = {p},
                fulfilled_at_epoch = {p}
            WHERE order_id = {p} AND status = 'CREATED'
            """,
            (clean_payment_id, inv_number, now_epoch, clean_order_id),
        )
        if cur.rowcount != 1:
            conn.rollback()
            return True, current_balance, existing_invoice or "", "Payment already processed."

        # 2. Insert credit_transactions record
        cur.execute(
            f"""
            INSERT INTO credit_transactions (
                id, user_id, amount_inr, credits_added, payment_gateway,
                gateway_order_id, gateway_payment_id, status, pack_type, invoice_number,
                customer_email, customer_name, base_amount_inr, tax_gst_inr, sac_code
            )
            VALUES ({p}, {p}, {p}, {p}, {p}, {p}, {p}, 'success', {p}, {p}, {p}, {p}, {p}, 0.0, '')
            """,
            (
                tx_id,
                owner_user_id,
                amount_inr,
                credits_to_add,
                effective_gateway,
                clean_order_id,
                clean_payment_id,
                pack_type,
                inv_number,
                cust_email,
                cust_name,
                amount_inr,
            ),
        )

        # 3. Update user_accounts balance & subscription expiry if applicable
        now_dt = datetime.now(IST)
        base_exp_dt = now_dt
        if raw_exp:
            try:
                parsed_exp = raw_exp if isinstance(raw_exp, datetime) else datetime.fromisoformat(str(raw_exp).replace("Z", "+00:00"))
                if parsed_exp.tzinfo is None:
                    parsed_exp = parsed_exp.replace(tzinfo=IST)
                if parsed_exp > now_dt:
                    base_exp_dt = parsed_exp
            except Exception as exp_err:
                logger.debug("Subscription expiry parse notice: %s", exp_err)

        if "PRO_MONTHLY" in pack_type:
            exp_iso = (base_exp_dt + timedelta(days=30)).isoformat()
            cur.execute(
                f"UPDATE user_accounts SET credits_balance = {p}, subscription_tier = 'pro_monthly', subscription_expires_at = {p} WHERE id = {p}",
                (new_balance, exp_iso, owner_user_id),
            )
        elif "PRO_ANNUAL" in pack_type:
            exp_iso = (base_exp_dt + timedelta(days=365)).isoformat()
            cur.execute(
                f"UPDATE user_accounts SET credits_balance = {p}, subscription_tier = 'pro_annual', subscription_expires_at = {p} WHERE id = {p}",
                (new_balance, exp_iso, owner_user_id),
            )
        else:
            cur.execute(
                f"UPDATE user_accounts SET credits_balance = {p} WHERE id = {p}",
                (new_balance, owner_user_id),
            )

        # 4. Append credit_usage_ledger
        cur.execute(
            f"""
            INSERT INTO credit_usage_ledger (user_id, ticker, action_type, credits_consumed, balance_after)
            VALUES ({p}, 'BILLING', {p}, {p}, {p})
            """,
            (owner_user_id, f"TOPUP_{pack_type}", -credits_to_add, new_balance),
        )

        # 5. Append credit_settlement_operations (atomic idempotent capture receipt)
        cur.execute(
            f"""
            INSERT INTO credit_settlement_operations (
                operation_id, user_id, operation_type, credits_delta, balance_after,
                idempotency_key, payment_id, order_id, metadata_json, created_at
            )
            VALUES ({p}, {p}, 'PAYMENT_CAPTURE_CREDIT', {p}, {p}, {p}, {p}, {p}, {p}, {p})
            ON CONFLICT (idempotency_key) DO NOTHING
            """,
            (
                f"cso_{tx_id}",
                owner_user_id,
                credits_to_add,
                new_balance,
                f"paycap:{clean_payment_id}",
                clean_payment_id,
                clean_order_id,
                json.dumps({"invoice_number": inv_number, "plan_id": intent_plan_id, "amount_inr": amount_inr}),
                now_epoch,
            ),
        )

        conn.commit()
        return True, new_balance, inv_number, f"Payment confirmed! Added {credits_to_add} credits to your account."
    except AuthoritativeDatabaseUnavailable:
        raise
    except Exception as exc:
        conn.rollback()
        logger.error("Error fulfilling Razorpay order %s: %s", clean_order_id, exc)
        return False, 0.0, "", "Database error during payment fulfilment."
    finally:
        cur.close()
        conn.close()


def captured_payment_terms(payment: Any, *, order_id: str, payment_id: str) -> Optional[Tuple[int, str]]:
    """Return verified capture terms for the exact payment and order."""
    if (
        not isinstance(payment, dict)
        or not order_id
        or not payment_id
        or payment.get("id") != payment_id
        or payment.get("order_id") != order_id
        or payment.get("status") != "captured"
    ):
        return None
    amount = payment.get("amount")
    currency = payment.get("currency")
    if type(amount) is not int or amount <= 0 or not isinstance(currency, str) or not currency.strip():
        return None
    return amount, currency


def _is_order_fulfilled_for_payment(order_id: str, payment_id: str) -> bool:
    """Return True if billing_order_intents already records this exact (order_id, payment_id) as FULFILLED."""
    clean_order_id = str(order_id or "").strip()
    clean_payment_id = str(payment_id or "").strip()
    if not clean_order_id or not clean_payment_id:
        return False
    init_db()
    conn = get_db_connection()
    cur = conn.cursor()
    p = "%s" if is_postgres_connection(conn) else "?"
    try:
        cur.execute(
            f"SELECT status, gateway_payment_id FROM billing_order_intents WHERE order_id = {p}",
            (clean_order_id,),
        )
        row = cur.fetchone()
        return bool(row and row[0] == "FULFILLED" and row[1] == clean_payment_id)
    except AuthoritativeDatabaseUnavailable:
        raise
    except Exception as exc:
        logger.warning("Order intent status check failed for %s: %s", clean_order_id, type(exc).__name__)
        return False
    finally:
        cur.close()
        conn.close()


def _fetch_payment(payment_id: str) -> Optional[Dict[str, Any]]:
    client = get_razorpay_client()
    if client:
        try:
            payment = client.payment.fetch(payment_id, timeout=8)
            if isinstance(payment, dict):
                return payment
        except Exception as exc:
            logger.warning("Razorpay SDK payment lookup failed: %s", type(exc).__name__)

    if os.environ.get("TESTING") == "1" and not is_hosted_production_runtime():
        return None
    key_id, key_secret, *_ = get_razorpay_keys()
    if not key_id or not key_secret:
        return None
    try:
        response = requests.get(
            f"https://api.razorpay.com/v1/payments/{quote(payment_id, safe='')}",
            auth=(key_id, key_secret),
            timeout=8,
        )
        response.raise_for_status()
        payment = response.json()
        return payment if isinstance(payment, dict) else None
    except (requests.RequestException, ValueError) as exc:
        logger.warning("Razorpay REST payment lookup failed: %s", type(exc).__name__)
        return None


def process_successful_payment(
    user_id: str,
    plan_id: str,
    order_id: str,
    payment_id: str,
    signature: str
) -> Tuple[bool, float, str, str]:
    """
    Browser callback entrypoint: verifies Razorpay order|payment signature and delegates
    to the shared atomic `fulfill_razorpay_order` path.
    """
    plan = get_plan_by_id(plan_id)
    if not plan:
        return False, 0.0, "", "Invalid plan selected."

    is_valid = verify_payment_signature(order_id, payment_id, signature)
    if not is_valid:
        return False, 0.0, "", "Payment signature verification failed. Transaction was not confirmed."

    verified_amount_paise = None
    verified_currency = None
    # Simulated orders already passed the explicit non-hosted test-only signature gate.
    if not order_id.startswith("order_sim_"):
        if not _is_order_fulfilled_for_payment(order_id, payment_id):
            payment = _fetch_payment(payment_id)
            terms = captured_payment_terms(payment, order_id=order_id, payment_id=payment_id)
            if terms is None and not _is_order_fulfilled_for_payment(order_id, payment_id):
                return False, 0.0, "", "Payment capture could not be confirmed. Credits have not been issued."
            if terms is not None:
                verified_amount_paise, verified_currency = terms

    return fulfill_razorpay_order(
        order_id=order_id,
        payment_id=payment_id,
        claimed_user_id=user_id,
        claimed_plan_id=plan["id"],
        verified_amount_paise=verified_amount_paise,
        verified_currency=verified_currency,
    )


def generate_invoice_html(
    invoice_number: str,
    user_email: str,
    plan_name: str,
    amount_inr: float,
    credits_added: float,
    payment_id: str,
    date_str: str
) -> str:
    """
    Generates a formal, printable HTML invoice receipt complying with Indian IT service rules.
    """
    import html as _html
    safe_inv = _html.escape(str(invoice_number or ""))
    safe_email = _html.escape(str(user_email or ""))
    safe_plan = _html.escape(str(plan_name or ""))
    safe_pay = _html.escape(str(payment_id or ""))
    safe_date = _html.escape(str(date_str or ""))
    tax_amount = 0.0
    base_amount = round(float(amount_inr), 2)

    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <title>Receipt {safe_inv}</title>
        <style>
            body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; margin: 40px; color: #1e293b; }}
            .header {{ display: flex; justify-content: space-between; border-bottom: 2px solid #e2e8f0; padding-bottom: 20px; }}
            .brand {{ font-size: 20px; font-weight: 800; color: #0f172a; }}
            .meta {{ text-align: right; font-size: 13px; color: #64748b; }}
            .inv-table {{ width: 100%; border-collapse: collapse; margin-top: 30px; }}
            .inv-table th, .inv-table td {{ padding: 12px; text-align: left; border-bottom: 1px solid #e2e8f0; font-size: 14px; }}
            .inv-table th {{ background-color: #f8fafc; font-weight: 600; }}
            .total-row td {{ font-weight: 800; font-size: 16px; border-top: 2px solid #0f172a; }}
            .disclaimer {{ margin-top: 40px; font-size: 11px; color: #94a3b8; line-height: 1.5; border-top: 1px solid #e2e8f0; padding-top: 15px; }}
        </style>
    </head>
    <body>
        <div class="header">
            <div>
                <div class="brand">MOATNOMICS</div>
                <div style="font-size: 12px; color: #64748b; margin-top: 4px;">Equity Thesis & Drift Monitoring</div>
            </div>
            <div class="meta">
                <div style="font-size: 16px; font-weight: 700; color: #0f172a;">PAYMENT RECEIPT</div>
                <div>Receipt #: {safe_inv}</div>
                <div>Date: {safe_date}</div>
                <div>Payment ID: {safe_pay}</div>
                <div>Billed To: {safe_email}</div>
            </div>
        </div>

        <table class="inv-table">
            <thead>
                <tr>
                    <th>Item Description</th>
                    <th>Credits Granted</th>
                    <th>Amount (INR)</th>
                    <th>Tax (0%)</th>
                    <th>Total (INR)</th>
                </tr>
            </thead>
            <tbody>
                <tr>
                    <td>
                        <strong>{safe_plan}</strong><br>
                        <span style="font-size: 12px; color: #64748b;">{INVOICE_SERVICE_DESCRIPTION}</span>
                    </td>
                    <td>{float(credits_added):.1f} Credits</td>
                    <td>₹{base_amount:.2f}</td>
                    <td>₹{tax_amount:.2f}</td>
                    <td>₹{float(amount_inr):.2f}</td>
                </tr>
                <tr class="total-row">
                    <td colspan="4" style="text-align: right;">Total Paid:</td>
                    <td>₹{float(amount_inr):.2f}</td>
                </tr>
            </tbody>
        </table>

        <div class="disclaimer">
            <p style="margin-bottom: 8px;"><strong>Entity Notice:</strong> Moatnomics is an independent computational research tool and is not registered as a corporate entity or under GST. This electronic transaction receipt confirms purchase of digital computational credits (Tax: ₹0.00).</p>
            <strong>Mandatory Safe-Harbor Disclosure:</strong><br>
            {INVOICE_DISCLAIMER}
        </div>
    </body>
    </html>
    """
