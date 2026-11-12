"""
Mailer monitoring for the two research emails (Market Close Wrap 19:30 IST, Fund NAV Update 07:30 IST).

After each Render sender job:
- a successful send, or an expected market-closed skip (weekend / NSE holiday), pings that mailer's
  own Better Stack heartbeat. The senders run every day, so each heartbeat expects one ping per
  24 hours and a missed ping (job never ran, key expired, data empty, Render outage) raises an alert;
- any outcome other than a send or an expected market-closed skip emails ADMIN_ALERT_EMAIL with the
  edition, date, status and the phases that were still unfinished.
"""
import logging
import os
import ssl
import urllib.request
from typing import Any, Dict, Optional

import certifi

logger = logging.getLogger(__name__)

EDITION_LABELS = {"MARKET_CLOSE": "Market Close Wrap", "FUND_NAV": "Fund NAV Update"}
HEARTBEAT_ENV = {
    "MARKET_CLOSE": "BETTER_STACK_HEARTBEAT_URL_MARKET_CLOSE",
    "FUND_NAV": "BETTER_STACK_HEARTBEAT_URL_FUND_NAV",
}
# The email went out (now or by an earlier run for the same date and kind).
SENT_STATUSES = {"COMPLETED", "ALREADY_DISPATCHED"}
# Expected: no email is due (weekend / NSE holiday).
EXPECTED_SKIPS = {"SKIPPED_MARKET_CLOSED"}


def _cfg(key: str) -> str:
    from core.config import get_secret

    return str(get_secret(key) or os.environ.get(key) or "").strip()


def classify_outcome(results: Optional[Dict[str, Any]]) -> str:
    """Returns SENT, PARTIAL, SKIPPED or NOT_SENT for a sender run's results."""
    status = str((results or {}).get("digest_dispatch") or "")
    if status in SENT_STATUSES:
        return "SENT"
    if status == "PARTIAL":
        return "PARTIAL"
    if status in EXPECTED_SKIPS:
        return "SKIPPED"
    return "NOT_SENT"


def ping_mailer_heartbeat(edition_kind: str) -> bool:
    """Pings the edition's Better Stack heartbeat URL; returns True when the ping succeeded."""
    url = _cfg(HEARTBEAT_ENV.get(edition_kind, ""))
    if not url:
        logger.warning("No %s configured; %s sends are not monitored for silence.",
                       HEARTBEAT_ENV.get(edition_kind), EDITION_LABELS.get(edition_kind, edition_kind))
        return False
    try:
        ctx = ssl.create_default_context(cafile=certifi.where())
        req = urllib.request.Request(url, headers={"User-Agent": f"Moatnomics-Mailer-Heartbeat/{edition_kind}"})
        with urllib.request.urlopen(req, timeout=10, context=ctx) as resp:
            logger.info("%s heartbeat sent (status=%s).", EDITION_LABELS.get(edition_kind), resp.status)
            return True
    except Exception as exc:
        logger.warning("%s heartbeat failed: %s", EDITION_LABELS.get(edition_kind), exc)
        return False


def send_mailer_alert(edition_kind: str, date_str: str, outcome: str, results: Dict[str, Any]) -> bool:
    """Emails ADMIN_ALERT_EMAIL about a mailer that did not fully send. Returns True when delivered."""
    from core.notify import _dispatch_via_resend, _dispatch_via_smtp, _is_live_email_dispatch_allowed

    label = EDITION_LABELS.get(edition_kind, edition_kind)
    recipient = _cfg("ADMIN_ALERT_EMAIL")
    status = str(results.get("digest_dispatch") or "no dispatch attempted")
    missing = results.get("phases_missing_at_send") or []
    headline = "partly delivered" if outcome == "PARTIAL" else "NOT sent"
    subject = f"[Moatnomics] {label} {headline} for {date_str}"
    body = "\n".join([
        f"{label} for {date_str}: {headline}.",
        f"Dispatch status: {status}",
        f"Phases unfinished at send time: {', '.join(missing) if missing else 'none'}",
        "",
        "Check the Render sender job log and the GitHub close/fund run for this date.",
    ])
    if not recipient:
        logger.error("ADMIN_ALERT_EMAIL is not set; cannot alert: %s | %s", subject, status)
        return False
    if not _is_live_email_dispatch_allowed():
        logger.error("Live email disabled on this host; alert not emailed: %s | %s", subject, status)
        return False
    sender = _cfg("SMTP_FROM") or _cfg("RESEND_FROM") or "noreply@moatnomics.com"
    if _cfg("RESEND_API_KEY"):
        ok = _dispatch_via_resend(sender, recipient, subject, body)
    elif _cfg("SMTP_HOST") and _cfg("SMTP_USER") and _cfg("SMTP_PASSWORD"):
        ok = _dispatch_via_smtp(sender, recipient, subject, body)
    else:
        logger.error("No email transport configured; alert not emailed: %s | %s", subject, status)
        return False
    if not ok:
        logger.error("Mailer alert delivery failed: %s", subject)
    return bool(ok)


def report_mailer_outcome(edition_kind: str, date_str: str, results: Optional[Dict[str, Any]]) -> str:
    """Heartbeat on a send or expected skip, alert on anything else. Returns the outcome.

    The skip pings too: the senders run daily and exit early on weekends and NSE holidays, so a
    24-hour Better Stack heartbeat only goes quiet when a run did not happen or did not finish.
    """
    results = results or {}
    outcome = classify_outcome(results)
    if outcome in ("SENT", "PARTIAL", "SKIPPED"):
        ping_mailer_heartbeat(edition_kind)
    if outcome in ("PARTIAL", "NOT_SENT"):
        send_mailer_alert(edition_kind, date_str, outcome, results)
    logger.info("%s for %s: outcome=%s", EDITION_LABELS.get(edition_kind, edition_kind), date_str, outcome)
    return outcome
