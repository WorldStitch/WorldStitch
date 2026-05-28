from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect

from WorldStitch.context.app_context import AppContext
from server.auth_utils import decode_jwt
from server.deps import get_ctx
from server.realtime import hub
from server.vault_access import resolve_vault

router = APIRouter()


@router.websocket("/ws")
async def websocket_events(
    websocket: WebSocket,
    token: str = Query(...),
    vault_id: str = Query(...),
    ctx: AppContext = Depends(get_ctx),
):
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
