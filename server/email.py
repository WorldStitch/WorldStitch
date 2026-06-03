"""
Email sending module for WorldStitch.

Uses Resend (https://resend.com) if RESEND_API_KEY is set.
If the key is absent, logs the email content and returns gracefully — no error raised.

Usage:
    from server.email import send_email
    send_email(to="user@example.com", subject="Hello", html="<p>Hi</p>")
"""

from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)

_FROM = "WorldStitch <hello@worldstitch.app>"
_RESEND_URL = "https://api.resend.com/emails"


def send_email(to: str, subject: str, html: str) -> bool:
    """
    Send an email to *to* with the given *subject* and *html* body.

    Returns True if the email was dispatched, False if skipped or failed.
    Never raises — callers should not depend on email delivery to complete a request.
    """
    api_key = os.getenv("RESEND_API_KEY", "").strip()

    if not api_key:
        logger.info(
            "Email skipped (RESEND_API_KEY not configured). To=%s | Subject=%s",
            to,
            subject,
        )
        return False

    try:
        import json as _json
        import urllib.request

        payload = _json.dumps(
            {
                "from": _FROM,
                "to": [to],
                "subject": subject,
                "html": html,
            }
        ).encode()

        req = urllib.request.Request(
            _RESEND_URL,
            data=payload,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )

        with urllib.request.urlopen(req, timeout=10) as resp:
            status = resp.status
            if status >= 200 and status < 300:
                logger.info("Email sent. To=%s | Subject=%s", to, subject)
                return True
            body = resp.read().decode(errors="replace")
            logger.warning("Resend returned %d: %s", status, body)
            return False

    except Exception as exc:
        logger.warning("Email send failed. To=%s | Error=%s", to, exc)
        return False
