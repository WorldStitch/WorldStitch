"""
PermissionChecker — basic ACL enforcement for WorldStitch.

Every resource (Note, Vault, Character, etc.) carries:
  - owner_id  : the user who created it — always has full access
  - permissions : dict mapping user_id or group_id -> role string
                  roles: "read", "write"

This checker is the single place that decides if a user can perform
an action on a resource. Wire it into managers before any CRUD call.

Multiuser expansion path:
  - Add group membership lookup (check if user_id is in any group
    that has permissions on the resource)
  - Add vault-level default permissions (inherited by all child resources)
  - Add richer role hierarchy beyond read/write
"""

from typing import Optional, Protocol, runtime_checkable

# ---------------------------------------------------------------------------
# Resource protocol — any object with owner_id and permissions qualifies
# ---------------------------------------------------------------------------


@runtime_checkable
class PermissionedResource(Protocol):
    owner_id: str
    permissions: dict  # {user_id_or_group_id: "read" | "write"}


# ---------------------------------------------------------------------------
# Role constants
# ---------------------------------------------------------------------------

ROLE_READ = "read"
ROLE_WRITE = "write"
_ROLE_RANK = {ROLE_READ: 1, ROLE_WRITE: 2}


# ---------------------------------------------------------------------------
# PermissionChecker
# ---------------------------------------------------------------------------


class PermissionChecker:
    """
    Evaluates whether a given user may perform an action on a resource.

    Rules (checked in order, first match wins):
      1. System/service actors ("system") are always granted access.
      2. The resource owner always has full access.
      3. If the user has an explicit entry in resource.permissions,
         that role determines access.
      4. Default: deny.

    Usage
    -----
        checker = PermissionChecker()

        if not checker.can_write(note, user_id=ctx.current_user_id):
            raise PermissionError(f"User {user_id} cannot write note {note.id}")
    """

    def can_read(self, resource: PermissionedResource, user_id: Optional[str]) -> bool:
        """Return True if user_id may read this resource."""
        return self._has_role(resource, user_id, ROLE_READ)

    def can_write(self, resource: PermissionedResource, user_id: Optional[str]) -> bool:
        """Return True if user_id may create or update this resource."""
        return self._has_role(resource, user_id, ROLE_WRITE)

    def can_delete(self, resource: PermissionedResource, user_id: Optional[str]) -> bool:
        """Return True if user_id may delete this resource."""
        if user_id == "system":
            return True
        if user_id is None:
            return False
        return user_id == resource.owner_id

    def require_read(self, resource: PermissionedResource, user_id: Optional[str]) -> None:
        """Raise PermissionError if user_id cannot read resource."""
        if not self.can_read(resource, user_id):
            raise PermissionError(
                f"User '{user_id}' does not have read access to "
                f"{type(resource).__name__} '{getattr(resource, 'id', '?')}'"
            )

    def require_write(self, resource: PermissionedResource, user_id: Optional[str]) -> None:
        """Raise PermissionError if user_id cannot write resource."""
        if not self.can_write(resource, user_id):
            raise PermissionError(
                f"User '{user_id}' does not have write access to "
                f"{type(resource).__name__} '{getattr(resource, 'id', '?')}'"
            )

    def require_delete(self, resource: PermissionedResource, user_id: Optional[str]) -> None:
        """Raise PermissionError if user_id cannot delete resource."""
        if not self.can_delete(resource, user_id):
            raise PermissionError(
                f"User '{user_id}' does not have delete access to "
                f"{type(resource).__name__} '{getattr(resource, 'id', '?')}'"
            )

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _has_role(
        self,
        resource: PermissionedResource,
        user_id: Optional[str],
        required_role: str,
    ) -> bool:
        """
        Return True if user_id holds at least the required_role on resource.
        """
        # Service/system actors bypass permission checks
        if user_id is None or user_id == "system":
            return True

        # Owner always has full access
        if user_id == resource.owner_id:
            return True

        # Explicit permission entry
        granted = resource.permissions.get(user_id)
        if granted:
            granted_rank = _ROLE_RANK.get(granted, 0)
            required_rank = _ROLE_RANK.get(required_role, 99)
            return granted_rank >= required_rank

        # Default deny
        return False


# ---------------------------------------------------------------------------
# Singleton instance — import and use directly in managers
# ---------------------------------------------------------------------------

permissions = PermissionChecker()
