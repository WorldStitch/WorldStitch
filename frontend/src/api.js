/**
 * MythosEngine API Client
 * Talks to the FastAPI backend on localhost:8741.
 */

const BASE =
  typeof window !== "undefined" && window.electronAPI
    ? "http://127.0.0.1:8741"
    : "/api";

export function getApiBase() {
  return BASE;
}

export function getWsBase() {
  if (BASE.startsWith("http://")) return BASE.replace("http://", "ws://");
  if (BASE.startsWith("https://")) return BASE.replace("https://", "wss://");
  if (typeof window !== "undefined") {
    const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
    return `${proto}//${window.location.host}${BASE}`;
  }
  return BASE;
}

let _token = localStorage.getItem("me_token") || null;
let _refreshToken = localStorage.getItem("me_refresh_token") || null;
let _isRefreshing = false;

export function setToken(t) {
  _token = t;
  if (t) localStorage.setItem("me_token", t);
  else localStorage.removeItem("me_token");
}

export function getToken() {
  return _token;
}

export function setRefreshToken(t) {
  _refreshToken = t;
  if (t) localStorage.setItem("me_refresh_token", t);
  else localStorage.removeItem("me_refresh_token");
}

export function getRefreshToken() {
  return _refreshToken;
}

async function tryRefresh() {
  if (!_refreshToken || _isRefreshing) return false;
  _isRefreshing = true;
  try {
    const res = await fetch(`${BASE}/auth/refresh`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ refresh_token: _refreshToken }),
    });
    if (!res.ok) {
      setRefreshToken(null);
      setToken(null);
      return false;
    }
    const data = await res.json();
    setToken(data.access_token);
    return true;
  } catch {
    return false;
  } finally {
    _isRefreshing = false;
  }
}

function makeOpts(method, body) {
  const headers = { "Content-Type": "application/json" };
  if (_token) headers["Authorization"] = `Bearer ${_token}`;
  const opts = { method, headers };
  if (body) opts.body = JSON.stringify(body);
  return opts;
}

async function request(method, path, body = null) {
  let res = await fetch(`${BASE}${path}`, makeOpts(method, body));

  if (res.status === 401) {
    const refreshed = await tryRefresh();
    if (refreshed) {
      res = await fetch(`${BASE}${path}`, makeOpts(method, body));
    }
    if (res.status === 401) {
      setToken(null);
      setRefreshToken(null);
      window.dispatchEvent(new CustomEvent('auth:logout'));
      throw new Error("Session expired");
    }
  }

  if (res.status === 429) throw new Error("__RATE_LIMIT__");
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || "Request failed");
  }
  if (res.status === 204) return null;
  return res.json();
}

async function requestText(method, path) {
  const headers = { "Content-Type": "application/json" };
  if (_token) headers["Authorization"] = `Bearer ${_token}`;
  let res = await fetch(`${BASE}${path}`, { method, headers });

  if (res.status === 401) {
    const refreshed = await tryRefresh();
    if (refreshed) {
      const retryHeaders = { "Content-Type": "application/json" };
      if (_token) retryHeaders["Authorization"] = `Bearer ${_token}`;
      res = await fetch(`${BASE}${path}`, { method, headers: retryHeaders });
    }
    if (res.status === 401) {
      setToken(null);
      setRefreshToken(null);
      window.dispatchEvent(new CustomEvent('auth:logout'));
      throw new Error("Session expired");
    }
  }

  if (res.status === 429) throw new Error("__RATE_LIMIT__");
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || "Request failed");
  }
  return res.text();
}

