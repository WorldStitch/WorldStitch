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
    let currentSocket = null;
    let pingInterval = null;

    const connect = () => {
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
        pingInterval = setInterval(() => {
          if (socket.readyState === WebSocket.OPEN) {
            socket.send(JSON.stringify({ type: 'ping' }));
          }
        }, 25000);
      };

      socket.onmessage = (event) => {
        try {
          const payload = JSON.parse(event.data);
          if (payload.type === 'pong') return;
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
        // Surface WS errors in the console so they're visible in devtools.
        console.warn('[RealtimeContext] WebSocket error', err);
      };

      socket.onclose = (event) => {
        clearInterval(pingInterval);
        setIsConnected(false);
        if (socketRef.current === socket) socketRef.current = null;
        setOnlineUsers([]);
        setEditing([]);
        if (cancelled) return;

        const scheduleReconnect = () => {
          if (cancelled) return;
          const delay = Math.min(Math.pow(2, attempt) * 1000, 30000);
          attempt += 1;
          timeoutId = setTimeout(connect, delay);
        };

        if (event.code === 1008) {
          // 1008 = Policy Violation — server rejected the token or vault.
          // Attempt a silent token refresh before reconnecting; if the token
          // is still valid the refresh is a no-op, if it's expired we get a
          // fresh one so the next connect() call succeeds.
          auth.refresh().catch(() => {}).finally(scheduleReconnect);
        } else {
          scheduleReconnect();
        }
      };
    };

    connect();

    return () => {
      cancelled = true;
      clearTimeout(timeoutId);
      clearInterval(pingInterval);
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
