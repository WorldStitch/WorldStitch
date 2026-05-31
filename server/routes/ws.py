from __future__ import annotations

import logging

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

    async def reject(code: int = 1008) -> None:
        """Send a close frame, tolerating an already-gone connection."""
        try:
            await websocket.close(code=code)
        except Exception:
            pass

    try:
        payload = decode_jwt(token)
    except HTTPException:
        await reject()
        return
    user = ctx.users.get_user(payload.get("sub", ""))
    if not user:
        await reject()
        return

    try:
        vault = resolve_vault(ctx, user, vault_id)
    except HTTPException:
        await reject()
        return

    email = getattr(user, "email", payload.get("email", ""))
    # The websocket is already accepted above; hub.connect registers the
    # connection and broadcasts presence without re-accepting.
    await hub.connect(vault.id, user.id, user.username, email, websocket)
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
        await hub.disconnect(vault.id, user.id, websocket)
    except Exception as exc:
        # Railway's proxy can drop the TCP connection without a clean WS close
        # frame. In that case receive_json() raises something other than
        # WebSocketDisconnect (RuntimeError, ConnectionResetError, etc.).
        # Always clean up the hub so the user's presence entry is removed.
        logger.debug("WebSocket connection lost unexpectedly: %s", exc)
        await hub.disconnect(vault.id, user.id, websocket)
