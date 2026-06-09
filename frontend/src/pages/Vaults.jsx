import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { Layers, Plus, Globe, Copy, Check, Trash2, X, Eye, EyeOff, Mail, RefreshCw, Ban, Users, ChevronDown, UserMinus } from 'lucide-react';
import Button from '@/components/Button';
import Input, { TextArea } from '@/components/Input';
import { vaults as vaultsApi, vaultInvites as vaultInvitesApi, vaultMembers as vaultMembersApi } from '@/api';
import { useVault } from '@/context/VaultContext';

const VAULT_TYPE_OPTIONS = [
  { value: 'worldbuilding', label: 'World Building' },
  { value: 'tabletop', label: 'Tabletop RPG' },
  { value: 'video_game', label: 'Video Game' },
  { value: 'novel', label: 'Novel / Story' },
  { value: 'film', label: 'Film / TV' },
  { value: 'custom', label: 'Custom' },
];

const VAULT_ROLES = ['owner', 'admin', 'editor', 'viewer', 'player'];

const ROLE_COLORS = {
  owner:  'bg-yellow-500/15 text-yellow-400 border-yellow-500/30',
  admin:  'bg-red-500/15 text-red-400 border-red-500/30',
  editor: 'bg-blue-500/15 text-blue-400 border-blue-500/30',
  viewer: 'bg-zinc-500/15 text-zinc-400 border-zinc-500/30',
  player: 'bg-green-500/15 text-green-400 border-green-500/30',
};

function RoleBadge({ role }) {
  return (
    <span className={`text-xs px-2 py-0.5 rounded-full border font-medium capitalize ${ROLE_COLORS[role] ?? ROLE_COLORS.viewer}`}>
      {role}
    </span>
  );
}

function MemberInitials({ username }) {
  const initials = (username || '?').slice(0, 2).toUpperCase();
  return (
    <div className="w-8 h-8 rounded-full bg-accent/20 text-accent flex items-center justify-center text-xs font-bold flex-shrink-0">
      {initials}
    </div>
  );
}

