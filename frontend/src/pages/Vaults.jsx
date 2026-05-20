import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { Layers, Plus, Globe, Copy, Check, Trash2, X } from 'lucide-react';
import Button from '@/components/Button';
import Input, { TextArea } from '@/components/Input';
import { vaults as vaultsApi, invites as invitesApi } from '@/api';
import { useVault } from '@/context/VaultContext';

function VaultDetailPanel({ vault, user, onRefresh, onDelete }) {
  const [tab, setTab] = useState('overview');
  const [editName, setEditName] = useState(vault.name);
  const [editDesc, setEditDesc] = useState(vault.description || '');
  const [generatedCode, setGeneratedCode] = useState(null);
  const [copied, setCopied] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);

  const isPlatformAdmin = ['owner', 'admin'].includes(user?.system_role);
  const canInvite = vault.owner_id === user?.id || isPlatformAdmin;

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

  const inviteMutation = useMutation({
    mutationFn: () => invitesApi.generate({ ttl_days: 7, max_uses: 1 }),
    onSuccess: (data) => setGeneratedCode(data.code),
    onError: (err) => toast.error(err.message),
  });

  const handleSave = () => {
    const payload = {};
    const trimmedName = editName.trim();
    if (trimmedName && trimmedName !== vault.name) payload.name = trimmedName;
    if (editDesc !== (vault.description || '')) payload.description = editDesc;
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

  const handleCopy = () => {
    navigator.clipboard.writeText(generatedCode);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
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
        {['overview', 'access', 'settings'].map((t) => (
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
              placeholder="Describe this vault…"
            />
            <div className="pt-1">
              <Button onClick={handleSave} disabled={updateMutation.isPending}>
                Save
              </Button>
            </div>
            <div className="pt-4 text-xs text-txt-muted space-y-1">
              <div>Members: {vault.members?.length ?? 0}</div>
              {vault.created_at && (
                <div>Created: {new Date(vault.created_at).toLocaleDateString()}</div>
              )}
            </div>
          </div>
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
                <h3 className="text-sm font-semibold text-txt mb-3">Invite</h3>
                <Button
                  variant="secondary"
                  onClick={() => inviteMutation.mutate()}
                  disabled={inviteMutation.isPending}
                >
                  Generate Invite
                </Button>
                {generatedCode && (
                  <div className="mt-3 space-y-2">
                    <div className="flex items-center gap-2 bg-elevated rounded-xl px-4 py-3">
                      <code className="flex-1 text-sm font-mono text-accent">{generatedCode}</code>
                      <button
                        onClick={handleCopy}
                        className="text-txt-muted hover:text-txt transition-colors"
                        title="Copy to clipboard"
                      >
                        {copied ? <Check size={16} className="text-green-500" /> : <Copy size={16} />}
                      </button>
                    </div>
                    <p className="text-xs text-txt-muted">Share this code for new users to register</p>
                  </div>
                )}
              </div>
            )}
          </div>
        )}

        {tab === 'settings' && (
          <div className="space-y-6 max-w-lg">
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
      vaultsApi.create({ name: newName.trim(), description: newDesc.trim() || undefined }),
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
                <div className="text-xs text-txt-muted mt-0.5">
                  {vault.members?.length ?? 0} member{vault.members?.length !== 1 ? 's' : ''}
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
                placeholder="Describe your campaign world…"
              />
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
