const { app, BrowserWindow, ipcMain } = require("electron");
const path = require("path");
const { spawn } = require("child_process");

let mainWindow;
let apiProcess = null;
// Tracks the latest backend status so we can replay it after page load
let backendState = { state: "starting", message: "Initializing..." };

const isDev = !app.isPackaged;
const API_PORT = 8741;
const API_URL = `http://127.0.0.1:${API_PORT}`;

// ── Backend status IPC ───────────────────────────────────────────────────────

function sendBackendStatus(state, message = "") {
  backendState = { state, message };
  if (mainWindow && !mainWindow.isDestroyed()) {
    mainWindow.webContents.send("backend:status", backendState);
  }
}

// ── Launch the FastAPI backend ───────────────────────────────────────────────

function startBackend() {
  sendBackendStatus("starting", "Starting MythosEngine server…");
  if (isDev) {
    // Dev: run uvicorn directly from the project root so that
    // `from server.routes import ...` and `from MythosEngine.* import ...` work.
    const projectRoot = path.join(__dirname, "..", "..");
    const pythonCmd = process.platform === "win32" ? "python" : "python3";
    apiProcess = spawn(
      pythonCmd,
      ["-m", "uvicorn", "server.app:app", "--host", "127.0.0.1", "--port", String(API_PORT)],
      { cwd: projectRoot, stdio: ["ignore", "pipe", "pipe"] }
    );
  } else {
    // Packaged: launch the PyInstaller-frozen server.exe bundled in resources.
    // Pass MYTHOS_DATA_DIR so the server writes vault/logs/DB to the user's
    // AppData dir (writable) rather than the read-only Program Files location.
    const serverExe = path.join(process.resourcesPath, "server", "server.exe");
    const userDataPath = app.getPath("userData");
    apiProcess = spawn(serverExe, [], {
      env: { ...process.env, MYTHOS_DATA_DIR: userDataPath },
      stdio: ["ignore", "pipe", "pipe"],
    });
  }

  apiProcess.stdout.on("data", (d) => {
    console.log(`[API] ${d.toString().trim()}`);
  });

  apiProcess.stderr.on("data", (d) => {
    const msg = d.toString().trim();
    console.error(`[API] ${msg}`);
    // Surface actionable startup errors to the renderer immediately
    if (backendState.state !== "ready") {
      if (msg.includes("ModuleNotFoundError") || msg.includes("No module named")) {
        sendBackendStatus(
          "error",
          `Missing Python module. Run:\n  pip install -r requirements.txt\n\nDetails: ${msg}`
        );
      } else if (msg.includes("Address already in use")) {
        sendBackendStatus("error", `Port ${API_PORT} is already in use by another process.`);
      }
    }
  });

  apiProcess.on("close", (code) => {
    console.log(`[API] exited with code ${code}`);
    if (code !== 0 && backendState.state !== "ready") {
      sendBackendStatus(
        "error",
        `Server process exited (code ${code}). Ensure Python 3.11+ is installed and run:\n  pip install -r requirements.txt`
      );
    }
  });

  apiProcess.on("error", (err) => {
    console.error("[API] Failed to spawn:", err);
    if (err.code === "ENOENT") {
      sendBackendStatus(
        "error",
        `Python not found. Install Python 3.11+ and run:\n  pip install -r requirements.txt`
      );
    } else {
      sendBackendStatus("error", err.message);
    }
  });
}

// ── Wait for the API to become ready ────────────────────────────────────────

async function waitForApi(retries = 40, delay = 500) {
  for (let i = 0; i < retries; i++) {
    try {
      const res = await fetch(`${API_URL}/health`);
      if (res.ok) return true;
    } catch {
      // not ready yet
    }
    await new Promise((r) => setTimeout(r, delay));
  }
  return false;
}

// ── Create the main browser window ──────────────────────────────────────────

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1360,
    height: 860,
    minWidth: 960,
    minHeight: 640,
    backgroundColor: "#0D0D14",
    titleBarStyle: "hiddenInset",
    frame: process.platform !== "darwin",
    webPreferences: {
      preload: path.join(__dirname, "preload.cjs"),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });

  if (isDev) {
    mainWindow.loadURL("http://localhost:5173");
    mainWindow.webContents.openDevTools({ mode: "detach" });
  } else {
    mainWindow.loadFile(path.join(__dirname, "..", "dist", "index.html"));
  }

  // Replay the latest backend state once React has mounted so it never misses
  // a status that arrived before the page finished loading.
  mainWindow.webContents.on("did-finish-load", () => {
    mainWindow.webContents.send("backend:status", backendState);
  });

  mainWindow.on("closed", () => {
    mainWindow = null;
  });
}

// ── App lifecycle ────────────────────────────────────────────────────────────

app.whenReady().then(async () => {
  // Show the window immediately — React handles the "starting" splash screen.
  createWindow();

  // In dev mode the bat file may have already started the API.
  let apiAlreadyRunning = false;
  try {
    const res = await fetch(`${API_URL}/health`);
    if (res.ok) apiAlreadyRunning = true;
  } catch {
    // not running
  }

  if (apiAlreadyRunning) {
    console.log("[Electron] API already running, skipping backend start");
    sendBackendStatus("ready");
  } else {
    startBackend();
    const ready = await waitForApi();
    if (ready) {
      console.log("[Electron] API is ready");
      sendBackendStatus("ready");
    } else if (backendState.state !== "error") {
      sendBackendStatus(
        "error",
        "Server did not respond within 20 seconds. Check that Python is installed and try again."
      );
    }
  }

  app.on("activate", () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
  });
});

app.on("window-all-closed", () => {
  if (process.platform !== "darwin") {
    if (apiProcess) apiProcess.kill();
    app.quit();
  }
});

app.on("before-quit", () => {
  if (apiProcess) apiProcess.kill();
});

// ── IPC handlers ─────────────────────────────────────────────────────────────

ipcMain.handle("get-api-url", () => API_URL);
// Allows React to request the current state synchronously on mount.
ipcMain.handle("get-backend-status", () => backendState);
