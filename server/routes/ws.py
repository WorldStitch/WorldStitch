from __future__ import annotations

import logging
import traceback

from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect

from server.auth_utils import decode_jwt
from server.deps import get_ctx
from server.realtime import hub
from server.vault_access import resolve_vault
from WorldStitch.context.app_context import AppContext

router = APIRouter()
logger = logging.getLogger(__name__)


@router.websocket("/ws")
async def websocket_events(
    websocket: WebSocket,
    token: str = Query(...),
    vault_id: str = Query(...),
    ctx: AppContext = Depends(get_ctx),
):
    await websocket.accept()
    logger.info(f"WS accepted — vault_id={vault_id}")

    try:
        payload = decode_jwt(token)
    except HTTPException as e:
        logger.warning(f"WS auth failed — bad token: {e.detail}")
        await websocket.close(code=1008)
        return

    sub = payload.get("sub", "")
    user = ctx.users.get_user(sub)
    logger.info(f"WS user lookup — sub={sub} found={bool(user)}")
    if not user:
        logger.warning(f"WS closing — user not found for sub={sub}")
        await websocket.close(code=1008)
        return

    try:
        vault = resolve_vault(ctx, user, vault_id)
    except HTTPException as e:
        logger.warning(f"WS closing — vault resolve failed: {e.detail}")
        await websocket.close(code=1008)
        return

    logger.info(f"WS connected — user={user.username} vault={vault.id}")
    email = getattr(user, "email", payload.get("email", ""))

    try:
        await hub.connect(vault.id, user.id, user.username, email, websocket)
    except Exception:
        logger.error(f"WS hub.connect error: {traceback.format_exc()}")
        await websocket.close(code=1011)
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
        logger.info(f"WS disconnected — user={user.username} vault={vault.id}")
        await hub.disconnect(vault.id, user.id, websocket)
    except Exception:
        logger.error(f"WS unexpected error for user={user.username}: {traceback.format_exc()}")
        await hub.disconnect(vault.id, user.id, websocket)
