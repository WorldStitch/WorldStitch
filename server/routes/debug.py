"""
Debug endpoints (admin only).

GET  /debug/crash-logs              — list crash log files
GET  /debug/crash-logs/{filename}   — return crash log content as JSON
DELETE /debug/crash-logs/{filename} — delete a crash log file
GET  /debug/runtime-log             — return last 500 lines of app.log
"""

from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from MythosEngine.context.app_context import AppContext
from MythosEngine.models.user import User

from server.deps import PLATFORM_ADMIN, get_ctx, get_current_user


router = APIRouter()

# Logs directory relative to the repo root (two levels up from this file)
_LOGS_DIR = Path(__file__).resolve().parent.parent.parent / "logs"


# ============================================================================
# Helper: require admin
# ============================================================================


def require_admin(user: User = Depends(get_current_user)) -> User:
    if user.system_role not in PLATFORM_ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )
    return user


def _logs_dir() -> Path:
    """Return logs dir path, creating it if it doesn't exist."""
    _LOGS_DIR.mkdir(parents=True, exist_ok=True)
    return _LOGS_DIR


# ============================================================================
# Response models
# ============================================================================


class CrashLogItem(BaseModel):
    name: str
    size: int
    modified: float


class LogContentResponse(BaseModel):
    name: str
    content: str


# ============================================================================
# Endpoints
# ============================================================================


@router.get("/crash-logs", response_model=List[CrashLogItem])
async def list_crash_logs(admin: User = Depends(require_admin)):
    """List crash log files in the logs directory."""
    logs_dir = _logs_dir()
    results = []
    for path in sorted(logs_dir.iterdir()):
        if path.is_file() and (
            path.name.startswith("crash_") and path.suffix == ".txt"
            or path.name == "last_crash_summary.txt"
        ):
            stat = path.stat()
            results.append(
                CrashLogItem(
                    name=path.name,
                    size=stat.st_size,
                    modified=stat.st_mtime,
                )
            )
    return results


@router.get("/crash-logs/{filename}", response_model=LogContentResponse)
async def get_crash_log(filename: str, admin: User = Depends(require_admin)):
    """Return the content of a crash log file."""
    logs_dir = _logs_dir()
    # Prevent path traversal: only allow plain filenames
    if "/" in filename or "\\" in filename or ".." in filename:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid filename")
    path = logs_dir / filename
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Log file not found")
    try:
        content = path.read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to read log: {e}",
        )
    return LogContentResponse(name=filename, content=content)


@router.delete("/crash-logs/{filename}")
async def delete_crash_log(filename: str, admin: User = Depends(require_admin)):
    """Delete a crash log file."""
    logs_dir = _logs_dir()
    if "/" in filename or "\\" in filename or ".." in filename:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid filename")
    path = logs_dir / filename
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Log file not found")
    try:
        path.unlink()
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete log: {e}",
        )
    return {"message": "Deleted", "filename": filename}


@router.get("/runtime-log", response_model=LogContentResponse)
async def get_runtime_log(admin: User = Depends(require_admin)):
    """Return the last 500 lines of logs/app.log."""
    logs_dir = _logs_dir()
    log_path = logs_dir / "app.log"
    if not log_path.exists():
        return LogContentResponse(name="app.log", content="")
    try:
        lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
        content = "\n".join(lines[-500:])
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to read runtime log: {e}",
        )
    return LogContentResponse(name="app.log", content=content)
