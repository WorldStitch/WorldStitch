import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import Button from '@/components/Button';
import { ai, aiSettings } from '@/api';

const AI_MODELS = [
  { value: 'gpt-4o', label: 'GPT-4o' },
  { value: 'gpt-4o-mini', label: 'GPT-4o Mini' },
  { value: 'claude-3-opus', label: 'Claude 3 Opus' },
  { value: 'claude-3-sonnet', label: 'Claude 3 Sonnet' },
  { value: 'claude-3-haiku', label: 'Claude 3 Haiku' },
];

const inputCls =
  'w-full bg-elevated rounded-xl px-4 py-3 text-txt border-2 border-transparent focus:border-accent focus:outline-none transition';

export default function AISettings({
  preferredModel, setPreferredModel,
  maxTokens, setMaxTokens,
  streamingEnabled, setStreamingEnabled,
  aiHistoryLimit, setAiHistoryLimit,
  onSave,
}) {
  const [newKey, setNewKey] = useState('');
  const [showNewKey, setShowNewKey] = useState(false);
  const queryClient = useQueryClient();

  const { data: keyStatus, isLoading: keyLoading } = useQuery({
    queryKey: ['ai-key-settings'],
    queryFn: aiSettings.get,
    retry: false,
  });

  const { data: usageData, isLoading: usageLoading } = useQuery({
    queryKey: ['ai-usage'],
    queryFn: ai.usage,
    retry: false,
  });

  const saveKeyMutation = useMutation({
    mutationFn: () => aiSettings.saveKey(newKey.trim()),
    onSuccess: () => {
      setNewKey('');
      queryClient.invalidateQueries({ queryKey: ['ai-key-settings'] });
      toast.success('Personal API key saved');
    },
    onError: (err) => toast.error(err.message || 'Failed to save key'),
  });

  const removeKeyMutation = useMutation({
    mutationFn: aiSettings.removeKey,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['ai-key-settings'] });
      toast.success('Personal key removed — using shared server key');
    },
    onError: () => toast.error('Failed to remove key'),
  });

  const handleSaveKey = () => {
    const trimmed = newKey.trim();
    if (!trimmed.startsWith('sk-')) {
      toast.error("API key must start with 'sk-'");
      return;
    }
    saveKeyMutation.mutate();
  };

  return (
    <div className="space-y-8">
      {/* ── Personal API Key ────────────────────────────────────────────── */}
      <div>
        <h3 className="text-lg font-bold text-txt mb-1">Your OpenAI API Key</h3>
        <p className="text-sm text-txt-muted mb-4">
          Your personal key takes priority over any vault or platform key — you are billed
          directly by OpenAI and have no platform request limit.
        </p>

        {keyLoading ? (
          <p className="text-sm text-txt-muted">Loading…</p>
        ) : keyStatus?.has_personal_key ? (
          /* ── Personal key active ── */
          <div className="bg-elevated rounded-xl p-4 flex items-center justify-between gap-4">
            <div>
              <p className="text-sm font-medium text-txt">Using your personal OpenAI key</p>
              <p className="text-xs text-txt-muted mt-0.5">Takes priority over vault and platform keys. No server-side request limit.</p>
            </div>
            <Button
              variant="danger"
              size="sm"
              onClick={() => removeKeyMutation.mutate()}
              disabled={removeKeyMutation.isPending}
            >
              Remove key
            </Button>
          </div>
        ) : (
          /* ── Server key + quota ── */
          <div className="space-y-3">
            <div className="bg-elevated rounded-xl p-4">
              <p className="text-sm font-medium text-txt mb-1">No personal key set</p>
              <p className="text-xs text-txt-muted mt-0.5">
                AI uses your vault owner's key (if shared) or the platform key.
                Add your own key above to override and remove request limits.
              </p>
              {keyStatus && (
                <div className="flex items-center gap-2 mt-2">
                  <div className="flex-1 bg-card rounded-full h-2 overflow-hidden">
                    <div
                      className="h-2 rounded-full bg-accent transition-all"
                      style={{
                        width: `${Math.min(
                          100,
                          keyStatus.monthly_request_limit > 0
                            ? (keyStatus.requests_this_month / keyStatus.monthly_request_limit) * 100
                            : 0
                        )}%`,
                      }}
                    />
                  </div>
                  <span className="text-xs text-txt-muted whitespace-nowrap">
                    {keyStatus.requests_this_month} / {keyStatus.monthly_request_limit} requests this month
                  </span>
                </div>
              )}
            </div>

            <div>
              <label className="block text-txt-muted text-sm mb-2 font-medium">
                Add your own OpenAI key
              </label>
              <div className="flex gap-2">
                <input
                  type={showNewKey ? 'text' : 'password'}
                  value={newKey}
                  onChange={(e) => setNewKey(e.target.value)}
                  placeholder="sk-..."
                  className="flex-1 bg-elevated rounded-xl px-4 py-3 text-txt border-2 border-transparent focus:border-accent focus:outline-none transition"
                />
                <button
                  onClick={() => setShowNewKey(!showNewKey)}
                  className="text-txt-secondary hover:text-txt transition px-2"
                >
                  {showNewKey ? '👁️' : '👁️‍🗨️'}
                </button>
                <Button
                  variant="primary"
                  onClick={handleSaveKey}
                  disabled={!newKey.trim() || saveKeyMutation.isPending}
                >
                  Save key
                </Button>
              </div>
            </div>
          </div>
        )}
      </div>

      {/* ── AI Model Settings ───────────────────────────────────────────── */}
      <div className="border-t border-txt-muted/10 pt-6">
        <h3 className="text-lg font-bold text-txt mb-4">AI Configuration</h3>
        <div className="space-y-4">

          <div>
            <label className="block text-txt-muted text-sm mb-2 font-medium">Preferred AI Model</label>
            <select
              value={preferredModel}
              onChange={(e) => setPreferredModel(e.target.value)}
              className={inputCls}
            >
              {AI_MODELS.map((m) => (
                <option key={m.value} value={m.value}>{m.label}</option>
              ))}
            </select>
          </div>

          <div>
            <label className="block text-txt-muted text-sm mb-2 font-medium">Max Tokens</label>
            <input
              type="number"
              value={maxTokens}
              onChange={(e) => setMaxTokens(e.target.value)}
              className={inputCls}
            />
          </div>

          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm font-medium text-txt">Use streaming responses</p>
              <p className="text-xs text-txt-muted mt-0.5">Stream tokens as they arrive instead of waiting for full response</p>
            </div>
            <label className="relative inline-flex items-center cursor-pointer">
              <input
                type="checkbox"
                checked={streamingEnabled}
                onChange={(e) => setStreamingEnabled(e.target.checked)}
                className="sr-only peer"
              />
              <div className="w-11 h-6 bg-elevated rounded-full peer peer-checked:bg-accent transition-colors" />
              <div className="absolute left-0.5 top-0.5 w-5 h-5 bg-white rounded-full shadow transition-transform peer-checked:translate-x-5" />
            </label>
          </div>

          <div>
            <label className="block text-txt-muted text-sm mb-2 font-medium">
              Max conversation history (messages)
            </label>
            <input
              type="number"
              min={1}
              max={20}
              value={aiHistoryLimit}
              onChange={(e) => setAiHistoryLimit(Math.min(20, Math.max(1, Number(e.target.value) || 10)))}
              className={inputCls}
            />
            <p className="text-xs text-txt-muted mt-1">How many past messages to include as context (1–20, default 10)</p>
          </div>
        </div>
      </div>

      <Button variant="primary" onClick={onSave} className="w-full">Save AI Settings</Button>

      {/* ── Usage This Month ─────────────────────────────────────────────── */}
      <div className="border-t border-txt-muted/10 pt-6">
        <h3 className="text-base font-bold text-txt mb-4">Usage this month</h3>
        {usageLoading ? (
          <p className="text-sm text-txt-muted">Loading usage…</p>
        ) : usageData ? (
          <div className="grid grid-cols-3 gap-4">
            <div className="bg-elevated rounded-xl p-4 text-center">
              <p className="text-2xl font-bold text-txt">{usageData.total_requests.toLocaleString()}</p>
              <p className="text-xs text-txt-muted mt-1">Requests</p>
            </div>
            <div className="bg-elevated rounded-xl p-4 text-center">
              <p className="text-2xl font-bold text-txt">{usageData.total_tokens.toLocaleString()}</p>
              <p className="text-xs text-txt-muted mt-1">Tokens</p>
            </div>
            <div className="bg-elevated rounded-xl p-4 text-center">
              <p className="text-2xl font-bold text-txt">${Number(usageData.estimated_cost).toFixed(4)}</p>
              <p className="text-xs text-txt-muted mt-1">Est. Cost</p>
            </div>
          </div>
        ) : (
          <p className="text-sm text-txt-muted">No usage data available.</p>
        )}
      </div>
    </div>
  );
}
