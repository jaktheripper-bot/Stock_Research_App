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

# Load environment variables from .env
try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

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

logger = logging.getLogger("equity_research.core.billing")


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


def verify_payment_signature(
    order_id: str,
    payment_id: str,
    signature: str
) -> bool:
    """
    Verifies HMAC-SHA256 signature using Razorpay SDK utility or cryptographic compare.
    Formula: HMAC-SHA256(order_id + "|" + payment_id, secret) == signature
    """
    if not order_id or not payment_id or not signature:
        return False

    # In sandbox simulation mode, verify simulation token
    if order_id.startswith("order_sim_"):
        return signature.startswith("sig_sim_") or signature == "simulated_success"

    key_id, key_secret, _ = get_razorpay_keys()
    if not key_secret:
        return False

    # 1. Try Razorpay SDK verify_payment_signature
    client = get_razorpay_client()
    if client:
        try:
            client.utility.verify_payment_signature({
                "razorpay_order_id": order_id,
                "razorpay_payment_id": payment_id,
                "razorpay_signature": signature
            })
            return True
        except Exception:
            # Fall through to raw HMAC compare
            pass

    # 2. Raw HMAC-SHA256 cryptographic verification
    try:
        msg = f"{order_id}|{payment_id}".encode("utf-8")
        expected_sig = hmac.new(key_secret.encode("utf-8"), msg, hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected_sig, signature)
    except Exception as e:
        logger.error(f"Signature verification exception: {e}")
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
    """
    plan = get_plan_by_id(plan_id)
    if not plan:
        return False, 0.0, "", "Invalid plan selected."

    is_valid = verify_payment_signature(order_id, payment_id, signature)
    if not is_valid:
        return False, 0.0, "", "Payment signature verification failed. Transaction was not confirmed."

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
    gst_rate = 0.18
    base_amount = round(amount_inr / (1 + gst_rate), 2)
    gst_amount = round(amount_inr - base_amount, 2)

    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <title>Invoice {invoice_number}</title>
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
                <div class="brand">STOCK RESEARCH APP</div>
                <div style="font-size: 12px; color: #64748b; margin-top: 4px;">Institutional Equity Thesis & Drift Surveillance</div>
            </div>
            <div class="meta">
                <div style="font-size: 16px; font-weight: 700; color: #0f172a;">TAX INVOICE / RECEIPT</div>
                <div>Invoice #: {invoice_number}</div>
                <div>Date: {date_str}</div>
                <div>Payment ID: {payment_id}</div>
                <div>Billed To: {user_email}</div>
            </div>
        </div>

        <table class="inv-table">
            <thead>
                <tr>
                    <th>Item Description</th>
                    <th>Credits Granted</th>
                    <th>Base Amount (INR)</th>
                    <th>GST (18%)</th>
                    <th>Total (INR)</th>
                </tr>
            </thead>
            <tbody>
                <tr>
                    <td>
                        <strong>{plan_name}</strong><br>
                        <span style="font-size: 12px; color: #64748b;">{INVOICE_SERVICE_DESCRIPTION}</span>
                    </td>
                    <td>{credits_added:.1f} Credits</td>
                    <td>₹{base_amount:.2f}</td>
                    <td>₹{gst_amount:.2f}</td>
                    <td>₹{amount_inr:.2f}</td>
                </tr>
                <tr class="total-row">
                    <td colspan="4" style="text-align: right;">Total Paid (Inclusive of Taxes):</td>
                    <td>₹{amount_inr:.2f}</td>
                </tr>
            </tbody>
        </table>

        <div class="disclaimer">
            <strong>Mandatory Safe-Harbor Disclosure:</strong><br>
            {INVOICE_DISCLAIMER}
        </div>
    </body>
    </html>
    """
