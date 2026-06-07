"""
Authentication endpoints.

GET /auth/status — check if setup is needed (no users exist)
POST /auth/setup — create initial admin account (only works when 0 users)
POST /auth/login — authenticate with email/password
POST /auth/logout — invalidate session (client drops token)
GET /auth/me — get current user info
POST /auth/change-password — change password
POST /auth/register — create new account with invite code
GET /auth/verify-email?token=TOKEN — verify email address
POST /auth/forgot-password — request a password reset email
POST /auth/reset-password — set a new password via reset token

NOTE: We bypass AuthManager here because it inherits QObject (PyQt6),
which is unavailable in the headless FastAPI server context. Instead we
use UserManager directly for credential verification.
"""

import asyncio
import logging
import secrets
import time
import uuid
from collections import defaultdict
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, EmailStr, field_validator

from server.analytics import track as analytics_track
from server.auth_utils import create_jwt, create_refresh_token, decode_refresh_jwt
from server.deps import get_ctx, get_current_user
from server.email import send_email
from WorldStitch.context.app_context import AppContext
from WorldStitch.models.user import User
from WorldStitch.utils.audit_logger import audit

logger = logging.getLogger(__name__)

_APP_BASE_URL = "https://app.worldstitch.app"


# ============================================================================
# Rate limiter — prevents brute-force login attempts (Item 60)
# ============================================================================


class RateLimiter:
    """Simple in-memory rate limiter. Tracks attempts per key (email)."""

    def __init__(self, max_attempts: int = 5, window_seconds: int = 900):
        self.max_attempts = max_attempts
        self.window = window_seconds
        self._attempts: dict[str, list[float]] = defaultdict(list)

    def is_blocked(self, key: str) -> bool:
        """Check if a key is currently rate-limited."""
        now = time.time()
        attempts = self._attempts[key]
        # Prune old attempts outside the window
        self._attempts[key] = [t for t in attempts if now - t < self.window]
        return len(self._attempts[key]) >= self.max_attempts

    def record(self, key: str) -> None:
        """Record a failed attempt."""
        self._attempts[key].append(time.time())

    def reset(self, key: str) -> None:
        """Reset attempts after successful login."""
        self._attempts.pop(key, None)


_login_limiter = RateLimiter(max_attempts=5, window_seconds=900)  # 5 per 15 min
_reset_limiter = RateLimiter(max_attempts=5, window_seconds=3600)  # 5 per hour

# Token TTL must match TokenStore default (30 days) so exp in response is accurate
_TOKEN_TTL_SECONDS = 30 * 24 * 3600


# ============================================================================
# Password strength validation (Item 54)
# ============================================================================

_SPECIAL_CHARS = set("!@#$%^&*-_")


def validate_password_strength(password: str) -> str:
    """Validate password meets minimum strength requirements."""
    msg = "Password must be at least 8 characters with 1 uppercase, 1 number, and 1 special character"
    if len(password) < 8:
        raise ValueError(msg)
    if not any(c.isupper() for c in password):
        raise ValueError(msg)
    if not any(c.isdigit() for c in password):
        raise ValueError(msg)
    if not any(c in _SPECIAL_CHARS for c in password):
        raise ValueError(msg)
    return password


def _jwt_role(user: User) -> str:
    """Return a stable JWT role claim even when a user has no explicit roles."""
    return user.roles[0] if user.roles else "member"


router = APIRouter()


# ============================================================================
# Request/Response models
# ============================================================================


class LoginRequest(BaseModel):
    """Request body for POST /auth/login"""

    email: EmailStr
    password: str


class LoginResponse(BaseModel):
    """Response body for successful login"""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    exp: datetime
    user: dict


class UserResponse(BaseModel):
    """User info response"""

    id: str
    username: str
    email: str
    roles: list[str]
    is_active: bool


class ChangePasswordRequest(BaseModel):
    """Request body for POST /auth/change-password"""

    current_password: str
    new_password: str

    @field_validator("new_password")
    @classmethod
    def check_new_password(cls, v):
        return validate_password_strength(v)


class RegisterRequest(BaseModel):
    """Request body for POST /auth/register"""

    email: EmailStr
    username: str
    password: str
    invite_code: str

    @field_validator("password")
    @classmethod
    def check_password(cls, v):
        return validate_password_strength(v)


class RefreshRequest(BaseModel):
    """Request body for POST /auth/refresh"""

    refresh_token: str