function MembersPanel({ members, vaultOwnerId, currentUser, canManage, onChangeRole, onRemove }) {
  return (
    <div className="space-y-4 max-w-lg">
      <div className="flex items-center gap-2 mb-1">
        <Users size={16} className="text-txt-muted" />
        <h3 className="text-sm font-semibold text-txt">Members of the Realm</h3>
        <span className="text-xs text-txt-muted">({members.length})</span>
      </div>

      {members.length === 0 ? (
        <p className="text-txt-muted text-sm italic">No members yet.</p>
      ) : (
        <div className="space-y-2">
          {members.map((m) => {
            const isOwner = m.vault_role === 'owner' || m.user_id === vaultOwnerId;
            const isSelf = m.user_id === currentUser?.id;
            return (
              <div
                key={m.user_id}
                className="flex items-center gap-3 bg-elevated rounded-xl px-4 py-3"
              >
                <MemberInitials username={m.username ?? m.email} />
                <div className="flex-1 min-w-0">
                  <div className="text-sm font-medium text-txt truncate">
                    {m.username ?? m.email ?? m.user_id}
                    {isSelf && <span className="ml-1.5 text-[10px] text-txt-muted">(you)</span>}
                  </div>
                  {m.email && m.username && (
                    <div className="text-xs text-txt-muted truncate">{m.email}</div>
                  )}
                </div>
                {canManage && !isOwner ? (
                  <div className="flex items-center gap-2 flex-shrink-0">
                    <select
                      value={m.vault_role}
                      onChange={(e) => onChangeRole(m.user_id, e.target.value)}
                      className="text-xs bg-surface border border-border-subtle rounded-lg px-2 py-1 text-txt focus:outline-none focus:border-accent"
                    >
                      {VAULT_ROLES.filter(r => r !== 'owner').map(r => (
                        <option key={r} value={r} className="capitalize">{r}</option>
                      ))}
                    </select>
                    <button
                      onClick={() => onRemove(m.user_id)}
                      className="text-txt-muted hover:text-danger transition-colors p-1"
                      title="Remove member"
                    >
                      <UserMinus size={14} />
                    </button>
                  </div>
                ) : (
                  <RoleBadge role={m.vault_role} />
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

function VaultDetailPanel({ vault, user, onRefresh, onDelete }) {
  const [tab, setTab] = useState('overview');
  const [editName, setEditName] = useState(vault.name);
  const [editDesc, setEditDesc] = useState(vault.description || '');
  const [editVaultType, setEditVaultType] = useState(vault.vault_type || 'worldbuilding');
  const [inviteEmail, setInviteEmail] = useState('');
  const [copied, setCopied] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [vaultAiKey, setVaultAiKey] = useState('');
  const [showVaultKey, setShowVaultKey] = useState(false);

  const isPlatformAdmin = ['owner', 'admin'].includes(user?.system_role);
  const isOwner = vault.owner_id === user?.id;
  const canInvite = isOwner || isPlatformAdmin;
  const canManageAiKey = isOwner || isPlatformAdmin;

  const updateMutation = useMutation({
    mutationFn: (data) => vaultsApi.update(vault.id, data),
    onSuccess: () => { onRefresh(); toast.success('Vault updated'); },
    onError: (err) => toast.error(err.message),
  });

  const deleteMutation = useMutation({
    mutationFn: () => vaultsApi.remove(vault.id),
    onSuccess: () => { onRefresh(); onDelete(); toast.success('Vault deleted'); },
    onError: (err) => toast.error(err.message),
  });

  const qc = useQueryClient();

  const inviteMutation = useMutation({
    mutationFn: (email) => vaultInvitesApi.send(vault.id, email),
    onSuccess: () => {
      setInviteEmail('');
      toast.success('Invite sent!');
      qc.invalidateQueries({ queryKey: ['vault-invites', vault.id] });
    },
    onError: (err) => toast.error(err.message),
  });

  const revokeInviteMutation = useMutation({
    mutationFn: (inviteId) => vaultInvitesApi.revoke(vault.id, inviteId),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['vault-invites', vault.id] }),
    onError: (err) => toast.error(err.message),
  });

  const resendInviteMutation = useMutation({
    mutationFn: (inviteId) => vaultInvitesApi.resend(vault.id, inviteId),
    onSuccess: () => toast.success('Invite resent'),
    onError: (err) => toast.error(err.message),
  });

  const { data: pendingInvites = [] } = useQuery({
    queryKey: ['vault-invites', vault.id],
    queryFn: () => vaultInvitesApi.list(vault.id),
    enabled: canInvite,
  });

  const { data: membersList = [], refetch: refetchMembers } = useQuery({
    queryKey: ['vault-members', vault.id],
    queryFn: () => vaultMembersApi.list(vault.id),
  });

  const changeRoleMutation = useMutation({
    mutationFn: ({ userId, vault_role }) => vaultMembersApi.updateRole(vault.id, userId, vault_role),
    onSuccess: () => { refetchMembers(); toast.success('Role updated'); },
    onError: (err) => toast.error(err.message),
  });

  const removeMemberMutation = useMutation({
    mutationFn: (userId) => vaultMembersApi.remove(vault.id, userId),
    onSuccess: () => { refetchMembers(); toast.success('Member removed'); },
    onError: (err) => toast.error(err.message),
  });

  const saveVaultKeyMutation = useMutation({
    mutationFn: () => vaultsApi.saveAiKey(vault.id, vaultAiKey.trim()),
    onSuccess: () => {
      setVaultAiKey('');
      onRefresh();
      toast.success('Vault AI key saved');
    },
    onError: (err) => toast.error(err.message || 'Failed to save vault key'),
  });

  const removeVaultKeyMutation = useMutation({
    mutationFn: () => vaultsApi.removeAiKey(vault.id),
    onSuccess: () => { onRefresh(); toast.success('Vault AI key removed'); },
    onError: (err) => toast.error(err.message || 'Failed to remove vault key'),
  });

  const setAiSharingMutation = useMutation({
    mutationFn: (shared) => vaultsApi.setAiSharing(vault.id, shared),
    onSuccess: () => { onRefresh(); },
    onError: (err) => toast.error(err.message || 'Failed to update sharing'),
  });

  const handleSave = () => {
    const payload = {};
    const trimmedName = editName.trim();
    if (trimmedName && trimmedName !== vault.name) payload.name = trimmedName;
    if (editDesc !== (vault.description || '')) payload.description = editDesc;
    if (editVaultType !== (vault.vault_type || 'worldbuilding')) payload.vault_type = editVaultType;
    if (!Object.keys(payload).length) { toast('No changes to save'); return; }
    updateMutation.mutate(payload);
  };

  const handleExport = async () => {
    try {
      const blob = await vaultsApi.exportZip(vault.id);
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `${vault.name.replace(/\s+/g, '_')}.zip`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (err) {
      toast.error(err.message);
    }
  };

  const handleCopyLink = (token) => {
    // HashRouter: path lives after '#'
    const url = `${window.location.origin}/#/invite?token=${token}`;
    navigator.clipboard.writeText(url);
    setCopied(token);
    setTimeout(() => setCopied(false), 2000);
  };

  const handleSaveVaultKey = () => {
    const trimmed = vaultAiKey.trim();
    if (!trimmed.startsWith('sk-')) {
      toast.error("API key must start with 'sk-'");
      return;
    }
    saveVaultKeyMutation.mutate();
  };

  return (
    <div className="flex flex-col h-full">
      <div className="px-6 py-5 border-b border-border-subtle">
        <div className="flex items-center gap-2">
          <Layers size={20} className="text-accent" />
          <h2 className="text-xl font-bold text-txt">{vault.name}</h2>
        </div>
        {vault.description && (
          <p className="text-txt-muted text-sm mt-1">{vault.description}</p>
        )}
      </div>

      <div className="flex gap-1 px-6 pt-4 border-b border-border-subtle">
        {['overview', 'members', 'access', 'settings'].map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`px-4 py-2 text-sm font-medium capitalize rounded-t-lg transition-colors ${
              tab === t
                ? 'bg-elevated text-accent border-b-2 border-accent'
                : 'text-txt-muted hover:text-txt'
            }`}
          >
            {t}
          </button>
        ))}
      </div>

      <div className="flex-1 overflow-y-auto p-6">
        {tab === 'overview' && (
          <div className="space-y-4 max-w-lg">
            <Input
              label="Vault Name"
              value={editName}
              onChange={(e) => setEditName(e.target.value)}
            />
            <TextArea
              label="Description"
              value={editDesc}
              onChange={(e) => setEditDesc(e.target.value)}
              placeholder="Describe this vault..."
            />
            <div>
              <label className="block text-xs font-semibold text-txt-muted uppercase tracking-wider mb-1.5">
                Vault Type
              </label>
              <select
                value={editVaultType}
                onChange={(e) => setEditVaultType(e.target.value)}
                className="w-full bg-surface border border-border-subtle rounded-lg px-3 py-2 text-txt text-sm focus:outline-none focus:border-accent"
              >
                {VAULT_TYPE_OPTIONS.map((opt) => (
                  <option key={opt.value} value={opt.value}>{opt.label}</option>
                ))}
              </select>
              <p className="text-xs text-txt-muted mt-1">
                Controls the terminology used throughout the UI for this vault.
              </p>
            </div>
            <div className="pt-1">
              <Button onClick={handleSave} disabled={updateMutation.isPending}>
                Save
              </Button>
            </div>
            <div className="pt-4 text-xs text-txt-muted space-y-1">
              <div>Members: {membersList.length || '—'}</div>
              {vault.created_at && (
                <div>Created: {new Date(vault.created_at).toLocaleDateString()}</div>
              )}
            </div>
          </div>
        )}

        {tab === 'members' && (
          <MembersPanel
            members={membersList}
            vaultOwnerId={vault.owner_id}
            currentUser={user}
            canManage={isOwner || isPlatformAdmin}
            onChangeRole={(userId, vault_role) => changeRoleMutation.mutate({ userId, vault_role })}
            onRemove={(userId) => removeMemberMutation.mutate(userId)}
          />
        )}

        {tab === 'access' && (
          <div className="space-y-6 max-w-lg">
            <div>
              <h3 className="text-sm font-semibold text-txt mb-3">Group Permissions</h3>
              {vault.permissions && Object.keys(vault.permissions).length > 0 ? (
                <div className="space-y-2">
                  {Object.entries(vault.permissions).map(([groupId, level]) => (
                    <div
                      key={groupId}
                      className="flex items-center justify-between bg-elevated rounded-xl px-4 py-2 text-sm"
                    >
                      <span className="text-txt-muted font-mono text-xs">{groupId}</span>
                      <span className="text-accent font-medium capitalize">{level}</span>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="text-txt-muted text-sm italic">No group permissions configured.</p>
              )}
            </div>

            {canInvite && (
              <div>
                <h3 className="text-sm font-semibold text-txt mb-3">Invite by Email</h3>
                <div className="flex gap-2">
                  <input
                    type="email"
                    value={inviteEmail}
                    onChange={(e) => setInviteEmail(e.target.value)}
                    placeholder="collaborator@example.com"
                    className="flex-1 bg-surface border border-border-subtle rounded-lg px-3 py-2 text-txt text-sm focus:outline-none focus:border-accent"
                    onKeyDown={(e) => {
                      if (e.key === 'Enter' && inviteEmail.trim()) inviteMutation.mutate(inviteEmail.trim());
                    }}
                  />
                  <Button
                    variant="primary"
                    size="sm"
                    onClick={() => inviteMutation.mutate(inviteEmail.trim())}
                    disabled={!inviteEmail.trim() || inviteMutation.isPending}
                  >
                    <Mail size={14} className="mr-1.5" />
                    Invite
                  </Button>
                </div>
                <p className="text-xs text-txt-muted mt-1.5">
                  Sends an email with a link to join this vault. Expires in 7 days.
                </p>

                {pendingInvites.length > 0 && (
                  <div className="mt-4">
                    <p className="text-xs font-semibold text-txt-muted uppercase tracking-wider mb-2">Pending &amp; Sent</p>
                    <div className="space-y-2">
                      {pendingInvites.map((inv) => (
                        <div
                          key={inv.id}
                          className="flex items-center gap-2 bg-surface rounded-xl px-3 py-2.5 text-sm"
                        >
                          <div className="flex-1 min-w-0">
                            <p className="text-txt truncate">{inv.email}</p>
                            <p className="text-xs text-txt-muted capitalize">{inv.status}</p>
                          </div>
                          {inv.status === 'pending' && (
                            <>
                              <button
                                onClick={() => inv.token && handleCopyLink(inv.token)}
                                className="text-txt-muted hover:text-txt transition-colors flex-shrink-0"
                                title="Copy invite link"
                              >
                                {copied === inv.token ? (
                                  <Check size={14} className="text-green-500" />
                                ) : (
                                  <Copy size={14} />
                                )}
                              </button>
                              <button
                                onClick={() => resendInviteMutation.mutate(inv.id)}
                                disabled={resendInviteMutation.isPending}
                                className="text-txt-muted hover:text-accent transition-colors flex-shrink-0"
                                title="Resend email"
                              >
                                <RefreshCw size={14} />
                              </button>
                              <button
                                onClick={() => revokeInviteMutation.mutate(inv.id)}
                                disabled={revokeInviteMutation.isPending}
                                className="text-txt-muted hover:text-danger transition-colors flex-shrink-0"
                                title="Revoke invite"
                              >
                                <Ban size={14} />
                              </button>
                            </>
                          )}
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>
        )}

        {tab === 'settings' && (
          <div className="space-y-6 max-w-lg">

            {/* AI Key Section */}
            <div>
              <h3 className="text-sm font-semibold text-txt mb-1">AI Key</h3>
              <p className="text-xs text-txt-muted mb-3">
                Set an OpenAI key for this vault. When sharing is on, all vault members
                can use AI features without their own key — you are billed for their usage.
              </p>

              {vault.has_ai_key ? (
                <div className="bg-elevated rounded-xl p-4 flex items-center justify-between gap-4 mb-3">
                  <div>
                    <p className="text-sm font-medium text-txt">Vault AI key is set</p>
                    <p className="text-xs text-txt-muted mt-0.5">Encrypted at rest.</p>
                  </div>
                  {canManageAiKey && (
                    <Button
                      variant="danger"
                      size="sm"
                      onClick={() => removeVaultKeyMutation.mutate()}
                      disabled={removeVaultKeyMutation.isPending}
                    >
                      Remove
                    </Button>
                  )}
                </div>
              ) : (
                canManageAiKey && (
                  <div className="flex gap-2 mb-3">
                    <div className="relative flex-1">
                      <input
                        type={showVaultKey ? 'text' : 'password'}
                        value={vaultAiKey}
                        onChange={(e) => setVaultAiKey(e.target.value)}
                        placeholder="sk-..."
                        className="w-full bg-elevated rounded-xl px-4 py-2.5 text-sm text-txt border-2 border-transparent focus:border-accent focus:outline-none transition pr-10"
                      />
                      <button
                        type="button"
                        onClick={() => setShowVaultKey((v) => !v)}
                        className="absolute right-3 top-1/2 -translate-y-1/2 text-txt-muted hover:text-txt transition"
                      >
                        {showVaultKey ? <EyeOff size={14} /> : <Eye size={14} />}
                      </button>
                    </div>
                    <Button
                      variant="primary"
                      size="sm"
                      onClick={handleSaveVaultKey}
                      disabled={!vaultAiKey.trim() || saveVaultKeyMutation.isPending}
                    >
                      Save key
                    </Button>
                  </div>
                )
              )}

              {vault.has_ai_key && canManageAiKey && (
                <div className="rounded-xl border border-border-subtle p-4">
                  <div className="flex items-center justify-between gap-4">
                    <div>
                      <p className="text-sm font-medium text-txt">Share key with vault members</p>
                      <p className="text-xs text-txt-muted mt-0.5">
                        Members can use AI features without their own key.
                      </p>
                    </div>
                    <label className="relative inline-flex items-center cursor-pointer shrink-0">
                      <input
                        type="checkbox"
                        checked={!!vault.ai_key_shared}
                        onChange={(e) => setAiSharingMutation.mutate(e.target.checked)}
                        disabled={setAiSharingMutation.isPending}
                        className="sr-only peer"
                      />
                      <div className="w-11 h-6 bg-elevated rounded-full peer peer-checked:bg-accent transition-colors" />
                      <div className="absolute left-0.5 top-0.5 w-5 h-5 bg-white rounded-full shadow transition-transform peer-checked:translate-x-5" />
                    </label>
                  </div>
                  {vault.ai_key_shared && (
                    <p className="text-xs text-amber-600 dark:text-amber-400 mt-3 bg-amber-50 dark:bg-amber-900/20 rounded-lg px-3 py-2">
                      All members of this vault can use your OpenAI key for AI features. You will be billed for their usage.
                    </p>
                  )}
                </div>
              )}
            </div>

            <div className="border-t border-border-subtle" />

            {/* Export */}
            <div>
              <h3 className="text-sm font-semibold text-txt mb-2">Export</h3>
              <p className="text-txt-muted text-sm mb-3">Download this vault as a ZIP archive.</p>
              <Button variant="secondary" onClick={handleExport}>
                Export Vault
              </Button>
            </div>

            <div className="border-t border-border-subtle pt-6">
              <h3 className="text-sm font-semibold text-danger mb-2">Danger Zone</h3>
              {!confirmDelete ? (
                <Button variant="danger" onClick={() => setConfirmDelete(true)}>
                  <Trash2 size={14} className="mr-1.5 inline" />
                  Delete Vault
                </Button>
              ) : (
                <div className="space-y-3">
                  <p className="text-sm text-danger font-medium">Are you sure? This cannot be undone.</p>
                  <div className="flex gap-2">
                    <Button
                      variant="danger"
                      onClick={() => deleteMutation.mutate()}
                      disabled={deleteMutation.isPending}
                    >
                      <Check size={14} className="mr-1.5 inline" />
                      Yes, delete
                    </Button>
                    <Button variant="secondary" onClick={() => setConfirmDelete(false)}>
                      <X size={14} className="mr-1.5 inline" />
                      Cancel
                    </Button>
                  </div>
                </div>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

export default function Vaults({ user }) {
  const qc = useQueryClient();
  const { activeVaultId, setActiveVaultId } = useVault();
  const [exploreAll, setExploreAll] = useState(false);
  const [selectedVaultId, setSelectedVaultId] = useState(null);
  const [showNewVault, setShowNewVault] = useState(false);
  const [newName, setNewName] = useState('');
  const [newDesc, setNewDesc] = useState('');
  const [newVaultType, setNewVaultType] = useState('worldbuilding');

  const isPlatformAdmin = ['owner', 'admin'].includes(user?.system_role);

  const { data: vaultList = [] } = useQuery({
    queryKey: ['vaults-page', exploreAll],
    queryFn: exploreAll ? vaultsApi.listAll : vaultsApi.list,
  });

  const effectiveSelected =
    vaultList.find((v) => v.id === selectedVaultId) ||
    vaultList.find((v) => v.id === activeVaultId) ||
    vaultList[0] ||
    null;

  const createMutation = useMutation({
    mutationFn: () =>
      vaultsApi.create({ name: newName.trim(), description: newDesc.trim() || undefined, vault_type: newVaultType }),
    onSuccess: (vault) => {
      qc.invalidateQueries({ queryKey: ['vaults'] });
      qc.invalidateQueries({ queryKey: ['vaults-page'] });
      setActiveVaultId(vault.id);
      localStorage.setItem('me_active_vault', vault.id);
      setSelectedVaultId(vault.id);
      toast.success(`Vault "${vault.name}" created`);
      setShowNewVault(false);
      setNewName('');
      setNewDesc('');
    },
    onError: (err) => toast.error(err.message),
  });

  const refreshVaults = () => {
    qc.invalidateQueries({ queryKey: ['vaults'] });
    qc.invalidateQueries({ queryKey: ['vaults-page'] });
  };

  const closeNewVault = () => {
    setShowNewVault(false);
    setNewName('');
    setNewDesc('');
    setNewVaultType('worldbuilding');
  };

  return (
    <div className="flex h-full">
      {/* Left panel */}
      <div className="w-[280px] flex-shrink-0 bg-surface border-r border-border-subtle flex flex-col">
        <div className="px-4 py-3 border-b border-border-subtle flex items-center justify-between">
          <span className="text-sm font-semibold text-txt">Vaults</span>
          <button
            onClick={() => setShowNewVault(true)}
            className="flex items-center gap-1 text-xs text-accent hover:opacity-80 transition-opacity font-medium"
          >
            <Plus size={13} />
            New Vault
          </button>
        </div>

        {isPlatformAdmin && (
          <div className="px-4 py-2 border-b border-border-subtle flex items-center justify-between">
            <span className="text-xs text-txt-muted">Explore all vaults</span>
            <button
              onClick={() => setExploreAll((v) => !v)}
              className={`relative inline-flex h-5 w-9 items-center rounded-full transition-colors ${
                exploreAll ? 'bg-accent' : 'bg-elevated'
              }`}
            >
              <span
                className={`inline-block h-3.5 w-3.5 transform rounded-full bg-white transition-transform ${
                  exploreAll ? 'translate-x-4' : 'translate-x-1'
                }`}
              />
            </button>
          </div>
        )}

        {exploreAll && (
          <div className="px-4 py-1.5 bg-accent/10 flex items-center gap-1.5">
            <Globe size={12} className="text-accent" />
            <span className="text-xs text-accent font-medium">Explore mode</span>
          </div>
        )}

        <div className="flex-1 overflow-y-auto">
          {vaultList.length === 0 ? (
            <div className="p-4 text-center text-txt-muted text-sm italic">No vaults</div>
          ) : (
            vaultList.map((vault) => (
              <button
                key={vault.id}
                onClick={() => setSelectedVaultId(vault.id)}
                className={`w-full text-left px-4 py-3 border-b border-border-subtle transition-colors hover:bg-hover ${
                  effectiveSelected?.id === vault.id ? 'bg-accent-soft' : ''
                }`}
              >
                <div className="flex items-center justify-between gap-2">
                  <span
                    className={`font-medium text-sm truncate ${
                      effectiveSelected?.id === vault.id ? 'text-accent' : 'text-txt'
                    }`}
                  >
                    {vault.name}
                  </span>
                  {vault.id === activeVaultId && (
                    <span className="shrink-0 text-[9px] uppercase tracking-widest font-bold bg-accent/20 text-accent px-1.5 py-0.5 rounded-full">
                      Active
                    </span>
                  )}
                </div>
                <div className="text-xs text-txt-muted mt-0.5 capitalize">
                  {vault.vault_type?.replace('_', ' ') || 'worldbuilding'}
                </div>
              </button>
            ))
          )}
        </div>
      </div>

      {/* Right panel */}
      <div className="flex-1 min-w-0 bg-base overflow-hidden">
        {effectiveSelected ? (
          <VaultDetailPanel
            key={effectiveSelected.id}
            vault={effectiveSelected}
            user={user}
            onRefresh={refreshVaults}
            onDelete={() => setSelectedVaultId(null)}
          />
        ) : (
          <div className="h-full flex items-center justify-center text-txt-muted">
            <div className="text-center">
              <Layers size={40} className="mx-auto mb-3 opacity-20" />
              <p className="text-sm">Select a vault or create one to get started.</p>
            </div>
          </div>
        )}
      </div>

      {/* New Vault Modal */}
      {showNewVault && (
        <div
          className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4"
          onClick={(e) => { if (e.target === e.currentTarget) closeNewVault(); }}
        >
          <div className="bg-surface rounded-2xl border border-border-subtle w-full max-w-md shadow-xl">
            <div className="flex items-center justify-between p-6 border-b border-border-subtle">
              <h2 className="text-lg font-bold text-txt">New Vault</h2>
              <button onClick={closeNewVault} className="text-txt-muted hover:text-txt transition-colors">
                <X size={20} />
              </button>
            </div>
            <div className="p-6 space-y-4">
              <Input
                label="Name"
                value={newName}
                onChange={(e) => setNewName(e.target.value)}
                placeholder="My Campaign"
                autoFocus
                onKeyDown={(e) => { if (e.key === 'Enter' && newName.trim()) createMutation.mutate(); }}
              />
              <TextArea
                label="Description"
                value={newDesc}
                onChange={(e) => setNewDesc(e.target.value)}
                placeholder="Describe your campaign world..."
              />
              <div>
                <label className="block text-xs font-semibold text-txt-muted uppercase tracking-wider mb-1.5">
                  Vault Type
                </label>
                <select
                  value={newVaultType}
                  onChange={(e) => setNewVaultType(e.target.value)}
                  className="w-full bg-surface border border-border-subtle rounded-lg px-3 py-2 text-txt text-sm focus:outline-none focus:border-accent"
                >
                  {VAULT_TYPE_OPTIONS.map((opt) => (
                    <option key={opt.value} value={opt.value}>{opt.label}</option>
                  ))}
                </select>
                <p className="text-xs text-txt-muted mt-1">
                  Controls the terminology used throughout the UI.
                </p>
              </div>
            </div>
            <div className="flex justify-end gap-3 px-6 pb-6">
              <Button variant="secondary" onClick={closeNewVault}>Cancel</Button>
              <Button
                onClick={() => createMutation.mutate()}
                disabled={!newName.trim() || createMutation.isPending}
              >
                Create Vault
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
