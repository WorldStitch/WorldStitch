import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import SectionHeader from '@/components/SectionHeader';
import Card from '@/components/Card';
import Button from '@/components/Button';
import Badge from '@/components/Badge';
import { invites } from '@/api';

export default function OwnerInvites() {
  const qc = useQueryClient();
  const { data: inviteList = [] } = useQuery({ queryKey: ['invites'], queryFn: invites.list });

  const generateInvite = useMutation({
    mutationFn: () => invites.generate(),
    onSuccess: (data) => {
      qc.invalidateQueries({ queryKey: ['invites'] });
      navigator.clipboard.writeText(data.code).catch(() => {});
      toast.success(`Invite code copied to clipboard: ${data.code}`);
    },
    onError: (err) => toast.error(err.message),
  });

  const revokeInvite = useMutation({
    mutationFn: (code) => invites.revoke(code),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['invites'] });
      toast.success('Invite revoked');
    },
    onError: (err) => toast.error(err.message),
  });

  const statusVariant = (status) => {
    if (status === 'Active') return 'active';
    if (status === 'Expired') return 'expired';
    return 'disabled';
  };

  return (
    <div className="p-10 space-y-6">
      <SectionHeader title="Invite Management" subtitle="Generate and manage invite codes for new users." />

      <div className="flex items-center gap-3">
        <Button onClick={() => generateInvite.mutate()} disabled={generateInvite.isPending}>
          {generateInvite.isPending ? 'Generating...' : 'Generate Invite'}
        </Button>
      </div>

      <Card className="p-6">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-txt-muted border-b border-border-subtle">
                <th className="pb-3 pr-4 font-medium">Code</th>
                <th className="pb-3 pr-4 font-medium">Created</th>
                <th className="pb-3 pr-4 font-medium">Expires</th>
                <th className="pb-3 pr-4 font-medium">Status</th>
                <th className="pb-3 pr-4 font-medium">Used By</th>
                <th className="pb-3 font-medium"></th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border-subtle">
              {inviteList.map((invite) => (
                <tr key={invite.id} className="text-txt">
                  <td className="py-3 pr-4">
                    <code className="font-mono text-accent text-xs bg-elevated px-2 py-1 rounded">
                      {invite.code}
                    </code>
                  </td>
                  <td className="py-3 pr-4 text-txt-muted">
                    {new Date(invite.created_at).toLocaleDateString()}
                  </td>
                  <td className="py-3 pr-4 text-txt-muted">
                    {new Date(invite.expires_at).toLocaleDateString()}
                  </td>
                  <td className="py-3 pr-4">
                    <Badge label={invite.status} variant={statusVariant(invite.status)} />
                  </td>
                  <td className="py-3 pr-4 text-txt-muted">
                    {invite.used_by ?? '—'}
                  </td>
                  <td className="py-3">
                    <Button
                      variant="danger"
                      size="sm"
                      disabled={invite.is_used || !invite.is_active || revokeInvite.isPending}
                      onClick={() => revokeInvite.mutate(invite.code)}
                    >
                      Revoke
                    </Button>
                  </td>
                </tr>
              ))}
              {!inviteList.length && (
                <tr>
                  <td colSpan={6} className="py-6 text-center text-txt-muted">
                    No invites yet.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  );
}
