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

logger = logging.getLogger("equity_research.core.notify")


def get_admin_notification_email() -> str:
    """Retrieves target admin recipient email."""
    return (
        os.environ.get("ADMIN_ALERT_EMAIL")
        or os.environ.get("ADMIN_EMAIL")
        or "lyndonpinto@gmail.com"  # Configured site owner from local system git config
    )


def send_ticket_notification_email(ticket: dict) -> bool:
    """
    Sends an email notification to the administrator regarding a newly submitted
    complaint, billing dispute, or support ticket.
    If SMTP credentials are not configured, logs the dispatch gracefully.
    """
    admin_email = get_admin_notification_email()
    smtp_host = os.environ.get("SMTP_HOST")
    smtp_port = int(os.environ.get("SMTP_PORT", 587))
    smtp_user = os.environ.get("SMTP_USER")
    smtp_password = os.environ.get("SMTP_PASSWORD")
    sender_email = os.environ.get("SMTP_FROM", smtp_user or "noreply@localhost")

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

    # If SMTP is configured, attempt secure delivery
    if smtp_host and smtp_user and smtp_password:
        try:
            msg = MIMEMultipart()
            msg["From"] = sender_email
            msg["To"] = admin_email
            msg["Subject"] = subject
            msg.attach(MIMEText(body, "plain"))

            with smtplib.SMTP(smtp_host, smtp_port, timeout=10) as server:
                server.starttls()
                server.login(smtp_user, smtp_password)
                server.send_message(msg)

            logger.info(f"Dispatched email notification for ticket {ticket.get('ticket_id')} to {admin_email}")
            return True
        except Exception as e:
            logger.error(f"Failed to dispatch SMTP email for ticket {ticket.get('ticket_id')}: {e}")
            return False
    else:
        # Graceful logging fallback when SMTP server is pending configuration
        logger.info(
            f"[MOCK/LOG EMAIL ALERT] Sent to: {admin_email} | Subject: {subject} | "
            f"Ticket: {ticket.get('ticket_id')} from {ticket.get('user_email')}"
        )
        return True


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
    If SMTP credentials are not configured, logs the dispatch gracefully and returns True (mock delivery).
    """
    user_email = ticket.get("user_email")
    if not user_email:
        logger.warning("Cannot dispatch reply email: ticket %s has no user_email", ticket.get("ticket_id"))
        return False

    smtp_host = os.environ.get("SMTP_HOST")
    smtp_port = int(os.environ.get("SMTP_PORT", 587))
    smtp_user = os.environ.get("SMTP_USER")
    smtp_password = os.environ.get("SMTP_PASSWORD")
    sender_email = os.environ.get("SMTP_FROM", smtp_user or "noreply@moatnomics.com")

    ticket_id = ticket.get("ticket_id", "TKT")
    original_subject = ticket.get("subject", "Support Inquiry")
    subject = f"Re: [{ticket_id}] {original_subject}"
    user_name = ticket.get("user_name") or "Investor"

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
    body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; line-height: 1.6; color: #1e293b; background-color: #f8fafc; margin: 0; padding: 24px; }}
    .container {{ max-width: 600px; margin: 0 auto; background: #ffffff; border-radius: 8px; border: 1px solid #e2e8f0; overflow: hidden; }}
    .header {{ background: #0b1329; color: #ffffff; padding: 20px 24px; border-bottom: 2px solid #0ea5e9; }}
    .header h2 {{ margin: 0; font-size: 18px; font-weight: 700; letter-spacing: -0.01em; color: #ffffff; }}
    .header p {{ margin: 4px 0 0; font-size: 12px; color: #94a3b8; }}
    .content {{ padding: 24px; }}
    .reply-box {{ background: #f0fdf4; border-left: 4px solid #10b981; padding: 16px; border-radius: 4px; font-size: 15px; color: #0f172a; margin: 16px 0; white-space: pre-wrap; }}
    .original-quote {{ background: #f8fafc; border-left: 4px solid #cbd5e1; padding: 14px; font-size: 13px; color: #64748b; margin-top: 20px; border-radius: 4px; }}
    .footer {{ background: #f1f5f9; padding: 16px 24px; font-size: 12px; color: #64748b; border-top: 1px solid #e2e8f0; text-align: center; }}
    .footer a {{ color: #0284c7; text-decoration: none; }}
    .badge {{ display: inline-block; background: #e0f2fe; color: #0369a1; padding: 2px 8px; border-radius: 4px; font-size: 11px; font-weight: 600; }}
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
        <p style="margin: 0 0 6px 0; font-weight: 600; color: #475569;">In reference to your message ({ticket.get('created_at', 'recently')}):</p>
        <p style="margin: 0; font-style: italic;">"{ticket.get('message', '').strip()}"</p>
      </div>

      <p style="margin-top: 24px; font-size: 14px;">If you have any further questions or require additional details, you can connect with us directly via the <a href="https://moatnomics.com/contact" style="color: #0284c7; font-weight: 600;">Feedback & Grievances Desk</a>.</p>
    </div>
    <div class="footer">
      <p style="margin: 0 0 4px 0;">Moatnomics &bull; Independent Quantitative Equity & Asset Intelligence</p>
      <p style="margin: 0;">This email was sent in direct response to inquiry {ticket_id}.</p>
    </div>
  </div>
</body>
</html>
"""

    if smtp_host and smtp_user and smtp_password:
        try:
            msg = MIMEMultipart("alternative")
            msg["From"] = sender_email
            msg["To"] = user_email
            msg["Subject"] = subject
            msg.attach(MIMEText(text_body, "plain"))
            msg.attach(MIMEText(html_body, "html"))

            with smtplib.SMTP(smtp_host, smtp_port, timeout=10) as server:
                server.starttls()
                server.login(smtp_user, smtp_password)
                server.send_message(msg)

            logger.info("Dispatched email response for ticket %s to %s", ticket_id, user_email)
            return True
        except Exception as e:
            logger.error("Failed to dispatch SMTP email response to %s for ticket %s: %s", user_email, ticket_id, e)
            return False
    else:
        logger.info(
            "[MOCK/LOG USER EMAIL REPLY] Dispatched to: %s | Subject: %s | Ticket: %s | Preview: %s...",
            user_email,
            subject,
            ticket_id,
            reply_message[:80],
        )
        return True
