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
import time
import logging
import requests
from typing import Dict, Any, Tuple, Optional

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


_ORDER_INTENT_CACHE: Dict[str, Dict[str, Any]] = {}


def _record_order_intent(order_id: str, user_id: str, plan_id: Optional[str], amount_paise: int) -> None:
    if order_id:
        _ORDER_INTENT_CACHE[order_id] = {
            "user_id": user_id,
            "plan_id": plan_id,
            "amount_paise": int(amount_paise),
            "created_at": int(time.time()),
        }


def create_razorpay_order(
    plan_id: Optional[str] = None,
    amount_paise: Optional[int] = None,
    currency: str = "INR",
    receipt: Optional[str] = None,
    user_id: str = "guest_web_user",
    user_email: str = "investor@example.com"
) -> Dict[str, Any]:
    """
    Creates an order via Razorpay Orders API / SDK.
    Supports either plan_id or explicit amount_paise (minimum 100 paise).
    """
    plan = None
    if plan_id:
        plan = get_plan_by_id(plan_id)
        if not plan:
            raise ValueError(f"Invalid plan ID: {plan_id}")
        amount_paise = int(plan["amount_inr"] * 100)
    elif amount_paise is not None:
        amount_paise = int(amount_paise)
    else:
        raise ValueError("Either plan_id or amount_paise must be provided.")

    if amount_paise < 100:
        raise ValueError("Minimum amount is 100 paise (₹1.00)")

    key_id, key_secret, is_live = get_razorpay_keys()
    receipt_id = receipt or f"rcpt_{int(time.time())}_{user_id[:8]}"

    # Live or Test API Call via Official Razorpay SDK / REST
    if key_id and key_secret:
        notes = {
            "user_id": user_id,
            "user_email": user_email,
            "plan_id": plan_id or "custom",
            "service": INVOICE_SERVICE_DESCRIPTION
        }
        if plan:
            notes["credits"] = str(plan["credits"])

        # Try official SDK first
        client = get_razorpay_client()
        if client:
            try:
                order_data = client.order.create({
                    "amount": amount_paise,
                    "currency": currency,
                    "receipt": receipt_id,
                    "notes": notes
                })
                order_data["order_id"] = order_data["id"]
                order_data["key_id"] = key_id
                order_data["is_simulated"] = False
                order_data["plan"] = plan
                _record_order_intent(order_data["id"], user_id, plan_id, amount_paise)
                return order_data
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
                "currency": currency,
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
                _record_order_intent(data["id"], user_id, plan_id, amount_paise)
                return data
            elif resp.status_code == 401:
                raise RazorpayAuthError("Razorpay authentication failed. Invalid API credentials.")
            else:
                raise RazorpayAPIError(f"Razorpay API Error {resp.status_code}: {resp.text}")
        except RazorpayAuthError:
            raise
        except Exception as e:
            logger.error(f"Failed to call Razorpay REST API: {e}")
            raise RazorpayAPIError(f"Razorpay order dispatch failed: {e}")

    # Fallback Seamless Sandbox Simulation Order for Dev & Offline Testing
    simulated_order_id = f"order_sim_{int(time.time())}_{user_id[:6]}"
    _record_order_intent(simulated_order_id, user_id, plan_id, amount_paise)
    return {
        "id": simulated_order_id,
        "order_id": simulated_order_id,
        "amount": amount_paise,
        "amount_inr": amount_paise / 100.0,
        "currency": currency,
        "key_id": key_id or "rzp_test_simulated_key",
        "receipt": receipt_id,
        "status": "created",
        "is_simulated": True,
        "plan": plan,
        "notes": {
            "user_id": user_id,
            "user_email": user_email,
            "plan_id": plan_id or "custom",
        }
    }


def verify_payment_signature(order_id: str, payment_id: str, signature: str) -> bool:
    """Cryptographically verifies the Razorpay HMAC-SHA256 payment signature."""
    if not order_id or not payment_id or not signature:
        return False

    is_prod = os.environ.get("ENVIRONMENT") == "production" or os.environ.get("RENDER") == "true"
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


