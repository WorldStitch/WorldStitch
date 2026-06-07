import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import SectionHeader from '@/components/SectionHeader';
import Card from '@/components/Card';
import Button from '@/components/Button';
import AdminSettings from '@/components/settings/AdminSettings';
import DebugSettings from '@/components/settings/DebugSettings';
import AdminAnalyticsEmbed from './AdminAnalytics';
import WaitlistAdmin from './WaitlistAdmin';
import { analytics, settings } from '@/api';

const OWNER_ONLY   = ['owner'];
const ADMIN_ABOVE  = ['owner', 'admin'];
const MOD_ABOVE    = ['owner', 'admin', 'moderator'];

export default function AdminPanel({ user }) {
  const role = user?.system_role ?? '';
  const isOwner     = OWNER_ONLY.includes(role);
  const isAdmin     = ADMIN_ABOVE.includes(role);
  const isModerator = MOD_ABOVE.includes(role);

  const defaultTab = isAdmin ? 'users' : 'support';
  const [activeTab, setActiveTab] = useState(defaultTab);

  const NavItem = ({ id, label, allowed }) => {
    if (!allowed) return null;
    return (
      <button
        onClick={() => setActiveTab(id)}
        className={`w-full text-left px-4 py-2.5 rounded-lg transition font-medium ${
          activeTab === id ? 'bg-accent/10 text-accent' : 'text-txt hover:bg-hover'
        }`}
      >
        {label}
      </button>
    );
  };

  return (
    <div className="p-10 space-y-6 h-full">
      <SectionHeader
        title="🛡️ Admin Panel"
        subtitle={`Signed in as ${role} — restricted tools only.`}
      />

      <div className="flex gap-6 flex-1 overflow-hidden">
        {/* Left Nav */}
        <div className="w-52 shrink-0">
          <nav className="space-y-1">
            <p className="uppercase text-[11px] tracking-widest text-txt-muted font-bold px-4 pb-2 pt-1">
              Management
            </p>
            <NavItem id="users"     label="User Management"  allowed={isAdmin} />
            <NavItem id="waitlist"  label="Waitlist"         allowed={isAdmin} />
            <NavItem id="analytics" label="Analytics"        allowed={isAdmin} />
            <NavItem id="ai_usage"  label="AI Usage"         allowed={isAdmin} />
            <NavItem id="support"   label="Reports / Support" allowed={isModerator} />
            <p className="uppercase text-[11px] tracking-widest text-txt-muted font-bold px-4 pb-2 pt-4">
              System
            </p>
            <NavItem id="settings"  label="System Settings"  allowed={isOwner} />
            <NavItem id="debug"     label="Debug"            allowed={isOwner} />
          </nav>
        </div>

        {/* Content */}
        <Card className="flex-1 p-6 overflow-y-auto">
          {activeTab === 'users'     && isAdmin     && <AdminSettings />}
          {activeTab === 'waitlist'  && isAdmin     && <WaitlistAdmin />}
          {activeTab === 'analytics' && isAdmin     && <AdminAnalyticsEmbed embedded />}
          {activeTab === 'ai_usage'  && isAdmin     && <AiUsagePanel />}
          {activeTab === 'support'   && isModerator && <SupportPanel />}
          {activeTab === 'settings'  && isOwner     && <SystemSettingsPanel />}
          {activeTab === 'debug'     && isOwner     && <DebugSettings />}
        </Card>
      </div>
    </div>
  );
}

// ── AI Usage Panel ────────────────────────────────────────────────────────────

