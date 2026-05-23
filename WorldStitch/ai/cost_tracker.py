"""
AI Cost Tracking for WorldStitch.

Tracks token usage and estimated USD cost per AI operation, scoped by user
and vault. Records are persisted in a dedicated 'ai_usage' table in the same
SQLite database used by SQLiteBackend.

Wire-in:
  - CostTracker is instantiated in SQLiteBackend.__init__() after migrations.
  - AppContext exposes it via the cost_tracker property (returns None if the
    active backend is not SQLite).
  - Call record() from AI engine adapters (openai_engine.py, etc.) after each
    successful API call, passing the token counts returned by the provider.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import DateTime, Float, Integer, String, select
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column


# ---------------------------------------------------------------------------
# Pricing table: model_key -> (prompt_$/1M_tokens, completion_$/1M_tokens)
# ---------------------------------------------------------------------------
_PRICING: dict[str, tuple[float, float]] = {
    "gpt-4o": (5.0, 15.0),
    "claude-3-5-sonnet": (3.0, 15.0),
}
_DEFAULT_PRICING: tuple[float, float] = (1.0, 3.0)


# ---------------------------------------------------------------------------
# ORM
# ---------------------------------------------------------------------------


class _CostBase(DeclarativeBase):
    pass


class AIUsageRecord(_CostBase):
    """One row per AI API call — stores token counts and computed cost."""

    __tablename__ = "ai_usage"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    vault_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    model: Mapped[str] = mapped_column(String, nullable=False)
    prompt_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    completion_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cost_usd: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    operation: Mapped[str] = mapped_column(String, nullable=False)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow
    )


# ---------------------------------------------------------------------------
# CostTracker
# ---------------------------------------------------------------------------


class CostTracker:
    """
    Records AI usage and exposes per-user and per-vault cost summaries.

    Parameters
    ----------
    engine : sqlalchemy.engine.Engine
        Shared with SQLiteBackend — no extra connection needed.
    """

    def __init__(self, engine) -> None:
        self.engine = engine
        _CostBase.metadata.create_all(self.engine)

    def record(
        self,
        user_id: str,
        vault_id: str,
        model: str,
        prompt_tokens: int,
        completion_tokens: int,
        operation: str,
    ) -> None:
        """Insert a usage record, computing cost_usd from the built-in pricing table."""
        prompt_rate, completion_rate = _PRICING.get(model, _DEFAULT_PRICING)
        cost_usd = (
            prompt_tokens * prompt_rate + completion_tokens * completion_rate
        ) / 1_000_000

        row = AIUsageRecord(
            user_id=user_id,
            vault_id=vault_id,
            model=model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=prompt_tokens + completion_tokens,
            cost_usd=cost_usd,
            operation=operation,
            timestamp=datetime.utcnow(),
        )
        with Session(self.engine) as session:
            session.add(row)
            session.commit()

    def get_user_summary(
        self,
        user_id: str,
        vault_id: Optional[str] = None,
        days: int = 30,
    ) -> dict:
        """
        Return cost summary for a user over the last *days* days.

        Returns
        -------
        dict
            total_tokens, total_cost_usd,
            by_operation: {op: cost_usd},
            by_model: {model: cost_usd}
        """
        since = datetime.utcnow() - timedelta(days=days)
        with Session(self.engine) as session:
            stmt = select(AIUsageRecord).where(
                AIUsageRecord.user_id == user_id,
                AIUsageRecord.timestamp >= since,
            )
            if vault_id is not None:
                stmt = stmt.where(AIUsageRecord.vault_id == vault_id)
            rows = session.scalars(stmt).all()

        return _aggregate(rows)

    def get_vault_summary(self, vault_id: str, days: int = 30) -> dict:
        """
        Return cost summary across all users in a vault over the last *days* days.

        Returns
        -------
        dict
            total_tokens, total_cost_usd,
            by_operation: {op: cost_usd},
            by_model: {model: cost_usd}
        """
        since = datetime.utcnow() - timedelta(days=days)
        with Session(self.engine) as session:
            rows = session.scalars(
                select(AIUsageRecord).where(
                    AIUsageRecord.vault_id == vault_id,
                    AIUsageRecord.timestamp >= since,
                )
            ).all()

        return _aggregate(rows)


# ---------------------------------------------------------------------------
# Internal helper
# ---------------------------------------------------------------------------


def _aggregate(rows: list) -> dict:
    total_tokens = 0
    total_cost = 0.0
    by_op: dict[str, float] = {}
    by_model: dict[str, float] = {}

    for r in rows:
        total_tokens += r.total_tokens
        total_cost += r.cost_usd
        by_op[r.operation] = by_op.get(r.operation, 0.0) + r.cost_usd
        by_model[r.model] = by_model.get(r.model, 0.0) + r.cost_usd

    return {
        "total_tokens": total_tokens,
        "total_cost_usd": total_cost,
        "by_operation": by_op,
        "by_model": by_model,
    }
