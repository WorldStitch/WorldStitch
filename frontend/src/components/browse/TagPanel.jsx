import { useState } from 'react';
import { Plus, X, Sparkles } from 'lucide-react';

export default function TagPanel({ selectedNote, onAddTag, onRemoveTag, onSuggestTags }) {
  const [newTag, setNewTag] = useState('');

  const handleAdd = () => {
    if (!newTag.trim()) return;
    onAddTag(newTag.trim());
    setNewTag('');
  };

  const tags = selectedNote?.tags || [];

  return (
    <div className="space-y-2.5">
      {tags.length > 0 ? (
        <div className="flex flex-wrap gap-1.5">
          {tags.map((tag) => (
            <span
              key={tag}
              className="inline-flex items-center gap-1 bg-accent/10 text-accent rounded-full px-2.5 py-0.5 text-xs font-medium"
            >
              {tag}
              <button
                onClick={() => onRemoveTag(tag)}
                className="hover:text-danger transition opacity-60 hover:opacity-100"
                aria-label={`Remove ${tag}`}
              >
                <X size={10} />
              </button>
            </span>
          ))}
        </div>
      ) : (
        <p className="text-xs text-txt-muted/70 italic">
          Add tags to organize this entry
        </p>
      )}

      <div className="flex gap-1.5">
        <input
          value={newTag}
          onChange={(e) => setNewTag(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && handleAdd()}
          placeholder="Add a tag…"
          className="flex-1 bg-elevated rounded-lg px-2.5 py-1.5 text-xs text-txt border border-transparent focus:border-accent/50 focus:outline-none placeholder:text-txt-muted/50"
        />
        <button
          onClick={handleAdd}
          disabled={!newTag.trim()}
          className="p-1.5 text-accent hover:bg-accent/10 rounded-lg transition disabled:opacity-30"
          aria-label="Add tag"
        >
          <Plus size={13} />
        </button>
        {onSuggestTags && (
          <button
            onClick={onSuggestTags}
            className="p-1.5 text-txt-muted hover:text-accent hover:bg-accent/10 rounded-lg transition"
            title="Suggest tags with AI"
            aria-label="Suggest tags with AI"
          >
            <Sparkles size={13} />
          </button>
        )}
      </div>
    </div>
  );
}
