import { useEffect, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import Button from '@/components/Button';
import { vaults, vaultMembers } from '@/api';

const VAULT_ROLE_RANK = { owner: 0, admin: 1, editor: 2, viewer: 3, player: 4 };

const BRAIN_EDIT_OPTIONS = [
  { value: 'owner', label: 'Owners only' },
  { value: 'admin', label: 'Admins & above' },
  { value: 'editor', label: 'Editors & above' },
];

function wordCount(text) {
  return (text || '').trim().split(/\s+/).filter(Boolean).length;
}

export default function VaultBrainSettings({ activeVaultId, user }) {
  const qc = useQueryClient();
  const [content, setContent] = useState('');
  const [dirty, setDirty] = useState(false);

  const { data: brain, isLoading: brainLoading } = useQuery({
    queryKey: ['vault-brain', activeVaultId],
    queryFn: () => vaults.getBrain(activeVaultId),
    enabled: !!activeVaultId,
  });

  const { data: members = [] } = useQuery({
    queryKey: ['vault-members', activeVaultId],
    queryFn: () => vaultMembers.list(activeVaultId),
    enabled: !!activeVaultId,
  });

  const myRole = members.find((m) => m.user_id === user?.id)?.vault_role ?? null;
  const editRole = brain?.brain_edit_role ?? 'admin';

  const canEdit =
    myRole != null &&
    (VAULT_ROLE_RANK[myRole] ?? 99) <= (VAULT_ROLE_RANK[editRole] ?? 99);
  const canChangeSettings =
    myRole != null && (VAULT_ROLE_RANK[myRole] ?? 99) <= VAULT_ROLE_RANK['admin'];

  useEffect(() => {
    if (brain) {
      setContent(brain.brain_content ?? '');
      setDirty(false);
    }
  }, [brain]);

  const saveBrain = useMutation({
    mutationFn: () => vaults.updateBrain(activeVaultId, content),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['vault-brain', activeVaultId] });
      setDirty(false);
      toast.success('Vault Brain saved');
    },
    onError: (err) => toast.error(err.message),
  });

  const saveSettings = useMutation({
    mutationFn: (role) => vaults.updateBrainSettings(activeVaultId, role),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['vault-brain', activeVaultId] });
      toast.success('Brain settings updated');
    },
    onError: (err) => toast.error(err.message),
  });

  if (!activeVaultId) {
    return (
      <p className="text-txt-muted text-sm">Select an active vault to configure its Brain.</p>
    );
  }

  if (brainLoading) {
    return <p className="text-txt-muted text-sm">Loading…</p>;
  }

  const chars = (content || '').length;
  const words = wordCount(content);

  return (
    <div className="space-y-4">
      <div>
        <p className="text-txt-muted text-sm mb-3">
          The Vault Brain is a persistent context document that the AI reads before every request in
          this vault — like a CLAUDE.md for your world. Use it to describe your world&apos;s tone,
          rules, key lore, and anything the AI should always know.
        </p>

        {canEdit ? (
          <textarea
            value={content}
            onChange={(e) => {
              setContent(e.target.value);
              setDirty(true);
            }}
            rows={14}
            placeholder="Describe your world&#39;s tone, key lore, house rules, recurring characters…"
            className="w-full bg-elevated rounded-xl px-4 py-3 text-txt text-sm border-2 border-transparent focus:border-accent focus:outline-none transition resize-y font-mono leading-relaxed"
          />
        ) : (
          <div className="space-y-2">
            <textarea
              value={content}
              readOnly
              rows={14}
              className="w-full bg-elevated/50 rounded-xl px-4 py-3 text-txt-muted text-sm border-2 border-transparent resize-y font-mono leading-relaxed cursor-not-allowed"
            />
            <p className="text-xs text-txt-muted italic">
              You don&apos;t have permission to edit this vault&apos;s brain (requires{' '}
              <span className="font-medium text-txt">{editRole}</span> role or above).
            </p>
          </div>
        )}

        <div className="flex items-center justify-between mt-2">
          <span className="text-xs text-txt-muted">
            {words.toLocaleString()} words · {chars.toLocaleString()} characters
          </span>
          {canEdit && (
            <Button
              variant="primary"
              size="sm"
              onClick={() => saveBrain.mutate()}
              disabled={!dirty || saveBrain.isPending}
            >
              {saveBrain.isPending ? 'Saving…' : 'Save Brain'}
            </Button>
          )}
        </div>
      </div>

      <div className="border-t border-border-subtle pt-4">
        <label className="block text-txt-muted text-sm mb-2 font-medium">Who can edit this brain</label>
        <select
          value={editRole}
          disabled={!canChangeSettings || saveSettings.isPending}
          onChange={(e) => saveSettings.mutate(e.target.value)}
          className={`w-full bg-elevated rounded-xl px-4 py-3 text-sm border-2 border-transparent focus:border-accent focus:outline-none transition ${
            canChangeSettings ? 'text-txt' : 'text-txt-muted cursor-not-allowed opacity-60'
          }`}
        >
          {BRAIN_EDIT_OPTIONS.map((opt) => (
            <option key={opt.value} value={opt.value}>
              {opt.label}
            </option>
          ))}
        </select>
        {!canChangeSettings && (
          <p className="text-xs text-txt-muted mt-1 italic">Only vault owners and admins can change this.</p>
        )}
      </div>
    </div>
  );
}
