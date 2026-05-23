from types import SimpleNamespace
from unittest.mock import patch

from server.routes.characters import CreateCharacterRequest, _get_character_or_404
from server.routes.maps import CreateMapRequest, _get_map_or_404
from server.routes.sessions import _get_session_or_404


def test_create_requests_default_to_resolved_vault_not_hardcoded_default():
    assert CreateMapRequest(name="x").vault_id is None
    assert CreateCharacterRequest(name="x").vault_id is None


def test_map_helper_enforces_vault_access():
    map_obj = SimpleNamespace(id="m1", vault_id="vault-1", is_deleted=False)
    ctx = SimpleNamespace(maps=SimpleNamespace(get_map=lambda _id: map_obj))
    user = SimpleNamespace(id="u1", roles=[])

    with patch("server.routes.maps.resolve_vault") as mock_resolve:
        out = _get_map_or_404(ctx, user, "m1")

    assert out is map_obj
    mock_resolve.assert_called_once_with(ctx, user, "vault-1")


def test_character_helper_enforces_vault_access():
    char = SimpleNamespace(id="c1", vault_id="vault-1", is_deleted=False)
    ctx = SimpleNamespace(storage=SimpleNamespace(get_character_by_id=lambda _id: char))
    user = SimpleNamespace(id="u1", roles=[])

    with patch("server.routes.characters.resolve_vault") as mock_resolve:
        out = _get_character_or_404(ctx, user, "c1")

    assert out is char
    mock_resolve.assert_called_once_with(ctx, user, "vault-1")


def test_session_helper_enforces_vault_access():
    session = {"id": "s1", "vault_id": "vault-1"}
    ctx = SimpleNamespace(storage=SimpleNamespace(get_session_log=lambda _id: session))
    user = SimpleNamespace(id="u1", roles=[])

    with patch("server.routes.sessions.resolve_vault") as mock_resolve:
        out = _get_session_or_404(ctx, user, "s1")

    assert out is session
    mock_resolve.assert_called_once_with(ctx, user, "vault-1")
