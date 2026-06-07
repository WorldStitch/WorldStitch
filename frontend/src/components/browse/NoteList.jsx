export default function NoteList({ notes, selectedNoteId, onNoteSelect, editingMap = {} }) {
  return (
    <div className="space-y-0.5">
      {notes.map((note) => {
        const editor = editingMap[note.id];
        return (
          <button
            key={note.id}
            onClick={() => onNoteSelect(note)}
            className={`w-full text-left px-3 py-1.5 rounded-lg text-sm transition truncate ${
              selectedNoteId === note.id
                ? 'bg-accent/10 text-accent font-medium'
                : 'text-txt hover:bg-hover'
            }`}
          >
            <div className="flex items-center gap-1.5">
              <span className="text-xs flex-shrink-0">📝</span>
              <span className="truncate">{note.title || note.name || 'Untitled'}</span>
              {editor && (
                <span
                  className="ml-auto flex-shrink-0 text-[10px] text-accent-secondary"
                  title={`${editor} is editing`}
                >
                  ✏️
                </span>
              )}
              {!editor && (note.tags || []).length > 0 && (
                <span className="text-txt-muted text-[10px] ml-auto flex-shrink-0">
                  {note.tags.length} tag{note.tags.length !== 1 ? 's' : ''}
                </span>
              )}
            </div>
          </button>
        );
      })}
    </div>
  );
}
