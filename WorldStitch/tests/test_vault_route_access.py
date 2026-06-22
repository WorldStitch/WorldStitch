from server.routes.characters import CreateCharacterRequest
from server.routes.maps import CreateMapRequest


def test_create_requests_default_to_resolved_vault_not_hardcoded_default():
    assert CreateMapRequest(name="x").vault_id is None
    assert CreateCharacterRequest(name="x").vault_id is None
