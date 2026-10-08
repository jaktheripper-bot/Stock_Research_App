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
STOCK RESEARCH AI - NEW USER COMPLAINT / SUPPORT TICKET
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
