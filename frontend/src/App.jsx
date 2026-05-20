import { useState, useEffect } from "react";
import { Routes, Route, Navigate, useNavigate, useLocation } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import Sidebar from "./components/Sidebar";
import ErrorBoundary from "./components/ErrorBoundary";
import Dashboard from "./pages/Dashboard";
import Chat from "./pages/Chat";
import Browse from "./pages/Browse";
import Characters from "./pages/Characters";
import Create from "./pages/Create";
import Sessions from "./pages/Sessions";
import Universe from "./pages/Universe";
import Maps from "./pages/Maps";
import Vaults from "./pages/Vaults";
import Settings from "./pages/Settings";
import Login from "./pages/Login";
import NotFound from "./pages/NotFound";
import OwnerGroups from "./pages/OwnerGroups";
import OwnerInvites from "./pages/OwnerInvites";
import AdminAnalytics from "./pages/AdminAnalytics";
import AdminPanel from "./pages/AdminPanel";
import { auth, setToken, getToken, setRefreshToken, vaults } from "./api";
import { useSessionExpiry } from "./hooks/useSessionExpiry";
import { VaultProvider } from "./context/VaultContext";
import { RealtimeProvider } from "./context/RealtimeContext";

// ── Backend startup splash ────────────────────────────────────────────────────

function BackendStartupScreen({ status }) {
  const isError = status.state === "error";
  return (
    <div className="h-screen w-screen bg-base flex items-center justify-center p-8">
      <div className="text-center max-w-sm space-y-5">
        <div className="text-5xl">⚡</div>
        <h1 className="text-2xl font-bold text-txt">MythosEngine</h1>

        {!isError && (
          <>
            <p className="text-txt-muted text-sm">
              {status.message || "Starting server…"}
            </p>
            <div className="flex justify-center gap-1.5 pt-1">
              {[0, 150, 300].map((delay) => (
                <span
                  key={delay}
                  className="w-2 h-2 rounded-full bg-accent animate-bounce"
                  style={{ animationDelay: `${delay}ms` }}
                />
              ))}
            </div>
          </>
        )}

        {isError && (
          <div className="space-y-4 text-left">
            <div className="p-4 bg-danger/10 border border-danger/20 rounded-xl">
              <p className="text-danger text-sm font-semibold mb-1">
                Failed to start server
              </p>
              <pre className="text-txt-muted text-xs whitespace-pre-wrap font-mono leading-relaxed">
                {status.message}
              </pre>
            </div>
            <button
              onClick={() => window.location.reload()}
              className="w-full px-6 py-2.5 bg-accent text-white rounded-xl font-medium hover:opacity-90 transition text-sm"
            >
              Retry
            </button>
          </div>
        )}
      </div>
    </div>
  );
}

