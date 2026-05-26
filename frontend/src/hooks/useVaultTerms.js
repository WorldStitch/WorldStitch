import { useVault } from '@/context/VaultContext';
import { VAULT_TERMINOLOGY, DEFAULT_TERMINOLOGY } from '@/terminology';

export function useVaultTerms() {
  const { activeVaultId, vaults } = useVault();
  const activeVault = vaults?.find((v) => v.id === activeVaultId);
  const type = activeVault?.vault_type || 'worldbuilding';
  return VAULT_TERMINOLOGY[type] || DEFAULT_TERMINOLOGY;
}
