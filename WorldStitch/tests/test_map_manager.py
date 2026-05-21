from unittest.mock import patch

from WorldStitch.managers.map_manager import MapManager


class _DummyStorage:
    def __init__(self):
        self.saved = {}

    def save_map(self, map_obj):
        self.saved[map_obj.id] = map_obj

    def get_map_by_id(self, map_id):
        return self.saved.get(map_id)

    def delete_map_by_id(self, map_id):
        self.saved.pop(map_id, None)


def test_create_map_audits_created_map_id():
    storage = _DummyStorage()
    mgr = MapManager(storage)

    with patch("WorldStitch.managers.map_manager.audit") as mock_audit:
        created = mgr.create_map(
            vault_id="vault-1",
            owner_id="user-1",
            name="World Map",
            file_path="maps/world.png",
        )

    assert created.id in storage.saved
    mock_audit.assert_called_once_with("update", "map", created.id, user_id="user-1")


def test_update_map_audits_updated_map_id():
    storage = _DummyStorage()
    mgr = MapManager(storage)

    created = mgr.create_map(
        vault_id="vault-1",
        owner_id="user-1",
        name="Dungeon Map",
        file_path="maps/dungeon.png",
    )

    with patch("WorldStitch.managers.map_manager.audit") as mock_audit:
        mgr.update_map(created)

    assert storage.saved[created.id].record_version >= 2
    mock_audit.assert_called_once_with("update", "map", created.id, user_id="user-1")
