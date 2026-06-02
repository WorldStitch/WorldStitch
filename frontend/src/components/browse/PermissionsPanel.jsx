import { useState } from 'react';
import Badge from '@/components/Badge';
import Button from '@/components/Button';

export default function PermissionsPanel({
  selectedNote,
  onSetGroup,
  groups = [],
  users = [],
  canEdit = true,
  onSetPermission,
  onToggleGmOnly,
}) {
  const [subjectId, setSubjectId] = useState('');
  const [role, setRole] = useState('read');

  const gmOnly =
    selectedNote?.meta?.gm_only === 'true' || selectedNote?.meta?.gm_only === true;

  const getDisplayName = (entityId) =>
    users.find((u) => u.id === entityId)?.username ||
    groups.find((g) => g.id === entityId)?.name ||
    entityId;

  return (
    <div className="space-y-4">
      {/* Shared Group */}
      <div className="space-y-1.5">
        <p className="text-xs font-medium text-txt-muted">Shared with group</p>
        <select
          value={selectedNote?.group_id || ''}
          onChange={(e) => onSetGroup(e.target.value)}
          disabled={!canEdit}
          className="w-full bg-elevated rounded-lg px-2.5 py-1.5 text-xs text-txt border border-transparent focus:border-accent/50 focus:outline-none disabled:opacity-60"
        >
          <option value="">No group</option>
          {groups.map((group) => (
            <option key={group.id} value={group.id}>
              {group.name}
            </option>
          ))}
        </select>
      </div>

      {/* GM Only */}
      <label className="flex items-center justify-between cursor-pointer select-none">
        <span className="text-xs font-medium text-txt-muted">GM only</span>
        <input
          type="checkbox"
          checked={gmOnly}
          disabled={!canEdit}
          onChange={(e) => onToggleGmOnly?.(e.target.checked)}
          className="rounded"
        />
      </label>

      {/* Current permissions */}
      <div className="space-y-1.5">
        <p className="text-xs font-medium text-txt-muted">Who has access</p>
        {Object.keys(selectedNote?.permissions || {}).length > 0 ? (
          <div>
            {Object.entries(selectedNote.permissions).map(([entityId, entityRole]) => (
              <div
                key={entityId}
                className="flex items-center justify-between text-xs py-1.5 border-b border-txt-muted/[0.06] last:border-b-0"
              >
                <span className="text-txt truncate">{getDisplayName(entityId)}</span>
                <Badge
                  label={entityRole === 'write' ? 'Can edit' : 'Can view'}
                  variant={entityRole === 'write' ? 'active' : 'player'}
                />
              </div>
            ))}
          </div>
        ) : (
          <p className="text-xs text-txt-muted/70 italic">Only you have access</p>
        )}
      </div>

      {/* Add permission */}
      {canEdit && (
        <div className="space-y-1.5">
          <p className="text-xs font-medium text-txt-muted">Share with someone</p>
          <select
            value={subjectId}
            onChange={(e) => setSubjectId(e.target.value)}
            className="w-full bg-elevated rounded-lg px-2.5 py-1.5 text-xs text-txt border border-transparent focus:border-accent/50 focus:outline-none"
          >
            <option value="">Select a person or group…</option>
            {users.map((u) => (
              <option key={`user-${u.id}`} value={u.id}>
                {u.username}
              </option>
            ))}
            {groups.map((group) => (
              <option key={`group-${group.id}`} value={group.id}>
                Group · {group.name}
              </option>
            ))}
          </select>
          <div className="flex gap-2">
            <select
              value={role}
              onChange={(e) => setRole(e.target.value)}
              className="flex-1 bg-elevated rounded-lg px-2.5 py-1.5 text-xs text-txt border border-transparent focus:border-accent/50 focus:outline-none"
            >
              <option value="read">Can view</option>
              <option value="write">Can edit</option>
            </select>
            <Button
              size="sm"
              onClick={() => {
                onSetPermission?.(subjectId, role);
                setSubjectId('');
              }}
              disabled={!subjectId}
            >
              Share
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}
