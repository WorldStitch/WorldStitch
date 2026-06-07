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


_APP_URL = os.getenv("APP_URL", "https://app.worldstitch.app")


def send_vault_invite_email(to: str, vault_name: str, inviter_name: str, token: str) -> bool:
    """Send a WorldStitch-branded vault invitation email."""
    # App uses HashRouter: path goes in the fragment after '#'
    invite_url = f"{_APP_URL}/#/invite?token={token}"
    subject = f"You've been invited to join {vault_name} on WorldStitch"
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Vault Invitation</title>
</head>
<body style="margin:0;padding:0;background:#0f1117;font-family:'Segoe UI',Arial,sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0" style="background:#0f1117;padding:40px 0;">
    <tr><td align="center">
      <table width="560" cellpadding="0" cellspacing="0" style="background:#1a1d27;border-radius:16px;overflow:hidden;border:1px solid #2a2d3e;">
        <!-- Header -->
        <tr>
          <td style="background:linear-gradient(135deg,#6c63ff 0%,#a855f7 100%);padding:32px 40px;text-align:center;">
            <p style="margin:0 0 8px 0;font-size:28px;font-weight:700;color:#fff;letter-spacing:-0.5px;">&#9889; WorldStitch</p>
            <p style="margin:0;font-size:13px;color:rgba(255,255,255,0.75);letter-spacing:1px;text-transform:uppercase;">Vault Invitation</p>
          </td>
        </tr>
        <!-- Body -->
        <tr>
          <td style="padding:36px 40px;">
            <p style="margin:0 0 20px 0;font-size:22px;font-weight:600;color:#e8eaf0;">You've been invited!</p>
            <p style="margin:0 0 16px 0;font-size:15px;color:#9ba0b4;line-height:1.6;">
              <strong style="color:#c8cadc;">{inviter_name}</strong> has invited you to join the vault
              <strong style="color:#a78bfa;">{vault_name}</strong> on WorldStitch — a collaborative
              worldbuilding platform for creators, storytellers, and game masters.
            </p>
            <p style="margin:0 0 28px 0;font-size:15px;color:#9ba0b4;line-height:1.6;">
              Click the button below to accept your invitation. This link expires in 7 days.
            </p>
            <!-- CTA Button -->
            <table cellpadding="0" cellspacing="0" style="margin:0 0 28px 0;">
              <tr>
                <td style="background:linear-gradient(135deg,#6c63ff 0%,#a855f7 100%);border-radius:10px;padding:1px;">
                  <a href="{invite_url}"
                     style="display:inline-block;background:#1a1d27;border-radius:9px;padding:14px 32px;font-size:15px;font-weight:600;color:#a78bfa;text-decoration:none;letter-spacing:0.2px;">
                    Accept Invitation &rarr;
                  </a>
                </td>
              </tr>
            </table>
            <p style="margin:0 0 8px 0;font-size:12px;color:#5a5f78;">Or copy this link into your browser:</p>
            <p style="margin:0 0 28px 0;font-size:12px;color:#6c63ff;word-break:break-all;">{invite_url}</p>
            <hr style="border:none;border-top:1px solid #2a2d3e;margin:0 0 24px 0;" />
            <p style="margin:0;font-size:12px;color:#5a5f78;line-height:1.6;">
              If you weren't expecting this invitation, you can safely ignore this email.
              This invitation was sent by <strong style="color:#7a7f9a;">{inviter_name}</strong>.
            </p>
          </td>
        </tr>
        <!-- Footer -->
        <tr>
          <td style="padding:16px 40px;background:#13151f;border-top:1px solid #2a2d3e;text-align:center;">
            <p style="margin:0;font-size:12px;color:#3a3f58;">
              &copy; WorldStitch &bull; <a href="https://worldstitch.app" style="color:#6c63ff;text-decoration:none;">worldstitch.app</a>
            </p>
          </td>
        </tr>
      </table>
    </td></tr>
  </table>
</body>
</html>"""
    return send_email(to=to, subject=subject, html=html)


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
