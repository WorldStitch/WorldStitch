import { createContext, useContext } from 'react';

const VaultContext = createContext(null);

export function VaultProvider({ value, children }) {
  return <VaultContext.Provider value={value}>{children}</VaultContext.Provider>;
}

export function useVault() {
  const ctx = useContext(VaultContext);
  if (!ctx) throw new Error('useVault must be used within VaultProvider');
  return ctx;
}
