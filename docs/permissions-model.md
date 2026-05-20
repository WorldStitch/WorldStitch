# Permissions Model

MythosEngine uses a layered permission system: a platform-level `system_role` on each user account, and a resource-level ACL (owner + explicit grants) enforced by `PermissionChecker`.

---

## How It Works

Every data record (Note, Vault, Character, etc.) carries two fields:

```python
owner_id: str        # User ID of the creator — always has full access
permissions: dict    # {user_id: role} overrides — e.g. {"u-abc": "read"}
```

The `PermissionChecker` (`auth/permission_checker.py`) evaluates access using these rules, checked in order:

1. **System actor** (`user_id == "system"`) — always granted (for background operations)
2. **Owner** (`user_id == resource.owner_id`) — always granted full access
3. **Explicit permission** — checks `resource.permissions[user_id]` for a role
4. **Default** — deny

---

## Resource-Level Roles

| Role | Can Read | Can Write | Can Delete |
|------|----------|-----------|------------|
| `read` | ✅ | ❌ | ❌ |
| `write` | ✅ | ✅ | ❌ |

Only the resource owner (matched via `owner_id`) can delete a resource.

## Platform-Level Roles (`system_role`)

| Role | Access |
|------|--------|
| `owner` | Full control — manage users, billing, instance settings |
| `admin` | Manage users within the instance |
| `moderator` | Moderate content; can view user list |
| `tester` | Access to pre-release features |
| `user` | Standard access |
| `suspended` | Login disabled |

---

## Usage in Managers

```python
from MythosEngine.auth.permission_checker import permissions

# Raise PermissionError if user cannot write
permissions.require_write(note, user_id=ctx.current_user_id)

# Check without raising
if permissions.can_read(vault, user_id=ctx.current_user_id):
    ...
```

---

## Current State

The app is fully multiuser. Users authenticate via JWT bearer tokens. `ctx.current_user_id` is set from the validated token on every request. Resource-level permissions are enforced in managers; platform-level access (`system_role`) is checked in route dependencies via `require_permission()`.

## Future Work

- Group membership lookups in `PermissionChecker._has_role()` (group-level permissions)
- Vault-level default permissions inherited by child resources
