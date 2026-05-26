import { useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import SectionHeader from '@/components/SectionHeader';
import Card from '@/components/Card';
import Button from '@/components/Button';
import { SkeletonLine, SkeletonStatCard } from '@/components/Skeleton';
import { dashboard } from '@/api';
import { useVault } from '@/context/VaultContext';

// Normalise the modified date field — backend may return either name
function getNoteDate(note) {
  return note.last_modified || note.modified_date;
}

export default function Dashboard({ user }) {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { activeVaultId } = useVault();

  // Invalidate recent notes on mount and on window focus
  useEffect(() => {
    queryClient.invalidateQueries({ queryKey: ['dashboard-recent', activeVaultId] });
    const onFocus = () => queryClient.invalidateQueries({ queryKey: ['dashboard-recent', activeVaultId] });
    window.addEventListener('focus', onFocus);
    return () => window.removeEventListener('focus', onFocus);
  }, [queryClient, activeVaultId]);

  const { data: stats, isLoading: statsLoading, isError: statsError } = useQuery({
    queryKey: ['dashboard-stats', activeVaultId],
    queryFn: () => dashboard.stats(activeVaultId),
  });

  const { data: recent = [], isLoading: recentLoading, isError: recentError } = useQuery({
    queryKey: ['dashboard-recent', activeVaultId],
    queryFn: () => dashboard.recent(activeVaultId),
    staleTime: 30000,
  });

  useEffect(() => {
    if (statsError) toast.error('Failed to load stats');
  }, [statsError]);

  useEffect(() => {
    if (recentError) toast.error('Failed to load recent notes');
  }, [recentError]);

  const loading = statsLoading || recentLoading;

  const StatCard = ({ icon, label, value, color }) => (
    <Card accent={color} className="p-6 flex flex-col justify-between h-full">
      <div>
        <div className="text-4xl mb-3">{icon}</div>
        <p className="text-txt-secondary text-sm font-medium">{label}</p>
      </div>
      <div className="text-3xl font-bold text-txt">
        {statsLoading ? '—' : value}
      </div>
    </Card>
  );

  return (
    <div className="p-10 space-y-10">
      <SectionHeader
        title="Dashboard"
        subtitle={`Welcome back, ${user?.username || 'there'} — here's your world at a glance.`}
      />

      {/* Stats Row */}
      <div className="grid grid-cols-3 lg:grid-cols-6 gap-4">
        {statsLoading ? (
          Array.from({ length: 6 }).map((_, i) => <SkeletonStatCard key={i} />)
        ) : (
          <>
            <StatCard icon="📝" label="Notes" value={stats?.notes || 0} color="#8b5cf6" />
            <StatCard icon="📁" label="Folders" value={stats?.folders || 0} color="#10b981" />
            <StatCard icon="👤" label="Characters" value={stats?.characters || 0} color="#f59e0b" />
            <StatCard icon="⚔️" label="Quests" value={stats?.quests || 0} color="#ef4444" />
            <StatCard icon="🌌" label="Timeline" value={stats?.timeline_events || 0} color="#60a5fa" />
            <StatCard icon="🎲" label="Sessions" value={stats?.sessions || 0} color="#a78bfa" />
          </>
        )}
      </div>

      {/* Bottom Row */}
      <div className="grid grid-cols-5 gap-5">
        {/* Recent Notes */}
        <div className="col-span-3">
          <Card className="p-6 h-full">
            <h3 className="text-lg font-bold text-txt mb-4">Recent Notes</h3>
            <div className="space-y-1">
              {recentLoading ? (
                <div className="space-y-2">
                  <SkeletonLine />
                  <SkeletonLine width="w-5/6" />
                  <SkeletonLine width="w-4/6" />
                </div>
              ) : recent.length > 0 ? (
                recent.map((note) => (
                  <div
                    key={note.id}
                    onClick={() => navigate(`/browse?note=${note.id}`)}
                    className="px-4 py-3 rounded-lg hover:bg-hover cursor-pointer transition"
                  >
                    <div className="flex justify-between items-center">
                      <span className="text-txt font-medium">{note.title}</span>
                      <span className="text-txt-muted text-xs">
                        {getNoteDate(note)
                          ? new Date(getNoteDate(note)).toLocaleDateString()
                          : 'N/A'}
                      </span>
                    </div>
                  </div>
                ))
              ) : (
                <div className="flex flex-col items-center justify-center py-8 text-center space-y-2">
                  <div className="text-3xl">📝</div>
                  <p className="text-txt-muted text-sm">No notes yet</p>
                  <Button variant="secondary" size="sm" onClick={() => navigate('/create')}>
                    Create your first note
                  </Button>
                </div>
              )}
            </div>
          </Card>
        </div>

        {/* Quick Actions */}
        <div className="col-span-2">
          <Card className="p-6 h-full">
            <h3 className="text-lg font-bold text-txt mb-4">Quick Actions</h3>
            <div className="space-y-3 flex flex-col h-full justify-center">
              <Button variant="primary" className="w-full" onClick={() => navigate('/create')}>
                New Note
              </Button>
              <Button variant="secondary" className="w-full" onClick={() => navigate('/browse')}>
                Browse Vault
              </Button>
              <Button variant="success" className="w-full" onClick={() => navigate('/chat')}>
                Ask AI
              </Button>
            </div>
          </Card>
        </div>
      </div>
    </div>
  );
}
