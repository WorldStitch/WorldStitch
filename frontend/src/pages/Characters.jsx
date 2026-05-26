import { useState, useEffect } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { toast } from 'sonner';
import { Users, Plus, Search, Trash2, Save, X, AlertCircle, Layers } from 'lucide-react';
import { characters as charsApi, notes as notesApi } from '@/api';
import { useVault } from '@/context/VaultContext';
import { SkeletonListItem } from '@/components/Skeleton';

// ─── Constants ────────────────────────────────────────────────────────────────

const EMPTY_FORM = {
  name: '',
  char_type: 'npc',
  race: '',
  char_class: '',
  attributes: [],
  backstory: '',
  ai_memory: '',
  note_ids: [],
  vault_id: '',
};

const TYPE_LABELS = { player: 'PC', npc: 'NPC', antagonist: 'Villain', background: 'BG' };

const FILTERS = [
  { value: 'all', label: 'All' },
  { value: 'player', label: 'Protagonists' },
  { value: 'npc', label: 'Supporting' },
  { value: 'antagonist', label: 'Antagonists' },
];

// ─── Sub-components ───────────────────────────────────────────────────────────

function CharCard({ char, isSelected, onClick }) {
  const subtitle = [char.race, char.char_class].filter(Boolean).join(' · ');
  const isAccent = char.char_type === 'player' || char.char_type === 'antagonist';
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
        <span
          className={`flex-shrink-0 text-xs px-2 py-0.5 rounded-full font-medium ${
            isAccent
              ? 'bg-accent-soft text-accent'
              : 'bg-surface-raised text-txt-muted'
          }`}
        >
          {TYPE_LABELS[char.char_type] ?? char.char_type}
        </span>
      </div>
      {subtitle && (
        <div className="text-xs text-txt-muted mt-0.5 truncate">{subtitle}</div>
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

// ─── Main page ────────────────────────────────────────────────────────────────

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

  const [filter, setFilter] = useState('all');
  const [search, setSearch] = useState('');
  const [selectedId, setSelectedId] = useState(null);
  const [isCreating, setIsCreating] = useState(false);
  const [form, setForm] = useState(EMPTY_FORM);
  const [dirty, setDirty] = useState(false);

  // ── Data queries ────────────────────────────────────────────────────────────

  const { data: listData, isLoading, isError, refetch } = useQuery({
    queryKey: ['characters', activeVaultId, filter],
    queryFn: () => charsApi.list(activeVaultId, filter === 'all' ? null : filter),
    enabled: !!activeVaultId,
  });
  const allChars = listData?.items ?? [];

  useEffect(() => {
    if (isError) toast.error('Failed to load characters');
  }, [isError]);

  const { data: notesData } = useQuery({
    queryKey: ['notes', activeVaultId],
    queryFn: () => notesApi.list('', '', activeVaultId),
    enabled: !!activeVaultId,
  });
  const allNotes = Array.isArray(notesData) ? notesData : notesData?.items ?? [];

  const { data: selectedChar } = useQuery({
    queryKey: ['character', selectedId],
    queryFn: () => charsApi.get(selectedId),
    enabled: !!selectedId && !isCreating,
  });

  // Populate form when a character is selected
  useEffect(() => {
    if (selectedChar && !isCreating) {
      setForm({
        name: selectedChar.name ?? '',
        char_type: selectedChar.char_type ?? 'npc',
        race: selectedChar.race ?? '',
        char_class: selectedChar.char_class ?? '',
        attributes: selectedChar.attributes ?? [],
        backstory: selectedChar.backstory ?? '',
        ai_memory: selectedChar.ai_memory ?? '',
        note_ids: selectedChar.note_ids ?? [],
        vault_id: selectedChar.vault_id ?? activeVaultId,
      });
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
  };

  const handleNew = () => {
    setIsCreating(true);
    setSelectedId(null);
    setForm({ ...EMPTY_FORM, vault_id: activeVaultId });
    setDirty(false);
  };

  const handleSelectChar = (id) => {
    setSelectedId(id);
    setIsCreating(false);
    setDirty(false);
  };

  const handleSave = () => {
    if (isCreating) createMut.mutate(form);
    else updateMut.mutate(form);
  };

  const addNote = (noteId) => {
    if (noteId && !form.note_ids.includes(noteId)) {
      setField('note_ids', [...form.note_ids, noteId]);
    }
  };

  const removeNote = (noteId) => {
    setField('note_ids', form.note_ids.filter((id) => id !== noteId));
  };

  const addAttribute = () =>
    setField('attributes', [...(form.attributes || []), { key: '', value: '' }]);

  const updateAttribute = (i, field, val) => {
    const attrs = [...(form.attributes || [])];
    attrs[i] = { ...attrs[i], [field]: val };
    setField('attributes', attrs);
  };

  const removeAttribute = (i) =>
    setField('attributes', (form.attributes || []).filter((_, idx) => idx !== i));

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
        {/* Header */}
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

          {/* Search */}
          <div className="relative mb-2">
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

          {/* Filter tabs */}
          <div className="flex gap-1">
            {FILTERS.map(({ value, label }) => (
              <button
                key={value}
                onClick={() => setFilter(value)}
                className={`flex-1 text-xs py-1.5 rounded-md font-medium transition-colors ${
                  filter === value
                    ? 'bg-accent text-white'
                    : 'bg-base text-txt-muted hover:text-txt'
                }`}
              >
                {label}
              </button>
            ))}
          </div>
        </div>

        {/* Character list */}
        <div className="flex-1 overflow-y-auto px-3 py-3 flex flex-col gap-2">
          {isLoading ? (
            Array.from({ length: 4 }).map((_, i) => <SkeletonListItem key={i} />)
          ) : isError ? (
            <div className="flex flex-col items-center gap-2 py-6 text-center">
              <AlertCircle size={20} className="text-red-400 opacity-70" />
              <p className="text-txt-muted text-xs">Failed to load characters.</p>
              <button
                onClick={() => refetch()}
                className="text-xs text-accent hover:underline"
              >
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
            {/* ── Title + action buttons ─────────────────────────── */}
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

            {/* ── Identity fields ────────────────────────────────── */}
            <div className="grid grid-cols-2 gap-4">
              <div className="col-span-2">
                <FieldLabel>Name</FieldLabel>
                <TextInput
                  value={form.name}
                  onChange={(v) => setField('name', v)}
                  placeholder="Character name"
                />
              </div>

              <div className="col-span-2">
                <FieldLabel>Type</FieldLabel>
                <select
                  value={form.char_type}
                  onChange={(e) => setField('char_type', e.target.value)}
                  className="w-full bg-surface border border-border-subtle rounded-lg px-3 py-2 text-txt text-sm focus:outline-none focus:border-accent"
                >
                  <option value="player">Protagonist</option>
                  <option value="npc">Supporting Character</option>
                  <option value="antagonist">Antagonist</option>
                  <option value="background">Background Figure</option>
                </select>
              </div>

              <div>
                <FieldLabel>Species / Origin</FieldLabel>
                <TextInput
                  value={form.race}
                  onChange={(v) => setField('race', v)}
                  placeholder="e.g. Human, Elf, Android…"
                />
              </div>

              <div>
                <FieldLabel>Role / Archetype</FieldLabel>
                <TextInput
                  value={form.char_class}
                  onChange={(v) => setField('char_class', v)}
                  placeholder="e.g. Warrior, Trickster, Scholar…"
                />
              </div>
            </div>

            {/* ── Custom attributes ──────────────────────────────── */}
            <div>
              <div className="flex items-center justify-between mb-2">
                <FieldLabel>Attributes</FieldLabel>
                <button
                  onClick={addAttribute}
                  className="text-xs text-accent hover:opacity-80 transition flex items-center gap-1"
                >
                  <Plus size={12} /> Add
                </button>
              </div>
              {(form.attributes || []).length === 0 ? (
                <p className="text-xs text-txt-muted">
                  No attributes yet — add things like Age, Alignment, Occupation, Power Level…
                </p>
              ) : (
                <div className="space-y-2">
                  {(form.attributes || []).map((attr, i) => (
                    <div key={i} className="flex items-center gap-2">
                      <input
                        value={attr.key}
                        onChange={(e) => updateAttribute(i, 'key', e.target.value)}
                        placeholder="Label"
                        className="w-1/3 bg-surface border border-border-subtle rounded-lg px-2 py-1.5 text-txt text-sm focus:outline-none focus:border-accent"
                      />
                      <input
                        value={attr.value}
                        onChange={(e) => updateAttribute(i, 'value', e.target.value)}
                        placeholder="Value"
                        className="flex-1 bg-surface border border-border-subtle rounded-lg px-2 py-1.5 text-txt text-sm focus:outline-none focus:border-accent"
                      />
                      <button
                        onClick={() => removeAttribute(i)}
                        className="text-txt-muted hover:text-danger transition flex-shrink-0"
                      >
                        <X size={14} />
                      </button>
                    </div>
                  ))}
                </div>
              )}
            </div>

            {/* ── Backstory ──────────────────────────────────────── */}
            <div>
              <FieldLabel>Backstory</FieldLabel>
              <textarea
                value={form.backstory}
                onChange={(e) => setField('backstory', e.target.value)}
                placeholder="Character history, background, motivations…"
                rows={4}
                className="w-full bg-surface border border-border-subtle rounded-lg px-3 py-2 text-txt text-sm focus:outline-none focus:border-accent resize-none"
              />
            </div>

            {/* ── AI Memory ──────────────────────────────────────── */}
            <div>
              <FieldLabel>AI Memory</FieldLabel>
              <p className="text-xs text-txt-muted mb-1.5">
                Notes the AI can reference about this character
              </p>
              <textarea
                value={form.ai_memory}
                onChange={(e) => setField('ai_memory', e.target.value)}
                placeholder="Key facts, personality traits, recent events, secrets…"
                rows={4}
                className="w-full bg-surface border border-border-subtle rounded-lg px-3 py-2 text-txt text-sm focus:outline-none focus:border-accent resize-none"
              />
            </div>

            {/* ── Attached notes ─────────────────────────────────── */}
            <div>
              <FieldLabel>Attached Notes</FieldLabel>

              {form.note_ids.length > 0 ? (
                <ul className="space-y-1 mb-3">
                  {form.note_ids.map((noteId) => {
                    const note = allNotes.find((n) => n.id === noteId);
                    return (
                      <li
                        key={noteId}
                        className="flex items-center justify-between bg-surface border border-border-subtle rounded-lg px-3 py-2 text-sm"
                      >
                        <span className="text-txt truncate">{note?.title ?? noteId}</span>
                        <button
                          onClick={() => removeNote(noteId)}
                          className="ml-2 flex-shrink-0 text-txt-muted hover:text-red-400 transition-colors"
                          title="Remove"
                        >
                          <X size={14} />
                        </button>
                      </li>
                    );
                  })}
                </ul>
              ) : (
                <p className="text-xs text-txt-muted mb-2">No notes attached.</p>
              )}

              <select
                defaultValue=""
                onChange={(e) => {
                  addNote(e.target.value);
                  e.target.value = '';
                }}
                className="w-full bg-surface border border-border-subtle rounded-lg px-3 py-2 text-txt text-sm focus:outline-none focus:border-accent"
              >
                <option value="">Attach a note…</option>
                {allNotes
                  .filter((n) => !form.note_ids.includes(n.id))
                  .map((n) => (
                    <option key={n.id} value={n.id}>
                      {n.title}
                    </option>
                  ))}
              </select>
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
