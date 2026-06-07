import { useState, useEffect } from 'react';
import { useSearchParams } from 'react-router-dom';
import Card from '@/components/Card';
import Button from '@/components/Button';
import { auth } from '@/api';

export default function VerifyEmail() {
  const [searchParams] = useSearchParams();
  const token = searchParams.get('token');

  const [state, setState] = useState('loading'); // 'loading' | 'success' | 'error'
  const [message, setMessage] = useState('');

  useEffect(() => {
    if (!token) {
      setState('error');
      setMessage('No verification token found in the link. Please use the link from your email.');
      return;
    }

    auth.verifyEmail(token)
      .then((data) => {
        setState('success');
        setMessage(data.message || 'Email verified successfully.');
      })
      .catch((err) => {
        setState('error');
        setMessage(err.message || 'Verification failed. The link may be expired or already used.');
      });
  }, [token]);

  return (
    <div className="h-screen w-screen bg-base flex items-center justify-center p-4">
      <Card className="w-full max-w-md p-10 text-center">
        <div className="text-4xl mb-4">⚡</div>
        <h1 className="text-2xl font-bold text-txt mb-8">WorldStitch</h1>

        {state === 'loading' && (
          <>
            <div className="text-3xl mb-4 animate-pulse">🔮</div>
            <h2 className="text-lg font-semibold text-txt mb-2">Verifying your email...</h2>
            <p className="text-txt-muted text-sm">The Arcane Council is reviewing your scroll.</p>
          </>
        )}

        {state === 'success' && (
          <>
            <div className="text-5xl mb-4">✅</div>
            <h2 className="text-xl font-bold text-txt mb-3">Email verified!</h2>
            <p className="text-txt-secondary text-sm mb-6">{message}</p>
            <Button variant="primary" className="w-full" onClick={() => { window.location.href = '/'; }}>
              Sign In
            </Button>
          </>
        )}

        {state === 'error' && (
          <>
            <div className="text-5xl mb-4">⚠️</div>
            <h2 className="text-xl font-bold text-txt mb-3">Verification failed</h2>
            <p className="text-txt-secondary text-sm mb-6">{message}</p>
            <Button variant="primary" className="w-full" onClick={() => { window.location.href = '/'; }}>
              Back to Sign In
            </Button>
          </>
        )}
      </Card>
    </div>
  );
}
