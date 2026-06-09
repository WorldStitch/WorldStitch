import { createContext, useCallback, useContext, useMemo, useState } from 'react';

const AIContext = createContext(null);

/**
 * Tracks which vault entity the user is currently viewing so that Chat
 * can include it in every AI request as the current_entity context packet.
 *
 * entity shape: { type: "note"|"character"|"map", id: string, content: string }
 */
export function AIContextProvider({ children }) {
  const [currentEntity, setCurrentEntityState] = useState(null);

  const setCurrentEntity = useCallback((entity) => {
    setCurrentEntityState(entity);
  }, []);

  const clearCurrentEntity = useCallback(() => {
    setCurrentEntityState(null);
  }, []);

  const value = useMemo(
    () => ({ currentEntity, setCurrentEntity, clearCurrentEntity }),
    [currentEntity, setCurrentEntity, clearCurrentEntity],
  );

  return <AIContext.Provider value={value}>{children}</AIContext.Provider>;
}

export function useAIContext() {
  const ctx = useContext(AIContext);
  if (!ctx) throw new Error('useAIContext must be used within AIContextProvider');
  return ctx;
}
