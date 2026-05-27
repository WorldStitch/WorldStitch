import { useEffect, useCallback, useRef } from 'react';
import { useEditor, EditorContent } from '@tiptap/react';
import StarterKit from '@tiptap/starter-kit';
import Link from '@tiptap/extension-link';
import Placeholder from '@tiptap/extension-placeholder';
import Typography from '@tiptap/extension-typography';
import { createWikiLinkExtension } from './WikiLinkExtension';
import {
  Bold,
  Italic,
  Heading1,
  Heading2,
  Heading3,
  List,
  ListOrdered,
  Quote,
  Link as LinkIcon,
  Download,
} from 'lucide-react';
import Card from '@/components/Card';
import Button from '@/components/Button';
import { SkeletonLine } from '@/components/Skeleton';

function processContent(content) {
  if (!content) return '';
  if (content.trimStart().startsWith('<')) return content;
  return content
    .split('\n\n')
    .map((para) => `<p>${para.replace(/\n/g, '<br>')}</p>`)
    .join('');
}

function stripHtml(html) {
  const div = document.createElement('div');
  div.innerHTML = html;
  return div.innerText || div.textContent || '';
}

function ToolbarBtn({ onClick, active, title, children }) {
  return (
    <button
      type="button"
      onMouseDown={(e) => { e.preventDefault(); onClick(); }}
      title={title}
      className={`p-1.5 rounded transition-colors ${
        active
          ? 'bg-accent/20 text-accent'
          : 'text-txt-muted hover:text-txt hover:bg-hover'
      }`}
    >
      {children}
    </button>
  );
}

