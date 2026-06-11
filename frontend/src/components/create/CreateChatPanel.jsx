import { useState, useRef, useEffect, useCallback } from 'react';
import ReactMarkdown from 'react-markdown';
import { ArrowUp, X, Square } from 'lucide-react';
import { getApiBase, getToken } from '@/api';
import DiffView from './DiffView';

const EDIT_FENCE_RE = /```edit\n([\s\S]*?)```/;

function parseEditProposal(text) {
  const match = text.match(EDIT_FENCE_RE);
  if (!match) return null;
  return match[1];
}

function MessageBubble({ msg, onAcceptEdit, onRejectEdit, currentNoteContent }) {
  const editProposal = msg.role === 'assistant' ? parseEditProposal(msg.content) : null;
  const displayText = editProposal
    ? msg.content.replace(EDIT_FENCE_RE, '').trim()
    : msg.content;

  if (msg.role === 'error') {
    return (
      <div className="px-3 py-2 rounded-xl bg-danger/10 border border-danger/20 text-xs text-danger">
        {msg.content}
      </div>
    );
  }

  return (
    <div className={`flex flex-col gap-2 ${msg.role === 'user' ? 'items-end' : 'items-start'}`}>
      {displayText && (
        <div
          className={`max-w-[90%] px-3 py-2 rounded-xl text-sm leading-relaxed ${
            msg.role === 'user'
              ? 'bg-accent/20 text-txt'
              : 'bg-elevated/50 text-txt'
          }`}
        >
          {msg.role === 'assistant' ? (
            <ReactMarkdown
              components={{
                p: ({ children }) => <p className="mb-1.5 last:mb-0">{children}</p>,
                code: ({ children }) => (
                  <code className="bg-elevated px-1 py-0.5 rounded text-xs font-mono">{children}</code>
                ),
              }}
            >
              {displayText}
            </ReactMarkdown>
          ) : (
            <span>{displayText}</span>
          )}
        </div>
      )}

      {/* Edit proposal shown as inline diff */}
      {editProposal && !msg.editHandled && (
        <div className="w-full rounded-xl overflow-hidden border border-txt-muted/15 bg-card max-h-72">
          <DiffView
            command="Edit proposal"
            oldText={currentNoteContent}
            newText={editProposal}
            loading={false}
            onAccept={() => onAcceptEdit(msg.id, editProposal)}
            onReject={() => onRejectEdit(msg.id)}
          />
        </div>
      )}

      {msg.editHandled && editProposal && (
        <div className="text-xs text-txt-muted italic">
          {msg.editHandled === 'accepted' ? '✓ Edit accepted' : '✗ Edit rejected'}
        </div>
      )}
    </div>
  );
}

/**
 * Create mode Chat panel — streaming sidebar conversation.
 *
 * Props:
 *   vaultId          string
 *   currentNote      { id, title, content } | null
 *   onApplyEdit      (newContent: string) => void   — called when user accepts an edit
 *   onClose          () => void
 */
