# WorldStitch — Project Brain

This file is read automatically at the start of every Claude session. It captures the project's vision, architecture decisions, and developer workflow so that AI assistance is grounded in context from the first message.

---

## 1. Project Vision (North Star)

WorldStitch is a collaborative worldbuilding platform built around one core idea: **"live in your world."** It's not just a notes tool — it's a place where creators build fictional worlds and then *inhabit* them.

- **For writers:** Build lore, characters, locations → explore your world from a character's perspective, test consistency, get writing help grounded in YOUR canon
- **For TTRPG players/GMs:** Build a custom world, then run full campaigns in it. AI acts as GM, narrator, or character. Eventually: import rules systems (D&D, custom, etc.) and run complete tabletop sessions inside WorldStitch
- **The key differentiator:** Unlike Notion or Obsidian (generic notes tools), WorldStitch is purpose-built for inhabiting fictional worlds. The AI isn't a generic assistant — it knows your vault's specific lore, characters, and rules
- **Audience:** Worldbuilders, writers, TTRPG players and GMs. Collaborative-first but fully functional solo
- **Current phase:** Private beta — inviting friends, iterating, not yet public

---

## 2. AI Philosophy

AI is **central to the app**, not a bolt-on feature. It's the thing that makes "living in your world" possible.

**4 AI modes (personas):**

| Mode | Role |
|------|------|
| **Lore** | World expert. Answers questions about the vault's lore, finds connections, explains canon |
| **Writing** | Creative collaborator. Helps draft, edit, and expand content in the world's voice and style |
| **GM** | Game master mode. Runs sessions, narrates encounters, controls NPCs, adjudicates rules. The premium north star feature |
| **Developer** | Admin/debug mode. Only accessible to owner/admin/mod/support/tester/system roles. Helps diagnose issues, create test data, inspect state |

**AI tool use:** The AI has real tools that execute against the vault — create/edit/delete notes, manage characters, build relationships, search content. It must actually use these tools, not just describe what it would do.

**AI key hierarchy:** user's own key → vault shared key → platform key (`OPENAI_API_KEY` env var). `PLATFORM_KEY_ROLES = {owner, admin, mod, support, tester, system}`.

**Future premium:** "Playable DM mode" is the flagship premium feature. Platform provides AI tokens with a markup for users who don't bring their own key.

**Out of scope:** 3D graphics, generic productivity features, social media feeds.

---

## 3. Platform Roles (9 total)

Defined in `server/deps.py`:

```
owner > admin > mod > support > tester > beta > user > guest > system
```

| Role | Access |
|------|--------|
| `owner` / `admin` | Full platform control (`PLATFORM_ADMIN`) |
| `mod` | Moderation capabilities (`MOD_AND_ABOVE`) |
| `support` | Can use platform AI key, help users |
| `tester` | Internal testers, platform AI key access |
| `beta` | Beta users, no platform key (bring their own) |
| `user` | Standard registered user |
| `guest` | Read-only access to shared content (future) |
| `system` | Bot/automation accounts |

Vault roles are **separate** from platform roles. A `user` can be a vault owner within their own vault.

---

## 4. Tech Stack

**Backend:** Python 3.11, FastAPI (async), SQLAlchemy (async), Alembic migrations, PostgreSQL (via asyncpg/psycopg2), JWT auth (python-jose)

**Frontend:** React 18, Vite, react-query, Tailwind CSS, lucide-react, React Router

**Infrastructure:** Railway (production), Docker, single dyno (`WORKERS=1`), auto-deploy on push to `main`

**Email:** Resend API (`server/email.py`) — gracefully no-ops if `RESEND_API_KEY` not set

**Monitoring:** Sentry (optional, init if `SENTRY_DSN` set), `/health` and `/metrics` endpoints

---

## 5. Critical Architecture Facts / Gotchas

These have caused production bugs. Read carefully before touching these areas.

### WebSocket