export default function NoteEditor({
  selectedNote,
  allFolders,
  isEditing,
  editTitle,
  onTitleChange,
  onContentChange,
  onEdit,
  onSave,
  onCancel,
  onDelete,
  onSummarize,
  onSuggestTags,
  onSuggestLinks,
  proposedLinks = [],
  onClearProposedLinks,
  summaryResult = '',
  onClearSummary,
  showMoveDialog,
  onToggleMove,
  onMove,
  wordCount,
  noteLoading,
  canEdit = true,
  editingPresence = null,
  onCursorChange,
  onNavigate,
}) {
  const editingUser =
    editingPresence?.email || editingPresence?.username || editingPresence?.user_id;
  const editingText = editingUser ? `${editingUser} is editing this note.` : null;

  // Keep a mutable ref so the WikiLink extension always sees the current note id
  // without needing to be recreated when the note changes.
  const noteIdRef = useRef(selectedNote?.id ?? null);
  useEffect(() => {
    noteIdRef.current = selectedNote?.id ?? null;
  }, [selectedNote?.id]);

  const editor = useEditor({
    extensions: [
      StarterKit.configure({ heading: { levels: [1, 2, 3] } }),
      Link.configure({
        openOnClick: false,
        HTMLAttributes: { class: 'text-accent underline cursor-pointer' },
      }),
      Placeholder.configure({ placeholder: 'Start writing...' }),
      Typography,
      createWikiLinkExtension({ noteIdRef, onNavigate }),
    ],
    content: '',
    editable: false,
    onUpdate: ({ editor: ed }) => {
      onContentChange(ed.getHTML());
      onCursorChange?.(ed.state.selection.anchor);
    },
  });

  // Sync editable mode
  useEffect(() => {
    if (editor) editor.setEditable(isEditing);
  }, [editor, isEditing]);
  // Sync content when note changes or editing stops
  useEffect(() => {
    if (!editor || !selectedNote) return;
    if (!isEditing) {
      editor.commands.setContent(processContent(selectedNote.content || ''), false);
    }
  }, [selectedNote?.id, selectedNote?.content, isEditing]);

  const handleInsertLink = useCallback(
    (link) => {
      if (!editor) return;
      editor.chain().focus().insertContent(`[[${link}]]`).run();
    },
    [editor],
  );

  const handleSetLink = useCallback(() => {
    if (!editor) return;
    const url = window.prompt('Enter URL:');
    if (!url) return;
    editor.chain().focus().extendMarkRange('link').setLink({ href: url }).run();
  }, [editor]);

  const handleDownload = useCallback(() => {
    if (!selectedNote) return;
    const title = selectedNote.title || 'note';
    const content = selectedNote.content || '';
    const body = content.trimStart().startsWith('<') ? stripHtml(content) : content;
    const text = `# ${title}\n\n${body}`;
    const blob = new Blob([text], { type: 'text/markdown' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${title}.md`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  }, [selectedNote]);

  if (noteLoading) {
    return (
      <Card className="flex-1 flex flex-col overflow-hidden p-5 space-y-4">
        <SkeletonLine width="w-1/2" height="h-6" />
        <SkeletonLine />
        <SkeletonLine width="w-5/6" />
        <SkeletonLine width="w-4/6" />
      </Card>
    );
  }

  if (!selectedNote) {
    return (
      <Card className="flex-1 flex flex-col overflow-hidden p-0">
        <div className="flex items-center justify-center h-full">
          <div className="text-center space-y-3">
            <div className="text-4xl">📖</div>
            <p className="text-txt-muted">Select a note to get started</p>
            <p className="text-txt-muted text-xs">or create a new note with + Note</p>
          </div>
        </div>
      </Card>
    );
  }

  return (
    <Card className="flex-1 flex flex-col overflow-hidden p-0 min-w-0">
      {/* Top toolbar */}
      <div className="flex items-center gap-2 px-4 py-3 border-b border-txt-muted/10 flex-wrap">
        {!isEditing ? (
          <>
            <h2 className="text-lg font-bold text-txt flex-1 truncate min-w-0">
              {selectedNote.title}
            </h2>
            <Button variant="secondary" size="sm" onClick={handleDownload} title="Download as .md">
              <Download size={13} className="inline mr-1" />.md
            </Button>
            <Button variant="secondary" size="sm" onClick={onEdit} disabled={!canEdit}>
              Edit
            </Button>
            <Button
              variant="secondary"
              size="sm"
              onClick={() => onToggleMove(!showMoveDialog)}
              disabled={!canEdit}
            >
              Move
            </Button>
            {onSummarize && (
              <Button variant="ghost" size="sm" onClick={onSummarize}>
                Summarize
              </Button>
            )}
            {onSuggestTags && (
              <Button variant="ghost" size="sm" onClick={onSuggestTags}>
                Suggest Tags
              </Button>
            )}
            {onSuggestLinks && (
              <Button variant="ghost" size="sm" onClick={onSuggestLinks}>
                Suggest Links
              </Button>
            )}
            <Button variant="danger" size="sm" onClick={onDelete} disabled={!canEdit}>
              Delete
            </Button>
          </>
        ) : (
          <>
            <input
              value={editTitle}
              onChange={(e) => onTitleChange(e.target.value)}
              className="flex-1 min-w-0 bg-elevated rounded-lg px-3 py-1.5 text-lg font-bold text-txt border border-transparent focus:border-accent focus:outline-none"
            />
            <Button variant="primary" size="sm" onClick={onSave} title="Ctrl+S">
              Save
            </Button>
            <Button variant="ghost" size="sm" onClick={onCancel}>
              Cancel
            </Button>
          </>
        )}
      </div>

      {/* Formatting toolbar — edit mode only */}
      {isEditing && editor && (
        <div className="flex items-center gap-0.5 px-3 py-1.5 border-b border-txt-muted/10 flex-wrap bg-elevated/50">
          <ToolbarBtn
            onClick={() => editor.chain().focus().toggleBold().run()}
            active={editor.isActive('bold')}
            title="Bold"
          >
            <Bold size={14} />
          </ToolbarBtn>
          <ToolbarBtn
            onClick={() => editor.chain().focus().toggleItalic().run()}
            active={editor.isActive('italic')}
            title="Italic"
          >
            <Italic size={14} />
          </ToolbarBtn>
          <span className="w-px h-4 bg-txt-muted/20 mx-1 flex-shrink-0" />
          <ToolbarBtn
            onClick={() => editor.chain().focus().toggleHeading({ level: 1 }).run()}
            active={editor.isActive('heading', { level: 1 })}
            title="Heading 1"
          >
            <Heading1 size={14} />
          </ToolbarBtn>
          <ToolbarBtn
            onClick={() => editor.chain().focus().toggleHeading({ level: 2 }).run()}
            active={editor.isActive('heading', { level: 2 })}
            title="Heading 2"
          >
            <Heading2 size={14} />
          </ToolbarBtn>
          <ToolbarBtn
            onClick={() => editor.chain().focus().toggleHeading({ level: 3 }).run()}
            active={editor.isActive('heading', { level: 3 })}
            title="Heading 3"
          >
            <Heading3 size={14} />
          </ToolbarBtn>
          <span className="w-px h-4 bg-txt-muted/20 mx-1 flex-shrink-0" />
          <ToolbarBtn
            onClick={() => editor.chain().focus().toggleBulletList().run()}
            active={editor.isActive('bulletList')}
            title="Bullet list"
          >
            <List size={14} />
          </ToolbarBtn>
          <ToolbarBtn
            onClick={() => editor.chain().focus().toggleOrderedList().run()}
            active={editor.isActive('orderedList')}
            title="Ordered list"
          >
            <ListOrdered size={14} />
          </ToolbarBtn>
          <ToolbarBtn
            onClick={() => editor.chain().focus().toggleBlockquote().run()}
            active={editor.isActive('blockquote')}
            title="Blockquote"
          >
            <Quote size={14} />
          </ToolbarBtn>
          <span className="w-px h-4 bg-txt-muted/20 mx-1 flex-shrink-0" />
          <ToolbarBtn
            onClick={handleSetLink}
            active={editor.isActive('link')}
            title="Set link"
          >
            <LinkIcon size={14} />
          </ToolbarBtn>
          {onSuggestLinks && (
            <Button variant="ghost" size="sm" onClick={onSuggestLinks} className="ml-1 text-xs">
              Suggest Links
            </Button>
          )}
        </div>
      )}

      {/* Editing presence warning */}
      {editingText && (
        <div className="px-4 py-2 bg-warning/10 border-b border-txt-muted/10 text-xs text-txt">
          {editingText}
        </div>
      )}

      {/* Move dialog */}
      {showMoveDialog && (
        <div className="px-4 py-2 bg-elevated/50 border-b border-txt-muted/10 flex flex-wrap gap-2 items-center">
          <span className="text-txt-muted text-xs font-medium">Move to:</span>
          <Button
            variant={!selectedNote.folder_id ? 'primary' : 'ghost'}
            size="sm"
            onClick={() => onMove(null)}
          >
            Unfiled
          </Button>
          {allFolders.map((f) => (
            <Button
              key={f.id}
              variant={selectedNote.folder_id === f.id ? 'primary' : 'ghost'}
              size="sm"
              onClick={() => onMove(f.id)}
            >
              📁 {f.name}
            </Button>
          ))}
        </div>
      )}

      {/* Proposed link chips */}
      {proposedLinks.length > 0 && (
        <div className="px-4 py-2 bg-elevated/40 border-b border-txt-muted/10">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-xs text-txt-muted font-medium shrink-0">Link suggestions:</span>
            {proposedLinks.map((link) => (
              <button
                key={link}
                onClick={() => handleInsertLink(link)}
                className="text-xs px-2.5 py-1 rounded-full bg-accent/15 text-accent hover:bg-accent/30 transition font-medium"
                title={`Insert [[${link}]]`}
              >
                {link}
              </button>
            ))}
            <button
              onClick={onClearProposedLinks}
              className="text-xs text-txt-muted hover:text-txt ml-auto transition"
              title="Dismiss"
            >
              ✕
            </button>
          </div>
        </div>
      )}

      {/* Editor content area */}
      <div className="flex-1 overflow-y-auto p-5">
        <EditorContent editor={editor} className="tiptap-editor" />
      </div>

      {/* Inline AI summary */}
      {summaryResult && (
        <div className="mx-5 mb-3 p-3 bg-accent/8 rounded-xl border border-accent/20">
          <div className="flex items-start justify-between gap-2">
            <div>
              <p className="text-xs font-bold text-accent uppercase tracking-wider mb-1">
                AI Summary
              </p>
              <p className="text-sm text-txt leading-relaxed">{summaryResult}</p>
            </div>
            <button
              onClick={onClearSummary}
              className="text-txt-muted hover:text-txt transition shrink-0 text-xs mt-0.5"
              title="Dismiss"
            >
              ✕
            </button>
          </div>
        </div>
      )}

      {/* Bottom bar */}
      <div className="px-4 py-2 border-t border-txt-muted/10 flex justify-between items-center text-xs text-txt-muted">
        <span>
          {wordCount(selectedNote.content)} words
          {selectedNote.folder_id && (
            <>
              {' '}· 📁{' '}
              {allFolders.find((f) => f.id === selectedNote.folder_id)?.name ||
                selectedNote.folder_id}
            </>
          )}
        </span>
        <span>Modified: {new Date(selectedNote.last_modified).toLocaleString()}</span>
      </div>
    </Card>
  );
}
