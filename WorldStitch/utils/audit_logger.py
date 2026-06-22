"""
AuditLogger — records every create/update/delete operation to audit.log.

Designed for the multiuser future: every log line includes the actor
(user_id), the resource type and ID, and the action taken. This gives
a full audit trail for debugging, compliance, and rollback support.

Usage in managers:
    from WorldStitch.utils.audit_logger import audit

    audit("create", "note", note.id, user_id=owner_id)
    audit("update", "user", user.id, user_id=actor_id, detail="email changed")
    audit("delete", "vault", vault_id, user_id=actor_id)
"""

import logging
from pathlib import Path

# Resolve audit log path relative to project root (3 levels up from this file)
_LOG_DIR = Path(__file__).resolve().parent.parent.parent / "logs"
_LOG_DIR.mkdir(parents=True, exist_ok=True)
_AUDIT_LOG = _LOG_DIR / "audit.log"

# Set up a dedicated audit logger — separate from the app logger
_audit_logger = logging.getLogger("mythos_audit")
if not _audit_logger.handlers:
    _handler = logging.FileHandler(_AUDIT_LOG, encoding="utf-8")
    _handler.setFormatter(
        logging.Formatter(
            fmt="%(asctime)s | %(levelname)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    )
    _audit_logger.addHandler(_handler)
    _audit_logger.setLevel(logging.INFO)
    _audit_logger.propagate = False  # don't flood the main app log


def audit(
    action: str,
    resource_type: str,
    resource_id: str,
    user_id: str = "system",
    detail: str = "",
) -> None:
    """
    Write one audit line to audit.log.

    Parameters
    ----------
    action : str
        What happened: "create", "update", "delete", "read", "login", etc.
    resource_type : str
        The type of resource affected: "note", "user", "vault", "character", etc.
    resource_id : str
        The ID of the affected resource.
    user_id : str
        ID of the user who performed the action. Defaults to "system" for
        automated or background operations.
    detail : str
        Optional human-readable extra context (e.g., "title changed").
    """
    msg = f"action={action} type={resource_type} id={resource_id} user={user_id}"
    if detail:
        msg += f" detail={detail!r}"
    _audit_logger.info(msg)
