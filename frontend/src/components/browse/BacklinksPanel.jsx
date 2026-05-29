import { useQuery } from '@tanstack/react-query';
import { toast } from 'sonner';
import { ArrowRight, ArrowLeft } from 'lucide-react';
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

  if (isLoading) {
    return (
      <div className="space-y-1.5">
        <SkeletonLine width="w-3/4" />
        <SkeletonLine width="w-1/2" />
        <SkeletonLine width="w-2/3" />
      </div>
    );
  }

  if (total === 0) {
    return (
      <p className="text-xs text-txt-muted/70 italic leading-relaxed">
        Nothing links here yet. Use{' '}
        <code className="font-mono bg-elevated rounded px-1 py-0.5 text-accent/80 not-italic">
          [[entry name]]
        </code>{' '}
        in any entry to create a link.
      </p>
    );
  }

  return (
    <div className="space-y-3">
      {fromLinks.length > 0 && (
        <div>
          <div className="flex items-center gap-1.5 mb-1.5 px-1">
            <ArrowRight size={10} className="text-txt-muted/50" />
            <p className="text-[10px] uppercase tracking-widest text-txt-muted/50 font-semibold">
              Links from here
            </p>
          </div>
          <div className="space-y-0.5">
            {fromLinks.map((link, i) => (
              <LinkItem key={i} link={link} onNavigate={onNavigate} />
            ))}
          </div>
        </div>
      )}
      {toLinks.length > 0 && (
        <div>
          <div className="flex items-center gap-1.5 mb-1.5 px-1">
            <ArrowLeft size={10} className="text-txt-muted/50" />
            <p className="text-[10px] uppercase tracking-widest text-txt-muted/50 font-semibold">
              Referenced by
            </p>
          </div>
          <div className="space-y-0.5">
            {toLinks.map((link, i) => (
              <LinkItem key={i} link={link} onNavigate={onNavigate} />
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
