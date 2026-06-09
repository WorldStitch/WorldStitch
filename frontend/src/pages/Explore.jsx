import { useState, useRef, useEffect } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import ReactMarkdown from 'react-markdown';
import { toast } from 'sonner';
import {
  ArrowUp, Plus, X, History, Square, BookOpen, Compass,
  FileText, User as UserIcon, Map as MapIcon,
} from 'lucide-react';
import { ai, notes, settings, getApiBase, getToken, isRateLimitError, RATE_LIMIT_MSG } from '@/api';
import { useVault } from '@/context/VaultContext';
import ContextTrace from '@/components/ContextTrace';

const MAX_STORED_MESSAGES = 200;

const SCHOLAR_CHIPS = [
  'Who is [character name]?',
  'Describe the history of [location]',
  'What factions exist in this world?',
  'Summarize recent events',
];

const IMMERSIVE_CHIPS = [
  'I step into the tavern…',
  'What do I see at the crossroads?',
  'I ask the innkeeper about rumors',
  'Describe the city at dusk',
];

const ENTITY_ICONS = { note: FileText, character: UserIcon, map: MapIcon };

// ── Entity badge ───────────────────────────────────────────────────────────────

function EntityBadge({ entity }) {
  if (!entity) return null;
  const Icon = ENTITY_ICONS[entity.type] || FileText;
  return (
    <div className="flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-accent/10 border border-accent/20 text-xs text-accent">
      <Icon size={11} />
      <span className="max-w-[160px] truncate">{entity.name}</span>
    </div>
  );
}

// ── Scholar/Immersive pill toggle ──────────────────────────────────────────────

function SubModeToggle({ scholar, onChange }) {
  return (
    <div className="flex items-center bg-elevated rounded-full p-0.5 border border-border/50 gap-0.5">
      <button
        onClick={() => onChange(true)}
        className={`flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-medium transition-all ${
          scholar
            ? 'bg-accent text-white shadow-sm'
            : 'text-txt-muted hover:text-txt'
        }`}
      >
        <BookOpen size={11} />
        Scholar
      </button>
      <button
        onClick={() => onChange(false)}
        className={`flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-medium transition-all ${
          !scholar
            ? 'bg-accent text-white shadow-sm'
            : 'text-txt-muted hover:text-txt'
        }`}
      >
        <Compass size={11} />
        Immersive
      </button>
    </div>
  );
}

// ── AI message bubble ──────────────────────────────────────────────────────────

function AiMessage({ msg, scholar, onPin, pinned }) {
  if (scholar) {
    return (
      <div className="max-w-[75%] group">
        <div className="relative bg-elevated text-txt px-4 py-3.5 rounded-2xl rounded-tl-md">
          <ReactMarkdown className="prose prose-sm prose-invert max-w-none text-txt leading-relaxed [&>*:last-child]:mb-0">
            {msg.content || '…'}
          </ReactMarkdown>
          {msg.content && (
            <button
              onClick={() => onPin(msg)}
              className={`absolute top-2 right-2 p-1 rounded transition-all text-sm ${
                pinned
                  ? 'text-accent opacity-100'
                  : 'text-txt-muted opacity-0 group-hover:opacity-100 hover:text-accent'
              }`}
              title="Save to Browse"
            >
              {pinned ? '★' : '☆'}
            </button>
          )}
        </div>
        <ContextTrace trace={msg.retrieval_trace} subtle={false} />
        {msg.tokens > 0 && (
          <p className="text-[10px] text-txt-muted mt-0.5 px-1">
            {msg.tokens.toLocaleString()} tokens
          </p>
        )}
      </div>
    );
  }

  // Immersive style — editorial, narrative feel
  return (
    <div className="max-w-[80%] group">
      <div className="relative border-l-2 border-accent/30 pl-4 py-0.5">
        <ReactMarkdown className="prose prose-sm prose-invert max-w-none text-txt leading-[1.8] italic [&>*:last-child]:mb-0 [&_strong]:not-italic [&_strong]:font-semibold">
          {msg.content || '…'}
        </ReactMarkdown>
        {msg.content && (
          <button
            onClick={() => onPin(msg)}
            className={`absolute -top-0.5 -right-2 p-1 rounded transition-all text-sm ${
              pinned
                ? 'text-accent opacity-100'
                : 'text-txt-muted opacity-0 group-hover:opacity-100 hover:text-accent'
            }`}
            title="Save to Browse"
          >
            {pinned ? '★' : '☆'}
          </button>
        )}
      </div>
      <ContextTrace trace={msg.retrieval_trace} subtle={true} />
    </div>
  );
}

