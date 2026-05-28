const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("electronAPI", {
  getApiUrl: () => ipcRenderer.invoke("get-api-url"),
  // Fetch the current backend status once (for mounting after page reload).
  getBackendStatus: () => ipcRenderer.invoke("get-backend-status"),
  // Subscribe to backend status updates; returns an unsubscribe function.
  onBackendStatus: (callback) => {
    const handler = (_, status) => callback(status);
    ipcRenderer.on("backend:status", handler);
    return () => ipcRenderer.removeListener("backend:status", handler);
  },
  platform: process.platform,
});
