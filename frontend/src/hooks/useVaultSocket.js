import { useMemo } from 'react';
import { useRealtime } from '@/context/RealtimeContext';

/**
 * Thin wrapper over the shared RealtimeContext that exposes a stable
 * {onlineUsers, lockedNotes, sendMessage, isConnected} API.
 *
 * vaultId and token params are accepted for API symmetry but the underlying
 * connection is managed by RealtimeProvider at the app level.
 */
export function useVaultSocket(_vaultId, _token) {
  const { onlineUsers, editing, isConnected, sendMessage } = useRealtime();

  const lockedNotes = useMemo(() => {
    const map = {};
    for (const entry of editing) {
      map[entry.note_id] = entry.email || entry.username || entry.user_id;
    }
    return map;
  }, [editing]);

  return { onlineUsers, lockedNotes, sendMessage, isConnected };
}
