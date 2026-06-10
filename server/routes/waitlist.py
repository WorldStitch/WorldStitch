"""
Waitlist / early access application endpoints.

Public (no auth required):
  POST /apply                           — submit an early access application

Admin-only:
  GET  /admin/waitlist                  — list all applications (optional ?status= filter)
  POST /admin/waitlist/{app_id}/approve — approve application and send signup email
  POST /admin/waitlist/{app_id}/reject  — reject application
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, EmailStr
from sqlalchemy import text

from server.context import AppContext
from server.deps import get_ctx, require_admin
from server.email import send_email
from server.limiter import limiter
from WorldStitch.models.user import User

router = APIRouter(tags=["waitlist"])


# ── Schemas ───────────────────────────────────────────────────────────────────


class ApplyRequest(BaseModel):
    name: str
    email: EmailStr
    world_description: Optional[str] = None
    referral_source: str = "other"


# ── Helpers ───────────────────────────────────────────────────────────────────


def _engine(ctx: AppContext):
    return getattr(ctx.storage, "_engine", None)


def _row_to_dict(r) -> dict:
    return {
        "id": r[0],
        "name": r[1],
        "email": r[2],
        "world_description": r[3],
        "referral_source": r[4],
        "status": r[5],
        "created_at": r[6].isoformat() if isinstance(r[6], datetime) else str(r[6]),
    }


# ── Public: Submit application ────────────────────────────────────────────────


@router.post("/apply", status_code=201)
@limiter.limit("3/minute")
async def submit_application(request: Request, body: ApplyRequest, ctx: AppContext = Depends(get_ctx)):
    """Accept an early access application. Returns 409 if email already submitted."""
    engine = _engine(ctx)
    if not engine:
        raise HTTPException(status_code=503, detail="Database unavailable.")

    email_lower = body.email.lower()

    async with engine.begin() as conn:
        existing = (
            await conn.execute(
                text("SELECT id FROM waitlist_applications WHERE email = :email"),
                {"email": email_lower},
            )
        ).fetchone()
        if existing:
            raise HTTPException(status_code=409, detail="already_on_list")

        app_id = str(uuid.uuid4())
        now = datetime.utcnow()
        await conn.execute(
            text(
                "INSERT INTO waitlist_applications "
                "(id, name, email, world_description, referral_source, status, created_at) "
                "VALUES (:id, :name, :email, :world_description, :referral_source, 'pending', :created_at)"
            ),
            {
                "id": app_id,
                "name": body.name,
                "email": email_lower,
                "world_description": body.world_description or None,
                "referral_source": body.referral_source or "other",
                "created_at": now,
            },
        )

    send_email(
        to=body.email,
        subject="You're on the WorldStitch Early Access list",
        html=f"""
<html><body style="font-family:sans-serif;color:#111;max-width:520px;margin:40px auto;padding:0 20px">
<h2 style="color:#7c3aed">WorldStitch Early Access</h2>
<p>Hi {body.name},</p>
<p>Thanks for applying! We received your application and will review it personally.</p>
<p>We'll reach out to you at this address when we have an update.</p>
<p style="color:#555">— The WorldStitch Team</p>
</body></html>
        """,
    )

    return {"status": "ok", "message": "Application received. We'll be in touch soon."}


# ── Admin: List applications ──────────────────────────────────────────────────


@router.get("/admin/waitlist")
async def list_waitlist(
    status: Optional[str] = None,
    ctx: AppContext = Depends(get_ctx),
    _user: User = Depends(require_admin),
):
    """Return all waitlist applications, optionally filtered by status."""
    engine = _engine(ctx)
    if not engine:
        return []

    async with engine.connect() as conn:
        if status and status in ("pending", "approved", "rejected"):
            rows = (
                await conn.execute(
                    text(
                        "SELECT id, name, email, world_description, referral_source, status, created_at "
                        "FROM waitlist_applications WHERE status = :status ORDER BY created_at DESC"
                    ),
                    {"status": status},
                )
            ).fetchall()
        else:
            rows = (
                await conn.execute(
                    text(
                        "SELECT id, name, email, world_description, referral_source, status, created_at "
                        "FROM waitlist_applications ORDER BY created_at DESC"
                    )
                )
            ).fetchall()

    return [_row_to_dict(r) for r in rows]


# ── Admin: Approve ────────────────────────────────────────────────────────────


@router.post("/admin/waitlist/{app_id}/approve")
async def approve_application(
    app_id: str,
    ctx: AppContext = Depends(get_ctx),
    _user: User = Depends(require_admin),
):
    """Approve an application and send the applicant a signup email."""
    engine = _engine(ctx)
    if not engine:
        raise HTTPException(status_code=503, detail="Database unavailable.")

    async with engine.begin() as conn:
        row = (
            await conn.execute(
                text("SELECT id, name, email FROM waitlist_applications WHERE id = :id"),
                {"id": app_id},
            )
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Application not found.")

        await conn.execute(
            text("UPDATE waitlist_applications SET status = 'approved' WHERE id = :id"),
            {"id": app_id},
        )

    _, name, email = row
    send_email(
        to=email,
        subject="You've been approved for WorldStitch Early Access!",
        html=f"""
<html><body style="font-family:sans-serif;color:#111;max-width:520px;margin:40px auto;padding:0 20px">
<h2 style="color:#7c3aed">You're in!</h2>
<p>Hi {name},</p>
<p>Great news — your WorldStitch Early Access application has been approved.</p>
<p>
  <a href="https://app.worldstitch.app" style="display:inline-block;padding:12px 24px;background:#7c3aed;color:#fff;border-radius:8px;text-decoration:none;font-weight:600">
    Sign up now →
  </a>
</p>
<p style="color:#555">— The WorldStitch Team</p>
</body></html>
        """,
    )

    return {"status": "approved"}


# ── Admin: Reject ─────────────────────────────────────────────────────────────


@router.post("/admin/waitlist/{app_id}/reject")
async def reject_application(
    app_id: str,
    ctx: AppContext = Depends(get_ctx),
    _user: User = Depends(require_admin),
):
    """Mark an application as rejected."""
    engine = _engine(ctx)
    if not engine:
        raise HTTPException(status_code=503, detail="Database unavailable.")

    async with engine.begin() as conn:
        row = (
            await conn.execute(
                text("SELECT id FROM waitlist_applications WHERE id = :id"),
                {"id": app_id},
            )
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Application not found.")

        await conn.execute(
            text("UPDATE waitlist_applications SET status = 'rejected' WHERE id = :id"),
            {"id": app_id},
        )

    return {"status": "rejected"}
