from datetime import datetime
from typing import Dict, List, Optional

from WorldStitch.auth.permission_checker import permissions
from WorldStitch.models.vault import Vault
from WorldStitch.storage.storage_base import StorageBackend
from WorldStitch.utils.audit_logger import audit


class VaultManager:
    """
    Handles all business logic and storage operations for Vault entities synchronously.
    """

    def __init__(self, storage: StorageBackend):
        self.storage = storage

    def create_vault(
        self,
        name: str,
        owner_id: str,
        description: Optional[str] = None,
        members: Optional[List[str]] = None,
        settings: Optional[Dict[str, str]] = None,
        permissions: Optional[Dict[str, str]] = None,
        vault_id: Optional[str] = None,
        vault_type: Optional[str] = None,
    ) -> Vault:
        """
        Create and store a new vault/campaign.
        """
        vault = Vault(
            id=vault_id or self._generate_id(),
            name=name,
            owner_id=owner_id,
            description=description,
            members=members or [],
            settings=settings or {},
            permissions=permissions or {},
            is_active=True,
            created_at=datetime.utcnow(),
            schema_version=1,
            record_version=1,
            vault_type=vault_type or "worldbuilding",
        )
        self.storage.save_vault(vault)
        audit("create", "vault", vault.id, user_id=getattr(vault, "owner_id", "system"))
        return vault

    def get_vault(self, vault_id: str) -> Optional[Vault]:
        return self.storage.get_vault_by_id(vault_id)

    def update_vault(self, vault: Vault) -> None:
        vault.schema_version = max(vault.schema_version, 1)
        vault.record_version += 1
        self.storage.save_vault(vault)
        audit("update", "vault", vault.id, user_id=getattr(vault, "owner_id", "system"))

    def delete_vault(self, vault_id: str, actor_id: str = "system") -> None:
        vault = self.get_vault(vault_id)
        if vault:
            permissions.require_delete(vault, actor_id)
            vault.is_active = False
            self.update_vault(vault)

    def add_member(self, vault_id: str, user_id: str) -> None:
        vault = self.get_vault(vault_id)
        if not vault:
            raise ValueError("Vault not found.")
        if user_id not in vault.members:
            vault.members.append(user_id)
            self.update_vault(vault)

    def remove_member(self, vault_id: str, user_id: str) -> None:
        vault = self.get_vault(vault_id)
        if not vault:
            raise ValueError("Vault not found.")
        if user_id in vault.members:
            vault.members.remove(user_id)
            self.update_vault(vault)

    def check_permission(self, vault_id: str, user_id: str, permission: str) -> bool:
        vault = self.get_vault(vault_id)
        if not vault or not vault.is_active:
            return False
        if vault.owner_id == user_id:
            return True
        if user_id in vault.members:
            return True
        # Extend with your permission rules
        return False

    def _generate_id(self) -> str:
        import uuid

        return str(uuid.uuid4())