def process_successful_payment(
    user_id: str,
    plan_id: str,
    order_id: str,
    payment_id: str,
    signature: str
) -> Tuple[bool, float, str, str]:
    """
    Validates payment signature, grants credits or upgrades subscription tier,
    and returns (success, new_balance, invoice_number, message).
    Enforces atomic idempotency so replay attacks return current balance without duplicate credits.
    """
    plan = get_plan_by_id(plan_id)
    if not plan:
        return False, 0.0, "", "Invalid plan selected."

    is_valid = verify_payment_signature(order_id, payment_id, signature)
    if not is_valid:
        return False, 0.0, "", "Payment signature verification failed. Transaction was not confirmed."

    # Verify order-to-plan amount and user integrity against recorded order intent
    intent = _ORDER_INTENT_CACHE.get(order_id)
    if intent:
        if int(intent.get("amount_paise", 0)) < int(plan["amount_paise"]):
            logger.error(
                "Payment amount mismatch for order %s: paid %s paise vs required %s paise for plan %s",
                order_id, intent.get("amount_paise"), plan["amount_paise"], plan["id"]
            )
            return False, 0.0, "", "Order amount does not match the selected plan price."
        if intent.get("plan_id") and intent["plan_id"] != plan["id"] and intent["plan_id"] != plan_id:
            logger.error(
                "Plan mismatch for order %s: created for %s, claimed %s",
                order_id, intent.get("plan_id"), plan["id"]
            )
            return False, 0.0, "", "Order plan mismatch."
        intent_uid = intent.get("user_id")
        if (
            intent_uid
            and intent_uid != "guest_web_user"
            and user_id
            and user_id != "guest_web_user"
            and intent_uid != user_id
        ):
            logger.error(
                "Order user mismatch for order %s: created for %s, claimed by %s",
                order_id, intent_uid, user_id
            )
            return False, 0.0, "", "Order belongs to a different user session."
    elif not order_id.startswith("order_sim_"):
        remote_order = None
        client = get_razorpay_client()
        if client:
            try:
                remote_order = client.order.fetch(order_id)
            except Exception as fetch_err:
                logger.warning("Could not fetch remote order metadata via SDK for %s: %s", order_id, fetch_err)
        if remote_order is None and os.environ.get("TESTING") != "1":
            key_id, key_secret, _ = get_razorpay_keys()
            if key_id and key_secret:
                try:
                    r_ord = requests.get(
                        f"https://api.razorpay.com/v1/orders/{order_id}",
                        auth=(key_id, key_secret),
                        timeout=8,
                    )
                    if r_ord.status_code == 200:
                        remote_order = r_ord.json()
                except Exception as rest_err:
                    logger.warning("Could not fetch remote order metadata via REST for %s: %s", order_id, rest_err)

        if isinstance(remote_order, dict):
            remote_amount = int(remote_order.get("amount", 0))
            if remote_amount < int(plan["amount_paise"]):
                logger.error(
                    "Remote Razorpay order %s amount %s < plan %s price %s",
                    order_id, remote_amount, plan["id"], plan["amount_paise"]
                )
                return False, 0.0, "", "Verified payment amount is less than plan price."
            notes = remote_order.get("notes") or {}
            note_plan = notes.get("plan_id")
            if note_plan and note_plan != "custom" and note_plan != plan["id"] and note_plan != plan_id:
                logger.error(
                    "Remote Razorpay order %s plan_id %s != claimed %s",
                    order_id, note_plan, plan["id"]
                )
                return False, 0.0, "", "Verified order plan does not match claimed plan."
        elif os.environ.get("TESTING") != "1":
            logger.error("Fail-closed: unable to verify remote Razorpay order %s metadata.", order_id)
            return False, 0.0, "", "Could not verify order metadata with payment gateway."

    # Idempotency check: if transaction already processed, return existing confirmation
    from core.db.users import get_credit_transaction_by_gateway_id, get_user_credits_balance
    existing = get_credit_transaction_by_gateway_id(payment_id=payment_id, order_id=order_id)
    if existing:
        current_bal = get_user_credits_balance(user_id)
        existing_inv = existing.get("invoice_number") or ""
        logger.info(
            f"Payment {payment_id} (order: {order_id}) already processed (idempotent replay). "
            f"User {user_id} balance preserved at {current_bal}."
        )
        return True, current_bal, existing_inv, "Payment already processed (idempotent replay). Balance preserved."

    inv_number = f"INV-{time.strftime('%Y%m')}-{int(time.time()) % 100000:05d}"
    success, new_balance = add_user_credits(
        user_id=user_id,
        amount_inr=float(plan["amount_inr"]),
        credits_added=float(plan["credits"]),
        pack_type=plan["id"].upper(),
        gateway_order_id=order_id,
        gateway_payment_id=payment_id,
        status="success",
        invoice_number=inv_number
    )

    if success:
        return True, new_balance, inv_number, f"Payment confirmed! Added {plan['credits']} credits to your account."
    return False, 0.0, "", "Could not credit account balance in database. Please contact support."


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
