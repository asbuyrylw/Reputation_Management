"""
Transactional email (SMTP; defaults to Zoho)
============================================
Sends onboarding mail -- invites, password resets, verification. Uses stdlib smtplib (no
new dependency). Configured for Zoho by default (smtp.zoho.com:465 SSL; use ZeptoMail's
smtp.zeptomail.com for higher-volume transactional). When SMTP isn't configured the message
is LOGGED instead of sent (incl. the action link), so onboarding works in dev and a pilot can
be set up before email credentials are added.

Env: SMTP_HOST, SMTP_PORT (465 SSL / 587 STARTTLS), SMTP_USER, SMTP_PASSWORD, EMAIL_FROM.
"""

from __future__ import annotations

import logging
import os
import smtplib
import ssl
from email.message import EmailMessage
from typing import Optional

log = logging.getLogger("email")


def enabled() -> bool:
    """True when SMTP is configured well enough to actually send."""
    return bool(os.getenv("SMTP_HOST") and os.getenv("SMTP_USER") and os.getenv("SMTP_PASSWORD"))


def _from() -> str:
    return os.getenv("EMAIL_FROM") or os.getenv("SMTP_USER") or "no-reply@localhost"


def send_email(to: str, subject: str, body_text: str, body_html: Optional[str] = None) -> bool:
    """Send an email (or, when SMTP is unconfigured, LOG it). Returns True if actually sent.
    Never raises on a send failure -- logs and returns False so onboarding still proceeds and
    the caller can surface the action link."""
    if not enabled():
        log.info("[email:dev -- not sent, SMTP unconfigured] To=%s | Subject=%s\n%s",
                 to, subject, body_text)
        return False
    host = os.getenv("SMTP_HOST", "smtp.zoho.com")
    port = int(os.getenv("SMTP_PORT", "465"))
    user, pw = os.getenv("SMTP_USER"), os.getenv("SMTP_PASSWORD")
    msg = EmailMessage()
    msg["From"], msg["To"], msg["Subject"] = _from(), to, subject
    msg.set_content(body_text)
    if body_html:
        msg.add_alternative(body_html, subtype="html")
    try:
        ctx = ssl.create_default_context()
        if port == 465:
            with smtplib.SMTP_SSL(host, port, context=ctx, timeout=20) as s:
                s.login(user, pw)
                s.send_message(msg)
        else:
            with smtplib.SMTP(host, port, timeout=20) as s:
                s.starttls(context=ctx)
                s.login(user, pw)
                s.send_message(msg)
        log.info("email sent to %s (%s)", to, subject)
        return True
    except Exception as e:  # noqa: BLE001 -- never let an email failure break onboarding
        log.error("email send failed to %s (%s): %s", to, subject, e)
        return False
