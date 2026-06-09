import { useEffect, useRef, useState } from 'react';
import {
  Pen, AlignJustify, RefreshCw, ZoomIn, ZoomOut, User, Lightbulb,
} from 'lucide-react';

const COMMANDS = [
  { id: 'continue',   icon: Pen,          label: 'Continue',          desc: 'Keep writing from here' },
  { id: 'describe',   icon: AlignJustify, label: 'Describe',          desc: 'Describe this scene or idea' },
  { id: 'rewrite',    icon: RefreshCw,    label: 'Rewrite',           desc: 'Rewrite this paragraph' },
  { id: 'expand',     icon: ZoomIn,       label: 'Expand',            desc: 'Expand with more detail' },
  { id: 'condense',   icon: ZoomOut,      label: 'Condense',          desc: 'Make it shorter' },
  { id: 'character',  icon: User,         label: 'Add character…',    desc: 'Weave a character into the text' },
  { id: 'brainstorm', icon: Lightbulb,    label: 'Brainstorm',        desc: 'Generate ideas from this context' },
];

/**
 * Floating slash-command palette. Rendered at fixed viewport coordinates.
 *
 * Props:
 *   open         boolean
 *   pos          { left, top } — viewport position (from editor.view.coordsAtPos)
 *   filter       string — text typed after the '/'
 *   onSelect     (commandId: string) => void
 *   onClose      () => void
 */
export default function SlashCommandMenu({ open, pos, filter, onSelect, onClose }) {
  const [activeIdx, setActiveIdx] = useState(0);
  const listRef = useRef(null);

  const filtered = COMMANDS.filter(
    (c) =>
      !filter ||
      c.label.toLowerCase().includes(filter.toLowerCase()) ||
      c.id.includes(filter.toLowerCase())
  );

  // Reset active index when filter or open state changes
  useEffect(() => {
    setActiveIdx(0);
  }, [filter, open]);

  // Keyboard navigation
  useEffect(() => {
    if (!open) return;

    const handler = (e) => {
      if (e.key === 'ArrowDown') {
        e.preventDefault();
        setActiveIdx((i) => Math.min(i + 1, filtered.length - 1));
      } else if (e.key === 'ArrowUp') {
        e.preventDefault();
        setActiveIdx((i) => Math.max(i - 1, 0));
      } else if (e.key === 'Enter') {
        e.preventDefault();
        if (filtered[activeIdx]) onSelect(filtered[activeIdx].id);
      } else if (e.key === 'Escape') {
        e.preventDefault();
        onClose();
      }
    };

    document.addEventListener('keydown', handler, true);
    return () => document.removeEventListener('keydown', handler, true);
  }, [open, filtered, activeIdx, onSelect, onClose]);

  // Click outside to close
  useEffect(() => {
    if (!open) return;
    const handler = (e) => {
      if (listRef.current && !listRef.current.contains(e.target)) {
        onClose();
      }
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, [open, onClose]);

  if (!open || filtered.length === 0) return null;

  // Adjust position so the menu doesn't overflow the viewport
  const menuWidth = 240;
  const menuHeight = Math.min(filtered.length * 44 + 8, 320);
  const left = Math.min(pos.left, window.innerWidth - menuWidth - 12);
  const top =
    pos.top + menuHeight > window.innerHeight - 12
      ? pos.top - menuHeight - 4
      : pos.top + 4;

  return (
    <div
      ref={listRef}
      className="fixed z-50 rounded-xl bg-card border border-txt-muted/15 shadow-xl py-1 overflow-y-auto"
      style={{ left, top, width: menuWidth, maxHeight: 320 }}
    >
      <p className="px-3 pt-1 pb-1.5 text-[10px] text-txt-muted font-semibold uppercase tracking-wider">
        AI Commands
      </p>
      {filtered.map((cmd, i) => {
        const Icon = cmd.icon;
        return (
          <button
            key={cmd.id}
            type="button"
            onMouseDown={(e) => { e.preventDefault(); onSelect(cmd.id); }}
            onMouseEnter={() => setActiveIdx(i)}
            className={`w-full flex items-center gap-2.5 px-3 py-2 text-left transition-colors ${
              i === activeIdx ? 'bg-accent/15 text-accent' : 'text-txt hover:bg-hover'
            }`}
          >
            <Icon size={13} className="flex-shrink-0 opacity-70" />
            <div className="min-w-0">
              <div className="text-sm font-medium leading-none">{cmd.label}</div>
              <div className="text-[11px] text-txt-muted mt-0.5 leading-none truncate">{cmd.desc}</div>
            </div>
          </button>
        );
      })}
    </div>
  );
}
