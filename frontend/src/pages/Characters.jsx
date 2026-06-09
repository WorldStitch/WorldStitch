import { useState, useEffect } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { toast } from 'sonner';
import { Users, Plus, Search, Trash2, Save, X, AlertCircle, Layers } from 'lucide-react';
import { characters as charsApi } from '@/api';
import { useVault } from '@/context/VaultContext';
import { SkeletonListItem } from '@/components/Skeleton';

const EMPTY_FORM = {
  name: '',
  description: '',
  image_url: '',
  metadata: '{}',
  vault_id: '',
};

function CharCard({ char, isSelected, onClick }) {
  return (
    <button
      onClick={onClick}
      className={`w-full text-left rounded-xl px-4 py-3 border transition-all ${
        isSelected
          ? 'border-accent bg-accent-soft'
          : 'border-border-subtle bg-surface hover:border-border'
      }`}
    >
      <div className="flex items-center justify-between gap-2">
        <span className="font-semibold text-txt truncate">{char.name}</span>
      </div>
      {char.description && (
        <div className="text-xs text-txt-muted mt-0.5 truncate">{char.description}</div>
      )}
    </button>
  );
}

function FieldLabel({ children }) {
  return (
    <label className="text-xs font-semibold text-txt-muted uppercase tracking-wider mb-1 block">
      {children}
    </label>
  );
}

function TextInput({ value, onChange, placeholder, className = '' }) {
  return (
    <input
      value={value}
      onChange={(e) => onChange(e.target.value)}
      placeholder={placeholder}
      className={`w-full bg-surface border border-border-subtle rounded-lg px-3 py-2 text-txt text-sm focus:outline-none focus:border-accent ${className}`}
    />
  );
}

