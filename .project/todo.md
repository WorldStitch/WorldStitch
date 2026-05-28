# MythosEngine — Master Roadmap

---

## ✅ PHASE 1 — Foundation (Complete)

All 8 original foundation sections done. Core architecture, models, SQLite storage,
auth scaffold, data isolation, audit logging, crash handler, SMTP reporter,
user management UI, CI/CD, and docs are all in place.

---

## 🔧 PHASE 2 — v0 Stabilization (Current Priority)

Goal: stable, shareable app for a small group of testers.

### Auth & Login
- [ ] Login dialog works end-to-end with fresh DB
- [ ] Admin bootstraps correctly from .env on first launch
- [ ] User Management panel creates player accounts correctly
- [ ] Reset password in User Management works
- [ ] Member accounts see only their own data; admin sees all
- [ ] Login failure shows error message (not crash)

### Stability
- [ ] All tabs load without errors after login
- [ ] App survives existing DB across restarts
- [ ] SMTP crash reporter tested and sending emails
- [ ] Cancel login exits cleanly

### Security cleanup
- [ ] Rotate exposed OpenAI API key
- [ ] Confirm .env and ward_dnd.db are gitignored and NOT on GitHub
- [ ] Delete leftover fix scripts from repo

### v0 Release
- [ ] Tag as v0.1.0
- [ ] Write tester onboarding doc (install, configure, first login)
- [ ] Send to first testers

---

## 🔒 PHASE 3 — Full User System & Multiuser (v1)

Goal: real multiuser with groups, roles, sharing, and online capability.

### Auth overhaul
- [ ] First-launch setup wizard (UI-driven, no terminal required)
- [ ] Real session tokens stored in DB (not just in-memory)
- [ ] Session expiry and auto-logout
- [ ] Self-service password change in UI
- [x] Invite code system for controlled signups
- [ ] Admin view — full user list, usage stats, account controls

### Groups & permissions
- [ ] Group/party creation and management UI
- [ ] Vault membership — group members share a vault's content
- [ ] Role-based access: vault admin sees everything, members see what's shared
- [ ] Per-resource sharing (individual notes/characters with specific users)

### Storage & data isolation
- [ ] Add owner_id SQL column to ALL remaining ORM tables
- [ ] Filter ALL list queries by owner_id (currently only notes filtered)
- [ ] Storage router — swap backend via config (SQLite → Postgres)
- [ ] Per-user API key OR shared key with per-user usage limits

### Online / offline
- [ ] Full offline functionality without internet
- [ ] Optional cloud DB via connection string in .env
- [ ] Conflict resolution for offline → online sync

---

## 🎨 PHASE 4 — UI/UX Modernization

Goal: looks and feels like a real product.

- [ ] New icon, color scheme, typography
- [ ] Modern sidebar navigation replacing tab bar
- [ ] Light/dark/custom theme system
- [ ] Consistent buttons, icons, spacing throughout
- [ ] Drag-and-drop for notes/folders
- [ ] Onboarding wizard for new users
- [ ] Command palette (Ctrl+P quick launcher)
- [ ] Status bar showing current user, vault, AI model

---

## 🤖 PHASE 5 — AI Expansion

Goal: AI is first-class across the whole app.

- [ ] AI setup wizard — walks through API key, picks optimal model
- [ ] Persistent chat history per session
- [ ] Streaming responses (text appears as it generates)
- [ ] Multiple AI providers (OpenAI, Anthropic, local Ollama)
- [ ] Bulk summarize entire vault or folder
- [ ] Consistency checker — finds contradictions in lore
- [ ] Shared AI context for groups — vault members query same lore base
- [ ] Session recap generator from notes
- [ ] NPC dialogue generator from character sheets
- [ ] API endpoint — expose AI query as REST for website integration

---

## 🗂️ PHASE 6 — Features & Content

Goal: all existing tabs actually work, plus new world-building tools.

### Browse & Notes
- [ ] Full-text search UI (backend exists, needs UI)
- [ ] Tag browser and tag cloud
- [ ] Note versioning UI — diff view, one-click restore
- [ ] Bulk operations — multi-select, batch move/tag/delete
- [ ] Note templates (NPC, Location, Item, etc.)

### World Builder module
- [ ] Location hierarchy (world → region → city → building)
- [ ] Faction tracker
- [ ] Timeline with linked events
- [ ] Relationship graph — visual connections between entities

### DND module
- [ ] Character sheet viewer and editor
- [ ] Party management
- [ ] Initiative tracker
- [ ] Dice roller in chat
- [ ] Encounter builder

### File types
- [ ] Import from Obsidian, Notion, Markdown folders
- [ ] Export to PDF, DOCX, HTML
- [ ] Image asset management in-app
- [ ] Audio ambience player (already partially built)

---

## 🌐 PHASE 7 — Website & Cloud Integration

- [ ] Public lore portal — publish notes as read-only website
- [ ] Player portal — players access notes via browser
- [ ] REST API backend
- [ ] Hosted database option (PostgreSQL)
- [ ] Cloud backup scheduled automatically
- [ ] Multi-device sync
- [ ] Vault marketplace — download community lore packs

---

## 📊 PHASE 8 — Analytics

- [ ] Per-account: notes created/edited, AI usage and cost, most-queried content
- [ ] App-wide (admin): total users, API cost, storage usage, error rate
- [ ] AI quality feedback (thumbs up/down on responses)

---

## 🔐 PHASE 9 — Security & Compliance

- [ ] Security audit before public launch
- [ ] Rate limiting on all endpoints
- [ ] GDPR-compliant data deletion
- [ ] Privacy policy and terms of service
- [ ] End-to-end encryption option for sensitive vaults

---

## 🚀 PHASE 10 — Distribution

- [ ] Windows installer (.exe)
- [ ] Mac installer (.dmg)
- [ ] In-app auto-updater
- [ ] CI/CD auto-build and release on tag
- [ ] Public landing page

---

## 📋 Tech Debt (see TECH_DEBT.md)

- [ ] Add owner_id SQL column to remaining ORM tables
- [ ] find_legacy_storage.py, rename_vault_storage.py, tree.py — move or delete
- [ ] mypy is continue-on-error — fix errors, make it a hard CI gate
