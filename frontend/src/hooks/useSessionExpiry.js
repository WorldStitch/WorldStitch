import { useEffect, useRef } from 'react';

const WARNING_THRESHOLD_SECONDS = 5 * 60; // 5 minutes
const CHECK_INTERVAL_MS = 30_000; // 30 seconds

/**
 * Monitors session expiry from a Unix timestamp.
 * Calls onWarning(minutesRemaining) when < 5 min remain.
 * Calls onExpired() when the session has expired.
 * Pass exp=null to disable (e.g. no active session).
 */
export function useSessionExpiry(exp, onWarning, onExpired) {
  const warned = useRef(false);

  useEffect(() => {
    if (!exp) return;

    warned.current = false;

    function check() {
      const now = Math.floor(Date.now() / 1000);
      const remaining = exp - now;

      if (remaining <= 0) {
        onExpired();
        return;
      }

      if (remaining <= WARNING_THRESHOLD_SECONDS) {
        const mins = Math.ceil(remaining / 60);
        onWarning(mins);
        warned.current = true;
      } else if (warned.current) {
        // Warning was previously shown but session was refreshed — clear it
        warned.current = false;
      }
    }

    // Run immediately, then on interval
    check();
    const id = setInterval(check, CHECK_INTERVAL_MS);
    return () => clearInterval(id);
  }, [exp]);
}
