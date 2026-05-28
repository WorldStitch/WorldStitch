# WorldStitch — External Tester Guide

**Build stage:** Alpha · **Platform:** Windows (primary), macOS/Linux (dev only)

Thank you for testing WorldStitch! This guide walks you through setup, a tour of every feature, and concrete things to try (and break).

---

## What Is WorldStitch?

WorldStitch is a desktop application for vault owners and world builders. It lets you:

- **Write and organize notes** about your world or project
- **Track characters** (player characters and characters) with stat blocks
- **Log session recaps** and generate AI summaries
- **Manage maps** with typed markers
- **Chat with an AI** that can reference your campaign notes
- **Collaborate** through vaults, groups, and invite-based access

The app runs as an Electron window. A small Python/FastAPI server runs in the background — you don't interact with it directly.

---

## Prerequisites

| Requirement | Version | How to check |
|-------------|---------|--------------|
| Python | 3.11 or later | `python --version` |
| Node.js | 18 or later | `node --version` |
| Git | Any | `git --version` |
| OpenAI API key | — | Needed for AI features only |

---

## Installation

### 1 — Clone the repo

```powershell
git clone https://github.com/sike-ward/WorldStitch.git
cd WorldStitch
```

### 2 — Create a Python virtual environment

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

> If you see a red error about `PyQt6`, ignore it — it's an optional GUI dependency not needed for the server.

### 3 — Set up your `.env` file

```powershell
Copy-Item .env.example .env
```

Open `.env` in any text editor and fill in:

```env
# Required — generate with: python -c "import secrets; print(secrets.token_hex(32))"
JWT_SECRET=<paste-generated-secret-here>

# Required for AI features (chat, recap, tag suggestions)
OPENAI_API_KEY=sk-proj-...

# Your admin login credentials (change before first launch)
ADMIN_EMAIL=admin@example.com
ADMIN_PASSWORD=YourStrongPassword123!
```

> If you skip `JWT_SECRET`, the server will warn but still start. It's safer to set it.

### 4 — Install Node dependencies

```powershell
cd frontend
npm install
cd ..
```

---

## Launching the App

### Option A — Double-click launcher (easiest)

Run `Launch_WorldStitch.bat` from the project root. It:
1. Verifies Python venv and Node.js
2. Starts the FastAPI backend in a minimized window
3. Opens the Electron app

### Option B — Manual (for developers)

In one terminal (from project root, venv activated):
```powershell
python -m uvicorn server.app:app --host 127.0.0.1 --port 8741
```

In another terminal:
```powershell
cd frontend
npm run electron:dev
```

---

## First-Run Setup

1. **Login screen appears** — use the admin credentials you set in `.env`
2. **Create a Vault** — click the vault selector in the sidebar → **New Vault**. Give it a name (e.g., "My Project"). All content belongs to a vault.
3. You're ready to explore.

> If you see "No vault selected" on the Characters / Sessions / Maps pages, click the **Go to Vaults** button that appears.

---

## Feature Tour & What to Test

### Dashboard

The home screen shows stat counts and recent notes.

**Try:**
- [ ] Verify stat counts update after you add a note, character, or session
- [ ] Click a recent note to jump to it in Browse

---

### Browse (Notes)

Hierarchical note editor. Create folders and markdown notes, attach tags, and link notes to each other.

**Try:**
- [ ] Create a folder, then create a note inside it
- [ ] Edit the note — write some markdown, save
- [ ] Use **Suggest Tags** (AI button) — should propose tags based on note content
- [ ] Use **Propose Links** — should suggest connections to other notes
- [ ] Rename and move a note via the right-click/context menu
- [ ] Delete a note (confirm it disappears from the tree)
- [ ] Search using the search bar above the note list

---

### Characters

Manage player characters and characters with full stat blocks.

**Try:**
- [ ] Click **New** and create a Player Character — fill in name, race, class, level, and some ability scores
- [ ] Create a character
- [ ] Use the All / Players / Characters filter tabs
- [ ] Search by character name
- [ ] Attach a note to a character (in the "Attached Notes" section)
- [ ] Save changes, then reload — verify data persisted
- [ ] Delete a character

