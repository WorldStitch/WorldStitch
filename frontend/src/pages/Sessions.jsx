import { useState, useEffect } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import ReactMarkdown from 'react-markdown';
import { toast } from 'sonner';
import { AlertCircle, Layers, Plus } from 'lucide-react';
import Button from '@/components/Button';
import Input, { TextArea } from '@/components/Input';
import { SkeletonListItem } from '@/components/Skeleton';
import { sessions } from '@/api';
import { useVault } from '@/context/VaultContext';

// ─── SessionDetail ────────────────────────────────────────────────────────────

function SessionDetail({ sessionId, isNew, vaultId, ownerId, onSaved, onDeleted }) {
  const queryClient = useQueryClient();

  const [title, setTitle] = useState('');
  const [sessionDate, setSessionDate] = useState('');
  const [participants, setParticipants] = useState('');
  const [xpGained, setXpGained] = useState(0);
  const [lootNotes, setLootNotes] = useState('');
  const [rawNotes, setRawNotes] = useState('');
  const [aiRecap, setAiRecap] = useState('');
  const [recapLoading, setRecapLoading] = useState(false);

  const { data: detail } = useQuery({
    queryKey: ['session', sessionId],
    queryFn: () => sessions.get(sessionId),
    enabled: !!sessionId && !isNew,
  });

  useEffect(() => {
    if (isNew) {
      setTitle('');
      setSessionDate('');
      setParticipants('');
      setXpGained(0);
      setLootNotes('');
      setRawNotes('');
      setAiRecap('');
    } else if (detail) {
      setTitle(detail.title || '');
      setSessionDate(detail.session_date || '');
      setParticipants(detail.participants || '');
      setXpGained(detail.xp_gained ?? 0);
      setLootNotes(detail.loot_notes || '');
      setRawNotes(detail.raw_notes || '');
      setAiRecap(detail.ai_recap || '');
    }
  }, [detail, isNew]);

  const saveMutation = useMutation({
    mutationFn: (data) =>
      isNew
        ? sessions.create(data)
        : sessions.update(sessionId, data),
    onSuccess: (saved) => {
      toast.success(isNew ? 'Session created' : 'Session saved');
      queryClient.invalidateQueries({ queryKey: ['sessions'] });
      queryClient.invalidateQueries({ queryKey: ['session', saved.id] });
      onSaved(saved.id);
    },
    onError: (err) => toast.error(err.message),
  });

  const deleteMutation = useMutation({
    mutationFn: () => sessions.delete(sessionId),
    onSuccess: () => {
      toast.success('Session deleted');
      queryClient.invalidateQueries({ queryKey: ['sessions'] });
      onDeleted();
    },
    onError: (err) => toast.error(err.message ?? 'Failed to delete session'),
  });

  const handleSave = () => {
    if (!title.trim()) {
      toast.error('Title is required');
      return;
    }
    saveMutation.mutate({
      vault_id: vaultId,
      title: title.trim(),
      session_date: sessionDate,
      participants,
      xp_gained: Number(xpGained) || 0,
      loot_notes: lootNotes,
      raw_notes: rawNotes,
    });
  };

  const handleGenerateRecap = async () => {
    if (!rawNotes.trim()) {
      toast.error('Add some session notes before generating a summary');
      return;
    }
    setRecapLoading(true);
    try {
      const result = await sessions.generateRecap(sessionId);
      setAiRecap(result.ai_recap);
      queryClient.invalidateQueries({ queryKey: ['session', sessionId] });
      toast.success('Summary generated!');
    } catch (err) {
      toast.error(err.message);
    } finally {
      setRecapLoading(false);
    }
  };

  return (
    <div className="flex-1 overflow-y-auto p-6 space-y-5">
      <div className="grid grid-cols-2 gap-4">
        <Input
          label="Title"
          placeholder="Session 1 — The Beginning"
          value={title}
          onChange={(e) => setTitle(e.target.value)}
        />
        <Input
          label="Session Date"
          type="date"
          value={sessionDate}
          onChange={(e) => setSessionDate(e.target.value)}
        />
      </div>

      <div className="grid grid-cols-2 gap-4">
        <Input
          label="Characters Involved"
          placeholder="Aria, Brom, Cael..."
          value={participants}
          onChange={(e) => setParticipants(e.target.value)}
        />
        <Input
          label="Milestone Points"
          type="number"
          min="0"
          placeholder="Story milestones reached"
          value={xpGained}
          onChange={(e) => setXpGained(e.target.value)}
        />
      </div>

      <TextArea
        label="Discoveries & Rewards"
        placeholder="Items found, secrets uncovered, plot threads opened..."
        value={lootNotes}
        onChange={(e) => setLootNotes(e.target.value)}
        rows={3}
      />

      <TextArea
        label="Session Notes"
        placeholder="Write your session notes here — what happened, key moments, decisions made..."
        value={rawNotes}
        onChange={(e) => setRawNotes(e.target.value)}
        rows={8}
      />

      {/* AI Summary section */}
      <div className="space-y-2">
        <div className="flex items-center justify-between">
          <label className="text-txt-muted text-sm font-medium">AI Summary</label>
          <Button
            variant="secondary"
            size="sm"
            onClick={handleGenerateRecap}
            disabled={isNew || recapLoading || !rawNotes.trim()}
          >
            {recapLoading ? 'Generating...' : '✨ Generate Summary'}
          </Button>
        </div>
        {aiRecap ? (
          <div className="bg-elevated rounded-xl px-4 py-3 text-txt text-sm leading-relaxed prose prose-invert prose-sm max-w-none">
            <ReactMarkdown>{aiRecap}</ReactMarkdown>
          </div>
        ) : (
          <div className="bg-elevated rounded-xl px-4 py-4 text-txt-muted text-sm text-center">
            {isNew
              ? 'Save the session first, then generate a summary from your notes.'
              : 'No summary yet. Add session notes and click Generate Summary.'}
          </div>
        )}
      </div>

      {/* Actions */}
      <div className="flex gap-3 pt-2 border-t border-border-subtle">
        <Button
          variant="primary"
          onClick={handleSave}
          disabled={saveMutation.isPending}
        >
          {saveMutation.isPending ? 'Saving...' : isNew ? 'Create Session' : 'Save'}
        </Button>
        {!isNew && (
          <Button
            variant="danger"
            onClick={() => {
              toast('Delete this session?', {
                action: { label: 'Delete', onClick: () => deleteMutation.mutate() },
                cancel: { label: 'Cancel', onClick: () => {} },
              });
            }}
            disabled={deleteMutation.isPending}
          >
            Delete
          </Button>
        )}
      </div>
    </div>
  );
}