// ── Auth ─────────────────────────────────────────────────────────────────────
export const auth = {
  status: async () => {
    // Raw fetch — no auth token, no 401 redirect
    const res = await fetch(`${BASE}/auth/status`);
    return res.json();
  },
  setup: async (email, username, password) => {
    const data = await request("POST", "/auth/setup", { email, username, password });
    return { token: data.access_token, refreshToken: data.refresh_token, user: data.user, exp: data.exp };
  },
  login: async (email, password) => {
    let res;
    try {
      res = await fetch(`${BASE}/auth/login`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, password }),
      });
    } catch {
      throw new Error("Cannot connect to MythosEngine server — is it running?");
    }
    if (res.status === 401) throw new Error("Invalid email or password");
    if (res.status === 403) throw new Error("Account is disabled");
    if (res.status === 429) throw new Error("__RATE_LIMIT__");
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(`Login failed: ${err.detail || "Unknown error"}`);
    }
    const data = await res.json();
    return { token: data.access_token, refreshToken: data.refresh_token, user: data.user, exp: data.exp };
  },
  refresh: async () => {
    const ok = await tryRefresh();
    if (!ok) throw new Error("Session expired");
    return _token;
  },
  logout: () => request("POST", "/auth/logout"),
  me: () => request("GET", "/auth/me"),
  changePassword: (current, newPw) =>
    request("POST", "/auth/change-password", {
      current_password: current,
      new_password: newPw,
    }),
  register: async (email, username, password, invite_code) => {
    const data = await request("POST", "/auth/register", { email, username, password, invite_code });
    return { token: data.access_token, refreshToken: data.refresh_token, user: data.user, exp: data.exp };
  },
};

// ── Notes ────────────────────────────────────────────────────────────────────
export const notes = {
  list: async (folder = "", tag = "", vault_id = "") => {
    const params = new URLSearchParams();
    if (folder) params.set("folder", folder);
    if (tag) params.set("tag", tag);
    if (vault_id) params.set("vault_id", vault_id);
    const qs = params.toString();
    const res = await request("GET", `/notes${qs ? `?${qs}` : ""}`);
    // The backend returns a paginated envelope {items, total, skip, limit}.
    // Unwrap to a plain array so callers can use it directly.
    return Array.isArray(res) ? res : (res?.items ?? []);
  },
  get: (id) => request("GET", `/notes/${encodeURIComponent(id)}`),
  search: (query, options = {}) => {
    const params = new URLSearchParams({ q: query });
    if (options.mode) params.set("mode", options.mode);
    if (options.folder) params.set("folder", options.folder);
    if (options.tags) params.set("tags", options.tags);
    if (options.date_from) params.set("date_from", options.date_from);
    if (options.date_to) params.set("date_to", options.date_to);
    if (options.vault_id) params.set("vault_id", options.vault_id);
    if (options.skip != null) params.set("skip", String(options.skip));
    if (options.limit != null) params.set("limit", String(options.limit));
    return request("GET", `/notes/search?${params.toString()}`);
  },

  create: (title, content = "", folder_id = null, tags = [], meta = {}, vault_id = null) =>
    request("POST", "/notes", { title, content, folder_id, tags, meta, vault_id }),
  update: (id, data) =>
    request("PUT", `/notes/${encodeURIComponent(id)}`, data),
  delete: (id) => request("DELETE", `/notes/${encodeURIComponent(id)}`),

  move: (note_id, dest_folder_id) =>
    request("POST", "/notes/move", { note_id, dest_folder_id }),

  addTag: (id, tag) =>
    request("POST", `/notes/${encodeURIComponent(id)}/tags`, { tag }),
  removeTag: (id, tag) =>
    request("DELETE", `/notes/${encodeURIComponent(id)}/tags/${encodeURIComponent(tag)}`),

  updateMeta: (id, meta) =>
    request("PUT", `/notes/${encodeURIComponent(id)}/meta`, { meta }),

  backlinks: (id) => request("GET", `/notes/${encodeURIComponent(id)}/backlinks`),

  createRelationship: (id, targetId, label = null) =>
    request("POST", `/notes/${encodeURIComponent(id)}/relationships`, {
      target_id: targetId,
      label,
    }),
};

