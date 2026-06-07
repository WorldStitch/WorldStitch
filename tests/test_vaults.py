"""
Integration tests for vault routes.

Deviations from spec (based on reading actual route code):
- test_vault_member_access: returns 404 (not 403).  resolve_vault() raises
  HTTP 404 "Vault not found or access denied" for any vault the user can't
  access — intentionally opaque to prevent vault enumeration.
"""

from server.auth_utils import create_jwt

# ---------------------------------------------------------------------------
# POST /vaults/
# ---------------------------------------------------------------------------


def test_create_vault(client, auth_headers):
    """POST /vaults/ with valid auth returns 201 and the new vault."""
    res = client.post(
        "/vaults/",
        json={"name": "My New Vault", "description": "Created in test"},
        headers=auth_headers,
    )
    assert res.status_code == 201
    body = res.json()
    assert body["name"] == "My New Vault"
    assert "id" in body
    assert body["is_active"] is True


# ---------------------------------------------------------------------------
# GET /vaults/
# ---------------------------------------------------------------------------


def test_list_vaults(client, auth_headers, test_vault):
    """GET /vaults/ returns 200 and a non-empty list for an authenticated user."""
    # test_vault is pre-created in conftest; listing should include at minimum that vault.
    res = client.get("/vaults/", headers=auth_headers)
    assert res.status_code == 200
    body = res.json()
    assert isinstance(body, list)
    assert len(body) >= 1
    # Each item has expected shape
    for vault in body:
        assert "id" in vault
        assert "name" in vault
        assert "owner_id" in vault


def test_vault_requires_auth(client):
    """GET /vaults/ without an Authorization header returns 401."""
    res = client.get("/vaults/")
    assert res.status_code == 401


# ---------------------------------------------------------------------------
# Non-member access to a specific vault
# ---------------------------------------------------------------------------


def test_vault_member_access(client, test_ctx, test_vault):
    """A user who doesn't own or belong to a vault gets 404 on GET /vaults/{id}.

    Note: the spec suggested 403, but resolve_vault() intentionally returns
    404 to avoid leaking which vault IDs exist (vault enumeration defence).
    """
    # Create a second user who has no relationship to test_vault
    outsider = test_ctx.users.create_user(
        email="outsider@example.com",
        username="outsider",
        password="Outsider1!",
        roles=["user"],
    )
    outsider_token = create_jwt(outsider.id, outsider.email, role="member")
    outsider_headers = {"Authorization": f"Bearer {outsider_token}"}

    res = client.get(f"/vaults/{test_vault.id}", headers=outsider_headers)
    assert res.status_code == 404
