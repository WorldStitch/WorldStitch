import { useState } from 'react';
import SectionHeader from '@/components/SectionHeader';
import Card from '@/components/Card';
import AdminSettings from '@/components/settings/AdminSettings';
import DebugSettings from '@/components/settings/DebugSettings';
import AdminAnalyticsEmbed from './AdminAnalytics';
import WaitlistAdmin from './WaitlistAdmin';

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

// ── Placeholder panels (light stubs until full implementations land) ──────────

function AiUsagePanel() {
  return (
    <div>
      <h2 className="text-lg font-bold text-txt mb-2">AI Usage</h2>
      <p className="text-txt-muted text-sm">
        Per-user AI request usage and limit management are shown in User Management above.
        A dedicated standalone view is coming soon.
      </p>
    </div>
  );
}

function SupportPanel() {
  return (
    <div>
      <h2 className="text-lg font-bold text-txt mb-2">Reports &amp; Support</h2>
      <p className="text-txt-muted text-sm">
        User reports and moderation tools will appear here.
      </p>
    </div>
  );
}

function SystemSettingsPanel() {
  return (
    <div>
      <h2 className="text-lg font-bold text-txt mb-2">System Settings</h2>
      <p className="text-txt-muted text-sm">
        Platform-wide configuration (registration mode, feature flags, etc.) will appear here.
      </p>
    </div>
  );
}
