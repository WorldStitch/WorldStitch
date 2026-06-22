import clsx from 'clsx';
import {
  Home,
  PenLine,
  BookOpen,
  Scroll,
  User,
  Globe,
  Map,
  Layers,
  Settings,
  LogOut,
  ShieldCheck,
  Compass,
  Share2,
} from 'lucide-react';
import { useRealtime } from '@/context/RealtimeContext';

const ADMIN_ROLES = ['owner', 'admin', 'moderator'];

const Sidebar = ({ currentPath, onNavigate, onLogout, user, vaults = [], activeVaultId, onVaultChange }) => {
  const { onlineUsers, isConnected } = useRealtime();
  const canAccessAdmin = ADMIN_ROLES.includes(user?.system_role);
  const activeVaultName = vaults.find((v) => v.id === activeVaultId)?.name;

  const workspaceItems = [
    { icon: Home, label: 'Dashboard', path: '/' },
    { icon: Layers, label: 'Vaults', path: '/vaults' },
  ];

  const aiItems = [
    { icon: Compass, label: 'Explore', path: '/explore' },
    { icon: PenLine, label: 'Create', path: '/chat' },
  ];

  const contentItems = [
    { icon: BookOpen, label: 'Browse', path: '/browse' },
    { icon: User, label: 'Characters', path: '/characters' },
    { icon: Scroll, label: 'Sessions', path: '/sessions' },
    { icon: Map, label: 'Maps', path: '/maps' },
    { icon: Globe, label: 'Universe', path: '/universe' },
    { icon: Share2, label: 'Graph', path: '/graph' },
  ];

  return (
    <div className="w-[250px] bg-surface h-full flex flex-col border-r border-border-subtle overflow-hidden">
      {/* Logo Section */}
      <div className="px-4 py-6 border-b border-border-subtle">
        <h2 className="text-lg font-bold text-txt flex items-center gap-2">
          ⚡ WorldStitch
        </h2>
        <p className="text-xs text-txt-muted mt-2">Your world. Your story.</p>
        <div className="mt-4 space-y-2">
          <label className="block text-[11px] uppercase tracking-widest text-txt-muted font-bold">
            Active Vault
          </label>
          {activeVaultName && (
            <button
              onClick={() => onNavigate('/vaults')}
              className="w-full text-left text-sm font-medium text-accent truncate hover:underline"
              title={activeVaultName}
            >
              {activeVaultName}
            </button>
          )}
          <select
            value={activeVaultId || ''}
            onChange={(e) => onVaultChange?.(e.target.value)}
            className="w-full bg-elevated rounded-lg px-3 py-2 text-sm text-txt border border-border-subtle focus:border-accent focus:outline-none"
          >
            {!vaults.length && <option value="">No project selected</option>}
            {vaults.map((vault) => (
              <option key={vault.id} value={vault.id}>
                {vault.name}
              </option>
            ))}
          </select>
          <div className="flex items-center gap-1.5 mt-1">
            <span
              className={`inline-block w-2 h-2 rounded-full flex-shrink-0 ${isConnected ? 'bg-green-500' : 'bg-gray-400'}`}
              title={isConnected ? 'Connected' : 'Reconnecting…'}
            />
            <span className="text-xs text-txt-muted">
              {isConnected ? `${onlineUsers.length} online` : 'Reconnecting…'}
            </span>
          </div>
          {isConnected && onlineUsers.length > 0 && (
            <div className="mt-2 space-y-1">
              {onlineUsers.map((u) => (
                <div key={u.id} className="flex items-center gap-1.5">
                  <span className="inline-block w-2 h-2 rounded-full bg-green-500 flex-shrink-0" />
                  <span className="text-xs text-txt-muted truncate" title={u.email || u.username}>
                    {u.email || u.username}
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Navigation Section */}
      <div className="px-4 py-4 flex-1 overflow-y-auto min-h-0">
        <nav className="flex flex-col gap-1">
          <p className="uppercase text-[11px] tracking-widest text-txt-muted font-bold mb-1 px-1">
            Workspace
          </p>
          {workspaceItems.map((item) => {
            const Icon = item.icon;
            const isActive = currentPath === item.path;

            return (
              <button
                key={item.path}
                onClick={() => onNavigate(item.path)}
                className={clsx(
                  'flex items-center gap-3 rounded-xl px-4 py-2.5 transition-all text-left w-full',
                  isActive
                    ? 'bg-accent-soft text-accent font-semibold border-l-4 border-accent'
                    : 'text-txt-dim hover:bg-hover'
                )}
              >
                <Icon size={18} />
                <span>{item.label}</span>
              </button>
            );
          })}

          <p className="uppercase text-[11px] tracking-widest text-txt-muted font-bold mt-4 mb-1 px-1">
            AI
          </p>
          {aiItems.map((item) => {
            const Icon = item.icon;
            const isActive = currentPath === item.path;

            return (
              <button
                key={item.path}
                onClick={() => onNavigate(item.path)}
                className={clsx(
                  'flex items-center gap-3 rounded-xl px-4 py-2.5 transition-all text-left w-full',
                  isActive
                    ? 'bg-accent-soft text-accent font-semibold border-l-4 border-accent'
                    : 'text-txt-dim hover:bg-hover'
                )}
              >
                <Icon size={18} />
                <span>{item.label}</span>
              </button>
            );
          })}

          <p className="uppercase text-[11px] tracking-widest text-txt-muted font-bold mt-4 mb-1 px-1">
            Content
          </p>
          {contentItems.map((item) => {
            const Icon = item.icon;
            const isActive = currentPath === item.path;

            return (
              <button
                key={item.path}
                onClick={() => onNavigate(item.path)}
                className={clsx(
                  'flex items-center gap-3 rounded-xl px-4 py-2.5 transition-all text-left w-full',
                  isActive
                    ? 'bg-accent-soft text-accent font-semibold border-l-4 border-accent'
                    : 'text-txt-dim hover:bg-hover'
                )}
              >
                <Icon size={18} />
                <span>{item.label}</span>
              </button>
            );
          })}
        </nav>
      </div>

      {/* Bottom Section */}
      <div className="px-4 py-4 border-t border-border-subtle flex flex-col gap-2">
        {/* User info */}
        {user && (
          <div className="px-4 py-2 mb-1">
            <p className="text-txt text-sm font-medium truncate">{user.username}</p>
            <p className="text-txt-muted text-xs truncate">{user.email}</p>
          </div>
        )}

        <button
          onClick={() => onNavigate('/settings')}
          className={clsx(
            'flex items-center gap-3 rounded-xl px-4 py-3 transition-all text-left w-full',
            currentPath === '/settings'
              ? 'bg-accent-soft text-accent font-semibold border-l-4 border-accent'
              : 'text-txt-dim hover:bg-hover'
          )}
        >
          <Settings size={20} />
          <span>Settings</span>
        </button>

        {canAccessAdmin && (
          <button
            onClick={() => onNavigate('/admin')}
            className={clsx(
              'flex items-center gap-3 rounded-xl px-4 py-3 transition-all text-left w-full',
              currentPath.startsWith('/admin')
                ? 'bg-accent-soft text-accent font-semibold border-l-4 border-accent'
                : 'text-txt-dim hover:bg-hover'
            )}
          >
            <ShieldCheck size={20} />
            <span>Admin Panel</span>
          </button>
        )}

        <button
          onClick={onLogout}
          className="flex items-center gap-3 rounded-xl px-4 py-3 transition-all text-left w-full text-txt-dim hover:bg-hover"
        >
          <LogOut size={20} />
          <span>Logout</span>
        </button>
      </div>
    </div>
  );
};

export default Sidebar;
