# Building WorldStitch for Distribution

Every time you want to send a new build to testers, follow these steps.
The result is one `.exe` file they double-click to install — no Python or Node required on their end.

Total time: about 5–10 minutes once everything is set up.

---

## Prerequisites

| Tool | Version | Notes |
|------|---------|-------|
| Python | 3.11+ | Must be in PATH; used only during the build |
| Node.js | 18+ | Required for the Electron/Vite build |
| Git | any | |

The project `.venv` must exist and have all dependencies installed:

```bat
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

Platform icon files must be present in `frontend/build-resources/` (see that
folder's README).

---

## Before you start

Make sure you have pulled the latest code from GitHub:

```
update.bat
```

Make sure your `.venv` is set up and your `.env` file has the right values.
If you have not done the first-time setup, see the README.

---

## Step 1 — Freeze the Python server

Open a terminal in the WorldStitch folder (or double-click `Dev_Console.bat`).

Run from the **project root**:

```bat
scripts\build-backend.bat
```

This activates `.venv`, installs PyInstaller, and produces:

```
dist\
  server\
    server.exe      ← entry point Electron will launch
    _internal\      ← all bundled DLLs and .pyc files
```

This will take **2–5 minutes**. You will see a lot of output scroll by — that is normal.

When it is done you should see:

```
[build-backend] Done.  Frozen backend at: dist\server\server.exe
```

If it says `ERROR` instead, see the Troubleshooting section below.

> **Why onedir instead of onefile?**  The `--onedir` format avoids Windows
> Defender false-positives common with self-extracting `--onefile` bundles and
> starts faster (no extraction on every launch).

---

## Step 2 — Build the Windows installer

In the same terminal, run:

```bat
cd frontend
npm install
npm run build:win
```

This will take **1–3 minutes**.

When it is done you will see something like:

```
  • building        target=NSIS name=WorldStitch file=WorldStitch Setup 1.0.0.exe
  • done
```

For other platforms:

```bash
# macOS (produces dist-electron/WorldStitch-x.x.x.dmg)
npm run electron:build:mac

# Linux (produces dist-electron/WorldStitch-x.x.x.AppImage)
npm run electron:build:linux
```

---

## Step 3 — Find your installer file

Your installer is at:

```
frontend\dist-electron\WorldStitch Setup 1.0.0.exe
```

(The version number may differ.) That is the file you send to testers.

---

## Step 4 — Test it yourself first

Before sending to anyone:

1. Run `WorldStitch Setup 1.0.0.exe` on your own machine
2. Click through the install wizard
3. Launch WorldStitch from the Start Menu or Desktop shortcut
4. The app should open and the API health check should pass (green status)

The Electron main process (`electron/main.cjs`) will:
1. Open the app window immediately showing a startup splash screen
2. Launch `server.exe` from `resources/server/` (packaged) or spawn uvicorn (dev)
3. Wait up to 20 seconds for the API to respond on port 8741
4. Show an error screen with details if startup fails

User data (vault, logs, `settings.json`, SQLite DB) is stored in:

```
%APPDATA%\WorldStitch\
```

If the app opens and you can log in, it is good to ship.

---

## Step 5 — Send to testers

Send testers:
- The `.exe` file
- The `TESTER_GUIDE.md` file (in the project root)

Testers need to create their own `.env` file before first launch. The TESTER_GUIDE walks them through it.

---

## Troubleshooting

### PyInstaller fails with import errors
Add the missing module via `--hidden-import` in `scripts\build-backend.bat`
and re-run.

### Step 1 fails with "ModuleNotFoundError" or similar

Your venv may be missing a package. Run:
```
.venv\Scripts\activate
pip install -r requirements.txt
```
Then try Step 1 again.

### Step 1 fails with "PyInstaller not found"

```
.venv\Scripts\activate
pip install pyinstaller
```

### `server.exe` crashes on launch / Step 2 fails with "cannot find dist\server\"

Step 1 did not finish successfully. Run it directly in a terminal to see the traceback:

```bat
set MYTHOS_DATA_DIR=%APPDATA%\WorldStitch
dist\server\server.exe
```

### Step 2 fails with npm errors

```
cd frontend
npm install
npm run build:win
```

### electron-builder can't find `dist\server\`
Make sure Step 1 completed successfully before running Step 2.  The path
`../dist/server` in `package.json` `extraResources` is relative to the
`frontend/` directory.

### App opens but API is unreachable
Check `%APPDATA%\WorldStitch\logs\app.log` for Python-side errors.

### The installed app works on your machine but crashes for testers
Check if their machine is Windows 10 or later (64-bit).
Ask them to send you the log file from: `%APPDATA%\WorldStitch\logs\app.log`

---

## Quick reference — the two commands

From the project root:

```
scripts\build-backend.bat
cd frontend && npm run build:win
```

Output file: `frontend\dist-electron\WorldStitch Setup x.x.x.exe`

---

## Development (local, no installer)

```bash
# Start the Python backend (from project root)
python -m uvicorn server.app:app --host 127.0.0.1 --port 8741 --reload

# Start the Electron + Vite frontend (from frontend/)
cd frontend
npm install
npm run electron:dev
```

Or use the convenience launcher:
```bat
Launch_WorldStitch.bat
```

---

## CI / automated builds

The two steps map cleanly to separate CI jobs:

```yaml
# (pseudo-code — adapt to your CI system)
build-backend:
  runs-on: windows-latest
  steps:
    - run: scripts\build-backend.bat
    - upload-artifact: dist/server

build-electron:
  needs: build-backend
  steps:
    - download-artifact: dist/server
    - run: cd frontend && npm ci && npm run build:win
    - upload-artifact: frontend/dist-electron/*.exe
```
