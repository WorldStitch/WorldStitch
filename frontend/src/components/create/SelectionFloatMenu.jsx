import { useEffect, useRef, useState } from 'react';

/**
 * Floating toolbar that appears above a text selection in the editor.
 *
 * Props:
 *   open           boolean
 *   pos            { left, top } — viewport position above the selection
 *   loading        boolean — an AI action is in flight
 *   onAction       (action: 'rewrite'|'expand'|'condense'|'ask', prompt?: string) => void
 *   onClose        () => void
 */
export default function SelectionFloatMenu({ open, pos, loading, onAction, onClose }) {
  const [askMode, setAskMode] = useState(false);
  const [askText, setAskText] = useState('');
  const menuRef = useRef(null);
  const inputRef = useRef(null);

  // Reset ask mode when menu closes
  useEffect(() => {
    if (!open) {
      setAskMode(false);
      setAskText('');
    }
  }, [open]);

  // Focus input when entering ask mode
  useEffect(() => {
    if (askMode && inputRef.current) {
      inputRef.current.focus();
    }
  }, [askMode]);

  // Click outside to close
  useEffect(() => {
    if (!open) return;
    const handler = (e) => {
      if (menuRef.current && !menuRef.current.contains(e.target)) {
        onClose();
      }
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, [open, onClose]);

  if (!open) return null;

  // Position: keep inside viewport
  const menuWidth = askMode ? 260 : 220;
  const left = Math.max(
    8,
    Math.min(pos.left - menuWidth / 2, window.innerWidth - menuWidth - 8)
  );
  const top = Math.max(8, pos.top - (askMode ? 48 : 36));

  const ACTIONS = [
    { id: 'rewrite', label: 'Rewrite' },
    { id: 'expand', label: 'Expand' },
    { id: 'condense', label: 'Condense' },
  ];

  return (
    <div
      ref={menuRef}
      className="fixed z-50 rounded-xl bg-card border border-txt-muted/15 shadow-xl"
      style={{ left, top, width: menuWidth }}
      onMouseDown={(e) => e.stopPropagation()}
    >
      {askMode ? (
        <div className="flex items-center gap-1.5 px-2 py-1.5">
          <input
            ref={inputRef}
            value={askText}
            onChange={(e) => setAskText(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && askText.trim()) {
                onAction('ask', askText.trim());
                setAskMode(false);
                setAskText('');
              }
              if (e.key === 'Escape') {
                setAskMode(false);
                setAskText('');
              }
            }}
            placeholder="Instruction for this selection…"
            className="flex-1 min-w-0 bg-elevated rounded-lg px-2.5 py-1.5 text-xs text-txt border border-txt-muted/20 focus:border-accent focus:outline-none"
          />
          <button
            type="button"
            disabled={!askText.trim()}
            onMouseDown={(e) => {
              e.preventDefault();
              if (askText.trim()) {
                onAction('ask', askText.trim());
                setAskMode(false);
                setAskText('');
              }
            }}
            className="px-2 py-1.5 rounded-lg bg-accent text-white text-xs font-medium disabled:opacity-40 hover:bg-accent/90 transition"
          >
            Go
          </button>
        </div>
      ) : (
        <div className="flex items-center gap-0.5 px-1.5 py-1.5">
          {ACTIONS.map((a) => (
            <button
              key={a.id}
              type="button"
              disabled={loading}
              onMouseDown={(e) => { e.preventDefault(); onAction(a.id); }}
              className="px-2.5 py-1 rounded-lg text-xs font-medium text-txt-muted hover:text-txt hover:bg-hover transition disabled:opacity-40"
            >
              {loading ? '…' : a.label}
            </button>
          ))}
          <span className="w-px h-3.5 bg-txt-muted/20 mx-0.5 flex-shrink-0" />
          <button
            type="button"
            disabled={loading}
            onMouseDown={(e) => { e.preventDefault(); setAskMode(true); }}
            className="px-2.5 py-1 rounded-lg text-xs font-medium text-accent hover:bg-accent/15 transition disabled:opacity-40"
          >
            Ask
          </button>
        </div>
      )}
    </div>
  );
}