- **NEVER** register WebSocket routes via `include_router` with a prefix — FastAPI doesn't resolve them correctly, causes 404
- **ALWAYS** use: `app.add_api_websocket_route("/api/ws", websocket_events)` directly on the app object in `server/app.py`
- `await websocket.accept()` must be the **FIRST line** in the handler before any auth checks — otherwise close frames deliver as TCP drops (browser sees 1006, retries forever)
- Frontend URL: `${getWsBase()}/api/ws?token=...&vault_id=...`

### Workers

- **`WORKERS=1` always.** `RealtimeHub` is in-memory — multiple workers means each has a separate hub, presence events from worker 2 never reach connections on worker 1. If we ever need horizontal scaling, we must migrate the hub to Redis pub/sub first.

### Alembic Migrations

- Keep the chain **strictly linear** — one head at a time
- All `CREATE TABLE` statements must use `IF NOT EXISTS` guards
- Boolean column defaults: use `DEFAULT FALSE` / `DEFAULT TRUE` — **never** `DEFAULT 0` / `DEFAULT 1` (PostgreSQL type mismatch error)
- Migration files live in `alembic/versions/`

### Async

- Any function that is `await`ed must be `async def` — Python silently returns a coroutine object if you forget, causing silent failures
- This burned us on `_execute_tool_call` in `server/routes/ai.py` — it is `async def`, keep it that way

### AI Tool Calling

- `_execute_tool_call` in `server/routes/ai.py` is `async def` — keep it that way
- Tools are only available when `vault_id` is provided
- Backend enforces Developer mode gating by `system_role` — frontend cannot be trusted for this check

---

## 6. Key Files

| File | Purpose |
|------|---------|
| `server/app.py` | FastAPI app, middleware, route registration, WebSocket direct registration |
| `server/deps.py` | Role definitions, auth dependencies, `PLATFORM_KEY_ROLES` |
| `server/routes/ai.py` | AI streaming, tool execution, mode gating |
| `server/routes/ws.py` | WebSocket handler (registered directly, not via router prefix) |
| `server/realtime.py` | `RealtimeHub` — in-memory presence/editing state |
| `server/email.py` | Resend email sending (no-ops if no API key) |
| `server/monitoring.py` | Sentry init, metrics |
| `server/vault_access.py` | `resolve_vault()` — vault membership checks |
| `frontend/src/context/RealtimeContext.jsx` | WebSocket client, reconnect logic, keepalive ping |
| `frontend/src/api.js` | API helpers, `getWsBase()`, auth token management |
| `frontend/src/pages/Chat.jsx` | AI chat UI — ChatGPT-style, 4 persona modes |
| `alembic/versions/` | Migration files — linear chain, one head at a time |

---

## 7. Developer Workflow

### Evan's rules — always follow these

- **Talk before building** any architectural decision — ask first, build after alignment
- **Fresh git worktree** for every code task (`git worktree add`) — never commit directly to `main` from a task branch
- **Assume all PRs are merged** unless Evan explicitly says otherwise — he merges between messages
- No SQLite anywhere — PostgreSQL only
- Tabletop/worldbuilding flavor in UI copy where appropriate (not everywhere — keep it tasteful)

### Railway deployment

- Push to `main` → auto-deploy
- Env vars set in Railway dashboard: `DATABASE_URL`, `SECRET_KEY`, `OPENAI_API_KEY`, `RESEND_API_KEY`, `SENTRY_DSN` (optional)
- Build uses Docker — `npm ci` runs before `COPY . .` for layer caching

### Local dev

```bash
# Backend
uvicorn server.app:app --reload

# Frontend
npm run dev
```

---

## 8. Monetization Model

- **Free tier:** Bring your own OpenAI API key (set in Settings → AI)
- **Beta/tester:** Free access to platform AI key
- **Future premium:**
  - Platform provides AI tokens (markup on usage)
  - "Playable DM mode" — full tabletop session running as flagship feature
  - Possible: advanced export, more AI context, private vaults with more members

---

## 9. What WorldStitch Is NOT

- Not a generic note-taking app (that's Obsidian/Notion)
- Not a social media platform
- Not a 3D world builder
- Not a standalone game engine

The worldbuilding/TTRPG flavor should be present but not overwhelming — the app should feel professional, not like a niche DnD tool.