// ── Main component ─────────────────────────────────────────────────────────────

export default function Explore({ user }) {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [searchParams] = useSearchParams();
  const { activeVaultId, vaults = [] } = useVault();
  const storageKey = `ws_explore_${activeVaultId || 'global'}`;

  // Entity in context — passed via URL params from Browse/Characters/Maps
  const currentEntity = (() => {
    const id = searchParams.get('entityId');
    const name = searchParams.get('entityName');
    const type = searchParams.get('entityType');
    return id && name ? { id, name, type: type || 'note' } : null;
  })();

  const [messages, setMessages] = useState([]);
  const [prompt, setPrompt] = useState('');
  const [loading, setLoading] = useState(false);
  const [scholar, setScholar] = useState(true);
  const [conversationId, setConversationId] = useState(null);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [toolStatus, setToolStatus] = useState('');
  const [pinnedMsg, setPinnedMsg] = useState(null);

  const chatEndRef = useRef(null);
  const abortControllerRef = useRef(null);
  const textAreaRef = useRef(null);
  const skipNextSaveRef = useRef(true);
  const storageKeyRef = useRef(storageKey);
  storageKeyRef.current = storageKey;

  // ── Storage ─────────────────────────────────────────────────────────────────

  useEffect(() => {
    skipNextSaveRef.current = true;
    try {
      const saved = localStorage.getItem(storageKey);
      setMessages(saved ? JSON.parse(saved) : []);
    } catch {
      setMessages([]);
    }
  }, [storageKey]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (skipNextSaveRef.current) {
      skipNextSaveRef.current = false;
      return;
    }
    try {
      localStorage.setItem(
        storageKeyRef.current,
        JSON.stringify(messages.slice(-MAX_STORED_MESSAGES)),
      );
    } catch { /* quota exceeded */ }
  }, [messages]);

  // ── Scroll ──────────────────────────────────────────────────────────────────

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, loading]);

  // ── Queries ─────────────────────────────────────────────────────────────────

  const { data: settingsData } = useQuery({
    queryKey: ['settings'],
    queryFn: settings.get,
  });
  const streamingMode = settingsData?.streaming_enabled ?? false;
  const historyLimit = settingsData?.ai_history_limit ?? 10;

  const { data: aiStatus } = useQuery({
    queryKey: ['ai-status'],
    queryFn: ai.status,
    staleTime: 60_000,
    retry: false,
    refetchInterval: query => {
      const data = query.state.data;
      if (data?.ready && data?.index_built === false) return 3_000;
      return false;
    },
  });

  const { data: conversations = [] } = useQuery({
    queryKey: ['ai-explore-conversations', activeVaultId],
    queryFn: () => (activeVaultId ? ai.listConversations(activeVaultId) : []),
    enabled: !!activeVaultId,
    staleTime: 30_000,
  });

  const deleteConversationMutation = useMutation({
    mutationFn: id => ai.deleteConversation(id),
    onSuccess: () =>
      queryClient.invalidateQueries({ queryKey: ['ai-explore-conversations', activeVaultId] }),
  });

  // ── Utilities ────────────────────────────────────────────────────────────────

  const nextId = () => `msg-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;

  // ── Actions ──────────────────────────────────────────────────────────────────

  const handleCancel = () => abortControllerRef.current?.abort('user');

  const handleNewChat = () => {
    setMessages([]);
    setPrompt('');
    setConversationId(null);
  };

  const handleLoadConversation = conv => {
    setMessages(
      conv.messages.map(m => ({
        id: nextId(),
        role: m.role,
        content: m.content,
        tokens: m.tokens,
        retrieval_trace: m.retrieval_trace || null,
      })),
    );
    setConversationId(conv.id);
    setSidebarOpen(false);
  };

  const handlePinMessage = async msg => {
    try {
      const timestamp = new Date().toISOString().replace(/[:.]/g, '-').slice(0, 19);
      await notes.create(`Explore Note ${timestamp}`, msg.content, null, ['explore', 'ai-note'], {}, activeVaultId);
      setPinnedMsg(msg.id);
      setTimeout(() => setPinnedMsg(null), 2000);
      toast.success('Saved to Browse');
    } catch (err) {
      toast.error('Failed to save: ' + err.message);
    }
  };

  // ── Ask ──────────────────────────────────────────────────────────────────────

  const handleAsk = async () => {
    if (!prompt.trim() || loading) return;

    const userMessage = { id: nextId(), role: 'user', content: prompt };
    const history = messages
      .slice(-historyLimit)
      .map(m => ({ role: m.role, content: m.content }));

    setMessages(prev => [...prev, userMessage]);
    setPrompt('');
    if (textAreaRef.current) textAreaRef.current.style.height = '36px';
    setLoading(true);

    if (streamingMode) {
      await handleStreamingAsk(prompt, history);
    } else {
      await handleRegularAsk(prompt, history);
    }
  };

  const buildRequestBody = (userPrompt, history) => ({
    prompt: userPrompt,
    history,
    vault_id: activeVaultId,
    mode: 'explore',
    sub_mode: scholar ? 'scholar' : 'immersive',
    conversation_id: conversationId,
    ...(currentEntity ? { current_entity: currentEntity } : {}),
  });

  const handleRegularAsk = async (userPrompt, history) => {
    try {
      const response = await ai.ask(userPrompt, history, activeVaultId, 'explore', conversationId, {
        sub_mode: scholar ? 'scholar' : 'immersive',
        current_entity: currentEntity,
      });
      const msgTokens = (response.prompt_tokens || 0) + (response.completion_tokens || 0);
      if (response.conversation_id) {
        setConversationId(response.conversation_id);
        queryClient.invalidateQueries({ queryKey: ['ai-explore-conversations', activeVaultId] });
      }
      setMessages(prev => [
        ...prev,
        {
          id: nextId(),
          role: 'assistant',
          content: response.response,
          tokens: msgTokens,
          retrieval_trace: response.retrieval_trace || null,
        },
      ]);
    } catch (err) {
      if (isRateLimitError(err)) {
        toast.error(RATE_LIMIT_MSG);
        setMessages(prev => prev.slice(0, -1));
      } else {
        setMessages(prev => [
          ...prev,
          { id: nextId(), role: 'error', content: `Error: ${err.message}` },
        ]);
      }
    } finally {
      setLoading(false);
    }
  };

  const handleStreamingAsk = async (userPrompt, history) => {
    const assistantId = nextId();
    setMessages(prev => [...prev, { id: assistantId, role: 'assistant', content: '' }]);

    const controller = new AbortController();
    abortControllerRef.current = controller;
    const timeoutId = setTimeout(() => controller.abort('timeout'), 30_000);

    try {
      const token = getToken();
      const res = await fetch(`${getApiBase()}/ai/ask/stream`, {
        method: 'POST',
        signal: controller.signal,
        headers: {
          'Content-Type': 'application/json',
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify(buildRequestBody(userPrompt, history)),
      });

      if (res.status === 429) {
        toast.error(RATE_LIMIT_MSG);
        setMessages(prev => prev.filter(m => m.id !== assistantId).slice(0, -1));
        return;
      }
      if (!res.ok) {
        let detail = `Stream error: ${res.status}`;
        try {
          const errBody = await res.json();
          if (errBody?.detail) detail = errBody.detail;
        } catch { /* ignore */ }
        throw new Error(detail);
      }

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let streamTokenCount = 0;
      let pendingTrace = null;
      let streamDone = false;
      let streamError = null;

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        const chunk = decoder.decode(value, { stream: true });
        for (const line of chunk.split('\n')) {
          if (!line.startsWith('data: ')) continue;
          const data = line.slice(6);
          if (data === '[DONE]') { streamDone = true; break; }
          try {
            const parsed = JSON.parse(data);
            if (parsed.error) { streamError = parsed.error; streamDone = true; break; }
            if (parsed.conversation_id) {
              setConversationId(parsed.conversation_id);
              queryClient.invalidateQueries({ queryKey: ['ai-explore-conversations', activeVaultId] });
            }
            if (parsed.tool_status !== undefined) setToolStatus(parsed.tool_status);
            if (parsed.retrieval_trace) pendingTrace = parsed.retrieval_trace;
            if (parsed.token) {
              streamTokenCount++;
              setMessages(prev =>
                prev.map(m =>
                  m.id === assistantId ? { ...m, content: m.content + parsed.token } : m,
                ),
              );
            }
          } catch { /* ignore parse errors */ }
        }
        if (streamDone) break;
      }

      if (streamError) throw new Error(streamError);

      setToolStatus('');
      if (streamTokenCount > 0) {
        setMessages(prev =>
          prev.map(m =>
            m.id === assistantId
              ? { ...m, tokens: streamTokenCount, retrieval_trace: pendingTrace }
              : m,
          ),
        );
      }
    } catch (err) {
      setToolStatus('');
      if (err.name === 'AbortError') {
        const reason = controller.signal.reason;
        if (reason === 'timeout') {
          setMessages(prev =>
            prev.map(m =>
              m.id === assistantId
                ? { ...m, role: 'error', content: 'Request timed out — try again' }
                : m,
            ),
          );
        } else {
          setMessages(prev => {
            const msg = prev.find(m => m.id === assistantId);
            return msg?.content ? prev : prev.filter(m => m.id !== assistantId);
          });
        }
      } else {
        setMessages(prev =>
          prev.map(m =>
            m.id === assistantId
              ? { ...m, role: 'error', content: `Error: ${err.message}` }
              : m,
          ),
        );
      }
    } finally {
      clearTimeout(timeoutId);
      abortControllerRef.current = null;
      setLoading(false);
    }
  };

  // ── Input handlers ────────────────────────────────────────────────────────────

  const handleKeyDown = e => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleAsk();
    }
  };

  const handlePromptChange = e => {
    setPrompt(e.target.value);
    e.target.style.height = 'auto';
    e.target.style.height = Math.min(e.target.scrollHeight, 200) + 'px';
  };

  const isEmpty = messages.length === 0 && !loading;
  const chips = scholar ? SCHOLAR_CHIPS : IMMERSIVE_CHIPS;
  const placeholder = scholar
    ? 'Ask about your world — history, characters, lore…'
    : 'Step into your world…';

  // ── Render ────────────────────────────────────────────────────────────────────

  return (
    <div className="flex h-full overflow-hidden">

      {/* ── Conversation sidebar ── */}
      {sidebarOpen && (
        <aside className="w-64 flex-shrink-0 border-r border-border bg-base flex flex-col">
          <div className="p-4 border-b border-border flex items-center justify-between">
            <span className="text-sm font-semibold text-txt">History</span>
            <button
              onClick={() => setSidebarOpen(false)}
              className="text-txt-muted hover:text-txt p-1 rounded-lg transition-colors"
            >
              <X size={15} />
            </button>
          </div>
          <div className="flex-1 overflow-y-auto p-2 space-y-1">
            {conversations.length === 0 ? (
              <p className="text-xs text-txt-muted p-2">No past conversations yet.</p>
            ) : (
              conversations.map(conv => (
                <div
                  key={conv.id}
                  className={`group flex items-start gap-1 rounded-lg px-2 py-2 cursor-pointer hover:bg-elevated ${
                    conv.id === conversationId ? 'bg-accent/10 text-accent' : 'text-txt'
                  }`}
                  onClick={() => handleLoadConversation(conv)}
                >
                  <div className="flex-1 min-w-0">
                    <p className="text-xs font-medium truncate">{conv.title}</p>
                    <p className="text-[10px] text-txt-muted">
                      {conv.updated_at ? new Date(conv.updated_at).toLocaleDateString() : ''}
                    </p>
                  </div>
                  <button
                    className="opacity-0 group-hover:opacity-100 text-txt-muted hover:text-danger text-xs mt-0.5 p-0.5 rounded"
                    title="Delete"
                    onClick={e => {
                      e.stopPropagation();
                      deleteConversationMutation.mutate(conv.id);
                      if (conv.id === conversationId) handleNewChat();
                    }}
                  >
                    <X size={12} />
                  </button>
                </div>
              ))
            )}
          </div>
          <div className="p-2 border-t border-border">
            <button
              onClick={handleNewChat}
              className="w-full flex items-center justify-center gap-1.5 px-3 py-2 rounded-lg bg-elevated text-txt-muted hover:text-txt hover:bg-card text-sm transition-colors"
            >
              <Plus size={14} />
              New
            </button>
          </div>
        </aside>
      )}

      {/* ── Main panel ── */}
      <div
        className={`flex-1 flex flex-col overflow-hidden min-w-0 transition-colors duration-300 ${
          !scholar ? 'bg-slate-950/20' : ''
        }`}
      >

        {/* ── Header ── */}
        <div className="flex items-center justify-between px-4 py-3 border-b border-border flex-shrink-0">
          <div className="flex items-center gap-3">
            <button
              onClick={() => setSidebarOpen(o => !o)}
              className="text-txt-muted hover:text-txt p-1.5 rounded-lg hover:bg-elevated transition-colors"
              title="Conversation history"
            >
              <History size={17} />
            </button>
            <span className="text-sm font-semibold text-txt">Explore</span>
            {currentEntity && <EntityBadge entity={currentEntity} />}
          </div>
          <div className="flex items-center gap-2">
            <SubModeToggle scholar={scholar} onChange={setScholar} />
            <button
              onClick={handleNewChat}
              disabled={loading}
              className="flex items-center gap-1 text-xs text-txt-muted hover:text-txt px-2.5 py-1.5 rounded-lg hover:bg-elevated transition-colors disabled:opacity-40"
            >
              <Plus size={13} />
              New
            </button>
          </div>
        </div>

        {/* ── Status banners ── */}
        {aiStatus && !aiStatus.ready && (
          <div className="px-4 py-2 bg-yellow-500/10 border-b border-yellow-500/20 text-sm text-yellow-400 flex-shrink-0">
            AI not configured.{' '}
            <button onClick={() => navigate('/settings')} className="underline font-medium">
              Add your key in Settings → AI
            </button>
          </div>
        )}
        {aiStatus?.ready && !aiStatus?.index_built && (
          <div className="px-4 py-1.5 bg-accent/5 border-b border-accent/10 text-xs text-accent flex-shrink-0">
            Building vault index — full context available shortly.
          </div>
        )}

        {/* ── Messages ── */}
        <div className="flex-1 overflow-y-auto px-4 md:px-8 py-6 space-y-5">

          {isEmpty ? (
            <div className="h-full flex flex-col items-center justify-center gap-6 pb-16">
              <div className="text-center">
                {scholar ? (
                  <>
                    <p className="text-4xl font-bold mb-3 text-accent">📚</p>
                    <p className="text-txt font-semibold text-xl">Scholar</p>
                    <p className="text-txt-muted text-sm mt-2 max-w-xs leading-relaxed">
                      Ask questions about your world. Get grounded answers drawn from your vault's actual lore.
                    </p>
                  </>
                ) : (
                  <>
                    <p className="text-4xl font-bold mb-3 text-accent">✦</p>
                    <p className="text-txt font-semibold text-xl">Immersive</p>
                    <p className="text-txt-muted text-sm mt-2 max-w-xs leading-relaxed">
                      Step into your world. The narrator knows your canon — explore it from the inside.
                    </p>
                  </>
                )}
              </div>
              <div className="flex flex-wrap gap-2 justify-center max-w-sm">
                {chips.map(chip => (
                  <button
                    key={chip}
                    onClick={() => {
                      setPrompt(chip);
                      textAreaRef.current?.focus();
                    }}
                    className="px-3 py-1.5 rounded-full text-xs font-medium transition-colors bg-accent/10 text-accent hover:bg-accent/20 border border-accent/20"
                  >
                    {chip}
                  </button>
                ))}
              </div>
            </div>
          ) : (
            <>
              {messages.map(msg => (
                <div
                  key={msg.id}
                  className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}
                >
                  {msg.role === 'user' ? (
                    <div className="max-w-[70%]">
                      <div className={`text-txt px-4 py-3 rounded-2xl rounded-tr-md ${
                        scholar ? 'bg-accent/15' : 'bg-elevated/60'
                      }`}>
                        <p className="text-sm whitespace-pre-wrap leading-relaxed">{msg.content}</p>
                      </div>
                    </div>
                  ) : msg.role === 'error' ? (
                    <div className="max-w-[75%] px-4 py-3 rounded-2xl rounded-tl-md bg-danger/10 border border-danger/20 text-danger text-sm">
                      {msg.content}
                    </div>
                  ) : (
                    <AiMessage
                      msg={msg}
                      scholar={scholar}
                      onPin={handlePinMessage}
                      pinned={pinnedMsg === msg.id}
                    />
                  )}
                </div>
              ))}

              {/* Loading indicator */}
              {loading && (
                <div className="flex justify-start">
                  <div className="bg-elevated px-4 py-3 rounded-2xl rounded-tl-md flex items-center gap-2.5">
                    <span className="w-2 h-2 rounded-full bg-accent animate-pulse" />
                    <span className="text-sm text-txt-secondary">
                      {toolStatus || (scholar ? 'Consulting the archives…' : 'The world stirs…')}
                    </span>
                    {streamingMode && (
                      <button
                        onClick={handleCancel}
                        className="p-0.5 rounded text-txt-muted hover:text-danger hover:bg-danger/10 transition-colors ml-1"
                        title="Cancel"
                      >
                        <Square size={13} />
                      </button>
                    )}
                  </div>
                </div>
              )}
            </>
          )}

          <div ref={chatEndRef} />
        </div>

        {/* ── Input area ── */}
        <div className="flex-shrink-0 border-t border-border px-4 py-3">
          <div className={`flex items-end gap-2 rounded-2xl px-3 py-2 border transition-colors duration-300 ${
            scholar
              ? 'bg-elevated border-border/50'
              : 'bg-elevated/80 border-accent/20'
          }`}>
            <textarea
              ref={textAreaRef}
              rows={1}
              value={prompt}
              onChange={handlePromptChange}
              onKeyDown={handleKeyDown}
              placeholder={placeholder}
              disabled={loading}
              className="flex-1 bg-transparent resize-none text-sm text-txt placeholder-txt-muted outline-none py-1.5 max-h-48 leading-relaxed disabled:opacity-60"
              style={{ height: '36px' }}
            />
            <button
              onClick={handleAsk}
              disabled={loading || !prompt.trim()}
              className={`p-2 rounded-xl transition-all flex-shrink-0 self-end ${
                loading || !prompt.trim()
                  ? 'bg-surface text-txt-muted cursor-not-allowed opacity-50'
                  : 'bg-accent hover:bg-accent/90 text-white shadow-sm'
              }`}
              title="Send (Enter)"
            >
              <ArrowUp size={17} />
            </button>
          </div>
          <p className="text-[10px] text-txt-muted mt-1.5 text-center">
            Enter to send · Shift+Enter for new line
          </p>
        </div>
      </div>
    </div>
  );
}