function AiUsagePanel() {
  const { data: summary, isLoading: loadingSummary } = useQuery({
    queryKey: ['admin-analytics-summary'],
    queryFn: analytics.summary,
    staleTime: 60_000,
  });

  const { data: userStats = [], isLoading: loadingUsers } = useQuery({
    queryKey: ['admin-analytics-users'],
    queryFn: analytics.users,
    staleTime: 60_000,
  });

  const totalAiReqs = summary?.ai_requests ?? 0;
  const totalCost = summary?.total_ai_cost_usd ?? 0;

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-lg font-bold text-txt mb-1">AI Usage</h2>
        <p className="text-txt-muted text-sm">Platform-wide AI activity for the last 30 days.</p>
      </div>

      {/* Summary cards */}
      <div className="grid grid-cols-2 gap-4">
        <div className="bg-elevated rounded-xl p-4">
          <p className="text-xs text-txt-muted uppercase tracking-widest font-bold mb-1">AI Requests</p>
          <p className="text-3xl font-bold text-txt">
            {loadingSummary ? '…' : totalAiReqs.toLocaleString()}
          </p>
          <p className="text-xs text-txt-muted mt-1">last 30 days</p>
        </div>
        <div className="bg-elevated rounded-xl p-4">
          <p className="text-xs text-txt-muted uppercase tracking-widest font-bold mb-1">Est. Cost</p>
          <p className="text-3xl font-bold text-txt">
            {loadingSummary ? '…' : `$${totalCost.toFixed(4)}`}
          </p>
          <p className="text-xs text-txt-muted mt-1">USD, last 30 days</p>
        </div>
      </div>

      {/* Per-user breakdown */}
      <div>
        <h3 className="text-sm font-semibold text-txt mb-3">Per-User AI Activity</h3>
        {loadingUsers ? (
          <p className="text-txt-muted text-sm">Loading…</p>
        ) : userStats.filter(u => u.ai_requests > 0).length === 0 ? (
          <p className="text-txt-muted text-sm">No AI activity recorded yet.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-txt-muted border-b border-border-subtle">
                  <th className="pb-2 font-medium">Username</th>
                  <th className="pb-2 font-medium text-right">AI Requests</th>
                  <th className="pb-2 font-medium text-right">Est. Cost</th>
                  <th className="pb-2 font-medium text-right">Consent</th>
                </tr>
              </thead>
              <tbody>
                {userStats
                  .filter(u => u.ai_requests > 0)
                  .sort((a, b) => b.ai_requests - a.ai_requests)
                  .map(u => (
                    <tr key={u.user_id} className="border-b border-border-subtle last:border-0">
                      <td className="py-2 text-txt truncate max-w-[200px]">{u.username}</td>
                      <td className="py-2 text-right text-txt">{u.ai_requests.toLocaleString()}</td>
                      <td className="py-2 text-right text-txt">${u.ai_cost_usd.toFixed(4)}</td>
                      <td className="py-2 text-right">
                        <span className={`px-2 py-0.5 rounded text-xs font-medium ${
                          u.consent ? 'bg-green-500/10 text-green-600' : 'bg-gray-500/10 text-txt-muted'
                        }`}>
                          {u.consent ? 'Yes' : 'No'}
                        </span>
                      </td>
                    </tr>
                  ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}

// ── Support / Reports Panel ───────────────────────────────────────────────────

function SupportPanel() {
  const { data: errors = [], isLoading } = useQuery({
    queryKey: ['admin-analytics-errors'],
    queryFn: analytics.errors,
    staleTime: 30_000,
  });

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-lg font-bold text-txt mb-1">Reports &amp; Support</h2>
        <p className="text-txt-muted text-sm">
          Recent server-side route errors — useful for diagnosing player-reported issues.
        </p>
      </div>

      <div>
        <h3 className="text-sm font-semibold text-txt mb-3">Recent Route Errors</h3>
        {isLoading ? (
          <p className="text-txt-muted text-sm">Loading…</p>
        ) : errors.length === 0 ? (
          <div className="bg-elevated rounded-xl p-4 text-center">
            <p className="text-txt-muted text-sm">No errors on record. The lore holds steady.</p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-txt-muted border-b border-border-subtle">
                  <th className="pb-2 font-medium">Timestamp</th>
                  <th className="pb-2 font-medium">Route</th>
                  <th className="pb-2 font-medium text-right">Status</th>
                </tr>
              </thead>
              <tbody>
                {errors.map(err => (
                  <tr key={err.id} className="border-b border-border-subtle last:border-0">
                    <td className="py-2 text-txt-muted text-xs">
                      {new Date(err.created_at).toLocaleString()}
                    </td>
                    <td className="py-2 font-mono text-xs text-txt">{err.route}</td>
                    <td className="py-2 text-right">
                      <span className="px-2 py-0.5 rounded text-xs bg-danger/10 text-danger font-medium">
                        {err.status_code}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}

// ── System Settings Panel ─────────────────────────────────────────────────────

const DISPLAY_SETTINGS = [
  { key: 'preferred_model',   label: 'Preferred AI Model',    type: 'text',   hint: 'e.g. gpt-4o, gpt-4o-mini' },
  { key: 'streaming_enabled', label: 'Streaming Responses',   type: 'toggle', hint: 'Stream AI replies token-by-token' },
  { key: 'ai_history_limit',  label: 'AI History Limit',      type: 'number', hint: 'Messages kept in AI context window' },
  { key: 'log_level',         label: 'Log Level',             type: 'select', hint: 'Server log verbosity', options: ['DEBUG', 'INFO', 'WARNING', 'ERROR'] },
  { key: 'compact_mode',      label: 'Compact Mode',          type: 'toggle', hint: 'Denser UI layout for all users' },
];

function SystemSettingsPanel() {
  const queryClient = useQueryClient();
  const { data: cfg, isLoading } = useQuery({
    queryKey: ['settings'],
    queryFn: settings.get,
    staleTime: 30_000,
  });

  const [draft, setDraft] = useState(null);

  const saveMutation = useMutation({
    mutationFn: (updates) => settings.update(updates),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['settings'] });
      setDraft(null);
      toast.success('Settings saved');
    },
    onError: () => toast.error('Failed to save settings'),
  });

  const current = draft ?? cfg ?? {};

  const setValue = (key, value) => {
    setDraft(prev => ({ ...(prev ?? cfg ?? {}), [key]: value }));
  };

  const handleSave = () => {
    if (!draft) return;
    saveMutation.mutate(draft);
  };

  const handleReset = () => setDraft(null);

  if (isLoading) {
    return <p className="text-txt-muted text-sm">Loading settings…</p>;
  }

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-lg font-bold text-txt mb-1">System Settings</h2>
        <p className="text-txt-muted text-sm">
          Platform-wide configuration. Changes apply to all users on this server.
        </p>
      </div>

      <div className="space-y-4">
        {DISPLAY_SETTINGS.map(({ key, label, type, hint, options }) => {
          const value = current[key];
          return (
            <div key={key} className="flex items-start justify-between gap-4 py-3 border-b border-border-subtle last:border-0">
              <div className="flex-1 min-w-0">
                <p className="text-sm font-medium text-txt">{label}</p>
                {hint && <p className="text-xs text-txt-muted mt-0.5">{hint}</p>}
              </div>
              <div className="shrink-0">
                {type === 'toggle' && (
                  <button
                    onClick={() => setValue(key, !value)}
                    className={`relative inline-flex h-5 w-9 items-center rounded-full transition-colors ${
                      value ? 'bg-accent' : 'bg-border-subtle'
                    }`}
                  >
                    <span className={`inline-block h-3.5 w-3.5 transform rounded-full bg-white transition-transform ${
                      value ? 'translate-x-4' : 'translate-x-0.5'
                    }`} />
                  </button>
                )}
                {type === 'text' && (
                  <input
                    type="text"
                    value={value ?? ''}
                    onChange={e => setValue(key, e.target.value)}
                    className="bg-elevated border border-border-subtle rounded-lg px-3 py-1.5 text-sm text-txt w-48 focus:outline-none focus:border-accent"
                  />
                )}
                {type === 'number' && (
                  <input
                    type="number"
                    value={value ?? 0}
                    min={0}
                    onChange={e => setValue(key, parseInt(e.target.value, 10) || 0)}
                    className="bg-elevated border border-border-subtle rounded-lg px-3 py-1.5 text-sm text-txt w-24 focus:outline-none focus:border-accent"
                  />
                )}
                {type === 'select' && (
                  <select
                    value={value ?? ''}
                    onChange={e => setValue(key, e.target.value)}
                    className="bg-elevated border border-border-subtle rounded-lg px-3 py-1.5 text-sm text-txt focus:outline-none focus:border-accent"
                  >
                    {(options ?? []).map(opt => (
                      <option key={opt} value={opt}>{opt}</option>
                    ))}
                  </select>
                )}
              </div>
            </div>
          );
        })}
      </div>

      {draft && (
        <div className="flex gap-3 pt-2">
          <Button
            variant="primary"
            size="sm"
            onClick={handleSave}
            disabled={saveMutation.isPending}
          >
            {saveMutation.isPending ? 'Saving…' : 'Save Changes'}
          </Button>
          <Button variant="ghost" size="sm" onClick={handleReset}>
            Discard
          </Button>
        </div>
      )}
    </div>
  );
}
