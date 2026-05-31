import { createContext, useContext, useEffect, useMemo, useRef, useState } from 'react';
import { getToken, getWsBase, auth } from '@/api';

const RealtimeContext = createContext(null);

export function RealtimeProvider({ user, activeVaultId, children }) {
  const socketRef = useRef(null);
  const [onlineUsers, setOnlineUsers] = useState([]);
  const [editing, setEditing] = useState([]);
  const [lastEvent, setLastEvent] = useState(null);
  const [isConnected, setIsConnected] = useState(false);

  useEffect(() => {
    if (!user || !activeVaultId) return undefined;

    let cancelled = false;
    let attempt = 0;
    let timeoutId = null;
    let pingId = null;
    let currentSocket = null;

    const connect = async () => {
      const token = getToken();
      if (!token || cancelled) return;

      const socket = new WebSocket(
        `${getWsBase()}/ws?token=${encodeURIComponent(token)}&vault_id=${encodeURIComponent(activeVaultId)}`
      );
      currentSocket = socket;
      socketRef.current = socket;

      socket.onopen = () => {
        attempt = 0;
        setIsConnected(true);
        // Ping every 25s so Railway's 30-minute idle-connection timeout never fires.
        pingId = setInterval(() => {
          if (socket.readyState === WebSocket.OPEN) {
            socket.send(JSON.stringify({ type: 'ping' }));
          }
        }, 25000);
      };

      socket.onmessage = (event) => {
        try {
          const payload = JSON.parse(event.data);
          setLastEvent(payload);
          if (payload.type === 'presence.snapshot') {
            setOnlineUsers(payload.users || []);
            setEditing(payload.editing || []);
          }
        } catch (error) {
          console.warn('Failed to parse realtime event', error);
        }
      };

      socket.onerror = (err) => {
        console.warn('WebSocket error', err);
      };

      socket.onclose = async (event) => {
        clearInterval(pingId);
        pingId = null;
        setIsConnected(false);
        if (socketRef.current === socket) socketRef.current = null;
        setOnlineUsers([]);
        setEditing([]);

        if (cancelled) return;

        // Code 1008 = Policy Violation — the server rejected the token.
        // This happens when the 1-hour JWT has expired. Try to get a new one
        // via the 30-day refresh token before scheduling the next reconnect.
        // Without this check the frontend loops forever: reconnect → 1008 →
        // reconnect → 1008 … because every attempt uses the same dead token.
        if (event.code === 1008) {
          try {
            await auth.refresh();
          } catch {
            // Refresh token also expired — force a full logout.
            window.dispatchEvent(new CustomEvent('auth:logout'));
            return;
          }
          if (cancelled) return; // guard: component may have unmounted during refresh
        }

        const delay = Math.min(Math.pow(2, attempt) * 1000, 30000);
        attempt += 1;
        timeoutId = setTimeout(connect, delay);
      };
    };

    connect();

    return () => {
      cancelled = true;
      clearTimeout(timeoutId);
      clearInterval(pingId);
      if (currentSocket) currentSocket.close();
      if (socketRef.current === currentSocket) socketRef.current = null;
      setOnlineUsers([]);
      setEditing([]);
      setIsConnected(false);
    };
  }, [user?.id, activeVaultId]);

  const send = (payload) => {
    const socket = socketRef.current;
    if (socket && socket.readyState === WebSocket.OPEN) {
      socket.send(JSON.stringify(payload));
    }
  };

  const value = useMemo(
    () => ({
      onlineUsers,
      editing,
      lastEvent,
      isConnected,
      startEditing: (noteId, cursor = 0) => send({ type: 'editing.start', note_id: noteId, cursor }),
      updateCursor: (noteId, cursor = 0) => send({ type: 'cursor.move', note_id: noteId, cursor }),
      stopEditing: (noteId) => send({ type: 'editing.stop', note_id: noteId }),
      sendMessage: (payload) => send(payload),
    }),
    [onlineUsers, editing, lastEvent, isConnected]
  );

  return <RealtimeContext.Provider value={value}>{children}</RealtimeContext.Provider>;
}

export function useRealtime() {
  const ctx = useContext(RealtimeContext);
  if (!ctx) throw new Error('useRealtime must be used within RealtimeProvider');
  return ctx;
}
