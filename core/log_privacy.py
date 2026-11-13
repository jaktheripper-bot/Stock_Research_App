"""Masks email addresses in every log record before any handler writes it.

Logs go to the Render console and Better Stack, so a subscriber's full address must never appear
there. Masking happens in the log-record factory rather than per log call, which covers all ~60
call sites, f-string messages, and every handler (including scripts that call `logging.basicConfig`).

`ra***@gmail.com` keeps enough to tell recipients apart while debugging; the domain stays visible
because delivery problems are often per-provider.
"""

import logging
import re
import sys

EMAIL_RE = re.compile(r"(?<![\w.+-])([A-Za-z0-9._%+-]{1,64})@([A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,})")

_INSTALLED = False


def mask_email(match: "re.Match[str]") -> str:
    local, domain = match.group(1), match.group(2)
    return f"{local[:2]}***@{domain}"


def mask_emails(text: str) -> str:
    """Replaces every email address in `text` with its masked form."""
    return EMAIL_RE.sub(mask_email, text)


def install_email_masking() -> None:
    """Wraps the current log-record factory once so each record's message is masked."""
    global _INSTALLED
    if _INSTALLED:
        return
    previous_factory = logging.getLogRecordFactory()

    def _masking_factory(*args, **kwargs):
        record = previous_factory(*args, **kwargs)
        try:
            message = record.getMessage()
        except (TypeError, ValueError, KeyError, IndexError) as format_err:
            # A log call whose arguments don't fit its format string. Logging from inside the
            # record factory would recurse, so note it on stderr, then emit the raw template and
            # arguments joined and masked, so the broken call is still visible and still private.
            sys.stderr.write(f"log_privacy: malformed log call ({type(format_err).__name__})\n")
            record.msg = mask_emails(f"{record.msg} | args={record.args!r}")
            record.args = None
            return record
        if "@" in message:
            record.msg = mask_emails(message)
            record.args = None
        return record

    logging.setLogRecordFactory(_masking_factory)
    _INSTALLED = True
