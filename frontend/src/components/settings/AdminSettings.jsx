import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { toast } from 'sonner';
import Button from '@/components/Button';
import Badge from '@/components/Badge';
import { users, invites, dashboard, aiSettings } from '@/api';

const ROLE_ADMIN = 'admin';
const ROLE_MEMBER = 'member';

export default function AdminSettings() {
  const queryClient = useQueryClient();
  const [resetUserId, setResetUserId] = useState(null);
  const [resetNewPassword, setResetNewPassword] = useState('');
  const [editLimitUserId, setEditLimitUserId] = useState(null);
  const [editLimitValue, setEditLimitValue] = useState('');

  const { data: usersList = [], isLoading: usersLoading } = useQuery({
    queryKey: ['users'],
    queryFn: users.list,
  });

  const { data: invitesList = [], isLoading: invitesLoading } = useQuery({
    queryKey: ['invites'],
    queryFn: invites.list,
  });

  const { data: dashboardStats = {}, isLoading: statsLoading } = useQuery({
    queryKey: ['dashboard-stats'],
    queryFn: dashboard.stats,
  });

  const { data: aiUsageList = [], isLoading: aiUsageLoading } = useQuery({
    queryKey: ['admin-ai-usage'],
    queryFn: aiSettings.adminUsage,
    retry: false,
  });

  const setLimitMutation = useMutation({
    mutationFn: ({ userId, limit }) => aiSettings.adminSetLimit(userId, limit),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['admin-ai-usage'] });
      setEditLimitUserId(null);
      setEditLimitValue('');
      toast.success('Request limit updated');
    },
    onError: () => toast.error('Failed to update limit'),
  });

  const handleSetLimit = () => {
    const limit = parseInt(editLimitValue, 10);
    if (isNaN(limit) || limit < 0) { toast.error('Enter a valid number >= 0'); return; }
    setLimitMutation.mutate({ userId: editLimitUserId, limit });
  };

  const generateInviteMutation = useMutation({
    mutationFn: invites.generate,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['invites'] });
      toast.success('Invite code generated');
    },
    onError: () => toast.error('Failed to generate invite'),
  });

  const revokeInviteMutation = useMutation({
    mutationFn: invites.revoke,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['invites'] });
      toast.success('Invite revoked');
    },
    onError: () => toast.error('Failed to revoke invite'),
  });

  const disableUserMutation = useMutation({
    mutationFn: users.disable,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['users'] });
      toast.success('User disabled');
    },
    onError: () => toast.error('Failed to disable user'),
  });

  const enableUserMutation = useMutation({
    mutationFn: users.enable,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['users'] });
      toast.success('User enabled');
    },
    onError: () => toast.error('Failed to enable user'),
  });

  const resetPasswordMutation = useMutation({
    mutationFn: ({ id, password }) => users.resetPassword(id, password),
    onSuccess: () => {
      setResetUserId(null);
      setResetNewPassword('');
      toast.success('Password reset successfully');
    },
    onError: () => toast.error('Failed to reset password'),
  });

  const handleCopyInvite = (code) => {
    navigator.clipboard.writeText(code)
      .then(() => toast.success('Copied to clipboard!'))
      .catch(() => toast.error('Failed to copy'));
  };

  const handleResetPassword = () => {
    if (!resetUserId || !resetNewPassword.trim()) return;
    if (resetNewPassword.length < 8) { toast.error('Password must be at least 8 characters'); return; }
    resetPasswordMutation.mutate({ id: resetUserId, password: resetNewPassword });
  };

  const normalizeRoles = (u) => {
    if (Array.isArray(u.roles)) {
      const roles = u.roles.filter(Boolean);
      return roles.length ? roles : [ROLE_MEMBER];
    }
    if (typeof u.role === 'string' && u.role.trim()) return [u.role];
    return [ROLE_MEMBER];
  };

  const getUserRole = (u) => normalizeRoles(u)[0] || ROLE_MEMBER;

  const hasAdminRole = (u) => normalizeRoles(u).includes(ROLE_ADMIN);
  const isInviteActive = (inv) => inv.is_active && (!inv.expires_at || new Date(inv.expires_at) > new Date());

  const adminCount = usersList.filter((u) => hasAdminRole(u)).length;
  const activeUserCount = usersList.filter((u) => u.is_active !== false).length;
  const activeInvites = invitesList.filter(isInviteActive).length;

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
        <div className="bg-elevated rounded-xl p-3">
          <p className="text-xs text-txt-muted uppercase">Users</p>
          <p className="text-xl font-bold text-txt">{usersLoading ? '...' : usersList.length}</p>
          <p className="text-xs text-txt-muted">{usersLoading ? 'Loading…' : `${activeUserCount} active`}</p>
        </div>
        <div className="bg-elevated rounded-xl p-3">
          <p className="text-xs text-txt-muted uppercase">Admins</p>
          <p className="text-xl font-bold text-txt">{usersLoading ? '...' : adminCount}</p>
          <p className="text-xs text-txt-muted">Accounts with admin role</p>
        </div>
        <div className="bg-elevated rounded-xl p-3">
          <p className="text-xs text-txt-muted uppercase">Invite Codes</p>
          <p className="text-xl font-bold text-txt">{invitesLoading ? '...' : activeInvites}</p>
          <p className="text-xs text-txt-muted">Active and unexpired</p>
        </div>
        <div className="bg-elevated rounded-xl p-3">
          <p className="text-xs text-txt-muted uppercase">Notes</p>
          <p className="text-xl font-bold text-txt">{statsLoading ? '...' : (dashboardStats.notes ?? 0)}</p>
          <p className="text-xs text-txt-muted">Worldbuilding entries</p>
        </div>
        <div className="bg-elevated rounded-xl p-3">
          <p className="text-xs text-txt-muted uppercase">Characters</p>
          <p className="text-xl font-bold text-txt">{statsLoading ? '...' : (dashboardStats.characters ?? 0)}</p>
          <p className="text-xs text-txt-muted">Character records</p>
        </div>
        <div className="bg-elevated rounded-xl p-3">
          <p className="text-xs text-txt-muted uppercase">Sessions</p>
          <p className="text-xl font-bold text-txt">{statsLoading ? '...' : (dashboardStats.sessions ?? 0)}</p>
          <p className="text-xs text-txt-muted">Campaign session logs</p>
        </div>
      </div>

      {/* Invite Codes */}
      <div>
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-lg font-bold text-txt">Invite Codes</h3>
          <Button variant="primary" size="sm" onClick={() => generateInviteMutation.mutate()}>
            + Generate Invite
          </Button>
        </div>
        <p className="text-txt-muted text-sm mb-3">Share invite codes with players so they can create their own accounts.</p>

        {invitesLoading ? (
          <p className="text-txt-muted text-sm">Loading invites...</p>
        ) : invitesList.length === 0 ? (
          <div className="bg-elevated rounded-xl p-4 text-center">
            <p className="text-txt-muted text-sm">No invite codes yet. Generate one to share with a player.</p>
          </div>
        ) : (
          <div className="space-y-2">
            {invitesList.map((inv) => {
              const isActive = isInviteActive(inv);
              const isUsed = inv.used_by || (inv.use_count > 0 && inv.use_count >= (inv.max_uses || 1));
              const statusLabel = isUsed ? 'used' : isActive ? 'active' : 'expired';
              const statusVariant = isUsed ? 'disabled' : isActive ? 'active' : 'expired';

              return (
                <div key={inv.id || inv.code} className="flex items-center gap-3 bg-elevated rounded-xl px-4 py-3">
                  <code className="text-txt font-mono text-sm flex-1 select-all">{inv.code}</code>
                  <Badge label={statusLabel} variant={statusVariant} />
                  {isActive && !isUsed && (
                    <>
                      <Button variant="secondary" size="sm" onClick={() => handleCopyInvite(inv.code)}>Copy</Button>
                      <Button variant="danger" size="sm" onClick={() => revokeInviteMutation.mutate(inv.id)}>Revoke</Button>
                    </>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* AI Usage Table */}
      <div className="border-t border-txt-muted/20 pt-6">
        <h3 className="text-lg font-bold text-txt mb-4">AI Usage This Month</h3>
        <p className="text-txt-muted text-sm mb-3">
          Users on the shared server key have a monthly request limit. Users with a personal key are unlimited.
        </p>

        {editLimitUserId && (
          <div className="bg-elevated rounded-xl p-4 mb-4 flex items-end gap-3">
            <div className="flex-1">
              <label className="block text-txt-muted text-xs mb-1 font-medium">
                New monthly limit for {aiUsageList.find((r) => r.user_id === editLimitUserId)?.username || editLimitUserId}
              </label>
              <input
                type="number"
                min={0}
                value={editLimitValue}
                onChange={(e) => setEditLimitValue(e.target.value)}
                placeholder="e.g. 100"
                className="w-full bg-card rounded-lg px-3 py-2 text-sm text-txt border border-transparent focus:border-accent focus:outline-none"
              />
            </div>
            <Button variant="primary" size="sm" onClick={handleSetLimit} disabled={setLimitMutation.isPending}>
              Save
            </Button>
            <Button variant="ghost" size="sm" onClick={() => { setEditLimitUserId(null); setEditLimitValue(''); }}>
              Cancel
            </Button>
          </div>
        )}

        {aiUsageLoading ? (
          <p className="text-txt-muted text-sm">Loading usage…</p>
        ) : aiUsageList.length === 0 ? (
          <div className="bg-elevated rounded-xl p-4 text-center">
            <p className="text-txt-muted text-sm">No AI usage records yet.</p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-txt-muted/20">
                  <th className="text-left py-3 px-4 text-txt-muted font-medium">User</th>
                  <th className="text-left py-3 px-4 text-txt-muted font-medium">Key</th>
                  <th className="text-left py-3 px-4 text-txt-muted font-medium">Requests</th>
                  <th className="text-left py-3 px-4 text-txt-muted font-medium">Limit</th>
                  <th className="text-left py-3 px-4 text-txt-muted font-medium">Actions</th>
                </tr>
              </thead>
              <tbody>
                {aiUsageList.map((row) => {
                  const pct = row.monthly_request_limit > 0
                    ? Math.min(100, (row.requests_this_month / row.monthly_request_limit) * 100)
                    : 0;
                  return (
                    <tr key={row.user_id} className="border-b border-txt-muted/10 hover:bg-hover transition">
                      <td className="py-3 px-4 text-txt font-medium">
                        {row.username}
                        {row.email && <span className="text-txt-muted font-normal ml-1">({row.email})</span>}
                      </td>
                      <td className="py-3 px-4">
                        <Badge
                          label={row.has_personal_key ? 'personal' : 'server'}
                          variant={row.has_personal_key ? 'active' : 'member'}
                        />
                      </td>
                      <td className="py-3 px-4">
                        {row.has_personal_key ? (
                          <span className="text-txt-muted text-xs">unlimited</span>
                        ) : (
                          <div className="flex items-center gap-2">
                            <div className="w-20 bg-card rounded-full h-1.5 overflow-hidden">
                              <div
                                className={`h-1.5 rounded-full transition-all ${pct >= 90 ? 'bg-red-400' : 'bg-accent'}`}
                                style={{ width: `${pct}%` }}
                              />
                            </div>
                            <span className="text-txt text-xs">{row.requests_this_month}</span>
                          </div>
                        )}
                      </td>
                      <td className="py-3 px-4 text-txt">
                        {row.has_personal_key ? '—' : row.monthly_request_limit}
                      </td>
                      <td className="py-3 px-4">
                        {!row.has_personal_key && (
                          <Button
                            variant="secondary"
                            size="sm"
                            onClick={() => {
                              setEditLimitUserId(row.user_id);
                              setEditLimitValue(String(row.monthly_request_limit));
                            }}
                          >
                            Edit Limit
                          </Button>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Users Table */}
      <div className="border-t border-txt-muted/20 pt-6">
        <h3 className="text-lg font-bold text-txt mb-4">Manage Users</h3>

        {resetUserId && (
          <div className="bg-elevated rounded-xl p-4 mb-4 flex items-end gap-3">
            <div className="flex-1">
              <label className="block text-txt-muted text-xs mb-1 font-medium">
                New password for {usersList.find((u) => u.id === resetUserId)?.username || 'user'}
              </label>
              <input
                type="text"
                value={resetNewPassword}
                onChange={(e) => setResetNewPassword(e.target.value)}
                placeholder="Min 8 characters"
                className="w-full bg-card rounded-lg px-3 py-2 text-sm text-txt border border-transparent focus:border-accent focus:outline-none"
              />
            </div>
            <Button variant="primary" size="sm" onClick={handleResetPassword}>Reset</Button>
            <Button variant="ghost" size="sm" onClick={() => { setResetUserId(null); setResetNewPassword(''); }}>Cancel</Button>
          </div>
        )}

        {usersLoading ? (
          <p className="text-txt-muted text-sm">Loading users...</p>
        ) : usersList.length === 0 ? (
          <p className="text-txt-muted text-sm">No users found</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-txt-muted/20">
                  <th className="text-left py-3 px-4 text-txt-muted font-medium">User</th>
                  <th className="text-left py-3 px-4 text-txt-muted font-medium">Email</th>
                  <th className="text-left py-3 px-4 text-txt-muted font-medium">Role</th>
                  <th className="text-left py-3 px-4 text-txt-muted font-medium">Status</th>
                  <th className="text-left py-3 px-4 text-txt-muted font-medium">Actions</th>
                </tr>
              </thead>
              <tbody>
                {usersList.map((u) => (
                  <tr key={u.id} className="border-b border-txt-muted/10 hover:bg-hover transition">
                    <td className="py-3 px-4 text-txt font-medium">{u.username}</td>
                    <td className="py-3 px-4 text-txt-secondary">{u.email}</td>
                    <td className="py-3 px-4">
                      <Badge label={getUserRole(u)} variant={getUserRole(u) === ROLE_ADMIN ? 'admin' : 'player'} />
                    </td>
                    <td className="py-3 px-4">
                      <Badge
                        label={u.is_active !== false ? 'active' : 'disabled'}
                        variant={u.is_active !== false ? 'active' : 'disabled'}
                      />
                    </td>
                    <td className="py-3 px-4 space-x-1">
                      <Button variant="secondary" size="sm" onClick={() => { setResetUserId(u.id); setResetNewPassword(''); }}>
                        Reset PW
                      </Button>
                      {u.is_active !== false ? (
                        <Button variant="danger" size="sm" onClick={() => disableUserMutation.mutate(u.id)}>Disable</Button>
                      ) : (
                        <Button variant="success" size="sm" onClick={() => enableUserMutation.mutate(u.id)}>Enable</Button>
                      )}
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
