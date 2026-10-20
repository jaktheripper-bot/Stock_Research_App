"""
Support Notification Dispatcher.

Handles:
- Dispatches alert events into the database for the Admin Console
- Sends instant email alerts to administrator when complaints/tickets are submitted
- Supports SMTP configuration with graceful mock/log fallback
"""

import os
import smtplib
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Optional

from core.db import record_alert_event
from core.config import get_secret

logger = logging.getLogger("equity_research.core.notify")


def _get_cfg(key: str, default: Optional[str] = None) -> Optional[str]:
    """Retrieves configuration value across os.environ, .env, and local secrets."""
    if key in os.environ:
        val = os.environ[key]
        return val if val != "" else default
    secret_val = get_secret(key)
    if secret_val:
        return str(secret_val)
    return default


def get_admin_notification_email() -> str:
    """Retrieves target admin recipient email."""
    return (
        _get_cfg("ADMIN_ALERT_EMAIL")
        or _get_cfg("ADMIN_EMAIL")
        or "admin@moatnomics.com"
    )


def is_email_service_configured() -> bool:
    """Checks whether real outgoing email credentials are configured in the environment."""
    if _get_cfg("RESEND_API_KEY"):
        return True
    return bool(_get_cfg("SMTP_HOST") and _get_cfg("SMTP_USER") and _get_cfg("SMTP_PASSWORD"))


def get_email_service_status() -> dict:
    """Returns metadata describing active outgoing email provider."""
    if _get_cfg("RESEND_API_KEY"):
        return {
            "configured": True,
            "provider": "Resend API",
            "from_email": _get_cfg("SMTP_FROM") or "noreply@moatnomics.com"
        }
    if _get_cfg("SMTP_HOST") and _get_cfg("SMTP_USER") and _get_cfg("SMTP_PASSWORD"):
        host = _get_cfg("SMTP_HOST")
        port = _get_cfg("SMTP_PORT", "587")
        return {
            "configured": True,
            "provider": f"SMTP ({host}:{port})",
            "from_email": _get_cfg("SMTP_FROM") or _get_cfg("SMTP_USER")
        }
    return {
        "configured": False,
        "provider": "Mock / Console Logging (Unsent)",
        "from_email": "noreply@localhost"
    }


def _dispatch_via_resend(from_email: str, to_email: str, subject: str, text: str, html: Optional[str] = None) -> bool:
    """Dispatches outgoing email via Resend HTTP REST API."""
    resend_api_key = _get_cfg("RESEND_API_KEY")
    if not resend_api_key:
        return False
    try:
        import json
        import urllib.request
        import ssl
        try:
            import certifi
            ctx = ssl.create_default_context(cafile=certifi.where())
        except Exception as e:
            logger.warning("certifi not available or context creation failed, using system default SSL context: %s", e)
            ctx = ssl.create_default_context()

        payload = {
            "from": from_email,
            "to": [to_email],
            "subject": subject,
            "text": text,
        }
        if html:
            payload["html"] = html

        req = urllib.request.Request(
            "https://api.resend.com/emails",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {resend_api_key}",
                "Content-Type": "application/json",
                "User-Agent": "Moatnomics-Notifier/1.0"
            },
            method="POST"
        )
        with urllib.request.urlopen(req, context=ctx, timeout=10) as resp:
            if resp.status in (200, 201):
                logger.info("Dispatched email via Resend API to %s (Subject: %s)", to_email, subject)
                return True
            logger.error("Resend API responded with unexpected status %s for %s", resp.status, to_email)
            return False
    except Exception as e:
        logger.error("Error dispatching email via Resend API to %s: %s", to_email, e)
        return False


