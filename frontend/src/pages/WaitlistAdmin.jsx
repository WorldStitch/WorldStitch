import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { getToken } from '../api';

const STATUS_COLORS = {
  pending:  'bg-yellow-500/10 text-yellow-400 border-yellow-500/20',
  approved: 'bg-green-500/10 text-green-400 border-green-500/20',
  rejected: 'bg-red-500/10 text-red-400 border-red-500/20',
};

async function apiFetch(path, options = {}) {
  const token = getToken();
  const res = await fetch(path, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(options.headers || {}),
    },
  });
  if (!res.ok) throw new Error(`${res.status}`);
  return res.json();
}

export default function WaitlistAdmin() {
  const [statusFilter, setStatusFilter] = useState('');
  const queryClient = useQueryClient();

  const url = statusFilter ? `/admin/waitlist?status=${statusFilter}` : '/admin/waitlist';

  const { data: applications = [], isLoading, error } = useQuery({
    queryKey: ['admin-waitlist', statusFilter],
    queryFn: () => apiFetch(url),
    refetchInterval: 30_000,
  });

  const approve = useMutation({
    mutationFn: (id) => apiFetch(`/admin/waitlist/${id}/approve`, { method: 'POST' }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['admin-waitlist'] }),
  });

  const reject = useMutation({
    mutationFn: (id) => apiFetch(`/admin/waitlist/${id}/reject`, { method: 'POST' }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['admin-waitlist'] }),
  });

  const counts = {
    all: applications.length,
    pending: applications.filter(a => a.status === 'pending').length,
  };

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <div>
          <h2 className="text-lg font-bold text-txt">Waitlist Applications</h2>
          <p className="text-txt-muted text-sm mt-0.5">
            {counts.all} total · {counts.pending} pending review
          </p>
        </div>

        <div className="flex gap-2">
          {['', 'pending', 'approved', 'rejected'].map((s) => (
            <button
              key={s}
              onClick={() => setStatusFilter(s)}
              className={`px-3 py-1.5 rounded-lg text-xs font-medium transition ${
                statusFilter === s
                  ? 'bg-accent/15 text-accent'
                  : 'text-txt-muted hover:bg-hover hover:text-txt'
              }`}
            >
              {s === '' ? 'All' : s.charAt(0).toUpperCase() + s.slice(1)}
            </button>
          ))}
        </div>
      </div>

      {isLoading && (
        <div className="text-txt-muted text-sm py-8 text-center">Loading applications…</div>
      )}

      {error && (
        <div className="text-red-400 text-sm py-8 text-center">
          Failed to load waitlist. Please refresh.
        </div>
      )}

      {!isLoading && !error && applications.length === 0 && (
        <div className="text-txt-muted text-sm py-12 text-center">
          No applications {statusFilter ? `with status "${statusFilter}"` : 'yet'}.
        </div>
      )}

      {!isLoading && applications.length > 0 && (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border">
                <th className="text-left text-txt-muted font-medium py-3 pr-4 whitespace-nowrap">Name</th>
                <th className="text-left text-txt-muted font-medium py-3 pr-4 whitespace-nowrap">Email</th>
                <th className="text-left text-txt-muted font-medium py-3 pr-4">World</th>
                <th className="text-left text-txt-muted font-medium py-3 pr-4 whitespace-nowrap">Source</th>
                <th className="text-left text-txt-muted font-medium py-3 pr-4 whitespace-nowrap">Applied</th>
                <th className="text-left text-txt-muted font-medium py-3 pr-4 whitespace-nowrap">Status</th>
                <th className="text-right text-txt-muted font-medium py-3">Actions</th>
              </tr>
            </thead>
            <tbody>
              {applications.map((app) => (
                <tr key={app.id} className="border-b border-border/50 hover:bg-hover/30 transition-colors">
                  <td className="py-3 pr-4 font-medium text-txt whitespace-nowrap">{app.name}</td>
                  <td className="py-3 pr-4 text-txt-muted">{app.email}</td>
                  <td className="py-3 pr-4 text-txt-muted max-w-[220px]">
                    {app.world_description ? (
                      <span className="line-clamp-2 block" title={app.world_description}>
                        {app.world_description}
                      </span>
                    ) : (
                      <span className="text-txt-dim italic">—</span>
                    )}
                  </td>
                  <td className="py-3 pr-4 text-txt-muted capitalize whitespace-nowrap">
                    {app.referral_source || '—'}
                  </td>
                  <td className="py-3 pr-4 text-txt-muted whitespace-nowrap">
                    {app.created_at
                      ? new Date(app.created_at).toLocaleDateString('en-US', {
                          month: 'short', day: 'numeric', year: 'numeric',
                        })
                      : '—'}
                  </td>
                  <td className="py-3 pr-4">
                    <span
                      className={`inline-flex px-2 py-0.5 rounded border text-xs font-medium capitalize ${
                        STATUS_COLORS[app.status] || 'bg-surface text-txt-muted border-border'
                      }`}
                    >
                      {app.status}
                    </span>
                  </td>
                  <td className="py-3 text-right">
                    {app.status === 'pending' && (
                      <div className="flex gap-2 justify-end">
                        <button
                          onClick={() => approve.mutate(app.id)}
                          disabled={approve.isPending || reject.isPending}
                          className="px-3 py-1 rounded text-xs font-medium bg-green-500/10 text-green-400 border border-green-500/20 hover:bg-green-500/20 transition disabled:opacity-50"
                        >
                          Approve
                        </button>
                        <button
                          onClick={() => reject.mutate(app.id)}
                          disabled={approve.isPending || reject.isPending}
                          className="px-3 py-1 rounded text-xs font-medium bg-red-500/10 text-red-400 border border-red-500/20 hover:bg-red-500/20 transition disabled:opacity-50"
                        >
                          Reject
                        </button>
                      </div>
                    )}
                    {app.status !== 'pending' && (
                      <span className="text-txt-dim text-xs">—</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