// ─── Sessions (main page) ─────────────────────────────────────────────────────

export default function Sessions({ user }) {
  const { activeVaultId } = useVault();
  const navigate = useNavigate();
  const vaultId = activeVaultId || '';
  const [selectedId, setSelectedId] = useState(null);
  const [isNew, setIsNew] = useState(false);
  const [search, setSearch] = useState('');

  const { data: listData, isLoading, isError, refetch } = useQuery({
    queryKey: ['sessions', vaultId],
    queryFn: () => sessions.list(vaultId),
    enabled: !!vaultId,
  });

  useEffect(() => {
    if (isError) toast.error('Failed to load sessions');
  }, [isError]);

  const items = listData?.items || [];
  const filtered = search
    ? items.filter((s) => s.title.toLowerCase().includes(search.toLowerCase()))
    : items;

  const handleNewSession = () => {
    setSelectedId(null);
    setIsNew(true);
  };

  const handleSelect = (id) => {
    setSelectedId(id);
    setIsNew(false);
  };

  const handleSaved = (id) => {
    setSelectedId(id);
    setIsNew(false);
  };

  const handleDeleted = () => {
    setSelectedId(null);
    setIsNew(false);
  };

  const participantCount = (p) =>
    p ? p.split(',').filter((s) => s.trim()).length : 0;

  if (!activeVaultId) {
    return (
      <div className="h-full flex flex-col items-center justify-center gap-3 text-txt-muted">
        <Layers size={48} className="opacity-20" />
        <p className="text-sm font-medium">No vault selected</p>
        <p className="text-xs text-center max-w-xs">Select or create a vault to log sessions.</p>
        <button
          onClick={() => navigate('/vaults')}
          className="mt-1 text-xs bg-accent text-white px-4 py-2 rounded-lg hover:bg-accent/90 transition-colors"
        >
          Go to Vaults
        </button>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full overflow-hidden">
      {/* Page header */}
      <div className="flex items-center justify-between px-6 py-4 border-b border-border-subtle flex-shrink-0">
        <div>
          <h1 className="text-2xl font-bold text-txt">Sessions</h1>
          <p className="text-sm text-txt-secondary mt-0.5">Story logs and world events.</p>
        </div>
        {activeVaultId && (
          <button
            onClick={handleNewSession}
            className="flex items-center gap-1.5 px-3 py-2 bg-accent text-white rounded-lg text-sm font-semibold hover:bg-accent/90 transition"
          >
            <Plus size={15} />
            New Session
          </button>
        )}
      </div>

      {/* Body */}
      <div className="flex flex-1 overflow-hidden">
        {/* Left panel — session list */}
        <div className="w-80 flex-shrink-0 flex flex-col bg-surface border-r border-border-subtle">
          <div className="px-4 pt-4 pb-3 border-b border-border-subtle">
            <input
              placeholder="Search sessions…"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="w-full bg-elevated rounded-lg px-3 py-2 text-sm text-txt border border-transparent focus:border-accent focus:outline-none placeholder:text-txt-muted"
            />
          </div>

          <div className="flex-1 overflow-y-auto p-3 space-y-1">
            {isLoading ? (
              <div className="space-y-2 pt-1">
                {Array.from({ length: 4 }).map((_, i) => <SkeletonListItem key={i} />)}
              </div>
            ) : isError ? (
              <div className="flex flex-col items-center gap-2 py-6 text-center">
                <AlertCircle size={20} className="text-red-400 opacity-70" />
                <p className="text-txt-muted text-xs">Failed to load sessions.</p>
                <button onClick={() => refetch()} className="text-xs text-accent hover:underline">
                  Retry
                </button>
              </div>
            ) : filtered.length === 0 ? (
              <div className="flex flex-col items-center justify-center h-40 text-center space-y-2">
                <div className="text-4xl">📜</div>
                <p className="text-txt-muted text-sm">
                  {search ? 'No sessions match your search.' : 'No sessions yet. Create your first one!'}
                </p>
              </div>
            ) : (
              filtered.map((s) => {
                const isActive = !isNew && selectedId === s.id;
                const pCount = participantCount(s.participants);
                return (
                  <button
                    key={s.id}
                    onClick={() => handleSelect(s.id)}
                    className={`w-full text-left rounded-xl px-3 py-3 transition-all ${
                      isActive
                        ? 'bg-accent/10 border border-accent/30'
                        : 'hover:bg-hover'
                    }`}
                  >
                    <p className="font-semibold text-txt text-sm truncate">{s.title}</p>
                    <div className="flex gap-3 mt-0.5 text-xs text-txt-muted">
                      <span>{s.session_date || 'No date'}</span>
                      {pCount > 0 && (
                        <span>{pCount} character{pCount !== 1 ? 's' : ''}</span>
                      )}
                      {s.xp_gained > 0 && (
                        <span>⭐ {s.xp_gained} pts</span>
                      )}
                    </div>
                  </button>
                );
              })
            )}
          </div>
        </div>

        {/* Right panel — session detail */}
        <div className="flex-1 flex flex-col overflow-hidden bg-base">
          {selectedId || isNew ? (
            <SessionDetail
              key={isNew ? 'new' : selectedId}
              sessionId={selectedId}
              isNew={isNew}
              vaultId={vaultId}
              ownerId={user?.id}
              onSaved={handleSaved}
              onDeleted={handleDeleted}
            />
          ) : (
            <div className="flex flex-col items-center justify-center h-full text-center space-y-3">
              <div className="text-5xl">📜</div>
              <p className="text-txt-muted">Select a session or create a new one.</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