class RefreshResponse(BaseModel):
    """Response body for token refresh"""

    access_token: str
    token_type: str = "bearer"


class RegisterResponse(BaseModel):
    """Response body for successful registration"""

    message: str
    email: str


class SetupRequest(BaseModel):
    """Request body for POST /auth/setup (first-run admin creation)"""

    email: EmailStr
    username: str
    password: str

    @field_validator("password")
    @classmethod
    def check_password(cls, v):
        return validate_password_strength(v)


class SetupResponse(BaseModel):
    """Response body for successful setup (auto-login as admin)"""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    exp: datetime
    user: dict


class ForgotPasswordRequest(BaseModel):
    """Request body for POST /auth/forgot-password"""

    email: EmailStr


class ResetPasswordRequest(BaseModel):
    """Request body for POST /auth/reset-password"""

    token: str
    new_password: str

    @field_validator("new_password")
    @classmethod
    def check_new_password(cls, v):
        return validate_password_strength(v)


# ============================================================================
# Helper: count users via SQLAlchemy
# ============================================================================


def _count_users(ctx: AppContext) -> int:
    """Return the total number of users in the database."""
    try:
        storage = ctx.storage
        if hasattr(storage, "engine"):
            from sqlalchemy.orm import Session as SASession

            from WorldStitch.storage.sqlite_backend import UserRecord

            with SASession(storage.engine) as session:
                return session.query(UserRecord).count()
    except Exception as exc:
        logger.warning("_count_users: database query failed: %s", exc)
    return -1  # unknown


def _get_engine(ctx: AppContext):
    """Return the SQLAlchemy engine from the storage backend, or None."""
    storage = ctx.storage
    if hasattr(storage, "engine"):
        return storage.engine
    return None


# ============================================================================
# Email templates
# ============================================================================

_EMAIL_STYLES = """
  body { font-family: Georgia, serif; background: #0f0e17; color: #fffffe; margin: 0; padding: 0; }
  .container { max-width: 560px; margin: 40px auto; background: #1a1a2e; border-radius: 12px;
               border: 1px solid #2a2a4a; overflow: hidden; }
  .header { background: linear-gradient(135deg, #6c3082 0%, #1a237e 100%);
            padding: 32px 40px; text-align: center; }
  .logo { font-size: 40px; margin-bottom: 8px; }
  .brand { font-size: 22px; font-weight: bold; color: #fffffe; letter-spacing: 1px; }
  .body { padding: 36px 40px; }
  h2 { color: #a78bfa; margin-top: 0; font-size: 20px; }
  p { color: #b8b8cc; line-height: 1.7; margin: 12px 0; }
  .btn { display: inline-block; margin: 24px 0; padding: 14px 32px;
         background: linear-gradient(135deg, #7c3aed, #4f46e5);
         color: #fffffe !important; text-decoration: none; border-radius: 8px;
         font-weight: bold; font-size: 15px; letter-spacing: 0.5px; }
  .footer { padding: 20px 40px; border-top: 1px solid #2a2a4a; text-align: center; }
  .footer p { font-size: 12px; color: #6b6b8a; margin: 4px 0; }
  .expiry { font-size: 13px; color: #6b6b8a; margin-top: 20px; }
"""


def _verification_email_html(username: str, verify_url: str) -> str:
    return f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><style>{_EMAIL_STYLES}</style></head>
<body>
  <div class="container">
    <div class="header">
      <div class="logo">&#9889;</div>
      <div class="brand">WorldStitch</div>
    </div>
    <div class="body">
      <h2>Hail, {username}! Your scroll of verification awaits.</h2>
      <p>You have registered for WorldStitch &mdash; your portal to extraordinary worlds and epic tales.</p>
      <p>Before your quest can truly begin, the Arcane Council requires proof that this missive
         has reached its rightful recipient.</p>
      <p style="text-align:center">
        <a href="{verify_url}" class="btn">&#10022; Verify My Email &#10022;</a>
      </p>
      <p>Or paste this link into your browser:</p>
      <p style="word-break:break-all; font-size:13px; color:#7c7ca0;">{verify_url}</p>
      <p class="expiry">This link expires in 24 hours. If you did not register for WorldStitch,
         you may safely ignore this message &mdash; no action is required.</p>
    </div>
    <div class="footer">
      <p>WorldStitch &mdash; Weave your world</p>
      <p>hello@worldstitch.app</p>
    </div>
  </div>