export default function CreateChatPanel({ vaultId, currentNote, onApplyEdit, onClose }) {
  const [messages, setMessages] = useState([]);
  const [prompt, setPrompt] = useState('');
  const [loading, setLoading] = useState(false);
  const bottomRef = useRef(null);
  const textareaRef = useRef(null);
  const abortRef = useRef(null);

  const brainKey = vaultId ? `vault_brain_enabled_${vaultId}` : null;
  const [useBrain, setUseBrain] = useState(() => {
    if (!vaultId) return true;
    const stored = localStorage.getItem(`vault_brain_enabled_${vaultId}`);
    return stored === null ? true : stored === 'true';
  });

  const toggleBrain = (val) => {
    setUseBrain(val);
    if (brainKey) localStorage.setItem(brainKey, String(val));
  };

  const nextId = () => `cm-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;

  // Scroll to bottom whenever messages change
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, loading]);

  const handleCancel = () => {
    abortRef.current?.abort('user');
  };

  const handleSend = useCallback(async () => {
    const text = prompt.trim();
    if (!text || loading) return;

    const history = messages
      .filter((m) => m.role === 'user' || m.role === 'assistant')
      .slice(-10)
      .map((m) => ({ role: m.role, content: m.content }));

    setMessages((prev) => [...prev, { id: nextId(), role: 'user', content: text }]);
    setPrompt('');
    if (textareaRef.current) textareaRef.current.style.height = '36px';
    setLoading(true);

    const assistantId = nextId();
    setMessages((prev) => [
      ...prev,
      { id: assistantId, role: 'assistant', content: '' },
    ]);

    const controller = new AbortController();
    abortRef.current = controller;

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
          prompt: text,
          history,
          vault_id: vaultId,
          mode: 'create',
          sub_mode: 'chat',
          use_brain: useBrain,
          current_entity: currentNote
            ? { type: 'note', id: currentNote.id, title: currentNote.title, content: currentNote.content }
            : null,
        }),
      });

      if (!res.ok) {
        const errBody = await res.json().catch(() => ({ detail: `HTTP ${res.status}` }));
        throw new Error(errBody.detail || `Request failed: ${res.status}`);
      }

      const reader = res.body.getReader();
      const decoder = new TextDecoder();

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        const chunk = decoder.decode(value, { stream: true });
        for (const line of chunk.split('\n')) {
          if (!line.startsWith('data: ')) continue;
          const data = line.slice(6);
          if (data === '[DONE]') break;
          try {
            const parsed = JSON.parse(data);
            if (parsed.token) {
              setMessages((prev) =>
                prev.map((m) =>
                  m.id === assistantId ? { ...m, content: m.content + parsed.token } : m
                )
              );
            }
            if (parsed.error) {
              setMessages((prev) =>
                prev.map((m) =>
                  m.id === assistantId ? { ...m, content: parsed.error, role: 'error' } : m
                )
              );
            }
          } catch {
            // malformed SSE line
          }
        }
      }
    } catch (err) {
      if (err.name === 'AbortError') return;
      setMessages((prev) =>
        prev.map((m) =>
          m.id === assistantId
            ? { ...m, role: 'error', content: `Error: ${err.message}` }
            : m
        )
      );
    } finally {
      setLoading(false);
      abortRef.current = null;
    }
  }, [prompt, loading, messages, vaultId, currentNote]);

  const handleAcceptEdit = (msgId, editText) => {
    onApplyEdit(editText);
    setMessages((prev) =>
      prev.map((m) => (m.id === msgId ? { ...m, editHandled: 'accepted' } : m))
    );
  };

  const handleRejectEdit = (msgId) => {
    setMessages((prev) =>
      prev.map((m) => (m.id === msgId ? { ...m, editHandled: 'rejected' } : m))
    );
  };

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const handleTextareaInput = (e) => {
    const el = e.target;
    el.style.height = '36px';
    el.style.height = `${Math.min(el.scrollHeight, 120)}px`;
    setPrompt(el.value);
  };

  return (
    <div className="flex flex-col h-full border-l border-txt-muted/10 bg-card">
      {/* Panel header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-txt-muted/10 flex-shrink-0">
        <div>
          <p className="text-sm font-semibold text-txt">Writing Assistant</p>
          {currentNote && (
            <p className="text-xs text-txt-muted mt-0.5 truncate max-w-[160px]">
              {currentNote.title}
            </p>
          )}
        </div>
        <div className="flex items-center gap-2">
          {vaultId && (
            <button
              onClick={() => toggleBrain(!useBrain)}
              title={useBrain ? 'Vault Brain active — click to disable' : 'Vault Brain disabled — click to enable'}
              className={`flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium border transition-all ${
                useBrain
                  ? 'bg-accent/10 border-accent/30 text-accent'
                  : 'bg-elevated border-border/50 text-txt-muted hover:text-txt'
              }`}
            >
              🧠 Brain
            </button>
          )}
          <button
            type="button"
            onClick={onClose}
            className="p-1.5 rounded-lg text-txt-muted hover:text-txt hover:bg-hover transition"
            title="Close chat"
          >
            <X size={14} />
          </button>
        </div>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto px-3 py-3 space-y-3 min-h-0">
        {messages.length === 0 && !loading && (
          <div className="flex flex-col items-center justify-center h-full space-y-2 text-center px-4">
            <div className="text-2xl">✍️</div>
            <p className="text-txt-muted text-sm">
              Ask anything about your world, get writing suggestions, or say{' '}
              <span className="text-accent font-medium">&quot;propose an edit&quot;</span> to have me revise the note.
            </p>
          </div>
        )}
        {messages.map((msg) => (
          <MessageBubble
            key={msg.id}
            msg={msg}
            currentNoteContent={currentNote?.content || ''}
            onAcceptEdit={handleAcceptEdit}
            onRejectEdit={handleRejectEdit}
          />
        ))}
        <div ref={bottomRef} />
      </div>

      {/* Input area */}
      <div className="border-t border-txt-muted/10 p-3 flex-shrink-0">
        <div className="flex items-end gap-2 bg-elevated rounded-xl px-3 py-2">
          <textarea
            ref={textareaRef}
            value={prompt}
            onChange={handleTextareaInput}
            onKeyDown={handleKeyDown}
            placeholder="Ask your writing partner…"
            rows={1}
            className="flex-1 min-w-0 bg-transparent text-sm text-txt placeholder-txt-muted resize-none focus:outline-none leading-5"
            style={{ height: 36, maxHeight: 120 }}
          />
          {loading ? (
            <button
              type="button"
              onClick={handleCancel}
              className="flex-shrink-0 w-7 h-7 rounded-lg bg-txt-muted/20 hover:bg-txt-muted/30 flex items-center justify-center transition"
              title="Stop"
            >
              <Square size={11} className="text-txt-muted" />
            </button>
          ) : (
            <button
              type="button"
              onClick={handleSend}
              disabled={!prompt.trim()}
              className="flex-shrink-0 w-7 h-7 rounded-lg bg-accent disabled:opacity-30 hover:bg-accent/90 flex items-center justify-center transition"
              title="Send (Enter)"
            >
              <ArrowUp size={13} className="text-white" />
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