def _dispatch_via_smtp(from_email: str, to_email: str, subject: str, text: str, html: Optional[str] = None) -> bool:
    """Dispatches outgoing email via SMTP TLS/SSL."""
    smtp_host = _get_cfg("SMTP_HOST")
    smtp_port = int(_get_cfg("SMTP_PORT", "587"))
    smtp_user = _get_cfg("SMTP_USER")
    smtp_password = _get_cfg("SMTP_PASSWORD")

    if not (smtp_host and smtp_user and smtp_password):
        return False

    try:
        if html:
            msg = MIMEMultipart("alternative")
            msg["From"] = from_email
            msg["To"] = to_email
            msg["Subject"] = subject
            msg.attach(MIMEText(text, "plain"))
            msg.attach(MIMEText(html, "html"))
        else:
            msg = MIMEMultipart()
            msg["From"] = from_email
            msg["To"] = to_email
            msg["Subject"] = subject
            msg.attach(MIMEText(text, "plain"))

        if smtp_port == 465:
            with smtplib.SMTP_SSL(smtp_host, smtp_port, timeout=10) as server:
                server.login(smtp_user, smtp_password)
                server.send_message(msg)
        else:
            with smtplib.SMTP(smtp_host, smtp_port, timeout=10) as server:
                server.starttls()
                server.login(smtp_user, smtp_password)
                server.send_message(msg)

        logger.info("Dispatched email via SMTP (%s:%s) to %s (Subject: %s)", smtp_host, smtp_port, to_email, subject)
        return True
    except Exception as e:
        logger.error("Failed to dispatch SMTP email to %s: %s", to_email, e)
        return False


def send_ticket_notification_email(ticket: dict) -> bool:
    """
    Sends an email notification to the administrator regarding a newly submitted
    complaint, billing dispute, or support ticket.
    If SMTP / Resend credentials are not configured, logs the dispatch gracefully and returns False.
    """
    admin_email = get_admin_notification_email()
    sender_email = _get_cfg("SMTP_FROM") or _get_cfg("RESEND_FROM") or _get_cfg("SMTP_USER") or "noreply@moatnomics.com"

    subject = f"🚨 [New Support Ticket] {ticket.get('ticket_id')} - {ticket.get('subject')}"
    body = f"""
===============================================================
MOATNOMICS - NEW USER COMPLAINT / SUPPORT TICKET
===============================================================

Ticket Reference: {ticket.get('ticket_id')}
Created At:       {ticket.get('created_at')}
Category:         {ticket.get('category', 'general').upper()}
Source:           {ticket.get('source', 'web_contact')}

USER DETAILS:
Name:             {ticket.get('user_name') or 'N/A'}
Email:            {ticket.get('user_email')}

SUBJECT:
{ticket.get('subject')}

MESSAGE / GRIEVANCE:
{ticket.get('message')}

===============================================================
Action: Review and resolve this complaint in the Admin Console (./run.sh admin).
Turnaround Target: 24h SEBI / IT Rules 2021 statutory acknowledgment.
===============================================================
"""

    if _get_cfg("RESEND_API_KEY"):
        return _dispatch_via_resend(sender_email, admin_email, subject, body)

    if _get_cfg("SMTP_HOST") and _get_cfg("SMTP_USER") and _get_cfg("SMTP_PASSWORD"):
        return _dispatch_via_smtp(sender_email, admin_email, subject, body)

    # Graceful logging fallback when SMTP server is pending configuration
    logger.info(
        f"[MOCK/LOG EMAIL ALERT] (Unsent: email service unconfigured) Sent to: {admin_email} | Subject: {subject} | "
        f"Ticket: {ticket.get('ticket_id')} from {ticket.get('user_email')}"
    )
    return False


def dispatch_support_ticket_alert(ticket: dict):
    """
    1. Records an alert event in the database (visible in Admin Console / Alert Hub)
    2. Sends an email notification to the administrator
    """
    tid = ticket.get("ticket_id", "TKT")
    category = ticket.get("category", "support")
    email = ticket.get("user_email", "Anonymous")
    subject = ticket.get("subject", "User Inquiry")
    msg_preview = ticket.get("message", "")[:120]

    severity = "critical" if category in ["billing", "grievance", "refund"] else "high"

    # 1. Post to database alert events
    try:
        record_alert_event(
            ticker="SUPPORT",
            category="Support 📩",
            severity=severity,
            title=f"New Ticket {tid}: {subject}",
            details=f"From: {email} | Category: {category} | Preview: {msg_preview}",
            source="Customer Support Desk"
        )
    except Exception as e:
        logger.error(f"Error recording alert event for ticket {tid}: {e}")

    # 2. Send email alert to administrator
    try:
        send_ticket_notification_email(ticket)
    except Exception as e:
        logger.error(f"Error sending email alert for ticket {tid}: {e}")


