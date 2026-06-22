import { useEffect, useMemo, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import Button from '@/components/Button';
import Input from '@/components/Input';
import { groups, vaults } from '@/api';
import { useVault } from '@/context/VaultContext';
import VaultBrainSettings from './VaultBrainSettings';

export default function CampaignSettings({ user }) {
  const qc = useQueryClient();
  const { vaults: vaultList = [], activeVaultId, setActiveVaultId } = useVault();
  const activeVault = useMemo(() => vaultList.find((vault) => vault.id === activeVaultId) || null, [vaultList, activeVaultId]);
  const [newVaultName, setNewVaultName] = useState('');
  const [activeVaultName, setActiveVaultName] = useState(activeVault?.name || '');
  const [backupCron, setBackupCron] = useState(activeVault?.settings?.backup_cron || '0 0 * * *');
  const [sharedGroupId, setSharedGroupId] = useState('');
  const { data: groupList = [] } = useQuery({ queryKey: ['groups'], queryFn: groups.list });

  useEffect(() => {
    setActiveVaultName(activeVault?.name || '');
    setBackupCron(activeVault?.settings?.backup_cron || '0 0 * * *');
    const matchedGroup = groupList.find((group) => (activeVault?.permissions || {})[group.id]);
    setSharedGroupId(matchedGroup?.id || '');
  }, [activeVault, groupList]);

  const refreshVaults = () => qc.invalidateQueries({ queryKey: ['vaults'] });

  const createVault = useMutation({
    mutationFn: () => vaults.create({ name: newVaultName }),
    onSuccess: (vault) => {
      setNewVaultName('');
      setActiveVaultId(vault.id);
      refreshVaults();
      toast.success('Vault created');
    },
    onError: (err) => toast.error(err.message),
  });

  const updateVault = useMutation({
    mutationFn: (payload) => vaults.update(activeVaultId, payload),
    onSuccess: () => {
      refreshVaults();
      toast.success('Vault updated');
    },
    onError: (err) => toast.error(err.message),
  });

  const deleteVault = useMutation({
    mutationFn: () => vaults.remove(activeVaultId),
    onSuccess: () => {
      refreshVaults();
      toast.success('Vault archived');
    },
    onError: (err) => toast.error(err.message),
  });

  const exportVault = async () => {
    if (!activeVaultId) return;
    const blob = await vaults.exportZip(activeVaultId);
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `${activeVault?.name || activeVaultId}.zip`;
    link.click();
    URL.revokeObjectURL(url);
  };

  const importVault = async (event) => {
    const file = event.target.files?.[0];
    if (!file) return;
    try {
      const imported = await vaults.importZip(file);
      refreshVaults();
      setActiveVaultId(imported.id);
      toast.success('Vault imported');
    } catch (err) {
      toast.error(err.message);
    } finally {
      event.target.value = '';
    }
  };

  const saveBackupSchedule = async () => {
    try {
      await vaults.updateBackup(activeVaultId, backupCron);
      refreshVaults();
      toast.success('Backup schedule saved');
    } catch (err) {
      toast.error(err.message);
    }
  };

  const shareVaultWithGroup = async () => {
    if (!activeVaultId || !sharedGroupId) return;
    try {
      await vaults.update(activeVaultId, { shared_group_id: sharedGroupId });
      refreshVaults();
      toast.success('Vault shared with group');
    } catch (err) {
      toast.error(err.message);
    }
  };

  return (
    <div className="space-y-6">
      <div className="space-y-4">
        <h4 className="text-lg font-bold text-txt">Vault Management</h4>
        <div className="grid md:grid-cols-[1fr,160px] gap-3">
          <Input label="New vault" value={newVaultName} onChange={(e) => setNewVaultName(e.target.value)} />
          <Button className="self-end" onClick={() => createVault.mutate()} disabled={!newVaultName.trim()}>Create vault</Button>
        </div>

        {activeVault && (
          <div className="space-y-4 bg-elevated rounded-xl p-4">
            <Input
              label="Active vault name"
              value={activeVaultName}
              onChange={(e) => setActiveVaultName(e.target.value)}
            />
            <Input
              label="Backup cron"
              value={backupCron}
              onChange={(e) => setBackupCron(e.target.value)}
              placeholder="0 0 * * *"
            />
            <div className="grid md:grid-cols-[1fr,220px] gap-3 items-end">
              <div>
                <label className="block text-txt-muted text-sm mb-2 font-medium">Shared group</label>
                <select
                  value={sharedGroupId}
                  onChange={(e) => setSharedGroupId(e.target.value)}
                  className="w-full bg-surface rounded-xl px-4 py-3 text-txt border-2 border-transparent focus:border-accent focus:outline-none transition"
                >
                  <option value="">None</option>
                  {groupList.map((group) => (
                    <option key={group.id} value={group.id}>{group.name}</option>
                  ))}
                </select>
              </div>
              <Button
                variant="secondary"
                onClick={shareVaultWithGroup}
                disabled={!activeVaultId || !sharedGroupId}
                title={!activeVaultId ? 'Select an active vault first' : (!sharedGroupId ? 'Select a group first' : '')}
                aria-label="Share active vault with selected group"
              >
                Share with group
              </Button>
            </div>
            <div className="flex flex-wrap gap-2">
              <Button variant="secondary" onClick={() => updateVault.mutate({ name: activeVaultName })}>Rename vault</Button>
              <Button variant="secondary" onClick={saveBackupSchedule}>Save backup schedule</Button>
              <Button variant="secondary" onClick={exportVault}>Export ZIP</Button>
              <label className="inline-flex items-center cursor-pointer">
                <input type="file" accept=".zip" className="hidden" onChange={importVault} />
                <span className="rounded-xl bg-elevated text-txt-muted hover:bg-hover hover:text-txt px-4 py-2.5">Import ZIP</span>
              </label>
              <Button variant="danger" onClick={() => deleteVault.mutate()}>Archive vault</Button>
            </div>
          </div>
        )}
      </div>

      <div className="border-t border-border-subtle pt-6 space-y-4">
        <h4 className="text-lg font-bold text-txt">Vault Brain</h4>
        <VaultBrainSettings activeVaultId={activeVaultId} user={user} />
      </div>
    </div>
  );
}
