"""
Email sending via Resend (https://resend.com).

Requires RESEND_API_KEY env var. If absent, logs and returns False without error.
Retries once on 429 after the Retry-After header (or 2 s default).
Never raises — callers must not depend on delivery to complete a request.
"""

from __future__ import annotations

import logging
import os
import time

import requests

logger = logging.getLogger(__name__)

_FROM = "WorldStitch <hello@worldstitch.app>"
_RESEND_URL = "https://api.resend.com/emails"
_TIMEOUT = 10


def send_email(to: str, subject: str, html: str) -> bool:
    """
    Send a transactional email.

    Returns True if Resend accepted it (2xx), False otherwise.
    """
    api_key = os.getenv("RESEND_API_KEY", "").strip()
    if not api_key:
        logger.info("Email skipped (RESEND_API_KEY not set). to=%s subject=%s", to, subject)
        return False

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    body = {"from": _FROM, "to": [to], "subject": subject, "html": html}

    for attempt in range(2):
        try:
            resp = requests.post(_RESEND_URL, json=body, headers=headers, timeout=_TIMEOUT)
        except requests.RequestException as exc:
            logger.warning("Email network error. to=%s error=%s", to, exc)
            return False

        if resp.status_code == 429 and attempt == 0:
            retry_after = float(resp.headers.get("Retry-After", 2))
            logger.info("Resend 429 — retrying in %.1fs", retry_after)
            time.sleep(retry_after)
            continue

        if resp.ok:
            logger.info("Email sent. to=%s subject=%s", to, subject)
            return True

        logger.warning("Resend %d: %s. to=%s", resp.status_code, resp.text[:200], to)
        return False

    return False
