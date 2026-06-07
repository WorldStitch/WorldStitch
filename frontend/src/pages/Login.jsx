import { useState, useEffect } from 'react';
import { useSearchParams } from 'react-router-dom';
import { toast } from 'sonner';
import Card from '@/components/Card';
import Button from '@/components/Button';
import Input from '@/components/Input';
import { auth, setToken, setRefreshToken, isRateLimitError, RATE_LIMIT_MSG } from '@/api';

// Must mirror server-side validate_password_strength rules (Item 54)
const SPECIAL_CHARS = /[!@#$%^&*\-_]/;
function validatePassword(pw) {
  if (pw.length < 8) return 'At least 8 characters required';
  if (!/[A-Z]/.test(pw)) return 'At least 1 uppercase letter required';
  if (!/[0-9]/.test(pw)) return 'At least 1 number required';
  if (!SPECIAL_CHARS.test(pw)) return 'At least 1 special character required (!@#$%^&*-_)';
  return null;
}

export default function Login({ onLogin, needsSetup = false }) {
  const [params] = useSearchParams();
  const inviteToken = params.get('token') || '';
  const urlMode = params.get('mode') || '';
  const [mode, setMode] = useState(needsSetup ? 'setup' : (urlMode === 'register' ? 'register' : 'login'));
  const [loading, setLoading] = useState(false);
  const [apiError, setApiError] = useState('');
  const [firstRunNotice, setFirstRunNotice] = useState(false);

  // Login form state
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');

  // Register form state
  const [regInviteCode, setRegInviteCode] = useState('');
  const [regEmail, setRegEmail] = useState('');
  const [regDisplayName, setRegDisplayName] = useState('');
  const [regPassword, setRegPassword] = useState('');
  const [regDone, setRegDone] = useState(false);
  const [regDoneEmail, setRegDoneEmail] = useState('');

  // Setup form state
  const [setupEmail, setSetupEmail] = useState('');
  const [setupUsername, setSetupUsername] = useState('');
  const [setupPassword, setSetupPassword] = useState('');
  const [setupPwHint, setSetupPwHint] = useState(null);
  const [setupConfirm, setSetupConfirm] = useState('');
  const [setupError, setSetupError] = useState('');

  useEffect(() => {
    auth.status().then(data => {
      if (data.needs_setup) setFirstRunNotice(true);
    }).catch(() => {});
  }, []);

  const switchMode = (next) => {
    setMode(next);
    setApiError('');
    setRegDone(false);
  };
  const redirectAfterAuth = inviteToken ? `/invite?token=${encodeURIComponent(inviteToken)}` : null;

  const handleLogin = async (e) => {
    e.preventDefault();
    if (!email || !password) {
      toast.error('Please enter your email and password');
      return;
    }
    setLoading(true);
    try {
      const data = await auth.login(email, password);
      setToken(data.token);
      setRefreshToken(data.refreshToken);
      onLogin(data.token, data.user, data.exp ?? null, redirectAfterAuth);
    } catch (err) {
      if (isRateLimitError(err)) {
        toast.error(RATE_LIMIT_MSG);
      } else {
        toast.error(err.message || 'Login failed');
      }
    } finally {
      setLoading(false);
    }
  };

  const handleRegister = async (e) => {
    e.preventDefault();
    setApiError('');
    if (!regInviteCode || !regEmail || !regDisplayName || !regPassword) {
      toast.error('All fields are required');
      return;
    }
    setLoading(true);
    try {
      const data = await auth.register(regEmail, regDisplayName, regPassword, regInviteCode);
      setRegDoneEmail(data.email);
      setRegDone(true);
    } catch (err) {
      toast.error(err.message || 'Registration failed');
    } finally {
      setLoading(false);
    }
  };

  const handleSetup = async (e) => {
    e.preventDefault();
    setSetupError('');
    if (setupPassword !== setupConfirm) {
      setSetupError('Passwords do not match');
      return;
    }
    const hint = validatePassword(setupPassword);
    if (hint) { setSetupError(hint); return; }
    setLoading(true);
    try {
      const data = await auth.setup(setupEmail, setupUsername, setupPassword);
      setToken(data.token);
      setRefreshToken(data.refreshToken);
      onLogin(data.token, data.user, data.exp ?? null);
    } catch (err) {
      setSetupError(err.message || 'Setup failed');
    } finally {
      setLoading(false);
    }
  };

  const ApiErrorBox = ({ msg }) =>
    msg ? (
      <div className="mb-4 p-3 rounded-lg bg-danger/10 border border-danger/20">
        <p className="text-danger text-sm">{msg}</p>
      </div>
    ) : null;

  return (
    <div className="h-screen w-screen bg-base flex items-center justify-center p-4">
      <Card className="w-full max-w-md p-10">
        {/* Logo */}
        <div className="text-center mb-8">
          <div className="text-4xl mb-4">⚡</div>
          <h1 className="text-2xl font-bold text-txt mb-2">WorldStitch</h1>
        </div>

        {/* ── Setup Mode ── */}
        {mode === 'setup' && (
          <>
            <h2 className="text-xl font-bold text-txt mb-2">Welcome to WorldStitch</h2>
            <p className="text-txt-secondary text-sm mb-6">Create your admin account to get started.</p>
            <ApiErrorBox msg={setupError} />
            <form onSubmit={handleSetup} className="space-y-4">
              <Input
                label="Email"
                type="email"
                placeholder="admin@example.com"
                value={setupEmail}
                onChange={(e) => setSetupEmail(e.target.value)}
                required
              />
              <Input
                label="Username"
                type="text"
                placeholder="Your name"
                value={setupUsername}
                onChange={(e) => setSetupUsername(e.target.value)}
                required
              />
              <div>
                <Input
                  label="Password"
                  type="password"
                  placeholder="Min 8 chars, uppercase, number, special"
                  value={setupPassword}
                  onChange={(e) => {
                    setSetupPassword(e.target.value);
                    setSetupPwHint(e.target.value ? validatePassword(e.target.value) : null);
                  }}
                  required
                />
                {setupPwHint && (
                  <p className="text-danger text-xs mt-1">{setupPwHint}</p>
                )}
              </div>
              <Input
                label="Confirm Password"
                type="password"
                placeholder="Repeat password"
                value={setupConfirm}
                onChange={(e) => setSetupConfirm(e.target.value)}
                required
              />
              <Button type="submit" variant="primary" className="w-full" disabled={loading}>
                {loading ? 'Creating account...' : 'Create Admin Account'}
              </Button>
            </form>
          </>
        )}

        {/* ── Login Mode ── */}
        {mode === 'login' && (
          <>
            <h2 className="text-xl font-bold text-txt mb-2">Welcome back</h2>
            <p className="text-txt-secondary text-sm mb-6">Sign in to your account to continue</p>
            {inviteToken && (
              <div className="mb-4 p-3 rounded-lg bg-accent/10 border border-accent/20">
                <p className="text-sm text-accent">Sign in to accept your vault invitation.</p>
              </div>
            )}
            {firstRunNotice && (
              <div className="mb-4 p-3 rounded-lg bg-accent/10 border border-accent/20">
                <p className="text-sm text-accent">
                  First run detected.{' '}
                  <button
                    type="button"
                    onClick={() => switchMode('setup')}
                    className="font-medium underline hover:no-underline"
                  >
                    Click here to set up your admin account.
                  </button>
                </p>
              </div>
            )}
            <form onSubmit={handleLogin} className="space-y-4">
              <Input
                label="Email"
                type="email"
                placeholder="you@example.com"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
              />
              <Input
                label="Password"
                type="password"
                placeholder="••••••••"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
              />
              <Button type="submit" variant="primary" className="w-full" disabled={loading}>
                {loading ? 'Signing in...' : 'Sign In'}
              </Button>
            </form>
            <div className="mt-4 text-center">
              <a
                href="/forgot-password"
                className="text-txt-muted text-sm hover:text-accent transition"
              >
                Forgot your password?
              </a>
            </div>
            <div className="mt-4 text-center">
              <p className="text-txt-muted text-sm">
                Have an invite code?{' '}
                <button onClick={() => switchMode('register')} className="text-accent hover:text-accent/80 font-medium transition">
                  Register
                </button>
              </p>
            </div>
          </>
        )}

        {/* ── Register Mode ── */}
        {mode === 'register' && !regDone && (
          <>
            <h2 className="text-xl font-bold text-txt mb-2">Create account</h2>
            <p className="text-txt-secondary text-sm mb-6">Join the worlds of WorldStitch</p>
            {inviteToken && (
              <div className="mb-4 p-3 rounded-lg bg-accent/10 border border-accent/20">
                <p className="text-sm text-accent">Create an account to accept your vault invitation.</p>
              </div>
            )}
            <form onSubmit={handleRegister} className="space-y-4">
              <Input
                label="Invite Code"
                type="text"
                placeholder="XXXX-XXXX-XXXX"
                value={regInviteCode}
                onChange={(e) => setRegInviteCode(e.target.value)}
              />
              <Input
                label="Email"
                type="email"
                placeholder="you@example.com"
                value={regEmail}
                onChange={(e) => setRegEmail(e.target.value)}
              />
              <Input
                label="Display Name"
                type="text"
                placeholder="your_username"
                value={regDisplayName}
                onChange={(e) => setRegDisplayName(e.target.value)}
              />
              <Input
                label="Password"
                type="password"
                placeholder="••••••••"
                value={regPassword}
                onChange={(e) => setRegPassword(e.target.value)}
              />
              <Button type="submit" variant="primary" className="w-full" disabled={loading}>
                {loading ? 'Creating account...' : 'Register'}
              </Button>
            </form>
            <div className="mt-6 text-center">
              <p className="text-txt-muted text-sm">
                Already have an account?{' '}
                <button onClick={() => switchMode('login')} className="text-accent hover:text-accent/80 font-medium transition">
                  Sign In
                </button>
              </p>
            </div>
          </>
        )}

        {/* ── Register success — check email ── */}
        {mode === 'register' && regDone && (
          <div className="text-center">
            <div className="text-5xl mb-4">📬</div>
            <h2 className="text-xl font-bold text-txt mb-3">Check your email</h2>
            <p className="text-txt-secondary text-sm mb-6">
              We sent a verification link to{' '}
              <span className="text-accent font-medium">{regDoneEmail}</span>.
              Click it to activate your account, then sign in.
            </p>
            <Button
              variant="primary"
              className="w-full"
              onClick={() => switchMode('login')}
            >
              Go to Sign In
            </Button>
          </div>
        )}
      </Card>
    </div>
  );
}
