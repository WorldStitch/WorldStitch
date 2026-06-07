import { useState } from 'react';
import Card from '@/components/Card';
import Button from '@/components/Button';
import Input from '@/components/Input';
import { auth } from '@/api';

export default function ForgotPassword() {
  const [email, setEmail] = useState('');
  const [loading, setLoading] = useState(false);
  const [submitted, setSubmitted] = useState(false);
  const [error, setError] = useState('');

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    if (!email) {
      setError('Please enter your email address.');
      return;
    }
    setLoading(true);
    try {
      await auth.forgotPassword(email);
      setSubmitted(true);
    } catch (err) {
      setError(err.message || 'Something went wrong. Please try again.');
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

        {!submitted ? (
          <>
            <h2 className="text-xl font-bold text-txt mb-2">Forgot your password?</h2>
            <p className="text-txt-secondary text-sm mb-6">
              Enter the email address on your account and we'll send you a link to reset your password.
            </p>

            {error && (
              <div className="mb-4 p-3 rounded-lg bg-danger/10 border border-danger/20">
                <p className="text-danger text-sm">{error}</p>
              </div>
            )}

            <form onSubmit={handleSubmit} className="space-y-4">
              <Input
                label="Email"
                type="email"
                placeholder="you@example.com"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
              />
              <Button type="submit" variant="primary" className="w-full" disabled={loading}>
                {loading ? 'Sending...' : 'Send Reset Link'}
              </Button>
            </form>

            <div className="mt-6 text-center">
              <a href="/" className="text-txt-muted text-sm hover:text-accent transition">
                Back to Sign In
              </a>
            </div>
          </>
        ) : (
          <div className="text-center">
            <div className="text-5xl mb-4">📬</div>
            <h2 className="text-xl font-bold text-txt mb-3">Check your email</h2>
            <p className="text-txt-secondary text-sm mb-6">
              If <span className="text-accent font-medium">{email}</span> is registered,
              you'll receive a password reset link shortly. It expires in 1 hour.
            </p>
            <a href="/" className="text-accent text-sm hover:text-accent/80 transition font-medium">
              Back to Sign In
            </a>
          </div>
        )}
      </Card>
    </div>
  );
}