// ── Folders ──────────────────────────────────────────────────────────────────
export const folders = {
  list: (vault_id = "") => request("GET", `/notes/folders${vault_id ? `?vault_id=${encodeURIComponent(vault_id)}` : ""}`),
  create: (name, parent_id = null, vault_id = null) =>
    request("POST", "/notes/folders", { name, parent_id, vault_id }),
  update: (id, data) =>
    request("PUT", `/notes/folders/${encodeURIComponent(id)}`, data),
  delete: (id) =>
    request("DELETE", `/notes/folders/${encodeURIComponent(id)}`),
};

// ── AI ───────────────────────────────────────────────────────────────────────
export const ai = {
  ask: (prompt, history = []) => request("POST", "/ai/ask", { prompt, history }),
  summarize: (text) => request("POST", "/ai/summarize", { text }),
  suggestTags: (text, existingTags = []) =>
    request("POST", "/ai/suggest-tags", { text, existing_tags: existingTags }),
  proposeLinks: (text, noteNames = []) =>
    request("POST", "/ai/propose-links", { text, note_names: noteNames }),
  usage: () => request("GET", "/ai/usage"),
};

// ── Dashboard ────────────────────────────────────────────────────────────────
export const dashboard = {
  stats: () => request("GET", "/dashboard/stats"),
  recent: () => request("GET", "/dashboard/recent"),
};

// ── Settings ─────────────────────────────────────────────────────────────────
export const settings = {
  get: () => request("GET", "/settings"),
  update: (data) => request("PUT", "/settings", data),
};

// ── AI key & quota settings ───────────────────────────────────────────────────
export const aiSettings = {
  get: () => request("GET", "/settings/ai"),
  saveKey: (api_key) => request("POST", "/settings/ai/key", { api_key }),
  removeKey: () => request("DELETE", "/settings/ai/key"),
  adminUsage: () => request("GET", "/admin/ai-usage"),
  adminSetLimit: (userId, monthly_request_limit) =>
    request("POST", `/admin/users/${userId}/ai-limit`, { monthly_request_limit }),
};

// ── Users (admin) ────────────────────────────────────────────────────────────
export const users = {
  list: () => request("GET", "/users"),
  get: (id) => request("GET", `/users/${id}`),
  updateRole: (id, roles) => request("PUT", `/users/${id}/roles`, { roles }),
  disable: (id) => request("POST", `/users/${id}/disable`),
  enable: (id) => request("POST", `/users/${id}/enable`),
  resetPassword: (id, newPw) =>
    request("POST", `/users/${id}/reset-password`, { new_password: newPw }),
};

// ── Invites (admin) ──────────────────────────────────────────────────────────
export const invites = {
  list: () => request("GET", "/invites"),
  generate: ({ ttl_days = 7, max_uses = 1 } = {}) => request("POST", "/invites", { ttl_days, max_uses }),
  revoke: (id) => request("DELETE", `/invites/${id}`),
};

export const vaults = {
  list: () => request("GET", "/vaults"),
  get: (id) => request("GET", `/vaults/${encodeURIComponent(id)}`),
  create: (data) => request("POST", "/vaults", data),
  update: (id, data) => request("PUT", `/vaults/${encodeURIComponent(id)}`, data),
  remove: (id) => request("DELETE", `/vaults/${encodeURIComponent(id)}`),
  exportZip: async (id) => {
    const headers = {};
    if (_token) headers["Authorization"] = `Bearer ${_token}`;
    const res = await fetch(`${BASE}/vaults/${encodeURIComponent(id)}/export`, { headers });
    if (!res.ok) throw new Error("Failed to export vault");
    return res.blob();
  },
  importZip: async (file, name = "") => {
    const headers = {};
    if (_token) headers["Authorization"] = `Bearer ${_token}`;
    const formData = new FormData();
    formData.append("file", file);
    if (name) formData.append("name", name);
    const res = await fetch(`${BASE}/vaults/import`, { method: "POST", headers, body: formData });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(err.detail || "Vault import failed");
    }
    return res.json();
  },
  updateBackup: (id, cron) => request("PUT", `/vaults/${encodeURIComponent(id)}/backup?cron=${encodeURIComponent(cron)}`),
};

