import { useState } from 'react';
import Badge from '@/components/Badge';
import Button from '@/components/Button';

export default function PermissionsPanel({
  selectedNote,
  allFolders,
  onSetGroup,
  groups = [],
  users = [],
  canEdit = true,
  onSetPermission,
  onToggleGmOnly,
}) {
  const [subjectId, setSubjectId] = useState('');
  const [role, setRole] = useState('read');
  const gmOnly = selectedNote?.meta?.gm_only === 'true' || selectedNote?.meta?.gm_only === true;
  const getDisplayName = (entityId) =>
    users.find((user) => user.id === entityId)?.username ||
    groups.find((group) => group.id === entityId)?.name ||
    entityId;

  return (
    <>
      <div>
        <p className="text-xs font-bold text-txt-muted uppercase tracking-wider mb-1">Folder</p>
        <p className="text-sm text-txt">
          {selectedNote.folder_id
            ? `📁 ${allFolders.find((f) => f.id === selectedNote.folder_id)?.name || selectedNote.folder_id}`
            : '📄 Unfiled'}
        </p>
      </div>

      <div>
        <p className="text-xs font-bold text-txt-muted uppercase tracking-wider mb-1">Shared Group</p>
        <select
          value={selectedNote.group_id || ''}
          onChange={(e) => onSetGroup(e.target.value)}
          disabled={!canEdit}
          className="w-full bg-elevated rounded-lg px-2 py-1 text-xs text-txt border border-transparent focus:border-accent focus:outline-none"
        >
          <option value="">None</option>
          {groups.map((group) => (
            <option key={group.id} value={group.id}>{group.name}</option>
          ))}
        </select>
      </div>

      <div className="space-y-2">
        <div className="flex items-center justify-between">
          <p className="text-xs font-bold text-txt-muted uppercase tracking-wider">Permissions</p>
          <label className="flex items-center gap-2 text-xs text-txt">
            <input type="checkbox" checked={gmOnly} disabled={!canEdit} onChange={(e) => onToggleGmOnly?.(e.target.checked)} />
            GM only
          </label>
        </div>
        {Object.keys(selectedNote.permissions || {}).length > 0 ? (
          <div className="space-y-1">
            {Object.entries(selectedNote.permissions).map(([entityId, entityRole]) => (
              <div key={entityId} className="flex justify-between text-xs">
                <span className="text-txt truncate">{getDisplayName(entityId)}</span>
                <Badge label={entityRole} variant={entityRole === 'write' ? 'active' : 'player'} />
              </div>
            ))}
          </div>
        ) : (
          <p className="text-txt-muted text-xs">Owner only</p>
        )}

        {canEdit && (
          <div className="space-y-2">
            <select
              value={subjectId}
              onChange={(e) => setSubjectId(e.target.value)}
              className="w-full bg-elevated rounded-lg px-2 py-1 text-xs text-txt border border-transparent focus:border-accent focus:outline-none"
            >
              <option value="">Select user or group</option>
              {users.map((user) => (
                <option key={`user-${user.id}`} value={user.id}>User · {user.username}</option>
              ))}
              {groups.map((group) => (
                <option key={`group-${group.id}`} value={group.id}>Group · {group.name}</option>
              ))}
            </select>
            <div className="flex gap-2">
              <select
                value={role}
                onChange={(e) => setRole(e.target.value)}
                className="flex-1 bg-elevated rounded-lg px-2 py-1 text-xs text-txt border border-transparent focus:border-accent focus:outline-none"
              >
                <option value="read">read</option>
                <option value="write">write</option>
              </select>
              <Button size="sm" onClick={() => onSetPermission?.(subjectId, role)} disabled={!subjectId}>Share</Button>
            </div>
          </div>
        )}
      </div>

      <div>
        <p className="text-xs font-bold text-txt-muted uppercase tracking-wider mb-1">
          Links ({(selectedNote.links || []).length})
        </p>
        {(selectedNote.links || []).length > 0 ? (
          <div className="space-y-1">
            {selectedNote.links.map((linkId) => (
              <p key={linkId} className="text-xs text-accent truncate">🔗 {linkId}</p>
            ))}
          </div>
        ) : (
          <p className="text-txt-muted text-xs">No links</p>
        )}
      </div>
    </>
  );
}
