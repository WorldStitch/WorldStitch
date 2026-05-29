import { useState } from 'react';
import { Plus, X } from 'lucide-react';

function PropertyRow({ propKey, value, onRemove, canEdit }) {
  return (
    <div className="flex items-start gap-2 py-1.5 group border-b border-txt-muted/[0.06] last:border-b-0">
      <span
        className="text-xs text-txt-muted w-[80px] flex-shrink-0 truncate pt-0.5"
        title={propKey}
      >
        {propKey}
      </span>
      <span className="flex-1 text-xs text-txt leading-relaxed min-w-0 break-words">{value}</span>
      {canEdit && (
        <button
          onClick={() => onRemove(propKey)}
          className="opacity-0 group-hover:opacity-100 transition-opacity text-txt-muted hover:text-danger flex-shrink-0 mt-0.5"
          aria-label={`Remove ${propKey}`}
        >
          <X size={11} />
        </button>
      )}
    </div>
  );
}

export default function MetaPanel({ selectedNote, onAddMeta, onRemoveMeta, canEdit }) {
  const [showForm, setShowForm] = useState(false);
  const [propKey, setPropKey] = useState('');
  const [propValue, setPropValue] = useState('');

  const entries = Object.entries(selectedNote?.meta || {}).filter(
    ([k]) => k !== 'gm_only' && k !== 'type',
  );

  const handleAdd = () => {
    if (!propKey.trim()) return;
    onAddMeta(propKey.trim(), propValue);
    setPropKey('');
    setPropValue('');
    setShowForm(false);
  };

  const handleCancel = () => {
    setShowForm(false);
    setPropKey('');
    setPropValue('');
  };

  return (
    <div>
      {entries.length > 0 ? (
        <div className="mb-2">
          {entries.map(([k, v]) => (
            <PropertyRow key={k} propKey={k} value={v} onRemove={onRemoveMeta} canEdit={canEdit} />
          ))}
        </div>
      ) : (
        <p className="text-xs text-txt-muted/70 italic mb-2">No properties yet</p>
      )}

      {canEdit &&
        (showForm ? (
          <div className="space-y-1.5 mt-2">
            <input
              value={propKey}
              onChange={(e) => setPropKey(e.target.value)}
              placeholder="Property name"
              className="w-full bg-elevated rounded-lg px-2.5 py-1.5 text-xs text-txt border border-transparent focus:border-accent/50 focus:outline-none placeholder:text-txt-muted/50"
              autoFocus
            />
            <input
              value={propValue}
              onChange={(e) => setPropValue(e.target.value)}
              placeholder="Value"
              onKeyDown={(e) => e.key === 'Enter' && handleAdd()}
              className="w-full bg-elevated rounded-lg px-2.5 py-1.5 text-xs text-txt border border-transparent focus:border-accent/50 focus:outline-none placeholder:text-txt-muted/50"
            />
            <div className="flex gap-1.5">
              <button
                onClick={handleAdd}
                disabled={!propKey.trim()}
                className="flex-1 py-1.5 text-xs font-medium text-white bg-accent rounded-lg hover:bg-accent/90 transition disabled:opacity-40"
              >
                Add
              </button>
              <button
                onClick={handleCancel}
                className="px-3 py-1.5 text-xs text-txt-muted hover:text-txt bg-elevated rounded-lg transition"
              >
                Cancel
              </button>
            </div>
          </div>
        ) : (
          <button
            onClick={() => setShowForm(true)}
            className="flex items-center gap-1.5 text-xs text-txt-muted/60 hover:text-accent transition mt-1"
          >
            <Plus size={12} />
            Add property
          </button>
        ))}
    </div>
  );
}
