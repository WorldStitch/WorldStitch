import { useState, useRef, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import ReactMarkdown from 'react-markdown';
import { toast } from 'sonner';
import SectionHeader from '@/components/SectionHeader';
import Card from '@/components/Card';
import Button from '@/components/Button';
import { TextArea } from '@/components/Input';
import { ai, aiSettings, notes, settings, getApiBase, isRateLimitError, RATE_LIMIT_MSG } from '@/api';
import { useVault } from '@/context/VaultContext';

const COST_PER_TOKEN = 0.000003;
// Max messages kept in localStorage to avoid quota errors (~200 messages ≈ a few KB)
const MAX_STORED_MESSAGES = 200;

const MODES = [
  { key: 'lore',    label: 'Lore Assistant' },
  { key: 'writing', label: 'Writing Helper' },
  { key: 'gm',      label: 'GM Prep' },
];

// ── Export helpers ────────────────────────────────────────────────────────────

function buildMarkdown(messages, vaultName) {
  const date = new Date().toLocaleDateString('en-US', {
    year: 'numeric', month: 'long', day: 'numeric',
  });
  const header = `# WorldStitch AI Chat\n**Vault:** ${vaultName || 'Unknown'}\n**Date:** ${date}\n\n---\n\n`;
  const body = messages
    .filter((m) => m.role !== 'error')
    .map((m) => {
      const label = m.role === 'user' ? '**You**' : '**WorldStitch AI**';
      return `${label}\n\n${m.content}`;
    })
    .join('\n\n---\n\n');
  return header + body;
}

function downloadFile(content, filename, mimeType) {
  const blob = new Blob([content], { type: mimeType });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

// ── Main component ────────────────────────────────────────────────────────────

export default function Chat() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { activeVaultId, vaults = [] } = useVault();
  const activeVault = vaults.find((v) => v.id === activeVaultId);
  const vaultName = activeVault?.name || 'your vault';
  const storageKey = `ws_chat_${activeVaultId || 'global'}`;

  const [messages, setMessages] = useState([]);
  const [prompt, setPrompt] = useState('');
  const [loading, setLoading] = useState(false);
  const [streamingMode, setStreamingMode] = useState(false);
  const [sessionTokens, setSessionTokens] = useState(0);
  const [saveStatus, setSaveStatus] = useState('');
  const [mode, setMode] = useState('lore');
  const [conversationId, setConversationId] = useState(null);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [pinnedMsg, setPinnedMsg] = useState(null);
  const chatEndRef = useRef(null);

  // Ref used to skip persisting messages immediately after a localStorage load
  // (prevents an empty-array save from racing with the loaded data on mount/
  // vault-switch).
  const skipNextSaveRef = useRef(true);

  // Keep a ref to the current storageKey so the persist effect always uses the
  // latest value without being listed as a dependency (avoids the vault-switch
  // cross-contamination problem).
  const storageKeyRef = useRef(storageKey);
  storageKeyRef.current = storageKey;

  // Load history from localStorage whenever the active vault changes (incl. mount)
  useEffect(() => {
    skipNextSaveRef.current = true;
    try {
      const saved = localStorage.getItem(storageKey);
      setMessages(saved ? JSON.parse(saved) : []);
    } catch {
      setMessages([]);
    }
    setSessionTokens(0);
  }, [storageKey]); // eslint-disable-line react-hooks/exhaustive-deps

  // Persist messages on every change — but skip the very first run after a load
  // to avoid overwriting good data with the stale empty-array initial state.
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
    } catch {
      // Quota exceeded — silently ignore; chat still works, just won't persist
    }
  }, [messages]);

  // ── Remote data ────────────────────────────────────────────────────────────
  const { data: settingsData } = useQuery({
    queryKey: ['settings'],
    queryFn: settings.get,
  });

  const { data: aiStatus } = useQuery({
    queryKey: ['ai-status'],
    queryFn: ai.status,
    staleTime: 60_000,
    retry: false,
    // Poll every 3 s while the index is still building so the "Vault index
    // is building…" banner disappears as soon as the backend finishes.
    // Once index_built is true (or AI is not ready) polling stops.
    refetchInterval: (query) => {
      const data = query.state.data;
      if (data?.ready && data?.index_built === false) return 3_000;
      return false;
    },
  });

  // Also check whether the current user has a personal key stored; used to
  // suppress the "AI not configured" banner when the user can actually use AI.
  const { data: keyStatus } = useQuery({
    queryKey: ['ai-key-settings'],
    queryFn: aiSettings.get,
    retry: false,
  });

  // ── Conversation history query ────────────────────────────────────────────
  const { data: conversations = [] } = useQuery({
    queryKey: ['ai-conversations', activeVaultId],
    queryFn: () => (activeVaultId ? ai.listConversations(activeVaultId) : []),
    enabled: !!activeVaultId,
    staleTime: 30_000,
  });

  const deleteConversationMutation = useMutation({
    mutationFn: (id) => ai.deleteConversation(id),
    onSuccess: () =>
      queryClient.invalidateQueries({ queryKey: ['ai-conversations', activeVaultId] }),
  });

  const historyLimit = settingsData?.ai_history_limit ?? 10;

  useEffect(() => {
    if (settingsData?.streaming_enabled !== undefined) {
      setStreamingMode(Boolean(settingsData.streaming_enabled));
    }
  }, [settingsData?.streaming_enabled]);

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, loading]);

  const nextId = () => `msg-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;

  // ── Ask handlers ───────────────────────────────────────────────────────────
  // ── New chat ──────────────────────────────────────────────────────────────
  const handleNewChat = () => {
    setMessages([]);
    setPrompt('');
    setSessionTokens(0);
    setConversationId(null);
  };

  // ── Load past conversation ────────────────────────────────────────────────
  const handleLoadConversation = (conv) => {
    setMessages(
      conv.messages.map((m) => ({
        id: nextId(),
        role: m.role,
        content: m.content,
        tokens: m.tokens,
      }))
    );
    setConversationId(conv.id);
    setSessionTokens(0);
    setSidebarOpen(false);
  };

  // ── Ask (regular) ─────────────────────────────────────────────────────────
  const handleAsk = async () => {
    if (!prompt.trim() || loading) return;

    const userMessage = { id: nextId(), role: 'user', content: prompt };
    const history = messages
      .slice(-historyLimit)
      .map((m) => ({ role: m.role, content: m.content }));
    setMessages((prev) => [...prev, userMessage]);
    setPrompt('');
    setLoading(true);

    if (streamingMode) {
      await handleStreamingAsk(prompt, history);
    } else {
      await handleRegularAsk(prompt, history);
    }
  };

  const handleRegularAsk = async (userPrompt, history) => {
    try {
      const response = await ai.ask(userPrompt, history, activeVaultId, mode, conversationId);
      const msgTokens = (response.prompt_tokens || 0) + (response.completion_tokens || 0);
      setSessionTokens((prev) => prev + msgTokens);
      if (response.conversation_id) {
        setConversationId(response.conversation_id);
        queryClient.invalidateQueries({ queryKey: ['ai-conversations', activeVaultId] });
      }
      setMessages((prev) => [
        ...prev,
        {
          id: nextId(),
          role: 'assistant',
          content: response.response,
          tokens: msgTokens,
        },
      ]);
    } catch (err) {
      if (isRateLimitError(err)) {
        toast.error(RATE_LIMIT_MSG);
        setMessages((prev) => prev.slice(0, -1));
      } else {
        setMessages((prev) => [
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
    setMessages((prev) => [...prev, { id: assistantId, role: 'assistant', content: '' }]);

    try {
      const { getToken } = await import('@/api');
      const token = getToken();
      const res = await fetch(`${getApiBase()}/ai/ask/stream`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({
          prompt: userPrompt,
          history,
          vault_id: activeVaultId,
          mode,
          conversation_id: conversationId,
        }),
      });

      if (res.status === 429) {
        toast.error(RATE_LIMIT_MSG);
        setMessages((prev) => prev.filter((m) => m.id !== assistantId).slice(0, -1));
        return;
      }
      if (!res.ok) {
        // Try to pull a meaningful detail string from the JSON error body
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

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        const chunk = decoder.decode(value, { stream: true });
        const lines = chunk.split('\n');
        for (const line of lines) {
          if (!line.startsWith('data: ')) continue;
          const data = line.slice(6);
          if (data === '[DONE]') break;
          try {
            const parsed = JSON.parse(data);
            if (parsed.error) throw new Error(parsed.error);
            if (parsed.conversation_id) {
              setConversationId(parsed.conversation_id);
              queryClient.invalidateQueries({ queryKey: ['ai-conversations', activeVaultId] });
            }
            if (parsed.token) {
              streamTokenCount++;
              setMessages((prev) =>
                prev.map((m) =>
                  m.id === assistantId ? { ...m, content: m.content + parsed.token } : m
                )
              );
            }
          } catch {
            // ignore parse errors on individual chunks
          }
        }
      }

      if (streamTokenCount > 0) {
        setSessionTokens((prev) => prev + streamTokenCount);
        setMessages((prev) =>
          prev.map((m) =>
            m.id === assistantId ? { ...m, tokens: streamTokenCount } : m
          )
        );
      }
    } catch (err) {
      setMessages((prev) =>
        prev.map((m) =>
          m.id === assistantId ? { ...m, role: 'error', content: `Error: ${err.message}` } : m
        )
      );
    } finally {
      setLoading(false);
    }
  };

  // ── Save to Note (full conversation) ─────────────────────────────────────
  const handleSaveToNote = async () => {
    if (messages.length === 0) return;
    const timestamp = new Date().toISOString().replace(/[:.]/g, '-').slice(0, 19);
    const content = messages
      .filter((m) => m.role !== 'error')
      .map((m) => (m.role === 'user' ? `**User:** ${m.content}` : `**AI:** ${m.content}`))
      .join('\n\n');

    try {
      await notes.create(`Chat ${timestamp}`, content, null, ['ai-chat'], {}, activeVaultId);
      setSaveStatus('Saved to Browse');
      setTimeout(() => setSaveStatus(''), 3000);
    } catch (err) {
      setSaveStatus('Failed to save: ' + err.message);
      setTimeout(() => setSaveStatus(''), 3000);
    }
  };

  // ── Export as markdown ────────────────────────────────────────────────────
  const handleExport = () => {
    if (messages.length === 0) return;
    const md = buildMarkdown(messages, vaultName);
    const timestamp = new Date().toISOString().slice(0, 10);
    downloadFile(md, `worldstitch-chat-${timestamp}.md`, 'text/markdown');
  };

  // ── Pin single AI message to Browse ──────────────────────────────────────
  const handlePinMessage = async (msg) => {
    try {
      const timestamp = new Date().toISOString().replace(/[:.]/g, '-').slice(0, 19);
      await notes.create(
        `AI Note ${timestamp}`,
        msg.content,
        null,
        ['ai-note'],
        {},
        activeVaultId
      );
      setPinnedMsg(msg.id);
      setTimeout(() => setPinnedMsg(null), 2000);
      toast.success('Saved to Browse');
    } catch (err) {
      toast.error('Failed to pin: ' + err.message);
    }
  };

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && e.ctrlKey) {
      handleAsk();
    }
  };

  const sessionCost = sessionTokens * COST_PER_TOKEN;

  // ── Banner logic ────────────────────────────────────────────────────────────
  // Show "AI not configured" only when the user genuinely can't use AI:
  //   - The new user_can_use_ai field (from the updated /ai/status endpoint) takes
  //     priority when present — it already factors in personal keys and role.
  //   - Legacy fallback: hide the banner if the user has a personal key saved,
  //     even if the platform key is absent (personal key always works).
  const userCanUseAi =
    aiStatus?.user_can_use_ai ??          // new field from updated backend
    ((aiStatus?.ready || keyStatus?.has_personal_key) ?? false);  // legacy fallback

  return (
    <div className="flex h-full overflow-hidden">
      {/* ── Conversation sidebar ── */}
      {sidebarOpen && (
        <aside className="w-64 flex-shrink-0 border-r border-border bg-base flex flex-col">
          <div className="p-4 border-b border-border flex items-center justify-between">
            <span className="text-sm font-semibold text-txt">History</span>
            <button
              onClick={() => setSidebarOpen(false)}
              className="text-txt-muted hover:text-txt text-lg leading-none"
            >
              ×
            </button>
          </div>
          <div className="flex-1 overflow-y-auto p-2 space-y-1">
            {conversations.length === 0 ? (
              <p className="text-xs text-txt-muted p-2">No past conversations yet.</p>
            ) : (
              conversations.map((conv) => (
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
                    className="opacity-0 group-hover:opacity-100 text-txt-muted hover:text-danger text-xs mt-0.5"
                    title="Delete conversation"
                    onClick={(e) => {
                      e.stopPropagation();
                      deleteConversationMutation.mutate(conv.id);
                      if (conv.id === conversationId) handleNewChat();
                    }}
                  >
                    ✕
                  </button>
                </div>
              ))
            )}
          </div>
          <div className="p-2 border-t border-border">
            <Button variant="secondary" size="sm" onClick={handleNewChat} className="w-full">
              + New Chat
            </Button>
          </div>
        </aside>
      )}

      {/* ── Main chat panel ── */}
      <div className="flex-1 flex flex-col overflow-hidden p-6 space-y-4">
        {/* Header */}
        <div className="flex items-start justify-between flex-shrink-0">
          <div className="flex items-center gap-3">
            <button
              onClick={() => setSidebarOpen((o) => !o)}
              className="text-txt-muted hover:text-txt p-1.5 rounded-lg hover:bg-elevated transition-colors"
              title="Conversation history"
            >
              ☰
            </button>
            <SectionHeader
              title="✦ AI Assistant"
              subtitle="Ask anything about your world, lore, or notes."
            />
          </div>
          <div className="flex items-center gap-2 flex-shrink-0">
            <label className="flex items-center gap-1.5 text-xs text-txt-muted cursor-pointer">
              <input
                type="checkbox"
                checked={streamingMode}
                onChange={(e) => setStreamingMode(e.target.checked)}
                className="w-3.5 h-3.5 rounded bg-elevated border border-txt-muted accent-accent"
              />
              Stream
            </label>
            {saveStatus && (
              <span className="text-accent text-xs font-medium bg-accent/10 px-2 py-1 rounded-lg">
                {saveStatus}
              </span>
            )}
            <Button
              variant="ghost"
              size="sm"
              onClick={handleExport}
              disabled={messages.length === 0}
              title="Export conversation as markdown"
            >
              Export
            </Button>
            <Button
              variant="secondary"
              size="sm"
              onClick={handleSaveToNote}
              disabled={messages.length === 0 || loading}
            >
              Save to Note
            </Button>
          </div>
        </div>

        {/* AI Status Banners */}
        {aiStatus && !aiStatus.ready && (
          <div className="p-3 bg-yellow-500/10 border border-yellow-500/30 rounded-xl text-sm text-yellow-400 flex-shrink-0">
            AI is not configured. Add your OpenAI key in{' '}
            <button onClick={() => navigate('/settings')} className="underline font-medium">
              Settings → AI
            </button>
            .
          </div>
        )}
        {aiStatus?.ready && !aiStatus?.index_built && (
          <div className="p-2 bg-accent/10 border border-accent/20 rounded-xl text-xs text-accent flex-shrink-0">
            Vault index is building in the background — AI will have full context shortly.
          </div>
        )}

        {/* Mode selector */}
        <div className="flex gap-1 flex-shrink-0">
          {MODES.map((m) => (
            <button
              key={m.key}
              onClick={() => setMode(m.key)}
              className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${
                mode === m.key
                  ? 'bg-accent text-white'
                  : 'bg-elevated text-txt-muted hover:text-txt hover:bg-card'
              }`}
            >
              {m.label}
            </button>
          ))}
        </div>

        {/* Chat History */}
        <div className="flex-1 overflow-y-auto space-y-3 pr-1">
          {messages.length === 0 ? (
            <div className="h-full flex items-center justify-center">
              <div className="text-center">
                <div className="text-5xl mb-4">✦</div>
                <p className="text-txt-secondary text-lg font-medium">Ask anything about your world</p>
                <p className="text-txt-muted text-sm mt-1">
                  Characters, lore, locations, history — your AI knows your vault.
                </p>
              </div>
            </div>
          ) : (
            messages.map((msg) => (
              <div
                key={msg.id}
                className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}
              >
                <div className="max-w-xs lg:max-w-2xl">
                  <div
                    className={`relative group px-4 py-3 rounded-xl ${
                      msg.role === 'user'
                        ? 'bg-accent/10 text-txt'
                        : msg.role === 'error'
                        ? 'bg-danger/10 text-danger border border-danger/20'
                        : 'bg-card text-txt'
                    }`}
                  >
                    {msg.role === 'assistant' ? (
                      <ReactMarkdown className="prose prose-sm prose-invert max-w-none text-txt">
                        {msg.content || '…'}
                      </ReactMarkdown>
                    ) : (
                      <p className="text-sm whitespace-pre-wrap">{msg.content}</p>
                    )}

                    {/* Pin to Browse — assistant messages only */}
                    {msg.role === 'assistant' && msg.content && (
                      <button
                        onClick={() => handlePinMessage(msg)}
                        className={`absolute top-2 right-2 p-1 rounded transition-all text-sm ${
                          pinnedMsg === msg.id
                            ? 'text-accent opacity-100'
                            : 'text-txt-muted opacity-0 group-hover:opacity-100 hover:text-accent'
                        }`}
                        title="Save this response to Browse"
                      >
                        {pinnedMsg === msg.id ? '★' : '☆'}
                      </button>
                    )}
                  </div>

                  {/* Per-message token count */}
                  {msg.role === 'assistant' && msg.tokens > 0 && (
                    <p className="text-[10px] text-txt-muted mt-0.5 px-1">
                      {msg.tokens.toLocaleString()} tokens · ${(msg.tokens * COST_PER_TOKEN).toFixed(5)}
                    </p>
                  )}
                </div>
              </div>
            ))
          )}

          {loading && !streamingMode && (
            <div className="flex justify-start">
              <Card className="px-4 py-3 max-w-xs lg:max-w-md">
                <div className="flex items-center gap-2">
                  <div className="w-2 h-2 bg-accent rounded-full animate-pulse" />
                  <p className="text-txt-secondary text-sm">Thinking...</p>
                </div>
              </Card>
            </div>
          )}
          <div ref={chatEndRef} />
        </div>

        {/* Session total */}
        {sessionTokens > 0 && (
          <p className="text-xs text-txt-muted text-right flex-shrink-0 -mb-2">
            Session: {sessionTokens.toLocaleString()} tokens · ${sessionCost.toFixed(5)} est.
          </p>
        )}

        {/* Input */}
        <Card className="p-4 space-y-3 flex-shrink-0">
          <TextArea
            placeholder="Ask about your world..."
            value={prompt}
            onChange={(e) => setPrompt(e.target.value)}
            onKeyDown={handleKeyDown}
            disabled={loading}
            title="Ctrl+Enter to send"
          />
          <div className="flex gap-2">
            <Button
              variant="primary"
              onClick={handleAsk}
              disabled={loading || !prompt.trim()}
              className="flex-1"
              title="Ctrl+Enter to send"
            >
              {loading ? 'Thinking...' : '✦ Ask AI'}
            </Button>
            <Button variant="ghost" onClick={handleNewChat} disabled={loading}>
              Clear
            </Button>
          </div>
        </Card>
      </div>
    </div>
  );
}
