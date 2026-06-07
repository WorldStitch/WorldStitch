from __future__ import annotations

import logging
import traceback

from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect

from server.auth_utils import decode_jwt
from server.deps import get_ctx
from server.realtime import hub
from server.vault_access import resolve_vault
from WorldStitch.context.app_context import AppContext

logger = logging.getLogger(__name__)

router = APIRouter()


@router.websocket("/ws")
async def websocket_events(
    websocket: WebSocket,
    token: str = Query(...),
    vault_id: str = Query(...),
    ctx: AppContext = Depends(get_ctx),
):
    # Accept the WebSocket handshake BEFORE any validation so that close
    # frames with meaningful codes (1008) are delivered to the client.
    # Without a prior accept() some ASGI servers drop the TCP connection
    # abruptly, giving the browser code 1006 (abnormal closure) instead of
    # 1008 — the frontend cannot distinguish a bad-token rejection from a
    # transient network hiccup and retries immediately and indefinitely.
    await websocket.accept()
    logger.info("WS connection attempt - token present: %s, vault_id: %s", bool(token), vault_id)

    async def reject(code: int = 1008) -> None:
        """Send a close frame, tolerating an already-gone connection."""
        try:
            await websocket.close(code=code)
        except Exception:
            pass

    try:
        payload = decode_jwt(token)
        logger.info("WS JWT decoded - sub: %s", payload.get("sub", "none"))
    except HTTPException as e:
        logger.warning("WS auth failed - bad token: %s", e)
        await reject()
        return

    sub = payload.get("sub", "")
    user = ctx.users.get_user(sub)
    logger.info("WS user lookup - sub=%s found=%s", sub, bool(user))
    if not user:
        logger.warning("WS auth failed - user not found for sub: %s", sub)
        await reject()
        return

    logger.info("WS connected - user: %s, vault: %s", user.username, vault_id)

    try:
        vault = resolve_vault(ctx, user, vault_id)
    except HTTPException as e:
        logger.warning("WS closing — vault resolve failed: %s", e.detail)
        await reject()
        return

    logger.info("WS connected — user=%s vault=%s", user.username, vault.id)
    email = getattr(user, "email", payload.get("email", ""))

    try:
        await hub.connect(vault.id, user.id, user.username, email, websocket)
    except Exception:
        logger.error("WS hub.connect error:\n%s", traceback.format_exc())
        await reject(code=1011)
        return

    try:
        while True:
            message = await websocket.receive_json()
            event_type = message.get("type")
            if event_type in ("editing.start", "note_lock"):
                await hub.set_editing(
                    vault.id,
                    note_id=message.get("note_id", ""),
                    user_id=user.id,
                    username=user.username,
                    email=email,
                    cursor=message.get("cursor"),
                    active=True,
                )
            elif event_type in ("editing.stop", "note_unlock"):
                await hub.set_editing(
                    vault.id,
                    note_id=message.get("note_id", ""),
                    user_id=user.id,
                    username=user.username,
                    email=email,
                    active=False,
                )
            elif event_type == "cursor.move":
                await hub.set_editing(
                    vault.id,
                    note_id=message.get("note_id", ""),
                    user_id=user.id,
                    username=user.username,
                    email=email,
                    cursor=message.get("cursor"),
                    active=True,
                )
            elif event_type == "ping":
                await websocket.send_json({"type": "pong"})
            else:
                await websocket.send_json({"type": "ack", "received": event_type})
    except WebSocketDisconnect:
        logger.info("WS disconnected — user=%s vault=%s", user.username, vault.id)
        await hub.disconnect(vault.id, user.id, websocket)
    except Exception:
        # Railway's proxy can drop the TCP connection without a clean WS close
        # frame. In that case receive_json() raises something other than
        # WebSocketDisconnect (RuntimeError, ConnectionResetError, etc.).
        # Always clean up the hub so the user's presence entry is removed.
        logger.error("WS unexpected error for user=%s:\n%s", user.username, traceback.format_exc())
        await hub.disconnect(vault.id, user.id, websocket)