</body>
</html>"""


def _reset_email_html(username: str, reset_url: str) -> str:
    return f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><style>{_EMAIL_STYLES}</style></head>
<body>
  <div class="container">
    <div class="header">
      <div class="logo">&#9889;</div>
      <div class="brand">WorldStitch</div>
    </div>
    <div class="body">
      <h2>Your quest to reclaim your account begins here...</h2>
      <p>Greetings, {username}. The Arcane Scribes have received a request to reset the password
         for your WorldStitch account.</p>
      <p>Click the rune below to forge a new password and restore your access to the realm:</p>
      <p style="text-align:center">
        <a href="{reset_url}" class="btn">&#9876; Reset My Password &#9876;</a>
      </p>
      <p>Or paste this link into your browser:</p>
      <p style="word-break:break-all; font-size:13px; color:#7c7ca0;">{reset_url}</p>
      <p class="expiry">This link expires in 1 hour. If you did not request a password reset,
         your account remains safe &mdash; no action is needed.</p>
    </div>
    <div class="footer">
      <p>WorldStitch &mdash; Weave your world</p>
      <p>hello@worldstitch.app</p>
    </div>
  </div>
</body>
</html>"""


# ============================================================================
# Auth endpoints
# ============================================================================


@router.get("/status")
async def auth_status(
    ctx: AppContext = Depends(get_ctx),
):
    """
    Check if the app needs initial setup.
    Returns {needs_setup: true} when no users exist in the database.
    This endpoint is public (no auth required).
    """
    count = _count_users(ctx)
    return {"needs_setup": count == 0}


@router.post("/setup", response_model=SetupResponse)
async def setup_admin(
    req: SetupRequest,
    ctx: AppContext = Depends(get_ctx),
):
    """
    Create the initial admin account. Only works when the database has zero users.
    After the first admin is created, this endpoint is permanently disabled.
    """
    count = _count_users(ctx)
    if count != 0:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Setup already completed. Use login or invite codes.",
        )

    try:
        user = ctx.users.create_user(
            email=req.email,
            username=req.username,
            password=req.password,
            roles=["admin"],
        )
        user.system_role = "owner"
        ctx.users.update_user(user)

        ctx.storage.set_user_context(
            user.id,
            is_admin=True,
        )

        role = _jwt_role(user)
        token = create_jwt(user.id, user.email, role)
        refresh = create_refresh_token(user.id)
        exp = datetime.utcnow() + timedelta(hours=1)

        return SetupResponse(
            access_token=token,
            refresh_token=refresh,
            token_type="bearer",
            exp=exp,
            user={
                "id": user.id,
                "username": user.username,
                "email": user.email,
                "roles": user.roles,
                "system_role": user.system_role,
                "groups": user.groups,
                "is_active": user.is_active,
            },
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Setup failed: {str(e)}",
        )


@router.post("/login", response_model=LoginResponse)
async def login(
    req: LoginRequest,
    request: Request,
    ctx: AppContext = Depends(get_ctx),
):
    """
    Authenticate with email and password.
    Returns a signed JWT bearer token and user info on success.
    Rate-limited: max 5 failed attempts per email per 15 minutes.
    """
    email_key = req.email.lower()
    client_ip = request.client.host if request.client else "unknown"

    # Rate limit check (Item 60)
    if _login_limiter.is_blocked(email_key):
        audit("FAILED_LOGIN", "auth", email_key, detail=f"ip={client_ip} reason=account_locked")
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many login attempts. Please try again in 15 minutes.",
        )

    try:
        # Look up user by email
        user = ctx.users.get_user_by_email(req.email)
        if not user or not user.is_active or user.system_role == "suspended":
            _login_limiter.record(email_key)
            audit("FAILED_LOGIN", "auth", email_key, detail=f"ip={client_ip} reason=user_not_found")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid email or password",
            )

        # Verify password using UserManager (bcrypt, Item 58)
        if not ctx.users.verify_password(req.password, user.password_hash):
            _login_limiter.record(email_key)
            audit("FAILED_LOGIN", "auth", email_key, detail=f"ip={client_ip} reason=wrong_password")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid email or password",
            )

        # Login successful — reset rate limiter and log (Items 59, 60)
        _login_limiter.reset(email_key)
        audit("SUCCESS_LOGIN", "auth", user.id, user_id=user.id, detail=f"ip={client_ip}")
        asyncio.create_task(analytics_track("user.login", user_id=user.id))

        # Set user context on storage for permission checks
        ctx.storage.set_user_context(
            user.id,
            is_admin=user.system_role in {"owner", "admin"},
        )

        # Update last_login
        user.last_login = datetime.utcnow()
        ctx.users.update_user(user)

        role = _jwt_role(user)
        token = create_jwt(user.id, user.email, role)
        refresh = create_refresh_token(user.id)
        exp = datetime.utcnow() + timedelta(hours=1)

        return LoginResponse(
            access_token=token,
            refresh_token=refresh,
            token_type="bearer",
            exp=exp,
            user={
                "id": user.id,
                "username": user.username,
                "email": user.email,
                "roles": user.roles,
                "system_role": user.system_role,
                "groups": user.groups,
                "is_active": user.is_active,
            },
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Login failed: {str(e)}",
        )


