import { useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import Card from '@/components/Card';
import Button from '@/components/Button';
import Input from '@/components/Input';
import { auth } from '@/api';

// Must mirror server-side validate_password_strength rules (Item 54)
const SPECIAL_CHARS = /[!@#$%^&*\-_]/;
function validatePassword(pw) {
  if (pw.length < 8) return 'At least 8 characters required';
  if (!/[A-Z]/.test(pw)) return 'At least 1 uppercase letter required';
  if (!/[0-9]/.test(pw)) return 'At least 1 number required';
  if (!SPECIAL_CHARS.test(pw)) return 'At least 1 special character required (!@#$%^&*-_)';
  return null;
}

export default function ResetPassword() {
  const [searchParams] = useSearchParams();
  const token = searchParams.get('token');

  const [newPassword, setNewPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [pwHint, setPwHint] = useState(null);
  const [loading, setLoading] = useState(false);
  const [done, setDone] = useState(false);
  const [error, setError] = useState('');

  if (!token) {
    return (
      <div className="h-screen w-screen bg-base flex items-center justify-center p-4">
        <Card className="w-full max-w-md p-10 text-center">
          <div className="text-4xl mb-4">⚡</div>
          <h1 className="text-2xl font-bold text-txt mb-8">WorldStitch</h1>
          <div className="text-5xl mb-4">⚠️</div>
          <h2 className="text-xl font-bold text-txt mb-3">Invalid link</h2>
          <p className="text-txt-secondary text-sm mb-6">
            This reset link is missing a token. Please use the link from your email.
          </p>
          <a href="/" className="text-accent text-sm hover:text-accent/80 font-medium transition">
            Back to Sign In
          </a>
        </Card>
      </div>
    );
  }

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');

    const hint = validatePassword(newPassword);
    if (hint) { setError(hint); return; }
    if (newPassword !== confirm) { setError('Passwords do not match'); return; }

    setLoading(true);
    try {
      await auth.resetPassword(token, newPassword);
      setDone(true);
    } catch (err) {
      setError(err.message || 'Reset failed. The link may be expired or already used.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="h-screen w-screen bg-base flex items-center justify-center p-4">
      <Card className="w-full max-w-md p-10">
        <div className="text-center mb-8">
          <div className="text-4xl mb-4">⚡</div>
          <h1 className="text-2xl font-bold text-txt mb-2">WorldStitch</h1>
        </div>

        {!done ? (
          <>
            <h2 className="text-xl font-bold text-txt mb-2">Set a new password</h2>
            <p className="text-txt-secondary text-sm mb-6">
              Your quest to reclaim your account is almost complete. Choose a strong new password.
            </p>

            {error && (
              <div className="mb-4 p-3 rounded-lg bg-danger/10 border border-danger/20">
                <p className="text-danger text-sm">{error}</p>
              </div>
            )}

            <form onSubmit={handleSubmit} className="space-y-4">
              <div>
                <Input
                  label="New Password"
                  type="password"
                  placeholder="Min 8 chars, uppercase, number, special"
                  value={newPassword}
                  onChange={(e) => {
                    setNewPassword(e.target.value);
                    setPwHint(e.target.value ? validatePassword(e.target.value) : null);
                  }}
                  required
                />
                {pwHint && (
                  <p className="text-danger text-xs mt-1">{pwHint}</p>
                )}
              </div>
              <Input
                label="Confirm Password"
                type="password"
                placeholder="Repeat your new password"
                value={confirm}
                onChange={(e) => setConfirm(e.target.value)}
                required
              />
              <Button type="submit" variant="primary" className="w-full" disabled={loading}>
                {loading ? 'Resetting...' : 'Reset Password'}
              </Button>
            </form>
          </>
        ) : (
          <div className="text-center">
            <div className="text-5xl mb-4">✅</div>
            <h2 className="text-xl font-bold text-txt mb-3">Password reset!</h2>
            <p className="text-txt-secondary text-sm mb-6">
              Your password has been updated. Sign in with your new password to continue your adventure.
            </p>
            <Button variant="primary" className="w-full" onClick={() => { window.location.href = '/'; }}>
              Sign In
            </Button>
          </div>
        )}
      </Card>
    </div>
  );
}
