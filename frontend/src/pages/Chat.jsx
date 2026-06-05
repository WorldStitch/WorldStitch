import { useState, useRef, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import ReactMarkdown from 'react-markdown';
import { toast } from 'sonner';
import { ArrowUp, Paperclip, Plus, ChevronDown, X, Square, History } from 'lucide-react';
import {
  ai, notes, settings, getApiBase, getToken,
  isRateLimitError, RATE_LIMIT_MSG,
} from '@/api';
import { useVault } from '@/context/VaultContext';

const COST_PER_TOKEN = 0.000003;
const MAX_STORED_MESSAGES = 200;

const DEVELOPER_ROLES = new Set(['owner', 'admin', 'mod', 'support', 'tester', 'system']);

const ALL_MODES = [
  {
    key: 'lore',
    label: 'Lore Assistant',
    placeholder: "Ask about your world's lore, history, or characters...",
    chips: ['Summarize my world', 'Find inconsistencies', 'Who is [character]?'],
    accentCls: 'text-accent',
    sendCls: 'bg-accent hover:bg-accent/90',
    chipCls: 'bg-accent/10 text-accent hover:bg-accent/20 border border-accent/20',
    dotCls: 'bg-accent',
  },
  {
    key: 'writing',
    label: 'Writing Helper',
    placeholder: "Let's write something together...",
    chips: ['Write a scene', 'Improve this passage', 'Draft character dialogue'],
    accentCls: 'text-purple-400',
    sendCls: 'bg-purple-500 hover:bg-purple-600',
    chipCls: 'bg-purple-500/10 text-purple-400 hover:bg-purple-500/20 border border-purple-500/20',
    dotCls: 'bg-purple-400',
  },
  {
    key: 'gm',
    label: 'GM Prep',
    placeholder: 'Plan your next session or generate content...',
    chips: ["Prep tonight's session", 'Generate 3 NPCs', 'Create encounter'],
    accentCls: 'text-amber-400',
    sendCls: 'bg-amber-500 hover:bg-amber-600',
    chipCls: 'bg-amber-500/10 text-amber-400 hover:bg-amber-500/20 border border-amber-500/20',
    dotCls: 'bg-amber-400',
  },
  {
    key: 'developer',
    label: 'Developer',
    placeholder: 'Run bulk operations, generate test data, debug...',
    chips: ['Create 20 test notes', 'List all notes', 'Clear test data'],
    accentCls: 'text-red-400',
    sendCls: 'bg-red-500 hover:bg-red-600',
    chipCls: 'bg-red-500/10 text-red-400 hover:bg-red-500/20 border border-red-500/20',
    dotCls: 'bg-red-400',
    adminOnly: true,
  },
];

// ── Helpers ───────────────────────────────────────────────────────────────────

function buildMarkdown(messages, vaultName) {
  const date = new Date().toLocaleDateString('en-US', {
    year: 'numeric', month: 'long', day: 'numeric',
  });
  const header = `# WorldStitch AI Chat\n**Vault:** ${vaultName || 'Unknown'}\n**Date:** ${date}\n\n---\n\n`;
  const body = messages
    .filter(m => m.role !== 'error')
    .map(m => {
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

function formatToolAction(action) {
  const r = action.result || {};
  switch (action.tool) {
    case 'create_note': return `Created note "${r.title || 'note'}"`;
    case 'create_folder': return `Created folder "${r.name || 'folder'}"`;
    case 'create_character': return `Created character "${r.name || 'character'}"`;
    case 'bulk_create_notes': return `Created ${r.created_count ?? 0} notes`;
    case 'update_note': return `Updated note "${r.title || 'note'}"`;
    case 'move_note': return `Moved note "${r.title || 'note'}"`;
    case 'delete_note': return `Deleted note "${r.title || 'note'}"`;
    case 'delete_character': return `Deleted character "${r.name || 'character'}"`;
    case 'delete_folder': return `Deleted folder "${r.name || 'folder'}"`;
    case 'search_vault': return `Searched vault — ${r.total ?? 0} results`;
    case 'get_note': return `Read note "${r.title || ''}"`;
    case 'list_notes': return `Listed ${r.total ?? 0} notes`;
    case 'list_characters': return `Listed ${r.total ?? 0} characters`;
    case 'create_relationship': return `Created "${r.relationship_type || 'relationship'}" relationship`;
    case 'add_tags': return 'Added tags to note';
    default: return action.tool.replace(/_/g, ' ');
  }
}

function ActionSummary({ actions }) {
  if (!actions?.length) return null;
  return (
    <div className="mt-2 px-3 py-2 bg-elevated/60 rounded-xl border border-border/40">
      <p className="text-[10px] text-txt-muted font-semibold uppercase tracking-wide mb-1.5">
        Actions taken
      </p>
      <ul className="space-y-1">
        {actions.map((a, i) => (
          <li key={i} className="flex items-center gap-2 text-xs text-txt-secondary">
            <span className="w-1.5 h-1.5 rounded-full bg-accent/70 flex-shrink-0" />
            {formatToolAction(a)}
          </li>
        ))}
      </ul>
    </div>
  );
}

// ── Main component ────────────────────────────────────────────────────────────

export default function Chat({ user }) {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { activeVaultId, vaults = [] } = useVault();
  const activeVault = vaults.find(v => v.id === activeVaultId);
  const vaultName = activeVault?.name || 'your vault';
  const storageKey = `ws_chat_${activeVaultId || 'global'}`;

  const canUseDeveloper = DEVELOPER_ROLES.has(user?.system_role);
  const MODES = ALL_MODES.filter(m => !m.adminOnly || canUseDeveloper);

  const [messages, setMessages] = useState([]);
  const [prompt, setPrompt] = useState('');
  const [loading, setLoading] = useState(false);
  const [mode, setMode] = useState('lore');
  const [modeOpen, setModeOpen] = useState(false);
  const [conversationId, setConversationId] = useState(null);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [toolStatus, setToolStatus] = useState('');
  const [sessionTokens, setSessionTokens] = useState(0);
  const [attachments, setAttachments] = useState([]);
  const [pinnedMsg, setPinnedMsg] = useState(null);
  const [saveStatus, setSaveStatus] = useState('');

  const chatEndRef = useRef(null);
  const abortControllerRef = useRef(null);
  const fileInputRef = useRef(null);
  const textAreaRef = useRef(null);
  const modeDropdownRef = useRef(null);
  const skipNextSaveRef = useRef(true);
  const storageKeyRef = useRef(storageKey);
  storageKeyRef.current = storageKey;

  const currentMode = MODES.find(m => m.key === mode) || MODES[0];

  // ── Storage ───────────────────────────────────────────────────────────────

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
      // Quota exceeded
    }
  }, [messages]);

  // ── Scroll & dropdown ────────────────────────────────────────────────────

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, loading]);

  useEffect(() => {
    const handle = e => {
      if (modeDropdownRef.current && !modeDropdownRef.current.contains(e.target)) {
        setModeOpen(false);
      }
    };
    document.addEventListener('mousedown', handle);
    return () => document.removeEventListener('mousedown', handle);
  }, []);

  // ── Queries ───────────────────────────────────────────────────────────────

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
    queryKey: ['ai-conversations', activeVaultId],
    queryFn: () => (activeVaultId ? ai.listConversations(activeVaultId) : []),
    enabled: !!activeVaultId,
    staleTime: 30_000,
  });

  const deleteConversationMutation = useMutation({
    mutationFn: id => ai.deleteConversation(id),
    onSuccess: () =>
      queryClient.invalidateQueries({ queryKey: ['ai-conversations', activeVaultId] }),
  });

  // ── Utilities ─────────────────────────────────────────────────────────────

  const nextId = () => `msg-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;

  const invalidateBrowse = () => {
    queryClient.invalidateQueries({ queryKey: ['notes'] });
    queryClient.invalidateQueries({ queryKey: ['folders'] });
    queryClient.invalidateQueries({ queryKey: ['characters'] });
  };

  // ── Chat actions ─────────────────────────────────────────────────────────

  const handleCancel = () => abortControllerRef.current?.abort('user');

  const handleNewChat = () => {
    setMessages([]);
    setPrompt('');
    setSessionTokens(0);
    setConversationId(null);
    setAttachments([]);
  };

  const handleLoadConversation = conv => {
    setMessages(
      conv.messages.map(m => ({
        id: nextId(),
        role: m.role,
        content: m.content,
        tokens: m.tokens,
      })),
    );
    setConversationId(conv.id);
    setSessionTokens(0);
    setSidebarOpen(false);
  };

  // ── File attachments ──────────────────────────────────────────────────────

  const handleFileAttach = e => {
    const files = Array.from(e.target.files || []);
    for (const file of files) {
      const reader = new FileReader();
      const id = `att-${Date.now()}-${Math.random().toString(36).slice(2)}`;
      if (file.type.startsWith('image/')) {
        reader.onload = ev =>
          setAttachments(prev => [
            ...prev,
            { id, name: file.name, type: 'image', dataUrl: ev.target.result },
          ]);
        reader.readAsDataURL(file);
      } else {
        reader.onload = ev =>
          setAttachments(prev => [
            ...prev,
            { id, name: file.name, type: 'text', content: ev.target.result },
          ]);
        reader.readAsText(file);
      }
    }
    e.target.value = '';
  };

  const removeAttachment = id => setAttachments(prev => prev.filter(a => a.id !== id));

  const buildEffectivePrompt = (text, atts) => {
    if (!atts.length) return text;
    const parts = atts.map(a =>
      a.type === 'text'
        ? `[Attached file: ${a.name}]\n${a.content}`
        : `[Attached image: ${a.name}]`,
    );
    return text
      ? `${text}\n\n${parts.join('\n\n---\n\n')}`
      : parts.join('\n\n---\n\n');
  };

  // ── Ask ───────────────────────────────────────────────────────────────────

  const handleAsk = async () => {
    const effectivePrompt = buildEffectivePrompt(prompt, attachments);
    if (!effectivePrompt.trim() || loading) return;

    const imageAtts = attachments.filter(a => a.type === 'image');
    const userMessage = {
      id: nextId(),
      role: 'user',
      content: prompt || '[See attachment]',
      imageAtts,
    };
    const history = messages
      .slice(-historyLimit)
      .map(m => ({ role: m.role, content: m.content }));

    setMessages(prev => [...prev, userMessage]);
    setPrompt('');
    setAttachments([]);
    if (textAreaRef.current) textAreaRef.current.style.height = '36px';
    setLoading(true);

    if (streamingMode) {
      await handleStreamingAsk(effectivePrompt, history);
    } else {
      await handleRegularAsk(effectivePrompt, history);
    }
  };

  const handleRegularAsk = async (userPrompt, history) => {
    try {
      const response = await ai.ask(userPrompt, history, activeVaultId, mode, conversationId);
      const msgTokens = (response.prompt_tokens || 0) + (response.completion_tokens || 0);
      setSessionTokens(prev => prev + msgTokens);
      if (response.conversation_id) {
        setConversationId(response.conversation_id);
        queryClient.invalidateQueries({ queryKey: ['ai-conversations', activeVaultId] });
      }
      if (response.tool_results?.length) invalidateBrowse();
      setMessages(prev => [
        ...prev,
        {
          id: nextId(),
          role: 'assistant',
          content: response.response,
          tokens: msgTokens,
          toolActions: response.tool_results?.length
            ? response.tool_results.map(r => ({ tool: r.tool, result: r.result || {} }))
            : null,
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
      let toolsRan = false;
      let pendingToolActions = null;
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
              queryClient.invalidateQueries({ queryKey: ['ai-conversations', activeVaultId] });
            }
            if (parsed.tool_status !== undefined) setToolStatus(parsed.tool_status);
            if (parsed.tools_ran) {
              toolsRan = true;
              if (parsed.tool_actions) pendingToolActions = parsed.tool_actions;
            }
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
      if (toolsRan) invalidateBrowse();

      if (streamTokenCount > 0) {
        setSessionTokens(prev => prev + streamTokenCount);
        setMessages(prev =>
          prev.map(m =>
            m.id === assistantId
              ? { ...m, tokens: streamTokenCount, toolActions: pendingToolActions }
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

  // ── Save / export / pin ───────────────────────────────────────────────────

  const handleSaveToNote = async () => {
    if (messages.length === 0) return;
    const timestamp = new Date().toISOString().replace(/[:.]/g, '-').slice(0, 19);
    const content = messages
      .filter(m => m.role !== 'error')
      .map(m => (m.role === 'user' ? `**User:** ${m.content}` : `**AI:** ${m.content}`))
      .join('\n\n');
    try {
      await notes.create(`Chat ${timestamp}`, content, null, ['ai-chat'], {}, activeVaultId);
      setSaveStatus('Saved!');
      setTimeout(() => setSaveStatus(''), 3000);
    } catch (err) {
      setSaveStatus('Failed');
      setTimeout(() => setSaveStatus(''), 3000);
    }
  };

  const handleExport = () => {
    if (messages.length === 0) return;
    const md = buildMarkdown(messages, vaultName);
    downloadFile(md, `worldstitch-chat-${new Date().toISOString().slice(0, 10)}.md`, 'text/markdown');
  };

  const handlePinMessage = async msg => {
    try {
      const timestamp = new Date().toISOString().replace(/[:.]/g, '-').slice(0, 19);
      await notes.create(`AI Note ${timestamp}`, msg.content, null, ['ai-note'], {}, activeVaultId);
      setPinnedMsg(msg.id);
      setTimeout(() => setPinnedMsg(null), 2000);
      toast.success('Saved to Browse');
    } catch (err) {
      toast.error('Failed to pin: ' + err.message);
    }
  };

  // ── Input handlers ────────────────────────────────────────────────────────

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

  const sessionCost = sessionTokens * COST_PER_TOKEN;
  const isEmpty = messages.length === 0 && !loading;

  // ── Render ────────────────────────────────────────────────────────────────

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
                    title="Delete conversation"
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
              New Chat
            </button>
          </div>
        </aside>
      )}

      {/* ── Main panel ── */}
      <div className="flex-1 flex flex-col overflow-hidden min-w-0">

        {/* ── Header ── */}
        <div className="flex items-center justify-between px-4 py-3 border-b border-border flex-shrink-0">
          <div className="flex items-center gap-2.5">
            <button
              onClick={() => setSidebarOpen(o => !o)}
              className="text-txt-muted hover:text-txt p-1.5 rounded-lg hover:bg-elevated transition-colors"
              title="Conversation history"
            >
              <History size={17} />
            </button>
            <span className="text-sm font-semibold text-txt">AI Assistant</span>
          </div>
          <div className="flex items-center gap-1">
            {saveStatus && (
              <span className="text-accent text-xs font-medium px-2">{saveStatus}</span>
            )}
            {messages.length > 0 && (
              <>
                <button
                  onClick={handleExport}
                  disabled={loading}
                  className="text-xs text-txt-muted hover:text-txt px-2.5 py-1.5 rounded-lg hover:bg-elevated transition-colors"
                >
                  Export
                </button>
                <button
                  onClick={handleSaveToNote}
                  disabled={loading}
                  className="text-xs text-txt-muted hover:text-txt px-2.5 py-1.5 rounded-lg hover:bg-elevated transition-colors"
                >
                  Save to Note
                </button>
              </>
            )}
            <button
              onClick={handleNewChat}
              disabled={loading}
              className="flex items-center gap-1 text-xs text-txt-muted hover:text-txt px-2.5 py-1.5 rounded-lg hover:bg-elevated transition-colors"
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
            /* Empty state */
            <div className="h-full flex flex-col items-center justify-center gap-6 pb-16">
              <div className="text-center">
                <p className={`text-5xl font-bold mb-3 ${currentMode.accentCls}`}>✦</p>
                <p className="text-txt font-semibold text-xl">{currentMode.label}</p>
                <p className="text-txt-muted text-sm mt-2 max-w-xs">
                  {currentMode.placeholder}
                </p>
              </div>
              <div className="flex flex-wrap gap-2 justify-center max-w-sm">
                {currentMode.chips.map(chip => (
                  <button
                    key={chip}
                    onClick={() => {
                      setPrompt(chip);
                      textAreaRef.current?.focus();
                    }}
                    className={`px-3 py-1.5 rounded-full text-xs font-medium transition-colors ${currentMode.chipCls}`}
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
                    <div className="max-w-[70%] space-y-2">
                      {/* Image attachment previews */}
                      {msg.imageAtts?.map(att => (
                        <div key={att.id} className="flex justify-end">
                          <img
                            src={att.dataUrl}
                            alt={att.name}
                            className="max-h-48 max-w-full rounded-xl object-cover"
                          />
                        </div>
                      ))}
                      <div className="bg-accent/15 text-txt px-4 py-3 rounded-2xl rounded-tr-md">
                        <p className="text-sm whitespace-pre-wrap leading-relaxed">
                          {msg.content}
                        </p>
                      </div>
                    </div>
                  ) : msg.role === 'error' ? (
                    <div className="max-w-[75%] px-4 py-3 rounded-2xl rounded-tl-md bg-danger/10 border border-danger/20 text-danger text-sm">
                      {msg.content}
                    </div>
                  ) : (
                    /* AI message */
                    <div className="max-w-[75%] group">
                      <div className="relative bg-elevated text-txt px-4 py-3 rounded-2xl rounded-tl-md">
                        <ReactMarkdown className="prose prose-sm prose-invert max-w-none text-txt [&>*:last-child]:mb-0">
                          {msg.content || '…'}
                        </ReactMarkdown>
                        {msg.content && (
                          <button
                            onClick={() => handlePinMessage(msg)}
                            className={`absolute top-2 right-2 p-1 rounded transition-all text-sm ${
                              pinnedMsg === msg.id
                                ? 'text-accent opacity-100'
                                : 'text-txt-muted opacity-0 group-hover:opacity-100 hover:text-accent'
                            }`}
                            title="Save to Browse"
                          >
                            {pinnedMsg === msg.id ? '★' : '☆'}
                          </button>
                        )}
                      </div>
                      {msg.toolActions && <ActionSummary actions={msg.toolActions} />}
                      {msg.tokens > 0 && (
                        <p className="text-[10px] text-txt-muted mt-0.5 px-1">
                          {msg.tokens.toLocaleString()} tokens
                          {mode === 'developer' && ` · $${(msg.tokens * COST_PER_TOKEN).toFixed(6)}`}
                        </p>
                      )}
                    </div>
                  )}
                </div>
              ))}

              {/* Loading bubble */}
              {loading && (
                <div className="flex justify-start">
                  <div className="bg-elevated px-4 py-3 rounded-2xl rounded-tl-md flex items-center gap-2.5">
                    <span className={`w-2 h-2 rounded-full ${currentMode.dotCls} animate-pulse`} />
                    <span className="text-sm text-txt-secondary">
                      {toolStatus || 'Thinking…'}
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

        {/* ── Session cost ── */}
        {sessionTokens > 0 && !isEmpty && (
          <p className="text-[10px] text-txt-muted text-right px-4 pb-1 flex-shrink-0">
            Session: {sessionTokens.toLocaleString()} tokens · ${sessionCost.toFixed(5)} est.
          </p>
        )}

        {/* ── Input area ── */}
        <div className="flex-shrink-0 border-t border-border px-4 py-3">

          {/* Attachment chips */}
          {attachments.length > 0 && (
            <div className="flex flex-wrap gap-2 mb-2.5">
              {attachments.map(att => (
                <div
                  key={att.id}
                  className="flex items-center gap-1.5 bg-elevated rounded-lg px-2 py-1 text-xs text-txt-secondary border border-border"
                >
                  {att.type === 'image' ? (
                    <img
                      src={att.dataUrl}
                      alt={att.name}
                      className="w-6 h-6 rounded object-cover"
                    />
                  ) : (
                    <span className="text-txt-muted text-base leading-none">📄</span>
                  )}
                  <span className="max-w-[120px] truncate">{att.name}</span>
                  <button
                    onClick={() => removeAttachment(att.id)}
                    className="text-txt-muted hover:text-danger ml-0.5 rounded transition-colors"
                  >
                    <X size={11} />
                  </button>
                </div>
              ))}
            </div>
          )}

          {/* Input row */}
          <div className="flex items-end gap-2 bg-elevated rounded-2xl px-3 py-2 border border-border/50">

            {/* Paperclip */}
            <button
              onClick={() => fileInputRef.current?.click()}
              disabled={loading}
              className="p-1.5 text-txt-muted hover:text-txt rounded-lg hover:bg-card transition-colors flex-shrink-0 self-end mb-0.5 disabled:opacity-40"
              title="Attach file (.txt, .md, .png, .jpg, .pdf)"
            >
              <Paperclip size={17} />
            </button>
            <input
              ref={fileInputRef}
              type="file"
              className="hidden"
              accept=".txt,.md,.png,.jpg,.jpeg,.gif"
              multiple
              onChange={handleFileAttach}
            />

            {/* Textarea */}
            <textarea
              ref={textAreaRef}
              rows={1}
              value={prompt}
              onChange={handlePromptChange}
              onKeyDown={handleKeyDown}
              placeholder={currentMode.placeholder}
              disabled={loading}
              className="flex-1 bg-transparent resize-none text-sm text-txt placeholder-txt-muted outline-none py-1.5 max-h-48 leading-relaxed disabled:opacity-60"
              style={{ height: '36px' }}
            />

            {/* Mode selector */}
            <div
              className="relative flex-shrink-0 self-end mb-0.5"
              ref={modeDropdownRef}
            >
              <button
                onClick={() => setModeOpen(o => !o)}
                className={`flex items-center gap-1 px-2 py-1.5 rounded-lg text-xs font-medium transition-colors hover:bg-card ${currentMode.accentCls}`}
              >
                {currentMode.label}
                <ChevronDown
                  size={11}
                  className={`transition-transform ${modeOpen ? 'rotate-180' : ''}`}
                />
              </button>
              {modeOpen && (
                <div className="absolute bottom-full mb-1.5 right-0 w-44 bg-card border border-border rounded-xl shadow-xl py-1 z-50">
                  {MODES.map(m => (
                    <button
                      key={m.key}
                      onClick={() => { setMode(m.key); setModeOpen(false); }}
                      className={`w-full text-left px-3 py-2 text-xs hover:bg-elevated transition-colors flex items-center gap-2 ${
                        mode === m.key ? `${m.accentCls} font-semibold` : 'text-txt'
                      }`}
                    >
                      <span className={`w-1.5 h-1.5 rounded-full flex-shrink-0 ${m.dotCls}`} />
                      {m.label}
                    </button>
                  ))}
                </div>
              )}
            </div>

            {/* Send button */}
            <button
              onClick={handleAsk}
              disabled={loading || (!prompt.trim() && attachments.length === 0)}
              className={`p-2 rounded-xl transition-all flex-shrink-0 self-end ${
                loading || (!prompt.trim() && attachments.length === 0)
                  ? 'bg-elevated text-txt-muted cursor-not-allowed opacity-50'
                  : `${currentMode.sendCls} text-white shadow-sm`
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
