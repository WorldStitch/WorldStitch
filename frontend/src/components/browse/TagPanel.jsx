export default function TagPanel({ selectedNote, newTag, onNewTagChange, onAddTag, onRemoveTag, onSuggestTags }) {
  return (
    <div>
      <div className="flex items-center justify-between mb-2">
        <p className="text-xs font-bold text-txt-muted uppercase tracking-wider">Tags</p>
        {onSuggestTags && (
          <button
            onClick={onSuggestTags}
            className="text-accent text-xs hover:bg-accent/10 px-1.5 py-0.5 rounded transition"
          >
            Suggest
          </button>
        )}
      </div>
      <div className="flex flex-wrap gap-1.5 mb-2">
        {(selectedNote.tags || []).length > 0 ? (
          selectedNote.tags.map((tag) => (
            <span
              key={tag}
              className="inline-flex items-center gap-1 bg-accent/10 text-accent rounded-full px-2.5 py-0.5 text-xs font-medium"
            >
              {tag}
              <button
                onClick={() => onRemoveTag(tag)}
                className="hover:text-danger transition text-[10px]"
              >
                ✕
              </button>
            </span>
          ))
        ) : (
          <span className="text-txt-muted text-xs">No tags</span>
        )}
      </div>
      <div className="flex gap-1">
        <input
          value={newTag}
          onChange={(e) => onNewTagChange(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && onAddTag()}
          placeholder="Add tag..."
          className="flex-1 bg-elevated rounded-lg px-2 py-1 text-xs text-txt border border-transparent focus:border-accent focus:outline-none"
        />
        <button
          onClick={onAddTag}
          disabled={!newTag.trim()}
          className="text-accent text-xs font-bold px-2 hover:bg-accent/10 rounded-lg transition disabled:opacity-30"
        >
          +
        </button>
      </div>
    </div>
  );
}
