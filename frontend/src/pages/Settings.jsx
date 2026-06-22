import { useState, useEffect } from 'react';
import { useQuery } from '@tanstack/react-query';
import { toast } from 'sonner';
import SectionHeader from '@/components/SectionHeader';
import Card from '@/components/Card';
import AppSettings from '@/components/settings/AppSettings';
import AccountSettings from '@/components/settings/AccountSettings';
import AISettings from '@/components/settings/AISettings';
import CampaignSettings from '@/components/settings/CampaignSettings';
import HelpSettings from '@/components/settings/HelpSettings';
import PrivacySettings from '@/components/settings/PrivacySettings';
import { settings } from '@/api';
import { getStoredTheme } from '@/theme';

export default function Settings({ user }) {
  const [activeTab, setActiveTab] = useState('app');

  // App Settings
  const [theme, setTheme] = useState(getStoredTheme());
  const [fontSize, setFontSize] = useState('medium');
  const [autosave, setAutosave] = useState(true);

  // AI Settings
  const [preferredModel, setPreferredModel] = useState('gpt-4o');
  const [maxTokens, setMaxTokens] = useState('2048');
  const [streamingEnabled, setStreamingEnabled] = useState(true);
  const [aiHistoryLimit, setAiHistoryLimit] = useState(10);

  // Admin tools live in /admin — Settings is personal only

  // Load settings via React Query
  const { data: settingsData } = useQuery({
    queryKey: ['settings'],
    queryFn: settings.get,
  });

  useEffect(() => {
    if (!settingsData) return;
    if (settingsData.font_size) setFontSize(settingsData.font_size.toLowerCase());
    if (settingsData.autosave !== undefined) setAutosave(settingsData.autosave);
    if (settingsData.preferred_model) setPreferredModel(settingsData.preferred_model);
    if (settingsData.completion_model && !settingsData.preferred_model) {
      setPreferredModel(settingsData.completion_model);
    }
    if (settingsData.max_tokens) setMaxTokens(String(settingsData.max_tokens));
    if (settingsData.streaming_enabled !== undefined) setStreamingEnabled(Boolean(settingsData.streaming_enabled));
    if (settingsData.ai_history_limit !== undefined) setAiHistoryLimit(Number(settingsData.ai_history_limit));
  }, [settingsData]);

  const handleSaveAppSettings = async () => {
    try {
      await settings.update({ theme, font_size: fontSize, autosave });
      toast.success('Settings saved');
    } catch {
      toast.error('Failed to save settings');
    }
  };

  const handleSaveAI = async () => {
    try {
      await settings.update({
        preferred_model: preferredModel,
        completion_model: preferredModel,
        max_tokens: parseInt(maxTokens, 10) || 2048,
        streaming_enabled: streamingEnabled,
        ai_history_limit: Number(aiHistoryLimit),
      });
      toast.success('AI settings saved');
    } catch {
      toast.error('Failed to save AI settings');
    }
  };

  const NavItem = ({ id, label }) => (
    <button
      onClick={() => setActiveTab(id)}
      className={`w-full text-left px-4 py-2.5 rounded-lg transition font-medium ${
        activeTab === id ? 'bg-accent/10 text-accent' : 'text-txt hover:bg-hover'
      }`}
    >
      {label}
    </button>
  );

  return (
    <div className="p-10 space-y-6 h-full">
      <SectionHeader title="⚙️ Settings" subtitle="Configure your WorldStitch experience." />

      <div className="flex gap-6 flex-1 overflow-hidden">
        {/* Left Sidebar */}
        <div className="w-48">
          <nav className="space-y-2">
            <NavItem id="app" label="App Settings" />
            <NavItem id="account" label="My Account" />
            <NavItem id="ai" label="AI Settings" />
            <NavItem id="campaign" label="Campaign" />
            <NavItem id="privacy" label="Privacy" />
            <NavItem id="help" label="Help & About" />
          </nav>
        </div>

        {/* Right Content */}
        <Card className="flex-1 p-6 overflow-y-auto">
          {activeTab === 'app' && (
            <AppSettings
              theme={theme} setTheme={setTheme}
              fontSize={fontSize} setFontSize={setFontSize}
              autosave={autosave} setAutosave={setAutosave}
              onSave={handleSaveAppSettings}
            />
          )}
          {activeTab === 'account' && <AccountSettings user={user} />}
          {activeTab === 'ai' && (
            <AISettings
              preferredModel={preferredModel} setPreferredModel={setPreferredModel}
              maxTokens={maxTokens} setMaxTokens={setMaxTokens}
              streamingEnabled={streamingEnabled} setStreamingEnabled={setStreamingEnabled}
              aiHistoryLimit={aiHistoryLimit} setAiHistoryLimit={setAiHistoryLimit}
              onSave={handleSaveAI}
            />
          )}
          {activeTab === 'campaign' && <CampaignSettings user={user} />}
          {activeTab === 'privacy' && <PrivacySettings />}
          {activeTab === 'help' && <HelpSettings />}
        </Card>
      </div>
    </div>
  );
}
