import { useEffect, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { toast } from 'sonner';
import { Layers, LogIn, UserPlus, Check, AlertTriangle, Loader } from 'lucide-react';
import Button from '@/components/Button';
import { vaultInvites } from '@/api';

export default function InviteAccept({ user }) {
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const token = params.get('token') || '';

  const [info, setInfo] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [accepting, setAccepting] = useState(false);
  const [accepted, setAccepted] = useState(false);

  useEffect(() => {
    if (!token) {
      setError('No invite token found in this link.');
      setLoading(false);
      return;
    }
    vaultInvites
      .validateToken(token)
      .then(setInfo)
      .catch((err) => setError(err.message || 'Invalid or expired invite link.'))
      .finally(() => setLoading(false));
  }, [token]);

  const handleAccept = async () => {
    setAccepting(true);
    try {
      const result = await vaultInvites.acceptToken(token);
      setAccepted(true);
      toast.success(`Welcome to ${result.vault_name}!`);
      setTimeout(() => navigate('/vaults'), 1500);
    } catch (err) {
      toast.error(err.message || 'Failed to accept invite');
    } finally {
      setAccepting(false);
    }
  };

  const goToLogin = (mode) => {
    const dest = `/login?token=${encodeURIComponent(token)}&mode=${mode}`;
    navigate(dest);
  };

  return (
    <div className="min-h-screen bg-base flex items-center justify-center p-4">
      <div className="w-full max-w-md">
        {/* Logo */}
        <div className="text-center mb-8">
          <div className="inline-flex items-center gap-2 text-2xl font-bold text-txt">
            <span className="text-3xl">⚡</span>
            <span>WorldStitch</span>
          </div>
        </div>

        <div className="bg-elevated rounded-2xl border border-border-subtle overflow-hidden">
          {/* Header stripe */}
          <div className="h-1.5 bg-gradient-to-r from-violet-600 to-purple-500" />

          <div className="p-8">
            {loading && (
              <div className="text-center py-8">
                <Loader size={32} className="animate-spin text-accent mx-auto mb-3" />
                <p className="text-txt-muted text-sm">Checking your invitation…</p>
              </div>
            )}

            {!loading && error && (
              <div className="text-center py-6">
                <AlertTriangle size={40} className="text-red-400 mx-auto mb-4" />
                <h2 className="text-lg font-semibold text-txt mb-2">Invalid Invitation</h2>
                <p className="text-txt-muted text-sm mb-6">{error}</p>
                <Button variant="secondary" onClick={() => navigate('/')}>
                  Go to WorldStitch
                </Button>
              </div>
            )}

            {!loading && !error && info && (
              <>
                <div className="flex items-center gap-3 mb-6">
                  <div className="w-12 h-12 rounded-xl bg-accent/10 flex items-center justify-center flex-shrink-0">
                    <Layers size={22} className="text-accent" />
                  </div>
                  <div>
                    <p className="text-xs text-txt-muted uppercase tracking-wider font-semibold mb-0.5">
                      Vault Invitation
                    </p>
                    <h2 className="text-xl font-bold text-txt leading-tight">{info.vault_name}</h2>
                  </div>
                </div>

                <p className="text-txt-muted text-sm mb-1">
                  <span className="text-txt font-medium">{info.invited_by_name}</span> has invited you to join this vault.
                </p>
                <p className="text-txt-muted text-xs mb-6">
                  Expires {new Date(info.expires_at).toLocaleDateString(undefined, { month: 'long', day: 'numeric', year: 'numeric' })}
                </p>

                {accepted ? (
                  <div className="flex items-center gap-2 text-green-400 text-sm font-medium">
                    <Check size={18} />
                    Joined! Redirecting to your vaults…
                  </div>
                ) : user ? (
                  <Button
                    className="w-full"
                    onClick={handleAccept}
                    disabled={accepting}
                  >
                    {accepting ? 'Joining…' : 'Accept Invitation'}
                  </Button>
                ) : (
                  <div className="space-y-3">
                    <Button className="w-full" onClick={() => goToLogin('register')}>
                      <UserPlus size={16} className="mr-2" />
                      Create account to join
                    </Button>
                    <Button variant="secondary" className="w-full" onClick={() => goToLogin('login')}>
                      <LogIn size={16} className="mr-2" />
                      Already have an account? Log in
                    </Button>
                  </div>
                )}
              </>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