export default function App() {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);
  const [needsSetup, setNeedsSetup] = useState(false);
  // Backend startup state — only meaningful in Electron.
  const [backendStatus, setBackendStatus] = useState(() =>
    window.electronAPI ? { state: "starting", message: "Initializing…" } : { state: "ready" }
  );
  const [activeVaultId, setActiveVaultId] = useState(() => localStorage.getItem("me_active_vault") || "");
  // exp stored in memory only — not persisted to localStorage
  const [sessionExp, setSessionExp] = useState(null);
  const [expiryWarning, setExpiryWarning] = useState(null);
  const navigate = useNavigate();
  const location = useLocation();

  // Subscribe to backend startup status (Electron only).
  useEffect(() => {
    if (!window.electronAPI) return;
    // Fetch current state in case we mounted after the event fired.
    window.electronAPI.getBackendStatus().then(setBackendStatus);
    const unsub = window.electronAPI.onBackendStatus(setBackendStatus);
    return unsub;
  }, []);

  // Listen for 401 auth:logout events dispatched by api.js
  useEffect(() => {
    const handler = () => {
      setUser(null);
      navigate('/login');
    };
    window.addEventListener('auth:logout', handler);
    return () => window.removeEventListener('auth:logout', handler);
  }, [navigate]);

  // Try to restore session on mount, and check if first-run setup is needed.
  // Only runs once the backend is confirmed ready to avoid premature API calls.
  useEffect(() => {
    if (backendStatus.state !== "ready") return;
    const init = async () => {
      try {
        // Check if the database needs first-time setup
        const statusData = await auth.status();
        if (statusData.needs_setup) {
          setNeedsSetup(true);
          setLoading(false);
          return;
        }

        // Try to restore existing session
        const token = getToken();
        if (token) {
          try {
            const data = await auth.me();
            setUser(data.user);
            if (location.pathname === "/admin/groups") {
              navigate("/owner/groups", { replace: true });
            }
            // No exp for restored sessions — token expiry handled by server 401
          } catch {
            setToken(null);
          }
        }
      } catch (err) {
        console.error("Init failed:", err);
      } finally {
        setLoading(false);
      }
    };
    init();
  }, [backendStatus.state]);

  // Session expiry countdown (Item 56)
  useSessionExpiry(
    sessionExp,
    (mins) =>
      setExpiryWarning(
        `Your session expires in ${mins} minute${mins !== 1 ? "s" : ""}. Please save your work.`
      ),
    () => {
      setExpiryWarning(null);
      handleLogout();
    }
  );

  // exp comes from the login/setup/register response (Item 55)
  const handleLogin = (token, userData, exp = null) => {
    setToken(token);
    setUser(userData);
    setSessionExp(exp);
    setExpiryWarning(null);
    setNeedsSetup(false);
    navigate("/");
  };

  const handleLogout = () => {
    auth.logout().catch((err) => console.error('Logout failed:', err));
    setToken(null);
    setRefreshToken(null);
    setUser(null);
    setSessionExp(null);
    setExpiryWarning(null);
    navigate("/login");
  };

  const ADMIN_ROLES = ['owner', 'admin', 'moderator'];
  const isAdmin = ADMIN_ROLES.includes(user?.system_role);
  const { data: vaultList = [] } = useQuery({
    queryKey: ["vaults", user?.id],
    queryFn: vaults.list,
    enabled: !!user,
  });

  useEffect(() => {
    if (!vaultList.length) return;
    const stillExists = vaultList.some((vault) => vault.id === activeVaultId);
    const nextVaultId = stillExists ? activeVaultId : vaultList[0].id;
    if (nextVaultId && nextVaultId !== activeVaultId) setActiveVaultId(nextVaultId);
    if (nextVaultId) localStorage.setItem("me_active_vault", nextVaultId);
  }, [vaultList, activeVaultId]);

  // Show backend startup / error screen until the server is ready.
  if (backendStatus.state !== "ready") {
    return <BackendStartupScreen status={backendStatus} />;
  }

  if (loading) {
    return (
      <div className="h-screen bg-base flex items-center justify-center">
        <div className="text-center">
          <div className="text-3xl mb-3">⚡</div>
          <div className="text-txt-muted text-sm">Loading MythosEngine...</div>
        </div>
      </div>
    );
  }

  // Not logged in → show login (or setup if first run)
  if (!user) {
    return <Login onLogin={handleLogin} needsSetup={needsSetup} />;
  }

  return (
    <VaultProvider value={{ vaults: vaultList, activeVaultId, setActiveVaultId }}>
      <RealtimeProvider user={user} activeVaultId={activeVaultId}>
        <div className="h-screen flex bg-base overflow-hidden">
          {expiryWarning && (
            <div className="fixed top-0 left-0 right-0 z-50 bg-warning/90 text-txt text-center py-2 px-4 text-sm font-medium">
              {expiryWarning}
            </div>
          )}

          <Sidebar
            currentPath={location.pathname}
            onNavigate={(path) => navigate(path)}
            onLogout={handleLogout}
            user={user}
            vaults={vaultList}
            activeVaultId={activeVaultId}
            onVaultChange={(vaultId) => {
              setActiveVaultId(vaultId);
              localStorage.setItem("me_active_vault", vaultId);
            }}
          />

          <main className="flex-1 min-w-0 min-h-0 overflow-y-auto">
            <ErrorBoundary>
              <Routes>
                <Route path="/" element={<Dashboard user={user} />} />
                <Route path="/chat" element={<Chat />} />
                <Route path="/browse" element={<Browse user={user} />} />
                <Route path="/characters" element={<Characters />} />
                <Route path="/create" element={<Create />} />
                <Route path="/sessions" element={<Sessions user={user} />} />
                <Route path="/universe" element={<Universe />} />
                <Route path="/maps" element={<Maps />} />
                <Route path="/vaults" element={<Vaults user={user} />} />
                <Route path="/settings" element={<Settings user={user} />} />
                <Route path="/groups" element={<Navigate to="/vaults" replace />} />
                {isAdmin && <Route path="/owner/groups" element={<OwnerGroups />} />}
                {isAdmin && <Route path="/owner/invites" element={<OwnerInvites />} />}
                {isAdmin && <Route path="/admin" element={<AdminPanel user={user} />} />}
                {isAdmin && <Route path="/admin/analytics" element={<AdminAnalytics />} />}
                {isAdmin && <Route path="/admin/groups" element={<Navigate to="/owner/groups" replace />} />}
                {isAdmin && <Route path="/admin/invites" element={<Navigate to="/owner/invites" replace />} />}
                {isAdmin && <Route path="/invites" element={<Navigate to="/owner/invites" replace />} />}
                <Route path="*" element={<NotFound />} />
              </Routes>
            </ErrorBoundary>
          </main>
        </div>
      </RealtimeProvider>
    </VaultProvider>
  );
}
