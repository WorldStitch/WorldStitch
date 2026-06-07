import { useState, useRef, useEffect } from 'react';
import { Plus, Loader2 } from 'lucide-react';
import Card from '@/components/Card';
import NoteList from './NoteList';
import { SkeletonLine } from '@/components/Skeleton';
import { useVaultTerms } from '@/hooks/useVaultTerms';

function InlineInput({ placeholder, onConfirm, onCancel, autoFocus = true }) {
  const [value, setValue] = useState('');
  const ref = useRef(null);

  useEffect(() => {
    if (autoFocus && ref.current) ref.current.focus();
  }, [autoFocus]);

  const confirm = () => {
    if (value.trim()) onConfirm(value.trim());
    else onCancel();
  };

  return (
    <input
      ref={ref}
      value={value}
      onChange={(e) => setValue(e.target.value)}
      onKeyDown={(e) => {
        if (e.key === 'Enter') confirm();
        if (e.key === 'Escape') onCancel();
      }}
      onBlur={onCancel}
      placeholder={placeholder}
      className="w-full bg-elevated rounded-lg px-2 py-1 text-xs text-txt border border-accent/40 focus:border-accent focus:outline-none"
    />
  );
}

export default function FolderTree({
  allFolders,
  allNotes,
  notesByFolder,
  unfiledNotes,
  activeFolder,
  onFolderSelect,
  expandedFolders,
  onToggleFolder,
  selectedNoteId,
  onNoteSelect,
  onDeleteFolder,
  searchQuery,
  onSearchChange,
  searchResults,
  searchLoading = false,
  allTags,
  tagFilter,
  onTagFilter,
  loading,
  searchHistory = [],
  onHistorySelect,
  onClearHistory,
  editingMap = {},
  onCreateNote,
  onCreateFolder,
}) {
  const terms = useVaultTerms();
  const [historyOpen, setHistoryOpen] = useState(false);
  const [showNewFolderInput, setShowNewFolderInput] = useState(false);
  const [inlineNoteFolderId, setInlineNoteFolderId] = useState(null);

  const handleNewFolder = (name) => {
    onCreateFolder(name);
    setShowNewFolderInput(false);
  };

  const handleFolderNote = (title, folderId) => {
    onCreateNote(title, folderId);
    setInlineNoteFolderId(null);
  };

  return (
    <Card className="w-60 flex-shrink-0 flex flex-col overflow-hidden p-0">
      {/* Search bar */}
      <div className="p-3 border-b border-txt-muted/10">
        <input
          placeholder="Search notes..."
          value={searchQuery}
          onChange={(e) => onSearchChange(e.target.value)}
          onFocus={() => setHistoryOpen(true)}
          onBlur={() => setHistoryOpen(false)}
          onKeyDown={(e) => {
            if (e.key === 'Escape') { onSearchChange(''); e.currentTarget.blur(); }
            if (e.key === 'Enter' && searchResults?.length > 0) { onNoteSelect(searchResults[0]); }
          }}
          className="w-full bg-elevated rounded-lg px-3 py-2 text-sm text-txt border border-transparent focus:border-accent focus:outline-none transition placeholder:text-txt-muted"
        />
      </div>

      {/* Search history */}
      {historyOpen && !searchQuery && searchHistory.length > 0 && (
        <div className="border-b border-txt-muted/10 bg-card">
          {searchHistory.map((q, i) => (
            <button
              key={i}
              onMouseDown={(e) => e.preventDefault()}
              onClick={() => { onHistorySelect(q); setHistoryOpen(false); }}
              className="w-full text-left px-3 py-2 text-sm text-txt hover:bg-hover transition flex items-center gap-2 truncate"
            >
              <span className="text-txt-muted text-xs flex-shrink-0">↩</span>
              <span className="truncate">{q}</span>
            </button>
          ))}
          <button
            onMouseDown={(e) => e.preventDefault()}
            onClick={() => { onClearHistory(); setHistoryOpen(false); }}
            className="w-full text-left px-3 py-2 text-xs text-txt-muted hover:bg-hover transition border-t border-txt-muted/10"
          >
            Clear history
          </button>
        </div>
      )}

      {/* Tag filter */}
      {allTags.length > 0 && (
        <div className="px-3 py-2 border-b border-txt-muted/10">
          <select
            value={tagFilter}
            onChange={(e) => onTagFilter(e.target.value)}
            className="w-full bg-elevated rounded-lg px-2 py-1.5 text-xs text-txt border border-transparent focus:border-accent focus:outline-none"
          >
            <option value="">All Tags</option>
            {allTags.map((t) => (
              <option key={t} value={t}>
                {t} ({allNotes.filter((n) => (n.tags || []).includes(t)).length})
              </option>
            ))}
          </select>
        </div>
      )}

      {/* Tree area */}
      <div className="flex-1 overflow-y-auto p-2">
        {loading ? (
          <div className="space-y-2 p-2">
            <SkeletonLine width="w-3/4" />
            <SkeletonLine width="w-1/2" />
            <SkeletonLine width="w-2/3" />
          </div>
        ) : searchLoading && searchQuery ? (
          <div className="flex items-center justify-center gap-2 py-8 text-txt-muted text-sm">
            <Loader2 size={15} className="animate-spin" />
            Searching…
          </div>
        ) : searchResults !== null ? (
          <div className="space-y-0.5">
            {searchResults.length === 0 ? (
              <div className="flex flex-col items-center justify-center py-8 text-center space-y-1">
                <p className="text-txt-muted text-sm">No results found</p>
                <p className="text-txt-muted text-xs">Try different keywords</p>
              </div>
            ) : (
              <>
                <p className="text-txt-muted text-xs px-2 py-1 font-medium">
                  {searchResults.length} result{searchResults.length !== 1 ? 's' : ''}
                </p>
                {searchResults.map((result) => (
                  <button
                    key={result.id}
                    onClick={() => onNoteSelect(result)}
                    className={`w-full text-left px-3 py-2 rounded-lg text-sm transition ${
                      selectedNoteId === result.id
                        ? 'bg-accent/10 text-accent'
                        : 'text-txt hover:bg-hover'
                    }`}
                  >
                    <div className="flex items-center gap-1.5 min-w-0">
                      <span className="text-xs flex-shrink-0">📝</span>
                      <span className="truncate font-medium">{result.title || 'Untitled'}</span>
                    </div>
                    {result.snippet && (
                      <div
                        className="text-xs text-txt-secondary mt-0.5 line-clamp-2 [&_mark]:bg-accent/20 [&_mark]:text-accent [&_mark]:rounded-sm [&_mark]:px-px"
                        dangerouslySetInnerHTML={{ __html: result.snippet }}
                      />
                    )}
                  </button>
                ))}
              </>
            )}
          </div>
        ) : (
          <div className="space-y-0.5">
            {allNotes.length === 0 && allFolders.length === 0 ? (
              <div className="flex flex-col items-center justify-center py-8 text-center space-y-2">
                <div className="text-3xl">📁</div>
                <p className="text-txt-muted text-sm">No {terms.notes.toLowerCase()} yet</p>
                <p className="text-txt-muted text-xs">Click New {terms.note} to get started</p>
              </div>
            ) : (
              <>
                {/* All Notes */}
                <button
                  onClick={() => onFolderSelect(null)}
                  className={`w-full text-left px-3 py-2 rounded-lg text-sm transition ${
                    !activeFolder
                      ? 'bg-accent/10 text-accent font-semibold'
                      : 'text-txt hover:bg-hover'
                  }`}
                >
                  📋 All {terms.notes} ({allNotes.length})
                </button>

                {/* Folders header with + */}
                <div className="flex items-center px-3 pt-2 pb-1">
                  <span className="text-[10px] uppercase tracking-widest text-txt-muted font-bold flex-1">
                    {terms.folders}
                  </span>
                  <button
                    onClick={() => setShowNewFolderInput(true)}
                    className="text-txt-muted hover:text-txt transition p-0.5 rounded"
                    title="New folder"
                  >
                    <Plus size={12} />
                  </button>
                </div>

                {/* Inline folder input */}
                {showNewFolderInput && (
                  <div className="px-1 pb-1">
                    <InlineInput
                      placeholder="Folder name..."
                      onConfirm={handleNewFolder}
                      onCancel={() => setShowNewFolderInput(false)}
                    />
                  </div>
                )}

                {/* Folder rows */}
                {allFolders.map((folder) => {
                  const folderNotes = notesByFolder[folder.id] || [];
                  const isExpanded = expandedFolders.has(folder.id);
                  const isActive = activeFolder === folder.id;

                  return (
                    <div key={folder.id}>
                      <div className="flex items-center group">
                        <button
                          onClick={() => {
                            onToggleFolder(folder.id);
                            onFolderSelect(folder.id);
                          }}
                          className={`flex-1 min-w-0 text-left px-3 py-2 rounded-lg text-sm transition flex items-center gap-2 ${
                            isActive
                              ? 'bg-accent/10 text-accent font-semibold'
                              : 'text-txt hover:bg-hover'
                          }`}
                        >
                          <span className="text-xs flex-shrink-0">{isExpanded ? '▼' : '▶'}</span>
                          <span className="truncate">📁 {folder.name}</span>
                          <span className="text-txt-muted text-xs ml-auto flex-shrink-0">
                            {folderNotes.length}
                          </span>
                        </button>
                        {/* Hover: add note + delete folder */}
                        <button
                          onClick={() =>
                            setInlineNoteFolderId(
                              inlineNoteFolderId === folder.id ? null : folder.id,
                            )
                          }
                          className="hidden group-hover:flex items-center justify-center text-txt-muted hover:text-accent transition text-xs w-6 h-6 rounded"
                          title="New note in folder"
                        >
                          <Plus size={11} />
                        </button>
                        <button
                          onClick={() => onDeleteFolder(folder.id)}
                          className="hidden group-hover:flex items-center justify-center text-danger text-xs w-5 h-6 rounded hover:bg-danger/10"
                          title="Delete folder"
                        >
                          ✕
                        </button>
                      </div>

                      {/* Inline note input for this folder */}
                      {inlineNoteFolderId === folder.id && (
                        <div className="ml-5 pr-1 py-0.5">
                          <InlineInput
                            placeholder="Note title..."
                            onConfirm={(title) => handleFolderNote(title, folder.id)}
                            onCancel={() => setInlineNoteFolderId(null)}
                          />
                        </div>
                      )}

                      {isExpanded && folderNotes.length > 0 && (
                        <div className="ml-5 space-y-0.5">
                          <NoteList
                            notes={folderNotes}
                            selectedNoteId={selectedNoteId}
                            onNoteSelect={onNoteSelect}
                            editingMap={editingMap}
                          />
                        </div>
                      )}

                      {isExpanded && folderNotes.length === 0 && (
                        <p className="ml-5 text-txt-muted text-xs px-3 py-1">Empty folder</p>
                      )}
                    </div>
                  );
                })}

                {/* Unfiled notes */}
                {unfiledNotes.length > 0 && (
                  <div>
                    <button
                      onClick={() => {
                        onToggleFolder('__unfiled__');
                        onFolderSelect(null);
                      }}
                      className="w-full text-left px-3 py-2 rounded-lg text-sm text-txt-muted hover:bg-hover transition flex items-center gap-2"
                    >
                      <span className="text-xs">
                        {expandedFolders.has('__unfiled__') ? '▼' : '▶'}
                      </span>
                      <span>📄 Unfiled</span>
                      <span className="text-xs ml-auto">{unfiledNotes.length}</span>
                    </button>
                    {expandedFolders.has('__unfiled__') && (
                      <div className="ml-5 space-y-0.5">
                        <NoteList
                          notes={unfiledNotes}
                          selectedNoteId={selectedNoteId}
                          onNoteSelect={onNoteSelect}
                          editingMap={editingMap}
                        />
                      </div>
                    )}
                  </div>
                )}
              </>
            )}
          </div>
        )}
      </div>
    </Card>
  );
}