---

### Sessions

Session log. Write raw session notes and optionally generate an AI recap.

**Try:**
- [ ] Click **+ New Session** and fill in a title, date, and participants
- [ ] Write some raw notes (a paragraph or two)
- [ ] Click **Create Session** to save
- [ ] Click **✨ Generate Recap** (requires OpenAI key) — should produce a formatted summary
- [ ] Edit and re-save the session
- [ ] Delete a session via the **Delete** button (should show a confirmation toast — no browser popup)

---

### Maps

Manage world maps, dungeon layouts, city plans, etc.

**Try:**
- [ ] Click **New** and create a Region map
- [ ] Add a description and some tags
- [ ] Click **Add Marker**, fill in label + X/Y coordinates, click Add
- [ ] Verify the marker appears in the marker list
- [ ] Save the map
- [ ] Filter the map list by type (Region, Dungeon, City, World)

---

### Chat (AI)

Conversational AI with optional campaign context.

**Try (requires OpenAI key):**
- [ ] Ask a general question: "What are the main factions in my story?"
- [ ] Ask something about your notes: "Summarize what I know about [character name]"
- [ ] Verify streaming works — text should appear word-by-word, not all at once
- [ ] Check that the conversation history persists across turns

---

### Vaults

Vaults are top-level containers. One vault = one campaign (or workspace).

**Try:**
- [ ] Create a second vault
- [ ] Switch between vaults using the sidebar selector — content should switch
- [ ] Edit the vault name/description
- [ ] Invite another user to a vault (if testing with multiple accounts)

---

### Groups (Members)

Groups let you assign roles to sets of users within a vault.

**Try:**
- [ ] Create a group ("Players", "Observers")
- [ ] Invite a user to the group
- [ ] Verify group members appear correctly

---

### Settings

**Try:**
- [ ] Change the AI model (if you have access to gpt-4o or similar)
- [ ] Toggle streaming on/off in AI Settings and re-test Chat
- [ ] Check Account Settings shows correct username/email

---

## Known Limitations (Alpha)

| Area | Status |
|------|--------|
| Map image rendering | Image paths are stored but not yet displayed; the image viewer is a placeholder |
| Electron packaged build | `npm run electron:build` produces an `.exe` but it's not yet signed — Windows Defender may warn |
| AI features offline | Chat, recap, and tag suggestion require an active internet connection and a valid OpenAI key |
| Multi-user real-time sync | Presence indicators exist but full conflict resolution is not implemented |
| Mobile / web | The app is desktop-only; the web dev server (`npm run dev`) works for development but is not supported for testing |

---

## Reporting Bugs

Please report issues at: **https://github.com/sike-ward/WorldStitch/issues**

When filing a bug, include:

1. **Steps to reproduce** — what did you click / type?
2. **Expected vs. actual behavior**
3. **Screenshot or screen recording** if the UI looks wrong
4. **Console logs** — in the Electron app, open DevTools with `Ctrl+Shift+I` → Console tab, copy any red errors

### Log files

The backend writes logs to `logs/app.log` in the project root. If the app crashed or the API didn't start, this file is the first place to look.

---

## Quick Troubleshooting

| Symptom | Fix |
|---------|-----|
| "Python not found" at launch | Install Python 3.11+ and ensure it's on `PATH`, or re-run `python -m venv .venv` |
| App opens but shows loading spinner forever | Check that uvicorn started — look at the minimized "WorldStitch-API" terminal window |
| Login fails with "Invalid credentials" | Double-check `ADMIN_EMAIL` / `ADMIN_PASSWORD` in `.env` |
| AI features return errors | Verify `OPENAI_API_KEY` in `.env` is valid and has available credits |
| "No vault selected" on Characters/Maps/Sessions | Go to `/vaults` and create or select a vault |
| Blank white Electron window | Wait 10–15 seconds — Vite dev server may still be compiling |

---

*Last updated: 2026-05-13*