def send_ticket_reply_email(ticket: dict, reply_message: str, admin_name: str = "Research Desk") -> bool:
    """
    Sends an email response directly to the user regarding their support ticket or grievance.
    If SMTP credentials are not configured, logs the dispatch gracefully and returns False (not delivered).
    """
    user_email = ticket.get("user_email")
    if not user_email:
        logger.warning("Cannot dispatch reply email: ticket %s has no user_email", ticket.get("ticket_id"))
        return False

    ticket_id = ticket.get("ticket_id", "TKT")
    original_subject = ticket.get("subject", "Support Inquiry")
    subject = f"Re: [{ticket_id}] {original_subject}"
    user_name = ticket.get("user_name") or "Investor"
    sender_email = _get_cfg("SMTP_FROM") or _get_cfg("RESEND_FROM") or _get_cfg("SMTP_USER") or "noreply@moatnomics.com"

    text_body = f"""Hello {user_name},

Thank you for reaching out to Moatnomics.

{reply_message}

---
Ticket Reference: {ticket_id}
Original Subject: {original_subject}
Original Message:
"{ticket.get('message', '').strip()}"

You can view ongoing status or submit further queries through our contact desk:
https://moatnomics.com/contact

Kind regards,
Moatnomics Service Desk
"""

    html_body = f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <style>
    body {{ font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; line-height: 1.6; color: #282F33; background-color: #F7F5EE; margin: 0; padding: 24px; }}
    .container {{ max-width: 600px; margin: 0 auto; background: #ffffff; border-radius: 8px; border: 1px solid #D9E3E8; overflow: hidden; }}
    .header {{ background: #0E3D32; color: #F7F5EE; padding: 20px 24px; border-bottom: 3px solid #7DA77A; }}
    .header h2 {{ margin: 0; font-family: 'Playfair Display', Georgia, serif; font-size: 18px; font-weight: 700; letter-spacing: -0.01em; color: #F7F5EE; }}
    .header p {{ margin: 4px 0 0; font-size: 12px; color: #D9E3E8; }}
    .content {{ padding: 24px; }}
    .reply-box {{ background: #F7F5EE; border-left: 4px solid #0E3D32; padding: 16px; border-radius: 4px; font-size: 15px; color: #0B2337; margin: 16px 0; white-space: pre-wrap; }}
    .original-quote {{ background: #F7F5EE; border-left: 4px solid #7DA77A; padding: 14px; font-size: 13px; color: #282F33; margin-top: 20px; border-radius: 4px; }}
    .footer {{ background: #F7F5EE; padding: 16px 24px; font-size: 12px; color: #282F33; border-top: 1px solid #D9E3E8; text-align: center; }}
    .footer a {{ color: #0E3D32; text-decoration: none; }}
    .badge {{ display: inline-block; background: #0B2337; color: #C7E268; padding: 2px 8px; border-radius: 4px; font-size: 11px; font-weight: 600; }}
  </style>
</head>
<body>
  <div class="container">
    <div class="header">
      <h2>Moatnomics Service Desk</h2>
      <p>Ticket Reference: <span class="badge">{ticket_id}</span></p>
    </div>
    <div class="content">
      <p>Hello <strong>{user_name}</strong>,</p>
      <p>Thank you for reaching out to us. We have reviewed your query and here is our update:</p>
      
      <div class="reply-box">{reply_message}</div>
      
      <div class="original-quote">
        <p style="margin: 0 0 6px 0; font-weight: 600; color: #0B2337;">In reference to your message ({ticket.get('created_at', 'recently')}):</p>
        <p style="margin: 0; font-style: italic;">"{ticket.get('message', '').strip()}"</p>
      </div>

      <p style="margin-top: 24px; font-size: 14px;">If you have any further questions or require additional details, you can connect with us directly via the <a href="https://moatnomics.com/contact" style="color: #0E3D32; font-weight: 600;">Feedback & Grievances Desk</a>.</p>
    </div>
    <div class="footer">
      <p style="margin: 0 0 4px 0;">Moatnomics &bull; Independent Quantitative Equity & Asset Intelligence</p>
      <p style="margin: 0;">This email was sent in direct response to inquiry {ticket_id}.</p>
    </div>
  </div>
</body>
</html>
"""

    if _get_cfg("RESEND_API_KEY"):
        return _dispatch_via_resend(sender_email, user_email, subject, text_body, html=html_body)

    if _get_cfg("SMTP_HOST") and _get_cfg("SMTP_USER") and _get_cfg("SMTP_PASSWORD"):
        return _dispatch_via_smtp(sender_email, user_email, subject, text_body, html=html_body)

    logger.warning(
        "[MOCK/LOG USER EMAIL REPLY] Outgoing email credentials not configured (SMTP_HOST/RESEND_API_KEY). "
        "Email NOT dispatched over network. Logged for ticket %s to %s | Subject: %s | Preview: %s...",
        ticket_id,
        user_email,
        subject,
        reply_message[:80],
    )
    return False


def dispatch_research_bouquet(
    edition_date: Optional[str] = None,
    test_recipient: Optional[str] = None,
    only_active_pro: bool = False
) -> dict:
    """
    Dispatches the Research Bouquet & Morning Digest to subscribers or a test recipient.
    Supports Resend API and SMTP with graceful mock/logging fallback.
    Records delivery in digest_dispatches.
    """
    from core.analysis.research_bouquet import (
        compile_research_bouquet,
        render_bouquet_html,
        render_bouquet_text,
    )
    from core.db.digest import (
        get_digest_subscribers,
        record_digest_dispatch,
    )

    bouquet = compile_research_bouquet(edition_date=edition_date)
    sender_email = _get_cfg("SMTP_FROM") or _get_cfg("RESEND_FROM") or _get_cfg("SMTP_USER") or "noreply@moatnomics.com"

    if test_recipient:
        # Test dispatch to specific admin email
        sub_mock = {
            "email": test_recipient,
            "full_name": "Moatnomics Administrator",
            "unsubscribe_token": "test_admin_token"
        }
        test_subject = f"[TEST DIGEST] {bouquet['subject']}"
        html = render_bouquet_html(bouquet, subscriber=sub_mock)
        text = render_bouquet_text(bouquet, subscriber=sub_mock)

        delivered = False
        if _get_cfg("RESEND_API_KEY"):
            delivered = _dispatch_via_resend(sender_email, test_recipient, test_subject, text, html=html)
        elif _get_cfg("SMTP_HOST") and _get_cfg("SMTP_USER") and _get_cfg("SMTP_PASSWORD"):
            delivered = _dispatch_via_smtp(sender_email, test_recipient, test_subject, text, html=html)
        else:
            logger.info("[MOCK/LOG TEST DIGEST] Dispatched to %s | Subject: %s", test_recipient, test_subject)
            delivered = True

        did = record_digest_dispatch(
            edition_date=bouquet["edition_date"],
            subject=test_subject,
            recipients_count=1,
            delivered_count=1 if delivered else 0,
            failed_count=0 if delivered else 1,
            status="TEST_SENT",
            html_content=html,
            plain_text_content=text
        )

        return {
            "success": True,
            "status": "TEST_SENT",
            "dispatch_id": did,
            "delivered": 1 if delivered else 0,
            "failed": 0 if delivered else 1,
            "recipients": 1,
            "edition_date": bouquet["edition_date"],
            "subject": test_subject,
            "test_email": test_recipient
        }

    # Broadcast to registered subscribers
    subscribers = get_digest_subscribers(only_active_pro=only_active_pro)
    if not subscribers:
        logger.warning("No eligible digest subscribers found for dispatch.")
        return {
            "success": False,
            "status": "NO_SUBSCRIBERS",
            "delivered": 0,
            "failed": 0,
            "recipients": 0,
            "message": "No active digest subscribers found in database."
        }

    delivered_count = 0
    failed_count = 0

    # Render a baseline copy for archive
    sample_html = render_bouquet_html(bouquet, subscriber=subscribers[0])
    sample_text = render_bouquet_text(bouquet, subscriber=subscribers[0])

    for sub in subscribers:
        sub_email = sub.get("email")
        if not sub_email:
            continue
        try:
            html = render_bouquet_html(bouquet, subscriber=sub)
            text = render_bouquet_text(bouquet, subscriber=sub)
            subj = bouquet["subject"]

            ok = False
            if _get_cfg("RESEND_API_KEY"):
                ok = _dispatch_via_resend(sender_email, sub_email, subj, text, html=html)
            elif _get_cfg("SMTP_HOST") and _get_cfg("SMTP_USER") and _get_cfg("SMTP_PASSWORD"):
                ok = _dispatch_via_smtp(sender_email, sub_email, subj, text, html=html)
            else:
                logger.info("[MOCK/LOG BROADCAST] Dispatched to subscriber %s (%s)", sub_email, sub.get("full_name"))
                ok = True

            if ok:
                delivered_count += 1
            else:
                failed_count += 1
        except Exception as e:
            logger.error("Error dispatching digest to %s: %s", sub_email, e)
            failed_count += 1

    did = record_digest_dispatch(
        edition_date=bouquet["edition_date"],
        subject=bouquet["subject"],
        recipients_count=len(subscribers),
        delivered_count=delivered_count,
        failed_count=failed_count,
        status="COMPLETED" if failed_count == 0 else "PARTIAL",
        html_content=sample_html,
        plain_text_content=sample_text
    )

    return {
        "success": True,
        "status": "COMPLETED" if failed_count == 0 else "PARTIAL",
        "dispatch_id": did,
        "delivered": delivered_count,
        "failed": failed_count,
        "recipients": len(subscribers),
        "edition_date": bouquet["edition_date"],
        "subject": bouquet["subject"]
    }


def send_otp_email(recipient_email: str, code: str, ttl_minutes: int = 10) -> bool:
    """
    Dispatches a 6-digit login verification code via Resend API or SMTP.
    Returns True if delivered via live email provider, False if running in local/mock mode.
    """
    clean_to = (recipient_email or "").strip().lower()
    if not clean_to:
        return False

    sender_email = (
        _get_cfg("SMTP_FROM")
        or _get_cfg("RESEND_FROM")
        or _get_cfg("SMTP_USER")
        or "Moatnomics Service Desk <desk@moatnomics.com>"
    )
    subject = f"{code} is your Moatnomics verification code"
    text_body = (
        f"Moatnomics Research Terminal\n\n"
        f"Your 6-digit sign-in verification code is: {code}\n\n"
        f"This code expires in {ttl_minutes} minutes. If you did not request this code, please ignore this email.\n"
    )
    html_body = f"""
    <div style="font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; max-width: 480px; margin: 0 auto; padding: 28px; background: #0B2337; color: #F7F5EE; border-radius: 12px; border: 1px solid #0E3D32;">
        <div style="font-size: 12px; font-weight: 700; color: #7DA77A; text-transform: uppercase; letter-spacing: 0.08em; margin-bottom: 8px;">
            Moatnomics Authentication Gate
        </div>
        <h2 style="margin: 0 0 12px; font-family: 'Playfair Display', Georgia, serif; font-size: 20px; color: #F7F5EE;">Your Sign-In Verification Code</h2>
        <p style="font-size: 14px; color: #D9E3E8; line-height: 1.5; margin-bottom: 20px;">
            Enter the 6-digit verification code below to complete your sign-in:
        </p>
        <div style="background: #0E3D32; border: 1px solid rgba(199, 226, 104, 0.45); border-radius: 10px; padding: 18px; text-align: center; font-family: 'JetBrains Mono', monospace; font-size: 32px; font-weight: 800; letter-spacing: 8px; color: #C7E268; margin-bottom: 20px;">
            {code}
        </div>
        <p style="font-size: 12px; color: #7DA77A; margin: 0;">
            Valid for {ttl_minutes} minutes. Single-use only.
        </p>
    </div>
    """

    if _get_cfg("RESEND_API_KEY"):
        return _dispatch_via_resend(sender_email, clean_to, subject, text_body, html=html_body)

    if _get_cfg("SMTP_HOST") and _get_cfg("SMTP_USER") and _get_cfg("SMTP_PASSWORD"):
        return _dispatch_via_smtp(sender_email, clean_to, subject, text_body, html=html_body)

    logger.info("OTP generated for %s (no external email provider configured)", clean_to)
    return False