@router.post("/logout")
async def logout(
    ctx: AppContext = Depends(get_ctx),
    user: User = Depends(get_current_user),
):
    """
    Logout the current user. JWTs are stateless so the client is responsible
    for discarding the token. This endpoint confirms the token was valid.
    """
    asyncio.create_task(analytics_track("user.logout", user_id=user.id))
    return {"message": "Logged out successfully"}


@router.get("/me")
async def get_me(
    user: User = Depends(get_current_user),
):
    """
    Get the current user's info.
    Returns nested {user: {...}} to match what the frontend expects.
    """
    return {
        "user": {
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "roles": user.roles,
            "system_role": user.system_role,
            "groups": user.groups,
            "is_active": user.is_active,
        }
    }


@router.post("/change-password")
async def change_password(
    req: ChangePasswordRequest,
    ctx: AppContext = Depends(get_ctx),
    user: User = Depends(get_current_user),
):
    """
    Change the current user's password.
    """
    try:
        ctx.users.change_password(user.id, req.current_password, req.new_password)
        return {"message": "Password changed successfully"}
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Password change failed: {str(e)}",
        )


@router.post("/refresh", response_model=RefreshResponse)
async def refresh_token(
    req: RefreshRequest,
    ctx: AppContext = Depends(get_ctx),
):
    """
    Exchange a valid refresh token for a new access token.
    Returns 401 if the refresh token is expired, invalid, or the user is inactive.
    """
    payload = decode_refresh_jwt(req.refresh_token)
    user_id = payload.get("sub")
    try:
        user = ctx.users.get_user(user_id)
    except Exception:
        user = None
    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive",
        )
    role = _jwt_role(user)
    token = create_jwt(user.id, user.email, role)
    return RefreshResponse(access_token=token, token_type="bearer")


@router.post("/register", response_model=RegisterResponse)
async def register(
    req: RegisterRequest,
    ctx: AppContext = Depends(get_ctx),
):
    """
    Register a new user with an invite code.
    Sends a verification email and returns a message asking the user to check their inbox.
    Email verification is tracked but not enforced at login (yet).
    """
    try:
        # Validate invite code
        invite = ctx.invites.validate(req.invite_code)
        if not invite:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid or expired invite code",
            )

        # Create the user (password hashed via bcrypt in UserManager, Item 58)
        user = ctx.users.create_user(
            email=req.email,
            username=req.username,
            password=req.password,
            roles=[],
        )

        # Redeem the invite
        ctx.invites.redeem(req.invite_code, user.id)
        asyncio.create_task(analytics_track("user.registered", user_id=user.id))

        # Issue and store a verification token
        ver_token = secrets.token_urlsafe(32)
        engine = _get_engine(ctx)
        if engine:
            from sqlalchemy.orm import Session as SASession

            from WorldStitch.storage.sqlite_backend import EmailVerificationTokenRecord

            with SASession(engine) as db:
                record = EmailVerificationTokenRecord(
                    id=str(uuid.uuid4()),
                    user_id=user.id,
                    token=ver_token,
                    expires_at=datetime.utcnow() + timedelta(hours=24),
                    used=False,
                    created_at=datetime.utcnow(),
                )
                db.add(record)
                db.commit()

        verify_url = f"{_APP_BASE_URL}/verify-email?token={ver_token}"
        asyncio.create_task(
            asyncio.to_thread(
                send_email,
                user.email,
                "Verify your WorldStitch account",
                _verification_email_html(user.username, verify_url),
            )
        )

        return RegisterResponse(
            message="Account created! Check your email to verify your address before signing in.",
            email=user.email,
        )
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Registration failed: {str(e)}",
        )


