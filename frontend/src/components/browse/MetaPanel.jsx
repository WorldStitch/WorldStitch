export default function MetaPanel({
  selectedNote,
  showMetaEditor,
  onToggleMetaEditor,
  metaKey,
  metaValue,
  onMetaKeyChange,
  onMetaValueChange,
  onAddMeta,
  onRemoveMeta,
}) {
  return (
    <div>
      <div className="flex items-center justify-between mb-1">
        <p className="text-xs font-bold text-txt-muted uppercase tracking-wider">Metadata</p>
        <button
          onClick={onToggleMetaEditor}
          className="text-accent text-xs font-bold hover:bg-accent/10 px-1.5 rounded transition"
        >
          {showMetaEditor ? '−' : '+'}
        </button>
      </div>
      {Object.keys(selectedNote.meta || {}).length > 0 ? (
        <div className="space-y-1">
          {Object.entries(selectedNote.meta).map(([k, v]) => (
            <div key={k} className="flex items-center justify-between text-xs group">
              <span className="text-txt-muted font-medium">{k}:</span>
              <span className="text-txt truncate ml-2">{v}</span>
              <button
                onClick={() => onRemoveMeta(k)}
                className="hidden group-hover:block text-danger text-[10px] ml-1"
              >
                ✕
              </button>
            </div>
          ))}
        </div>
      ) : (
        <p className="text-txt-muted text-xs">No metadata</p>
      )}
      {showMetaEditor && (
        <div className="mt-2 space-y-1">
          <input
            value={metaKey}
            onChange={(e) => onMetaKeyChange(e.target.value)}
            placeholder="Key"
            className="w-full bg-elevated rounded-lg px-2 py-1 text-xs text-txt border border-transparent focus:border-accent focus:outline-none"
          />
          <input
            value={metaValue}
            onChange={(e) => onMetaValueChange(e.target.value)}
            placeholder="Value"
            onKeyDown={(e) => e.key === 'Enter' && onAddMeta()}
            className="w-full bg-elevated rounded-lg px-2 py-1 text-xs text-txt border border-transparent focus:border-accent focus:outline-none"
          />
          <button
            onClick={onAddMeta}
            disabled={!metaKey.trim()}
            className="text-accent text-xs font-bold hover:bg-accent/10 px-2 py-0.5 rounded transition disabled:opacity-30"
          >
            Add
          </button>
        </div>
      )}
    </div>
  );
}
