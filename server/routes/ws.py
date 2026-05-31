from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect

from server.auth_utils import decode_jwt
from server.deps import get_ctx
from server.realtime import hub
from server.vault_access import resolve_vault
from WorldStitch.context.app_context import AppContext

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

    try:
        payload = decode_jwt(token)
    except HTTPException:
        await websocket.close(code=1008)
        return
    user = ctx.users.get_user(payload.get("sub", ""))
    if not user:
        await websocket.close(code=1008)
        return

    try:
        vault = resolve_vault(ctx, user, vault_id)
    except HTTPException:
        await websocket.close(code=1008)
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
