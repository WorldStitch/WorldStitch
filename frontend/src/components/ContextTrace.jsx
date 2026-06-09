import { useState } from 'react';
import { ChevronDown, ChevronRight, FileText, User, Map } from 'lucide-react';

const NODE_ICONS = {
  note: FileText,
  character: User,
  map: Map,
};

export default function ContextTrace({ trace, subtle = false }) {
  const [open, setOpen] = useState(false);

  if (!trace?.length) return null;

  const count = trace.length;
  const Icon = open ? ChevronDown : ChevronRight;

  return (
    <div className={`mt-2 ${subtle ? 'opacity-70' : ''}`}>
      <button
        onClick={() => setOpen(o => !o)}
        className="flex items-center gap-1.5 text-[11px] text-txt-muted hover:text-txt transition-colors rounded px-1 -ml-1"
      >
        <Icon size={11} className="flex-shrink-0" />
        <span>
          {count} {count === 1 ? 'source' : 'sources'} used
        </span>
      </button>

      {open && (
        <ul className="mt-1.5 space-y-1 pl-1">
          {trace.map((node, i) => {
            const NodeIcon = NODE_ICONS[node.node_type] || FileText;
            return (
              <li key={node.node_id ?? i} className="flex items-start gap-1.5 text-[11px] text-txt-secondary">
                <NodeIcon size={11} className="flex-shrink-0 mt-0.5 text-txt-muted" />
                <div className="min-w-0">
                  <span className="font-medium text-txt truncate">{node.node_name}</span>
                  {node.reason && (
                    <span className="text-txt-muted ml-1 truncate">— {node.reason}</span>
                  )}
                </div>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
