import { useState, useRef, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
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

export default function Chat() {
  const navigate = useNavigate();
  const { activeVaultId } = useVault();
  const storageKey = `ws_chat_${activeVaultId || 'global'}`;

  // ── Messages — persisted in localStorage ───────────────────────────────────
  const [messages, setMessages] = useState([]);
  const [prompt, setPrompt] = useState('');
  const [loading, setLoading] = useState(false);
  const [streamingMode, setStreamingMode] = useState(false);
  const [sessionTokens, setSessionTokens] = useState(0);
  const [saveStatus, setSaveStatus] = useState('');
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
  });

  // Also check whether the current user has a personal key stored; used to
  // suppress the "AI not configured" banner when the user can actually use AI.
  const { data: keyStatus } = useQuery({
    queryKey: ['ai-key-settings'],
    queryFn: aiSettings.get,
    retry: false,
  });

  const historyLimit = settingsData?.ai_history_limit ?? 10;

  // Initialize streaming mode from saved setting
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
      const response = await ai.ask(userPrompt, history, activeVaultId);
      const msgTokens = (response.prompt_tokens || 0) + (response.completion_tokens || 0);
      setSessionTokens((prev) => prev + msgTokens);
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
        setMessages((prev) => prev.slice(0, -1)); // remove the user message optimistic update
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
        body: JSON.stringify({ prompt: userPrompt, history, vault_id: activeVaultId }),
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

      // Update token count for streamed message
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

  const handleClear = () => {
    setMessages([]);
    setPrompt('');
    setSessionTokens(0);
  };

  const handleSaveToNote = async () => {
    if (messages.length === 0) return;
    const timestamp = new Date().toISOString().replace(/[:.]/g, '-').slice(0, 19);
    const content = messages
      .filter((m) => m.role !== 'error')
      .map((m) => (m.role === 'user' ? `**User:** ${m.content}` : `**AI:** ${m.content}`))
      .join('\n\n');

    try {
      await notes.create(`Chat ${timestamp}`, content, null, ['ai-chat']);
      setSaveStatus('Saved to Browse → Chat folder');
      setTimeout(() => setSaveStatus(''), 3000);
    } catch (err) {
      setSaveStatus('Failed to save: ' + err.message);
      setTimeout(() => setSaveStatus(''), 3000);
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
    (aiStatus?.ready || keyStatus?.has_personal_key ?? false);  // legacy fallback

  return (
    <div className="p-10 space-y-6 flex flex-col h-full">
      {/* Header */}
      <div className="flex items-start justify-between">
        <SectionHeader
          title="✦ AI Assistant"
          subtitle="Ask anything about your world, lore, or notes."
        />
        <div className="flex items-center gap-3 flex-shrink-0">
          <label className="flex items-center gap-2 text-sm text-txt-muted cursor-pointer">
            <input
              type="checkbox"
              checked={streamingMode}
              onChange={(e) => setStreamingMode(e.target.checked)}
              className="w-4 h-4 rounded bg-elevated border-2 border-txt-muted accent-accent"
            />
            Streaming
          </label>
          {saveStatus && (
            <span className="text-accent text-xs font-medium bg-accent/10 px-3 py-1.5 rounded-lg">
              {saveStatus}
            </span>
          )}
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
      {aiStatus && !userCanUseAi && (
        <div className="mx-4 mt-4 p-3 bg-yellow-500/10 border border-yellow-500/30 rounded-xl text-sm text-yellow-400">
          AI is not configured. Add your OpenAI key in{' '}
          <button onClick={() => navigate('/settings')} className="underline font-medium">Settings → AI</button>.
        </div>
      )}
      {aiStatus?.ready && !aiStatus?.index_built && (
        <div className="mx-4 mt-2 p-2 bg-accent/10 border border-accent/20 rounded-xl text-xs text-accent">
          Vault index is building in the background — AI will have full context shortly.
        </div>
      )}

      {/* Chat History */}
      <div className="flex-1 overflow-y-auto space-y-4">
        {messages.length === 0 ? (
          <div className="h-full flex items-center justify-center">
            <div className="text-center">
              <div className="text-5xl mb-4">✦</div>
              <p className="text-txt-secondary text-lg font-medium">Ask anything about your world</p>
              <p className="text-txt-muted text-sm mt-1">Characters, lore, locations, history — your AI knows your vault.</p>
            </div>
          </div>
        ) : (
          messages.map((msg) => (
            <div
              key={msg.id}
              className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}
            >
              <div>
                <div
                  className={`max-w-xs lg:max-w-2xl px-4 py-4 rounded-xl ${
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
                </div>
                {/* Per-message token count + cost estimate */}
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
            <Card className="px-4 py-4 max-w-xs lg:max-w-md">
              <div className="flex items-center gap-2">
                <div className="w-2 h-2 bg-accent rounded-full animate-pulse" />
                <p className="text-txt-secondary text-sm">Thinking...</p>
              </div>
            </Card>
          </div>
        )}
        <div ref={chatEndRef} />
      </div>

      {/* Session token total + cost */}
      {sessionTokens > 0 && (
        <p className="text-xs text-txt-muted text-right -mb-2">
          Session: {sessionTokens.toLocaleString()} tokens · ${sessionCost.toFixed(5)} est.
        </p>
      )}

      {/* Input Area */}
      <Card className="p-6 space-y-4">
        <TextArea
          placeholder="Ask about your world..."
          value={prompt}
          onChange={(e) => setPrompt(e.target.value)}
          onKeyDown={handleKeyDown}
          disabled={loading}
          title="Ctrl+Enter to send"
        />
        <div className="flex gap-3">
          <Button
            variant="primary"
            onClick={handleAsk}
            disabled={loading || !prompt.trim()}
            className="flex-1"
            title="Ctrl+Enter to send"
          >
            {loading ? 'Thinking...' : '✦ Ask AI'}
          </Button>
          <Button
            variant="ghost"
            onClick={handleClear}
            disabled={loading}
            className="flex-1"
          >
            Clear
          </Button>
        </div>
      </Card>
    </div>
  );
}
