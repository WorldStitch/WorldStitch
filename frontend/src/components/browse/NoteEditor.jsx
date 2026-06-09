import { useEffect, useCallback, useRef, useState, useMemo } from 'react';
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
import { ai } from '@/api';

import CreateModeToolbar from '@/components/create/CreateModeToolbar';
import SlashCommandMenu from '@/components/create/SlashCommandMenu';
import SelectionFloatMenu from '@/components/create/SelectionFloatMenu';
import DiffView from '@/components/create/DiffView';
import CreateChatPanel from '@/components/create/CreateChatPanel';
import { createGhostTextExtension } from '@/components/create/GhostTextExtension';

// ── Helpers ──────────────────────────────────────────────────────────────────

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

function noteTextContent(htmlContent) {
  if (!htmlContent) return '';
  if (!htmlContent.trimStart().startsWith('<')) return htmlContent;
  return stripHtml(htmlContent);
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

// ── Build the prompt for a slash command or selection action ─────────────────

function buildCopilotPrompt(command, noteText, selectionText, extraArg) {
  switch (command) {
    case 'continue':
      return `Continue the following text naturally. Output only the continuation — do not repeat existing text.\n\nText so far:\n${noteText}`;
    case 'describe':
      return `Describe the following passage or concept more vividly. Output only the description.\n\n${selectionText || noteText}`;
    case 'rewrite':
      return `Rewrite the following in the same voice but with improved clarity and flow. Output only the rewritten text.\n\n${selectionText || noteText}`;
    case 'expand':
      return `Expand the following with richer detail, atmosphere, and depth. Output only the expanded text.\n\n${selectionText || noteText}`;
    case 'condense':
      return `Condense the following to its essential ideas without losing meaning. Output only the condensed text.\n\n${selectionText || noteText}`;
    case 'character':
      return `Weave a mention of the character "${extraArg || 'the character'}" naturally into the following text. Output only the new version.\n\n${selectionText || noteText}`;
    case 'brainstorm':
      return `Based on the following note content, generate 5 interesting ideas, plot hooks, or directions to explore. Be creative and specific to this world.\n\n${noteText}`;
    case 'ask':
      return `${extraArg}\n\nContext (current note content):\n${selectionText || noteText}`;
    default:
      return `${command}\n\nContext:\n${noteText}`;
  }
}

// ── Main component ────────────────────────────────────────────────────────────

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
  vaultId = null,
}) {
  // ── Create mode state ────────────────────────────────────────────────────
  const [aiEnabled, setAiEnabled] = useState(false);
  const [subMode, setSubMode] = useState('copilot');
  const [aiLoading, setAiLoading] = useState(false);

  // Pending diff: { old, new, command, selectionFrom, selectionTo, append }
  const [pendingDiff, setPendingDiff] = useState(null);

  // Slash command state
  const [slashOpen, setSlashOpen] = useState(false);
  const [slashPos, setSlashPos] = useState({ left: 0, top: 0 });
  const [slashFilter, setSlashFilter] = useState('');
  const [slashStartPos, setSlashStartPos] = useState(null);

  // Selection float menu state
  const [selMenuOpen, setSelMenuOpen] = useState(false);
  const [selMenuPos, setSelMenuPos] = useState({ left: 0, top: 0 });
  const selectionRef = useRef({ from: 0, to: 0, text: '' });

  // Chat panel
  const [chatOpen, setChatOpen] = useState(false);

  // ── Refs for GhostTextExtension ──────────────────────────────────────────
  const aiEnabledRef = useRef(false);
  const onGetSuggestionRef = useRef(null);

  useEffect(() => {
    aiEnabledRef.current = aiEnabled && subMode === 'copilot';
  }, [aiEnabled, subMode]);

  // Ghost text suggestion callback — updated whenever note/vault changes
  useEffect(() => {
    onGetSuggestionRef.current = async (textBefore, signal) => {
      if (!vaultId || !selectedNote) return null;
      try {
        const resp = await ai.ask(
          `Continue the following text with one or two sentences in the same voice. Output only the continuation.\n\n${textBefore}`,
          [],
          vaultId,
          'create',
          null,
          {
            sub_mode: 'copilot',
            current_entity: {
              type: 'note', id: selectedNote.id, title: selectedNote.title, content: textBefore,
            },
          }
        );
        if (signal?.aborted) return null;
        const text = resp?.response?.trim() || null;
        return text && text.length > 400 ? text.slice(0, 400) : text;
      } catch {
        return null;
      }
    };
  }, [vaultId, selectedNote]);

  // Ghost text extension — created once, reads from refs
  const ghostTextExtension = useMemo(
    () => createGhostTextExtension({ enabledRef: aiEnabledRef, onGetSuggestionRef }),
    [] // eslint-disable-line react-hooks/exhaustive-deps
  );

  const editingUser =
    editingPresence?.email || editingPresence?.username || editingPresence?.user_id;
  const editingText = editingUser ? `${editingUser} is editing this note.` : null;

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
      ghostTextExtension,
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

  // Close AI overlays when note changes or edit mode exits
  useEffect(() => {
    setSlashOpen(false);
    setSelMenuOpen(false);
    setPendingDiff(null);
  }, [selectedNote?.id, isEditing]);

  // Keep chat in sync with AI toggle and sub-mode
  useEffect(() => {
    if (!aiEnabled) setChatOpen(false);
  }, [aiEnabled]);

  useEffect(() => {
    if (aiEnabled && subMode === 'chat') setChatOpen(true);
    if (subMode === 'copilot') setChatOpen(false);
  }, [aiEnabled, subMode]);

  // ── Slash command detection ──────────────────────────────────────────────

  useEffect(() => {
    if (!editor || !aiEnabled || subMode !== 'copilot') {
      setSlashOpen(false);
      return;
    }

    const handleUpdate = () => {
      if (!editor.state.selection.empty) { setSlashOpen(false); return; }

      const { $head } = editor.state.selection;
      const textBefore = $head.parent.textContent.slice(0, $head.parentOffset);

      const slashIdx = textBefore.lastIndexOf('/');
      if (slashIdx === -1) { setSlashOpen(false); setSlashFilter(''); return; }

      // Only treat '/' at start of line or after a space as a command trigger
      const charBefore = textBefore[slashIdx - 1];
      if (slashIdx > 0 && charBefore !== ' ') { setSlashOpen(false); return; }

      const typedAfterSlash = textBefore.slice(slashIdx + 1);
      if (/\s/.test(typedAfterSlash)) { setSlashOpen(false); return; }

      const coords = editor.view.coordsAtPos(editor.state.selection.head);
      const docSlashPos = $head.pos - $head.parentOffset + slashIdx;

      setSlashPos({ left: coords.left, top: coords.bottom });
      setSlashFilter(typedAfterSlash);
      setSlashStartPos(docSlashPos);
      setSlashOpen(true);
    };

    editor.on('update', handleUpdate);
    editor.on('selectionUpdate', handleUpdate);
    return () => {
      editor.off('update', handleUpdate);
      editor.off('selectionUpdate', handleUpdate);
    };
  }, [editor, aiEnabled, subMode]);

  // ── Selection float menu detection ──────────────────────────────────────

  useEffect(() => {
    if (!editor || !aiEnabled || subMode !== 'copilot') {
      setSelMenuOpen(false);
      return;
    }

    const handleSelectionUpdate = () => {
      const { selection } = editor.state;
      if (selection.empty) {
        setSelMenuOpen(false);
        selectionRef.current = { from: 0, to: 0, text: '' };
        return;
      }

      const text = editor.state.doc.textBetween(selection.from, selection.to, '\n');
      selectionRef.current = { from: selection.from, to: selection.to, text };

      const fromCoords = editor.view.coordsAtPos(selection.from);
      setSelMenuPos({ left: fromCoords.left + 80, top: fromCoords.top });
      setSelMenuOpen(true);
    };

    editor.on('selectionUpdate', handleSelectionUpdate);
    return () => editor.off('selectionUpdate', handleSelectionUpdate);
  }, [editor, aiEnabled, subMode]);

  // ── Execute slash command ────────────────────────────────────────────────

  const executeSlashCommand = useCallback(
    async (commandId) => {
      setSlashOpen(false);
      setSlashFilter('');

      // Delete the '/' and any typed filter text from the editor
      if (slashStartPos !== null && editor) {
        const cursorPos = editor.state.selection.from;
        if (cursorPos > slashStartPos) {
          editor.chain().focus().deleteRange({ from: slashStartPos, to: cursorPos }).run();
        }
      }

      let extraArg = null;
      if (commandId === 'character') {
        extraArg = window.prompt('Character name to weave in:');
        if (!extraArg?.trim()) return;
      }

      const noteText = noteTextContent(selectedNote?.content || '');
      await runCopilotAction(commandId, noteText, null, extraArg);
    },
    [editor, slashStartPos, selectedNote] // eslint-disable-line react-hooks/exhaustive-deps
  );

  // ── Execute selection action ─────────────────────────────────────────────

  const executeSelectionAction = useCallback(
    async (action, customPrompt) => {
      setSelMenuOpen(false);
      const { from, to, text: selText } = selectionRef.current;
      const noteText = noteTextContent(selectedNote?.content || '');
      await runCopilotAction(action, noteText, { from, to, text: selText }, customPrompt || null);
    },
    [selectedNote] // eslint-disable-line react-hooks/exhaustive-deps
  );

  // ── Core copilot action ──────────────────────────────────────────────────

  const runCopilotAction = useCallback(
    async (commandId, noteText, selection, extraArg) => {
      if (!vaultId || !selectedNote || aiLoading) return;
      setAiLoading(true);

      const useText = noteText || noteTextContent(selectedNote?.content || '');
      const prompt = buildCopilotPrompt(commandId, useText, selection?.text || null, extraArg);

      try {
        const resp = await ai.ask(
          prompt,
          [],
          vaultId,
          'create',
          null,
          {
            sub_mode: 'copilot',
            current_entity: {
              type: 'note', id: selectedNote.id, title: selectedNote.title, content: useText,
            },
          }
        );

        const newText = resp?.response?.trim() || '';
        if (!newText) return;

        if (commandId === 'brainstorm') {
          setPendingDiff({
            old: '',
            new: newText,
            command: 'Brainstorm ideas',
            selectionFrom: null,
            selectionTo: null,
            append: true,
          });
        } else if (selection) {
          setPendingDiff({
            old: selection.text,
            new: newText,
            command: commandId.charAt(0).toUpperCase() + commandId.slice(1),
            selectionFrom: selection.from,
            selectionTo: selection.to,
            append: false,
          });
        } else {
          setPendingDiff({
            old: useText,
            new: newText,
            command: commandId.charAt(0).toUpperCase() + commandId.slice(1),
            selectionFrom: null,
            selectionTo: null,
            append: false,
          });
        }
      } catch (err) {
        console.error('[Create mode] copilot action failed:', err);
      } finally {
        setAiLoading(false);
      }
    },
    [vaultId, selectedNote, aiLoading]
  );

  // ── Accept / reject diff ─────────────────────────────────────────────────

  const handleAcceptDiff = useCallback(() => {
    if (!pendingDiff || !editor) return;

    if (pendingDiff.append) {
      editor
        .chain()
        .focus()
        .insertContentAt(editor.state.doc.content.size, `\n\n${pendingDiff.new}`)
        .run();
    } else if (pendingDiff.selectionFrom !== null) {
      editor
        .chain()
        .focus()
        .deleteRange({ from: pendingDiff.selectionFrom, to: pendingDiff.selectionTo })
        .insertContentAt(pendingDiff.selectionFrom, pendingDiff.new)
        .run();
    } else {
      editor.commands.setContent(processContent(pendingDiff.new), true);
    }

    setPendingDiff(null);
  }, [pendingDiff, editor]);

  const handleRejectDiff = useCallback(() => setPendingDiff(null), []);

  // ── Apply edit from chat panel ────────────────────────────────────────────

  const handleApplyChatEdit = useCallback(
    (newContent) => {
      if (editor) editor.commands.setContent(processContent(newContent), true);
    },
    [editor]
  );

  // ── Standard callbacks ────────────────────────────────────────────────────

  const handleInsertLink = useCallback(
    (link) => {
      if (!editor) return;
      editor.chain().focus().insertContent(`[[${link}]]`).run();
    },
    [editor]
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

  // ── Render ────────────────────────────────────────────────────────────────

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
    <>
      {/* Floating menus — outside the card to avoid overflow clipping */}
      <SlashCommandMenu
        open={slashOpen}
        pos={slashPos}
        filter={slashFilter}
        onSelect={executeSlashCommand}
        onClose={() => { setSlashOpen(false); setSlashFilter(''); }}
      />
      <SelectionFloatMenu
        open={selMenuOpen && !pendingDiff}
        pos={selMenuPos}
        loading={aiLoading}
        onAction={executeSelectionAction}
        onClose={() => setSelMenuOpen(false)}
      />

      {/* Editor + optional chat panel */}
      <div className="flex flex-1 min-w-0 overflow-hidden">
        <Card className="flex flex-col overflow-hidden p-0 min-w-0 flex-1">
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

              {/* Create mode AI toggle — rightmost in toolbar */}
              <CreateModeToolbar
                aiEnabled={aiEnabled}
                onToggleAI={setAiEnabled}
                subMode={subMode}
                onSubModeChange={setSubMode}
              />
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

          {/* Co-pilot hint bar */}
          {isEditing && aiEnabled && subMode === 'copilot' && !pendingDiff && (
            <div className="px-4 py-1.5 bg-accent/5 border-b border-accent/10 text-xs text-txt-muted flex items-center gap-3 flex-wrap">
              <span className="text-accent font-semibold">Co-pilot on</span>
              <span>
                Type{' '}
                <kbd className="px-1.5 py-0.5 rounded bg-elevated font-mono border border-txt-muted/20">/</kbd>
                {' '}for commands · Pause for ghost text{' '}
                <kbd className="px-1.5 py-0.5 rounded bg-elevated font-mono border border-txt-muted/20">Tab</kbd>
                {' '}to accept · Select text for quick actions
              </span>
            </div>
          )}

          {/* Editor content area OR diff view */}
          <div className="flex-1 overflow-hidden flex flex-col min-h-0">
            {pendingDiff ? (
              <DiffView
                command={pendingDiff.command}
                oldText={pendingDiff.old}
                newText={pendingDiff.new}
                loading={aiLoading}
                onAccept={handleAcceptDiff}
                onReject={handleRejectDiff}
              />
            ) : (
              <div className="flex-1 overflow-y-auto p-5">
                <EditorContent editor={editor} className="tiptap-editor" />
              </div>
            )}
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

        {/* Chat panel — slides in to the right */}
        {chatOpen && (
          <div className="w-72 flex-shrink-0 flex flex-col overflow-hidden">
            <CreateChatPanel
              vaultId={vaultId}
              currentNote={selectedNote}
              onApplyEdit={handleApplyChatEdit}
              onClose={() => { setChatOpen(false); setSubMode('copilot'); }}
            />
          </div>
        )}
      </div>
    </>
  );
}
