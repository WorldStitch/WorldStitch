from datetime import datetime
from typing import Any, Dict, List, Optional

from WorldStitch.models.image import Image
from WorldStitch.storage.storage_base import StorageBackend
from WorldStitch.utils.audit_logger import audit


class ImageManager:
    """
    Handles business logic and storage operations for Image assets synchronously.
    """

    def __init__(self, storage: StorageBackend):
        self.storage = storage

    def create_image(
        self,
        vault_id: str,
        owner_id: str,
        file_path: str,
        name: Optional[str] = None,
        description: Optional[str] = None,
        prompt: Optional[str] = None,
        source: Optional[str] = None,
        linked_notes: Optional[List[str]] = None,
        scene_id: Optional[str] = None,
        tags: Optional[List[str]] = None,
        meta: Optional[Dict[str, Any]] = None,
        is_public: bool = True,
    ) -> Image:
        """
        Create and store a new image asset.
        """
        image = Image(
            id=self._generate_id(),
            vault_id=vault_id,
            owner_id=owner_id,
            file_path=file_path,
            name=name,
            description=description,
            prompt=prompt,
            source=source,
            linked_notes=linked_notes or [],
            scene_id=scene_id,
            tags=tags or [],
            meta=meta or {},
            is_public=is_public,
            is_deleted=False,
            created_at=datetime.utcnow(),
            last_modified=datetime.utcnow(),
            schema_version=1,
            version=1,
        )
        self.storage.save_image(image)
        audit("update", "image", image.id, user_id=getattr(image, "owner_id", "system"))
        return image

    def get_image(self, image_id: str) -> Optional[Image]:
        return self.storage.get_image_by_id(image_id)

    def update_image(self, image: Image) -> None:
        image.schema_version = max(image.schema_version, 1)
        image.version += 1
        image.last_modified = datetime.utcnow()
        self.storage.save_image(image)
        audit("update", "image", image.id, user_id=getattr(image, "owner_id", "system"))

    def delete_image(self, image_id: str) -> None:
        image = self.get_image(image_id)
        if image:
            image.is_deleted = True
            self.update_image(image)

    def check_permission(self, image_id: str, user_id: str, permission: str) -> bool:
        image = self.get_image(image_id)
        if not image:
            return False
        if "admin" in image.permissions.get(user_id, ""):
            return True
        # Extend permission logic here
        return False

    def _generate_id(self) -> str:
        import uuid

        return str(uuid.uuid4())
