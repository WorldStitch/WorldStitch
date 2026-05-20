"""
User management endpoints (admin only).

GET /users — list all users
GET /users/{id} — get a single user
PUT /users/{id}/roles — update user roles
POST /users/{id}/disable — disable user
POST /users/{id}/enable — enable user
POST /users/{id}/reset-password — admin password reset

NOTE: StorageBackend has no list_users() method. We query the SQLAlchemy
UserRecord table directly through the storage engine.
"""

import json
import logging
from datetime import datetime
from typing import List, Optional

logger = logging.getLogger(__name__)

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, field_validator

from MythosEngine.context.app_context import AppContext
from MythosEngine.models.user import User

from server.deps import get_ctx, get_current_user, require_permission


router = APIRouter()


# ============================================================================
# Request/Response models
# ============================================================================


class UserListItem(BaseModel):
    """User item in list response"""
    id: str
    username: str
    email: str
    roles: List[str]
    is_active: bool
    last_login: Optional[datetime] = None


class UpdateRolesRequest(BaseModel):
    """Request body for PUT /users/{id}/roles"""
    roles: List[str]


class ResetPasswordRequest(BaseModel):
    """Request body for POST /users/{id}/reset-password"""
    new_password: str

    @field_validator("new_password")
    @classmethod
    def check_password(cls, v):
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        if not any(c.isalpha() for c in v):
            raise ValueError("Password must contain at least one letter")
        if not any(c.isdigit() for c in v):
            raise ValueError("Password must contain at least one number")
        return v


def _list_all_users(ctx: AppContext) -> List[User]:
    """
    List all users by querying the SQLAlchemy storage directly.
    StorageBackend doesn't have a list_users() method, so we access
    the engine and UserRecord table.
    """
    users = []
    try:
        # Access the SQLAlchemy engine from the storage backend
        storage = ctx.storage
        if hasattr(storage, "engine"):
            from sqlalchemy.orm import Session as SASession
            # Import the ORM model from the sqlite backend
            from MythosEngine.storage.sqlite_backend import UserRecord
            with SASession(storage.engine) as session:
                for rec in session.query(UserRecord).all():
                    try:
                        user = User.model_validate_json(rec.data)
                        users.append(user)
                    except Exception as exc:
                        logger.warning("_list_all_users: skipping corrupt user record: %s", exc)
    except Exception as exc:
        logger.error("_list_all_users: database query failed: %s", exc)
    return users


def _get_creator_user(ctx: AppContext) -> Optional[User]:
    """Return the original creator account (earliest created user)."""
    users = _list_all_users(ctx)
    if not users:
        return None
    eligible_users = [u for u in users if getattr(u, "id", None)]
    if not eligible_users:
        return None
    users_with_created_at = [u for u in eligible_users if getattr(u, "created_at", None) is not None]
    if users_with_created_at:
        return min(users_with_created_at, key=lambda u: (u.created_at, u.id))
    return min(eligible_users, key=lambda u: u.id)


# ============================================================================
# User management endpoints
# ============================================================================


@router.get("/", response_model=List[UserListItem])
async def list_users(
    ctx: AppContext = Depends(get_ctx),
    admin: User = require_permission("moderator"),
):
    """
    List all users in the system. Requires moderator or above.
    """
    try:
        users = _list_all_users(ctx)
        return [
            UserListItem(
                id=u.id,
                username=u.username,
                email=u.email,
                roles=u.roles or [],
                is_active=u.is_active,
                last_login=getattr(u, "last_login", None),
            )
            for u in users
        ]
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list users: {str(e)}",
        )


@router.get("/{user_id}", response_model=UserListItem)
async def get_user(
    user_id: str,
    ctx: AppContext = Depends(get_ctx),
    admin: User = require_permission("moderator"),
):
    """
    Get a single user by ID. Requires moderator or above.
    """
    user = ctx.users.get_user(user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )
    return UserListItem(
        id=user.id,
        username=user.username,
        email=user.email,
        roles=user.roles or [],
        is_active=user.is_active,
        last_login=getattr(user, "last_login", None),
    )


@router.put("/{user_id}/roles")
async def update_user_roles(
    user_id: str,
    req: UpdateRolesRequest,
    ctx: AppContext = Depends(get_ctx),
    admin: User = require_permission("admin"),
):
    """
    Update user roles. Requires admin role.
    """
    try:
        user = ctx.users.get_user(user_id)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found",
            )

        normalized_roles = []
        for role in req.roles or []:
            value = (role or "").strip().lower()
            if value and value not in normalized_roles:
                normalized_roles.append(value)

        if not normalized_roles:
            normalized_roles = ["player"]

        creator = _get_creator_user(ctx)
        creator_id = creator.id if creator else None

        if "admin" in normalized_roles and user.id != creator_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Admin is reserved for the creator account and cannot be assigned to non-creator accounts",
            )
        if user.id == creator_id and "admin" not in normalized_roles:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Creator account must retain admin role",
            )

        user.roles = normalized_roles
        ctx.users.update_user(user)
        return {"message": "Roles updated successfully", "user_id": user.id}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update roles: {str(e)}",
        )


@router.post("/{user_id}/disable")
async def disable_user(
    user_id: str,
    ctx: AppContext = Depends(get_ctx),
    admin: User = require_permission("admin"),
):
    """
    Disable a user (prevent login). Requires admin role.
    """
    try:
        user = ctx.users.get_user(user_id)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found",
            )

        user.is_active = False
        ctx.users.update_user(user)
        return {"message": "User disabled successfully", "user_id": user.id}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to disable user: {str(e)}",
        )


@router.post("/{user_id}/enable")
async def enable_user(
    user_id: str,
    ctx: AppContext = Depends(get_ctx),
    admin: User = require_permission("admin"),
):
    """
    Enable a previously disabled user. Requires admin role.
    """
    try:
        user = ctx.users.get_user(user_id)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found",
            )

        user.is_active = True
        ctx.users.update_user(user)
        return {"message": "User enabled successfully", "user_id": user.id}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to enable user: {str(e)}",
        )


@router.post("/{user_id}/reset-password")
async def reset_password(
    user_id: str,
    req: ResetPasswordRequest,
    ctx: AppContext = Depends(get_ctx),
    admin: User = require_permission("admin"),
):
    """
    Reset a user's password (admin action). Requires admin role.
    """
    try:
        user = ctx.users.get_user(user_id)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found",
            )

        user.password_hash = ctx.users._hash_password(req.new_password)
        ctx.users.update_user(user)
        return {"message": "Password reset successfully", "user_id": user.id}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to reset password: {str(e)}",
        )
