"""
Admin analytics endpoints.

All endpoints require the 'admin' role and query the analytics_events table.

GET /admin/analytics/summary      — last-30d totals
GET /admin/analytics/events-by-day — daily event counts for last 30 days
GET /admin/analytics/breakdown     — event type breakdown with percentages
GET /admin/analytics/errors        — last 20 route exceptions
GET /admin/analytics/users         — per-user stats for last 30 days
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from WorldStitch.context.app_context import AppContext
from WorldStitch.models.user import User
from server.deps import get_ctx, require_admin

router = APIRouter(prefix="/admin/analytics", tags=["admin-analytics"])

_DAYS = 30


def _engine(ctx: AppContext):
    """Return the SQLAlchemy engine from the storage backend."""
    return getattr(ctx.storage, "engine", None)


def _cutoff() -> datetime:
    return datetime.utcnow() - timedelta(days=_DAYS)


# ── Summary ───────────────────────────────────────────────────────────────────


@router.get("/summary")
def analytics_summary(
    ctx: AppContext = Depends(get_ctx),
    _user: User = Depends(require_admin),
):
    """Return aggregate totals for the last 30 days."""
    engine = _engine(ctx)
    if not engine:
        return {"total_events": 0, "active_users": 0, "ai_requests": 0, "total_ai_cost_usd": 0.0}

    cutoff = _cutoff()
    with Session(engine) as session:
        total_events = session.execute(
            text("SELECT COUNT(*) FROM analytics_events WHERE created_at >= :cutoff"),
            {"cutoff": cutoff},
        ).scalar() or 0

        active_users = session.execute(
            text("SELECT COUNT(DISTINCT user_id) FROM analytics_events WHERE created_at >= :cutoff"),
            {"cutoff": cutoff},
        ).scalar() or 0

        ai_requests = session.execute(
            text(
                "SELECT COUNT(*) FROM analytics_events "
                "WHERE event_type = 'ai.request_sent' AND created_at >= :cutoff"
            ),
            {"cutoff": cutoff},
        ).scalar() or 0

        cost_rows = session.execute(
            text(
                "SELECT event_data FROM analytics_events "
                "WHERE event_type = 'ai.request_completed' AND created_at >= :cutoff"
            ),
            {"cutoff": cutoff},
        ).fetchall()

    total_cost = 0.0
    for (raw,) in cost_rows:
        try:
            total_cost += float(json.loads(raw or "{}").get("cost_usd", 0))
        except Exception:
            pass

    return {
        "total_events": total_events,
        "active_users": active_users,
        "ai_requests": ai_requests,
        "total_ai_cost_usd": round(total_cost, 6),
    }


# ── Events by day ─────────────────────────────────────────────────────────────


@router.get("/events-by-day")
def analytics_events_by_day(
    ctx: AppContext = Depends(get_ctx),
    _user: User = Depends(require_admin),
):
    """Return daily event counts for the last 30 days."""
    engine = _engine(ctx)
    if not engine:
        return []

    cutoff = _cutoff()
    with Session(engine) as session:
        rows = session.execute(
            text(
                "SELECT date(created_at) AS day, COUNT(*) AS cnt "
                "FROM analytics_events "
                "WHERE created_at >= :cutoff "
                "GROUP BY day ORDER BY day ASC"
            ),
            {"cutoff": cutoff},
        ).fetchall()

    return [{"date": row[0], "count": row[1]} for row in rows]


# ── Breakdown ─────────────────────────────────────────────────────────────────


@router.get("/breakdown")
def analytics_breakdown(
    ctx: AppContext = Depends(get_ctx),
    _user: User = Depends(require_admin),
):
    """Return event type counts with percentage of total for last 30 days."""
    engine = _engine(ctx)
    if not engine:
        return []

    cutoff = _cutoff()
    with Session(engine) as session:
        rows = session.execute(
            text(
                "SELECT event_type, COUNT(*) AS cnt "
                "FROM analytics_events "
                "WHERE created_at >= :cutoff "
                "GROUP BY event_type ORDER BY cnt DESC"
            ),
            {"cutoff": cutoff},
        ).fetchall()

    total = sum(r[1] for r in rows)
    return [
        {
            "event_type": r[0],
            "count": r[1],
            "pct": round(r[1] / total * 100, 1) if total else 0.0,
        }
        for r in rows
    ]


# ── Errors ────────────────────────────────────────────────────────────────────


@router.get("/errors")
def analytics_errors(
    ctx: AppContext = Depends(get_ctx),
    _user: User = Depends(require_admin),
):
    """Return the last 20 route exception events."""
    engine = _engine(ctx)
    if not engine:
        return []

    with Session(engine) as session:
        rows = session.execute(
            text(
                "SELECT id, created_at, event_data "
                "FROM analytics_events "
                "WHERE event_type = 'error.route_exception' "
                "ORDER BY created_at DESC LIMIT 20"
            )
        ).fetchall()

    results = []
    for row_id, created_at, raw_data in rows:
        try:
            data = json.loads(raw_data or "{}")
        except Exception:
            data = {}
        results.append(
            {
                "id": row_id,
                "created_at": created_at.isoformat() if isinstance(created_at, datetime) else str(created_at),
                "route": data.get("route", ""),
                "status_code": data.get("status_code", 500),
            }
        )
    return results


# ── Per-user stats ────────────────────────────────────────────────────────────


@router.get("/users")
def analytics_users(
    ctx: AppContext = Depends(get_ctx),
    _user: User = Depends(require_admin),
):
    """Return per-user analytics stats for the last 30 days."""
    engine = _engine(ctx)
    if not engine:
        return []

    cutoff = _cutoff()
    with Session(engine) as session:
        # All users with their consent flag
        user_rows = session.execute(
            text("SELECT id, data, COALESCE(analytics_consent, 0) FROM users")
        ).fetchall()

        # Per-user event counts
        event_counts = {
            row[0]: row[1]
            for row in session.execute(
                text(
                    "SELECT user_id, COUNT(*) FROM analytics_events "
                    "WHERE created_at >= :cutoff GROUP BY user_id"
                ),
                {"cutoff": cutoff},
            ).fetchall()
        }

        # Per-user AI request counts
        ai_counts = {
            row[0]: row[1]
            for row in session.execute(
                text(
                    "SELECT user_id, COUNT(*) FROM analytics_events "
                    "WHERE event_type = 'ai.request_sent' AND created_at >= :cutoff GROUP BY user_id"
                ),
                {"cutoff": cutoff},
            ).fetchall()
        }

        # Per-user AI cost (sum cost_usd from ai.request_completed)
        cost_rows = session.execute(
            text(
                "SELECT user_id, event_data FROM analytics_events "
                "WHERE event_type = 'ai.request_completed' AND created_at >= :cutoff"
            ),
            {"cutoff": cutoff},
        ).fetchall()

    user_costs: dict[str, float] = {}
    for uid, raw in cost_rows:
        try:
            user_costs[uid] = user_costs.get(uid, 0.0) + float(json.loads(raw or "{}").get("cost_usd", 0))
        except Exception:
            pass

    results = []
    for uid, user_data_raw, consent in user_rows:
        try:
            user_data = json.loads(user_data_raw or "{}")
            username = user_data.get("username") or user_data.get("email") or uid
        except Exception:
            username = uid
        results.append(
            {
                "user_id": uid,
                "username": username,
                "events_this_month": event_counts.get(uid, 0),
                "ai_requests": ai_counts.get(uid, 0),
                "ai_cost_usd": round(user_costs.get(uid, 0.0), 6),
                "consent": bool(consent),
            }
        )

    results.sort(key=lambda r: r["events_this_month"], reverse=True)
    return results