export const groups = {
  list: (vault_id = "") => request("GET", `/groups${vault_id ? `?vault_id=${encodeURIComponent(vault_id)}` : ""}`),
  get: (id) => request("GET", `/groups/${encodeURIComponent(id)}`),
  create: (data) => request("POST", "/groups", data),
  update: (id, data) => request("PUT", `/groups/${encodeURIComponent(id)}`, data),
  remove: (id) => request("DELETE", `/groups/${encodeURIComponent(id)}`),
  addMember: (id, user_id, role = "player") =>
    request("POST", `/groups/${encodeURIComponent(id)}/members`, { user_id, role }),
  removeMember: (id, user_id) =>
    request("DELETE", `/groups/${encodeURIComponent(id)}/members/${encodeURIComponent(user_id)}`),
};

// ── Sessions ─────────────────────────────────────────────────────────────────
export const sessions = {
  list: (vaultId, skip = 0, limit = 50) => {
    const params = new URLSearchParams({ vault_id: vaultId, skip, limit });
    return request("GET", `/sessions?${params.toString()}`);
  },
  get: (id) => request("GET", `/sessions/${encodeURIComponent(id)}`),
  create: (data) => request("POST", "/sessions", data),
  update: (id, data) => request("PUT", `/sessions/${encodeURIComponent(id)}`, data),
  delete: (id) => request("DELETE", `/sessions/${encodeURIComponent(id)}`),
  generateRecap: (id) => request("POST", `/sessions/${encodeURIComponent(id)}/recap`),
};

// ── Characters ────────────────────────────────────────────────────────────────
export const characters = {
  list: (vaultId = "default", type = null) => {
    const params = new URLSearchParams({ vault_id: vaultId });
    if (type) params.set("type", type);
    return request("GET", `/characters?${params}`);
  },
  get: (id) => request("GET", `/characters/${id}`),
  create: (data) => request("POST", "/characters", data),
  update: (id, data) => request("PUT", `/characters/${id}`, data),
  delete: (id) => request("DELETE", `/characters/${id}`),
};

// ── Maps ─────────────────────────────────────────────────────────────────────
export const maps = {
  list: (vault_id = "default", type = null) => {
    const params = new URLSearchParams({ vault_id });
    if (type) params.set("type", type);
    return request("GET", `/maps?${params.toString()}`);
  },
  get: (id) => request("GET", `/maps/${encodeURIComponent(id)}`),
  create: (data) => request("POST", "/maps", data),
  update: (id, data) => request("PUT", `/maps/${encodeURIComponent(id)}`, data),
  delete: (id) => request("DELETE", `/maps/${encodeURIComponent(id)}`),
};

// ── Analytics ─────────────────────────────────────────────────────────────────
export const analytics = {
  summary: () => request("GET", "/admin/analytics/summary"),
  eventsByDay: () => request("GET", "/admin/analytics/events-by-day"),
  breakdown: () => request("GET", "/admin/analytics/breakdown"),
  errors: () => request("GET", "/admin/analytics/errors"),
  users: () => request("GET", "/admin/analytics/users"),
  getConsent: () => request("GET", "/settings/analytics"),
  setConsent: (consent) => request("POST", "/settings/analytics/consent", { consent }),
};

// ── Debug (admin) ─────────────────────────────────────────────────────────────
export const debug = {
  listCrashLogs: () => request("GET", "/debug/crash-logs"),
  getCrashLog: (filename) => request("GET", `/debug/crash-logs/${encodeURIComponent(filename)}`),
  deleteCrashLog: (filename) => request("DELETE", `/debug/crash-logs/${encodeURIComponent(filename)}`),
  getRuntimeLog: () => request("GET", "/debug/runtime-log"),
};

// ── Helpers ───────────────────────────────────────────────────────────────────
export function isRateLimitError(err) {
  return err?.message === "__RATE_LIMIT__";
}

export const RATE_LIMIT_MSG = "Rate limit reached — please wait a moment before trying again.";
