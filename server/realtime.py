from __future__ import annotations

import asyncio
from collections import defaultdict
from typing import Any, Set

from fastapi import WebSocket


class RealtimeHub:
    def __init__(self) -> None:
        self._connections: dict[str, set[WebSocket]] = defaultdict(set)
        self._online_users: dict[str, dict[str, dict[str, str]]] = defaultdict(dict)
        self._editing: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
        self._lock = asyncio.Lock()

    @staticmethod
    def _is_connected(websocket: WebSocket) -> bool:
        return getattr(getattr(websocket, "client_state", None), "name", "") == "CONNECTED"

    async def connect(self, vault_id: str, user_id: str, username: str, email: str, websocket: WebSocket) -> None:
        await websocket.accept()
        async with self._lock:
            self._connections[vault_id].add(websocket)
            self._online_users[vault_id][user_id] = {"id": user_id, "username": username, "email": email}
        await self.broadcast_presence(vault_id)

    async def disconnect(self, vault_id: str, user_id: str, websocket: WebSocket) -> None:
        async with self._lock:
            self._connections[vault_id].discard(websocket)
            if not any(self._is_connected(ws) for ws in self._connections[vault_id]):
                self._connections.pop(vault_id, None)
            self._online_users[vault_id].pop(user_id, None)
            for note_id, presence in list(self._editing[vault_id].items()):
                if presence.get("user_id") == user_id:
                    self._editing[vault_id].pop(note_id, None)
        await self.broadcast_presence(vault_id)

    async def broadcast(self, vault_id: str, payload: dict[str, Any]) -> None:
        async with self._lock:
            sockets: Set[WebSocket] = set(self._connections.get(vault_id, set()))
        dead: list[WebSocket] = []
        for websocket in sockets:
            try:
                await websocket.send_json(payload)
            except Exception:
                dead.append(websocket)
        if dead:
            async with self._lock:
                for websocket in dead:
                    self._connections[vault_id].discard(websocket)

    async def broadcast_presence(self, vault_id: str) -> None:
        users = list(self._online_users.get(vault_id, {}).values())
        editing = list(self._editing.get(vault_id, {}).values())
        await self.broadcast(
            vault_id,
            {"type": "presence.snapshot", "vault_id": vault_id, "users": users, "editing": editing},
        )

    async def publish_note_saved(self, vault_id: str, note: dict[str, Any]) -> None:
        await self.broadcast(vault_id, {"type": "note.saved", "vault_id": vault_id, "note": note})

    async def set_editing(
        self,
        vault_id: str,
        note_id: str,
        user_id: str,
        username: str,
        email: str = "",
        cursor: int | None = None,
        active: bool = True,
    ) -> None:
        async with self._lock:
            if active:
                self._editing[vault_id][note_id] = {
                    "note_id": note_id,
                    "user_id": user_id,
                    "username": username,
                    "email": email,
                    "cursor": cursor,
                }
            else:
                existing = self._editing.get(vault_id, {}).get(note_id)
                if existing and existing.get("user_id") == user_id:
                    self._editing[vault_id].pop(note_id, None)
        await self.broadcast_presence(vault_id)


hub = RealtimeHub()