export default function Characters() {
  const qc = useQueryClient();
  const { activeVaultId } = useVault();
  const navigate = useNavigate();

  if (!activeVaultId) {
    return (
      <div className="h-full flex flex-col items-center justify-center gap-3 text-txt-muted">
        <Layers size={48} className="opacity-20" />
        <p className="text-sm font-medium">No vault selected</p>
        <p className="text-xs text-center max-w-xs">Select or create a vault to manage characters.</p>
        <button
          onClick={() => navigate('/vaults')}
          className="mt-1 text-xs bg-accent text-white px-4 py-2 rounded-lg hover:bg-accent/90 transition-colors"
        >
          Go to Vaults
        </button>
      </div>
    );
  }

  const [search, setSearch] = useState('');
  const [selectedId, setSelectedId] = useState(null);
  const [isCreating, setIsCreating] = useState(false);
  const [form, setForm] = useState(EMPTY_FORM);
  const [metaError, setMetaError] = useState('');
  const [dirty, setDirty] = useState(false);

  // ── Data queries ────────────────────────────────────────────────────────────

  const { data: listData, isLoading, isError, refetch } = useQuery({
    queryKey: ['characters', activeVaultId],
    queryFn: () => charsApi.list(activeVaultId),
    enabled: !!activeVaultId,
  });
  const allChars = listData?.items ?? [];

  useEffect(() => {
    if (isError) toast.error('Failed to load characters');
  }, [isError]);

  const { data: selectedChar } = useQuery({
    queryKey: ['character', selectedId],
    queryFn: () => charsApi.get(selectedId),
    enabled: !!selectedId && !isCreating,
  });

  useEffect(() => {
    if (selectedChar && !isCreating) {
      setForm({
        name: selectedChar.name ?? '',
        description: selectedChar.description ?? '',
        image_url: selectedChar.image_url ?? '',
        metadata: selectedChar.metadata
          ? JSON.stringify(selectedChar.metadata, null, 2)
          : '{}',
        vault_id: selectedChar.vault_id ?? activeVaultId,
      });
      setMetaError('');
      setDirty(false);
    }
  }, [selectedChar, isCreating]);

  // ── Mutations ───────────────────────────────────────────────────────────────

  const createMut = useMutation({
    mutationFn: (data) => charsApi.create(data),
    onSuccess: (char) => {
      qc.invalidateQueries({ queryKey: ['characters'] });
      setIsCreating(false);
      setSelectedId(char.id);
      setDirty(false);
      toast.success('Character created');
    },
    onError: (e) => toast.error(e.message),
  });

  const updateMut = useMutation({
    mutationFn: (data) => charsApi.update(selectedId, data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['characters'] });
      qc.invalidateQueries({ queryKey: ['character', selectedId] });
      setDirty(false);
      toast.success('Saved');
    },
    onError: (e) => toast.error(e.message),
  });

  const deleteMut = useMutation({
    mutationFn: () => charsApi.delete(selectedId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['characters'] });
      setSelectedId(null);
      setIsCreating(false);
      toast.success('Character deleted');
    },
    onError: (e) => toast.error(e.message),
  });

  // ── Handlers ────────────────────────────────────────────────────────────────

  const setField = (key, val) => {
    setForm((f) => ({ ...f, [key]: val }));
    setDirty(true);
    if (key === 'metadata') setMetaError('');
  };

  const handleNew = () => {
    setIsCreating(true);
    setSelectedId(null);
    setForm({ ...EMPTY_FORM, vault_id: activeVaultId });
    setMetaError('');
    setDirty(false);
  };

  const handleSelectChar = (id) => {
    setSelectedId(id);
    setIsCreating(false);
    setDirty(false);
  };

  const handleSave = () => {
    let parsedMeta = {};
    try {
      parsedMeta = form.metadata.trim() ? JSON.parse(form.metadata) : {};
    } catch {
      setMetaError('Metadata is not valid JSON');
      return;
    }
    const payload = {
      name: form.name,
      description: form.description,
      image_url: form.image_url || null,
      metadata: parsedMeta,
      vault_id: form.vault_id || activeVaultId,
    };
    if (isCreating) createMut.mutate(payload);
    else updateMut.mutate(payload);
  };

  const filtered = allChars.filter(
    (c) => !search || c.name.toLowerCase().includes(search.toLowerCase())
  );

  const isBusy = createMut.isPending || updateMut.isPending;
  const showEditor = isCreating || !!selectedId;

  // ── Render ──────────────────────────────────────────────────────────────────

  return (
    <div className="h-full flex overflow-hidden">
      {/* ── Left panel ────────────────────────────────────────────── */}
      <div className="w-[300px] border-r border-border-subtle flex flex-col h-full bg-surface flex-shrink-0">
        <div className="px-4 pt-5 pb-3 border-b border-border-subtle">
          <div className="flex items-center justify-between mb-3">
            <h1 className="text-lg font-bold text-txt flex items-center gap-2">
              <Users size={20} />
              Characters
            </h1>
            <button
              onClick={handleNew}
              className="flex items-center gap-1 text-sm bg-accent text-white rounded-lg px-3 py-1.5 hover:bg-accent/90 transition-colors"
            >
              <Plus size={14} />
              New
            </button>
          </div>

          <div className="relative">
            <Search
              size={14}
              className="absolute left-3 top-1/2 -translate-y-1/2 text-txt-muted pointer-events-none"
            />
            <input
              type="text"
              placeholder="Search characters..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="w-full pl-8 pr-3 py-1.5 text-sm bg-base border border-border-subtle rounded-lg text-txt placeholder:text-txt-muted focus:outline-none focus:border-accent"
            />
          </div>
        </div>

        <div className="flex-1 overflow-y-auto px-3 py-3 flex flex-col gap-2">
          {isLoading ? (
            Array.from({ length: 4 }).map((_, i) => <SkeletonListItem key={i} />)
          ) : isError ? (
            <div className="flex flex-col items-center gap-2 py-6 text-center">
              <AlertCircle size={20} className="text-red-400 opacity-70" />
              <p className="text-txt-muted text-xs">Failed to load characters.</p>
              <button onClick={() => refetch()} className="text-xs text-accent hover:underline">
                Retry
              </button>
            </div>
          ) : filtered.length === 0 ? (
            <p className="text-txt-muted text-sm text-center py-6">
              {search ? 'No characters match your search.' : 'No characters yet. Click New to add one.'}
            </p>
          ) : (
            filtered.map((c) => (
              <CharCard
                key={c.id}
                char={c}
                isSelected={c.id === selectedId}
                onClick={() => handleSelectChar(c.id)}
              />
            ))
          )}
        </div>
      </div>

      {/* ── Right panel ───────────────────────────────────────────── */}
      <div className="flex-1 overflow-y-auto">
        {!showEditor ? (
          <div className="h-full flex flex-col items-center justify-center gap-3 text-txt-muted">
            <Users size={52} className="opacity-20" />
            <p className="text-sm">Select a character or click New to get started.</p>
          </div>
        ) : (
          <div className="max-w-2xl mx-auto px-6 py-6 space-y-6">
            <div className="flex items-center justify-between gap-4">
              <h2 className="text-xl font-bold text-txt truncate">
                {isCreating ? 'New Character' : (form.name || 'Unnamed')}
              </h2>
              <div className="flex gap-2 flex-shrink-0">
                <button
                  onClick={handleSave}
                  disabled={isBusy}
                  className="flex items-center gap-1.5 bg-accent text-white text-sm px-4 py-2 rounded-lg hover:bg-accent/90 disabled:opacity-50 transition-colors"
                >
                  <Save size={14} />
                  {isBusy ? 'Saving…' : 'Save'}
                </button>
                {!isCreating && (
                  <button
                    onClick={() => deleteMut.mutate()}
                    disabled={deleteMut.isPending}
                    className="flex items-center gap-1.5 bg-red-500/10 text-red-400 text-sm px-4 py-2 rounded-lg hover:bg-red-500/20 disabled:opacity-50 transition-colors"
                  >
                    <Trash2 size={14} />
                    Delete
                  </button>
                )}
              </div>
            </div>

            {/* Name */}
            <div>
              <FieldLabel>Name *</FieldLabel>
              <TextInput
                value={form.name}
                onChange={(v) => setField('name', v)}
                placeholder="Character name"
              />
            </div>

            {/* Description */}
            <div>
              <FieldLabel>Description</FieldLabel>
              <textarea
                value={form.description}
                onChange={(e) => setField('description', e.target.value)}
                placeholder="Who is this character? Background, personality, role in the world…"
                rows={4}
                className="w-full bg-surface border border-border-subtle rounded-lg px-3 py-2 text-txt text-sm focus:outline-none focus:border-accent resize-none"
              />
            </div>

            {/* Image URL */}
            <div>
              <FieldLabel>Image URL</FieldLabel>
              <TextInput
                value={form.image_url}
                onChange={(v) => setField('image_url', v)}
                placeholder="https://… portrait or avatar image"
              />
              {form.image_url && (
                <img
                  src={form.image_url}
                  alt=""
                  className="mt-2 w-24 h-24 rounded-xl object-cover border border-border-subtle"
                  onError={(e) => { e.currentTarget.style.display = 'none'; }}
                />
              )}
            </div>

            {/* Metadata */}
            <div>
              <FieldLabel>Metadata (JSON)</FieldLabel>
              <p className="text-xs text-txt-muted mb-1.5">
                World-specific attributes — race, class, backstory, alignment, abilities, etc.
              </p>
              <textarea
                value={form.metadata}
                onChange={(e) => setField('metadata', e.target.value)}
                rows={8}
                spellCheck={false}
                className={`w-full bg-surface border rounded-lg px-3 py-2 text-txt text-sm font-mono focus:outline-none focus:border-accent resize-y ${
                  metaError ? 'border-red-500' : 'border-border-subtle'
                }`}
              />
              {metaError && (
                <p className="text-xs text-red-400 mt-1">{metaError}</p>
              )}
            </div>

            {dirty && (
              <p className="text-xs text-txt-muted text-right">Unsaved changes</p>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