@router.get("/verify-email")
async def verify_email(
    token: str = Query(...),
    ctx: AppContext = Depends(get_ctx),
):
    """
    Validate an email verification token, mark the user verified, and mark the token used.
    """
    engine = _get_engine(ctx)
    if not engine:
        raise HTTPException(status_code=500, detail="Database unavailable")

    from sqlalchemy.orm import Session as SASession

    from WorldStitch.storage.sqlite_backend import EmailVerificationTokenRecord, UserRecord

    with SASession(engine) as db:
        record = db.query(EmailVerificationTokenRecord).filter_by(token=token).first()

        if not record:
            raise HTTPException(status_code=400, detail="Invalid or expired verification link")
        if record.used:
            raise HTTPException(status_code=400, detail="This verification link has already been used")
        if record.expires_at < datetime.utcnow():
            raise HTTPException(status_code=400, detail="This verification link has expired")

        record.used = True

        user_row = db.query(UserRecord).filter_by(id=record.user_id).first()
        if user_row:
            user_row.email_verified = True

        db.commit()

    return {"message": "Email verified successfully. You can now sign in."}


@router.post("/forgot-password")
async def forgot_password(
    req: ForgotPasswordRequest,
    ctx: AppContext = Depends(get_ctx),
):
    """
    Request a password reset email. Always returns 200 to prevent email enumeration.
    Rate-limited to 5 requests per hour per email address.
    """
    email_key = req.email.lower()
    if _reset_limiter.is_blocked(email_key):
        # Return the same message — don't leak that this address is throttled
        return {"message": "If that email is registered, you'll receive a reset link shortly."}

    _reset_limiter.record(email_key)

    async def _send_reset():
        try:
            user = ctx.users.get_user_by_email(req.email)
            if not user or not user.is_active:
                return

            rst_token = secrets.token_urlsafe(32)
            engine = _get_engine(ctx)
            if not engine:
                return

            from sqlalchemy.orm import Session as SASession

            from WorldStitch.storage.sqlite_backend import PasswordResetTokenRecord

            with SASession(engine) as db:
                record = PasswordResetTokenRecord(
                    id=str(uuid.uuid4()),
                    user_id=user.id,
                    token=rst_token,
                    expires_at=datetime.utcnow() + timedelta(hours=1),
                    used=False,
                    created_at=datetime.utcnow(),
                )
                db.add(record)
                db.commit()

            reset_url = f"{_APP_BASE_URL}/reset-password?token={rst_token}"
            await asyncio.to_thread(
                send_email,
                user.email,
                "Reset your WorldStitch password",
                _reset_email_html(user.username, reset_url),
            )
        except Exception as exc:
            logger.warning("forgot_password background task failed: %s", exc)

    asyncio.create_task(_send_reset())
    return {"message": "If that email is registered, you'll receive a reset link shortly."}


@router.post("/reset-password")
async def reset_password(
    req: ResetPasswordRequest,
    ctx: AppContext = Depends(get_ctx),
):
    """
    Reset a user's password using a valid single-use reset token.
    Marks the token used and updates the password hash.
    """
    engine = _get_engine(ctx)
    if not engine:
        raise HTTPException(status_code=500, detail="Database unavailable")

    from sqlalchemy.orm import Session as SASession

    from WorldStitch.storage.sqlite_backend import PasswordResetTokenRecord

    with SASession(engine) as db:
        record = db.query(PasswordResetTokenRecord).filter_by(token=req.token).first()

        if not record:
            raise HTTPException(status_code=400, detail="Invalid or expired reset link")
        if record.used:
            raise HTTPException(status_code=400, detail="This reset link has already been used")
        if record.expires_at < datetime.utcnow():
            raise HTTPException(status_code=400, detail="This reset link has expired")

        user = ctx.users.get_user(record.user_id)
        if not user or not user.is_active:
            raise HTTPException(status_code=400, detail="Invalid or expired reset link")

        # Hash and persist the new password
        user.password_hash = ctx.users._hash_password(req.new_password)
        ctx.users.update_user(user)
        audit("PASSWORD_RESET", "auth", user.id, user_id=user.id)

        # Consume the token
        record.used = True
        db.commit()

    return {"message": "Password reset successfully. You can now sign in with your new password."}
