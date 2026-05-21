"""
Per-user OpenAI API key storage and monthly request quota enforcement.

Each user can optionally store their own OpenAI API key.  If they do, all
their AI requests use that key with no server-side quota.  If they rely on
the server key, a monthly request counter is checked and incremented on
every AI call — reset lazily at the start of each calendar month.
"""

from __future__ import annotations

import threading
from datetime import date
from typing import Optional

from fastapi import HTTPException, status
from sqlalchemy import Date, Integer, String, Text, select
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column


class _ApiKeyBase(DeclarativeBase):
    pass


class UserApiKeyRecord(_ApiKeyBase):
    """One row per user — stores personal API key and monthly quota state."""

    __tablename__ = "user_api_settings"

    user_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    # TODO: encrypt at rest
    openai_api_key: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    monthly_request_limit: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    requests_this_month: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    month_reset_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)


class UserApiKeyStore:
    """CRUD + quota enforcement for per-user API key settings."""

    def __init__(self, engine) -> None:
        self.engine = engine
        self._lock = threading.Lock()
        _ApiKeyBase.metadata.create_all(self.engine)

    def _get_or_create(self, session: Session, user_id: str) -> UserApiKeyRecord:
        record = session.get(UserApiKeyRecord, user_id)
        if record is None:
            record = UserApiKeyRecord(
                user_id=user_id,
                openai_api_key=None,
                monthly_request_limit=100,
                requests_this_month=0,
                month_reset_date=date.today().replace(day=1),
            )
            session.add(record)
            session.flush()
        return record

    def get_settings(self, user_id: str) -> dict:
        with Session(self.engine) as session:
            rec = self._get_or_create(session, user_id)
            session.commit()
            return {
                "has_personal_key": bool(rec.openai_api_key),
                "requests_this_month": rec.requests_this_month,
                "monthly_request_limit": rec.monthly_request_limit,
            }

    def save_key(self, user_id: str, api_key: str) -> None:
        with Session(self.engine) as session:
            rec = self._get_or_create(session, user_id)
            rec.openai_api_key = api_key
            session.commit()

    def remove_key(self, user_id: str) -> None:
        with Session(self.engine) as session:
            rec = self._get_or_create(session, user_id)
            rec.openai_api_key = None
            session.commit()

    def get_personal_key(self, user_id: str) -> Optional[str]:
        with Session(self.engine) as session:
            rec = session.get(UserApiKeyRecord, user_id)
            return rec.openai_api_key if rec else None

    def check_and_increment(self, user_id: str) -> None:
        """
        Verify the user is under their monthly quota and increment the counter.

        Raises HTTP 429 if the limit is reached.  Resets the counter
        automatically when a new calendar month has started (lazy reset).
        """
        first_of_month = date.today().replace(day=1)

        with self._lock:
            with Session(self.engine) as session:
                rec = self._get_or_create(session, user_id)

                if rec.month_reset_date is None or rec.month_reset_date < first_of_month:
                    rec.requests_this_month = 0
                    rec.month_reset_date = first_of_month

                if rec.requests_this_month >= rec.monthly_request_limit:
                    session.commit()
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail=(
                            "Monthly AI request limit reached. "
                            "Add your own OpenAI key in Settings to continue."
                        ),
                    )

                rec.requests_this_month += 1
                session.commit()

    def set_limit(self, user_id: str, monthly_request_limit: int) -> None:
        with Session(self.engine) as session:
            rec = self._get_or_create(session, user_id)
            rec.monthly_request_limit = monthly_request_limit
            session.commit()

    def get_all_usage(self) -> list[dict]:
        with Session(self.engine) as session:
            records = session.scalars(select(UserApiKeyRecord)).all()
            return [
                {
                    "user_id": r.user_id,
                    "has_personal_key": bool(r.openai_api_key),
                    "requests_this_month": r.requests_this_month,
                    "monthly_request_limit": r.monthly_request_limit,
                }
                for r in records
            ]
