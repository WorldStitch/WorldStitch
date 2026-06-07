"""
Integration tests for authentication routes.

Deviations from spec (based on reading actual route code):
- test_register_duplicate_email: returns 400 (not 409).  create_user() raises
  ValueError("Email already in use.") which the route catches as 400.
- test_register_success: the route returns 200 (not 201); the response model is
  RegisterResponse which includes access_token + user dict.
- Both login error cases return 401 with detail "Invalid email or password"
  (the route uses the same message for both to avoid enumeration).
"""

import pytest

# ---------------------------------------------------------------------------
# Helper: generate a fresh invite code for each registration test
# ---------------------------------------------------------------------------


@pytest.fixture()
def invite_code(test_ctx, test_user):
    """A single-use invite code, re-created for each test that needs one."""
    return test_ctx.invites.generate(created_by_user_id=test_user.id).code


# ---------------------------------------------------------------------------
# /auth/register
# ---------------------------------------------------------------------------


def test_register_success(client, test_ctx, test_user):
    """POST /auth/register with valid data returns 200 and a JWT."""
    invite = test_ctx.invites.generate(created_by_user_id=test_user.id)
    res = client.post(
        "/auth/register",
        json={
            "email": "newuser@example.com",
            "username": "newuser",
            "password": "NewPass1!",
            "invite_code": invite.code,
        },
    )
    assert res.status_code == 200
    body = res.json()
    assert "access_token" in body
    assert "refresh_token" in body
    assert body["token_type"] == "bearer"
    assert body["user"]["email"] == "newuser@example.com"


def test_register_duplicate_email(client, test_ctx, test_user):
    """Registering with an email that already exists returns 400.

    Note: the spec suggested 409, but create_user() raises ValueError which
    the /auth/register route maps to HTTP 400.
    """
    invite = test_ctx.invites.generate(created_by_user_id=test_user.id)
    res = client.post(
        "/auth/register",
        json={
            "email": "testuser@example.com",  # same as test_user
            "username": "duplicate",
            "password": "TestPass1!",
            "invite_code": invite.code,
        },
    )
    assert res.status_code == 400
    assert "already" in res.json()["detail"].lower()


# ---------------------------------------------------------------------------
# /auth/login
# ---------------------------------------------------------------------------


def test_login_success(client, test_user):
    """POST /auth/login with valid credentials returns 200 and a JWT.

    test_user is declared as a dependency to guarantee the account exists
    in the test DB before this request is sent.
    """
    res = client.post(
        "/auth/login",
        json={"email": "testuser@example.com", "password": "TestPass1!"},
    )
    assert res.status_code == 200
    body = res.json()
    assert "access_token" in body
    assert "refresh_token" in body
    assert body["token_type"] == "bearer"
    assert body["user"]["email"] == "testuser@example.com"


def test_login_wrong_password(client, test_user):
    """POST /auth/login with a wrong password returns 401."""
    res = client.post(
        "/auth/login",
        json={"email": "testuser@example.com", "password": "WrongPass9!"},
    )
    assert res.status_code == 401
    assert "invalid" in res.json()["detail"].lower()


def test_login_nonexistent_user(client, test_user):
    """POST /auth/login for an email that doesn't exist returns 401."""
    res = client.post(
        "/auth/login",
        json={"email": "nobody@example.com", "password": "AnyPass1!"},
    )
    assert res.status_code == 401
    assert "invalid" in res.json()["detail"].lower()


# ---------------------------------------------------------------------------
# /auth/me
# ---------------------------------------------------------------------------


def test_me_authenticated(client, auth_headers):
    """GET /auth/me with a valid token returns 200 and the user payload."""
    res = client.get("/auth/me", headers=auth_headers)
    assert res.status_code == 200
    body = res.json()
    assert "user" in body
    user = body["user"]
    assert user["email"] == "testuser@example.com"
    assert "id" in user
    assert "username" in user
    assert "roles" in user
    assert user["is_active"] is True


def test_me_no_token(client):
    """GET /auth/me without an Authorization header returns 401."""
    res = client.get("/auth/me")
    assert res.status_code == 401


def test_me_bad_token(client):
    """GET /auth/me with an invalid token returns 401."""
    res = client.get("/auth/me", headers={"Authorization": "Bearer this.is.garbage"})
    assert res.status_code == 401
