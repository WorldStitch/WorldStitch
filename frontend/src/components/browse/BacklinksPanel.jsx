import { useQuery } from '@tanstack/react-query';
import { toast } from 'sonner';
import { notes as notesApi } from '@/api';
import { SkeletonLine } from '@/components/Skeleton';

function EntityTypeBadge({ type }) {
  return (
    <span className="text-[9px] uppercase tracking-widest font-bold bg-txt-muted/10 text-txt-muted rounded px-1 py-0.5 flex-shrink-0">
      {type}
    </span>
  );
}

function LinkItem({ link, onNavigate }) {
  const handleClick = () => {
    if (link.other_entity_type === 'note') {
      onNavigate?.(link.other_entity_id, link.other_entity_type, link.label);
    } else {
      toast.info(`Navigate to ${link.other_entity_type}: ${link.label}`);
    }
  };

  return (
    <button
      onClick={handleClick}
      className="w-full flex items-center gap-2 px-2 py-1.5 rounded-lg hover:bg-hover transition text-left group"
    >
      <EntityTypeBadge type={link.other_entity_type} />
      <span className="text-xs text-txt truncate flex-1 group-hover:text-accent transition-colors">
        {link.label || link.other_entity_id}
      </span>
      {link.relation_type && link.relation_type !== 'wikilink' && (
        <span className="text-[9px] text-txt-muted flex-shrink-0">{link.relation_type}</span>
      )}
    </button>
  );
}

export default function BacklinksPanel({ noteId, onNavigate }) {
  const { data, isLoading } = useQuery({
    queryKey: ['backlinks', noteId],
    queryFn: () => notesApi.backlinks(noteId),
    enabled: !!noteId,
    staleTime: 30_000,
  });

  const fromLinks = (data || []).filter((l) => l.direction === 'from');
  const toLinks = (data || []).filter((l) => l.direction === 'to');
  const total = fromLinks.length + toLinks.length;

  return (
    <div>
      <p className="text-xs font-bold text-txt-muted uppercase tracking-wider mb-2">Links</p>

      {isLoading ? (
        <div className="space-y-1.5">
          <SkeletonLine width="w-3/4" />
          <SkeletonLine width="w-1/2" />
          <SkeletonLine width="w-2/3" />
        </div>
      ) : total === 0 ? (
        <p className="text-xs text-txt-muted leading-relaxed">
          No links yet — use{' '}
          <code className="font-mono bg-elevated rounded px-1 py-0.5 text-accent/80">
            [[brackets]]
          </code>{' '}
          to link entities
        </p>
      ) : (
        <>
          {/* Summary card */}
          <div className="mb-3 px-2 py-1.5 bg-accent/8 rounded-lg border border-accent/15">
            <p className="text-xs text-accent font-semibold">
              {total} relationship{total !== 1 ? 's' : ''}
            </p>
            {total > 0 && (
              <p className="text-[10px] text-txt-muted mt-0.5">
                {fromLinks.length} outgoing · {toLinks.length} incoming
              </p>
            )}
          </div>

          {/* Links from this note → targets */}
          {fromLinks.length > 0 && (
            <div className="mb-2">
              <p className="text-[10px] uppercase tracking-widest text-txt-muted font-bold px-1 mb-1">
                Links from this note
              </p>
              <div className="space-y-0.5">
                {fromLinks.map((link, i) => (
                  <LinkItem key={i} link={link} onNavigate={onNavigate} />
                ))}
              </div>
            </div>
          )}

          {/* Backlinks: sources that link TO this note */}
          {toLinks.length > 0 && (
            <div>
              <p className="text-[10px] uppercase tracking-widest text-txt-muted font-bold px-1 mb-1">
                Linked here
              </p>
              <div className="space-y-0.5">
                {toLinks.map((link, i) => (
                  <LinkItem key={i} link={link} onNavigate={onNavigate} />
                ))}
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}
