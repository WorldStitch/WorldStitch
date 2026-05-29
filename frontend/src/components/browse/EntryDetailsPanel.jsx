import { useState } from 'react';
import {
  ChevronDown,
  ChevronRight,
  Tag,
  LayoutList,
  Network,
  Link2,
  Sparkles,
  Shield,
  Info,
  FolderOpen,
} from 'lucide-react';
import TagPanel from './TagPanel';
import MetaPanel from './MetaPanel';
import PermissionsPanel from './PermissionsPanel';
import BacklinksPanel from './BacklinksPanel';
import RelationshipPanel from './RelationshipPanel';

function usePersistedToggle(key, defaultOpen) {
  return useState(() => {
    const saved = localStorage.getItem(`ws-panel-${key}`);
    return saved === null ? defaultOpen : saved === 'true';
  });
}

function Section({ icon, label, badge, defaultOpen = true, storageKey, children }) {
  const [open, setOpen] = usePersistedToggle(storageKey, defaultOpen);

  const toggle = () => {
    setOpen((v) => {
      const next = !v;
      localStorage.setItem(`ws-panel-${storageKey}`, String(next));
      return next;
    });
  };

  return (
    <div className="border-b border-txt-muted/[0.08] last:border-b-0">
      <button
        type="button"
        onClick={toggle}
        className="w-full flex items-center gap-2.5 px-4 py-2.5 hover:bg-hover/40 transition-colors text-left"
      >
        <span className="text-txt-muted/60">{icon}</span>
        <span className="flex-1 text-sm font-medium text-txt">{label}</span>
        {badge != null && badge > 0 && (
          <span className="text-[10px] font-semibold text-txt-muted bg-txt-muted/10 rounded-full px-1.5 py-0.5 mr-0.5 tabular-nums">
            {badge}
          </span>
        )}
        <ChevronDown
          size={13}
          className={`text-txt-muted/40 flex-shrink-0 transition-transform duration-150 ${open ? '' : '-rotate-90'}`}
        />
      </button>
      {open && <div className="px-4 pb-4 pt-0.5">{children}</div>}
    </div>
  );
}

function TypeBadge({ type }) {
  return (
    <span className="text-[10px] font-bold uppercase tracking-widest bg-accent/10 text-accent rounded px-1.5 py-0.5">
      {type}
    </span>
  );
}

function InfoRow({ label, children }) {
  return (
    <div className="flex items-start justify-between gap-3 py-1.5 border-b border-txt-muted/[0.06] last:border-b-0">
      <span className="text-xs text-txt-muted flex-shrink-0">{label}</span>
      <span className="text-xs text-txt text-right min-w-0">{children}</span>
    </div>
  );
}

function formatDate(d) {
  if (!d) return '—';
  return new Date(d).toLocaleDateString(undefined, {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
  });
}

function formatDateTime(d) {
  if (!d) return '—';
  const date = new Date(d);
  return (
    date.toLocaleDateString(undefined, { month: 'short', day: 'numeric' }) +
    ' at ' +
    date.toLocaleTimeString(undefined, { hour: 'numeric', minute: '2-digit' })
  );
}

export default function EntryDetailsPanel({
  selectedNote,
  user,
  userList = [],
  allFolders = [],
  allNotes = [],
  activeVaultId,
  canEdit,
  canManagePermissions,
  groupList = [],
  wordCount,
  onAddTag,
  onRemoveTag,
  onSuggestTags,
  onAddMeta,
  onRemoveMeta,
  onSetGroup,
  onSetPermission,
  onToggleGmOnly,
  onNavigate,
}) {
  const [advancedOpen, setAdvancedOpen] = useState(() => {
    const saved = localStorage.getItem('ws-panel-advanced');
    return saved === 'true';
  });

  const toggleAdvanced = () => {
    setAdvancedOpen((v) => {
      const next = !v;
      localStorage.setItem('ws-panel-advanced', String(next));
      return next;
    });
  };

  const isOwner = selectedNote?.owner_id === user?.id;
  const canSeeSharing = isOwner || canManagePermissions;

  const ownerName = (() => {
    if (!selectedNote?.owner_id) return null;
    if (selectedNote.owner_id === user?.id) return 'You';
    const found = userList.find((u) => u.id === selectedNote.owner_id);
    if (found) return found.username;
    return `${selectedNote.owner_id.slice(0, 8)}…`;
  })();

  const folder = allFolders.find((f) => f.id === selectedNote?.folder_id);
  const entryType = selectedNote?.meta?.type || selectedNote?.entity_type || null;
  const tagCount = (selectedNote?.tags || []).length;
  const metaCount = Object.keys(selectedNote?.meta || {}).filter(
    (k) => k !== 'gm_only' && k !== 'type',
  ).length;
  const wc = wordCount ? wordCount(selectedNote?.content) : 0;
  const hasAISummary = !!selectedNote?.ai_summary;

  return (
    <div className="flex flex-col">
      {/* Panel header */}
      <div className="px-4 py-3 border-b border-txt-muted/[0.08] flex items-center gap-2 flex-shrink-0">
        <h3 className="text-sm font-semibold text-txt flex-1">Entry Details</h3>
        {entryType && <TypeBadge type={entryType} />}
      </div>

      {/* Tags */}
      <Section
        icon={<Tag size={13} />}
        label="Tags"
        badge={tagCount}
        storageKey="tags"
      >
        <TagPanel
          selectedNote={selectedNote}
          onAddTag={onAddTag}
          onRemoveTag={onRemoveTag}
          onSuggestTags={onSuggestTags}
        />
      </Section>

      {/* Details / Properties */}
      <Section
        icon={<LayoutList size={13} />}
        label="Details"
        badge={metaCount}
        storageKey="details"
      >
        <MetaPanel
          selectedNote={selectedNote}
          onAddMeta={onAddMeta}
          onRemoveMeta={onRemoveMeta}
          canEdit={canEdit}
        />
      </Section>

      {/* Connections (Relationships) */}
      <Section icon={<Network size={13} />} label="Connections" storageKey="connections">
        <RelationshipPanel
          entityId={selectedNote?.id}
          vaultId={activeVaultId}
          allNotes={allNotes}
          onNavigate={(noteId) => {
            const note = allNotes.find((n) => n.id === noteId);
            if (note) onNavigate?.(note.id, 'note', note.title);
          }}
          headless
        />
      </Section>

      {/* Mentioned In (Backlinks) */}
      <Section icon={<Link2 size={13} />} label="Mentioned in" storageKey="backlinks">
        <BacklinksPanel noteId={selectedNote?.id} onNavigate={onNavigate} />
      </Section>

      {/* AI Summary — only shown when one exists */}
      {hasAISummary && (
        <Section
          icon={<Sparkles size={13} />}
          label="AI Summary"
          storageKey="ai-summary"
        >
          <p className="text-xs text-txt-secondary leading-relaxed">{selectedNote.ai_summary}</p>
        </Section>
      )}

      {/* Sharing — visible to owners and admins only */}
      {canSeeSharing && (
        <Section
          icon={<Shield size={13} />}
          label="Sharing"
          storageKey="sharing"
          defaultOpen={false}
        >
          <PermissionsPanel
            selectedNote={selectedNote}
            allFolders={allFolders}
            onSetGroup={onSetGroup}
            groups={groupList}
            users={userList}
            canEdit={canEdit}
            onSetPermission={onSetPermission}
            onToggleGmOnly={onToggleGmOnly}
          />
        </Section>
      )}

      {/* Info */}
      <Section icon={<Info size={13} />} label="Info" storageKey="info">
        <div>
          {folder && (
            <InfoRow label="Folder">
              <span className="flex items-center gap-1 justify-end">
                <FolderOpen size={11} className="text-txt-muted flex-shrink-0" />
                {folder.name}
              </span>
            </InfoRow>
          )}
          {ownerName && <InfoRow label="Owner">{ownerName}</InfoRow>}
          <InfoRow label="Created">{formatDate(selectedNote?.created_at)}</InfoRow>
          <InfoRow label="Modified">{formatDateTime(selectedNote?.last_modified)}</InfoRow>
          <InfoRow label="Words">{wc.toLocaleString()}</InfoRow>
        </div>

        {/* Advanced toggle for Entry ID */}
        <div className="mt-3">
          <button
            type="button"
            onClick={toggleAdvanced}
            className="flex items-center gap-1 text-[10px] text-txt-muted/50 hover:text-txt-muted transition-colors"
          >
            <ChevronRight
              size={10}
              className={`flex-shrink-0 transition-transform ${advancedOpen ? 'rotate-90' : ''}`}
            />
            Advanced
          </button>
          {advancedOpen && (
            <div className="mt-2">
              <p className="text-[10px] text-txt-muted/50 uppercase tracking-widest mb-1">
                Entry ID
              </p>
              <p className="text-[10px] font-mono text-txt-muted bg-elevated rounded px-2 py-1.5 break-all select-all leading-relaxed">
                {selectedNote?.id}
              </p>
            </div>
          )}
        </div>
      </Section>
    </div>
  );
}
