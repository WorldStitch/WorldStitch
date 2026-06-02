import { useState } from 'react';
import { toast } from 'sonner';
import SectionHeader from '@/components/SectionHeader';
import Card from '@/components/Card';
import Button from '@/components/Button';
import Input, { TextArea } from '@/components/Input';
import { ai, notes } from '@/api';

// ════════════════════════════════════════════════════════════════════════════
// Create — AI-powered world-building tools
// ════════════════════════════════════════════════════════════════════════════

const TABS = [
  { id: 'random', label: '🎲 Generator' },
  { id: 'npc', label: '👤 NPC Builder' },
  { id: 'quest', label: '⚔️ Quest Designer' },
  { id: 'map', label: '🗺️ Map Maker' },
];

export default function Create() {
  const [activeTab, setActiveTab] = useState('random');
  const [output, setOutput] = useState('');
  const [loading, setLoading] = useState(false);

  // ── Random Generator state ───────────────────────────────────────────
  const [prompt, setPrompt] = useState('');
  const [category, setCategory] = useState('character');

  // ── NPC Builder state ────────────────────────────────────────────────
  const [npcName, setNpcName] = useState('');
  const [npcRace, setNpcRace] = useState('');
  const [npcClass, setNpcClass] = useState('');
  const [npcRole, setNpcRole] = useState('ally');
  const [npcTraits, setNpcTraits] = useState('');
  const [npcBackstory, setNpcBackstory] = useState('');

  // ── Quest Designer state ─────────────────────────────────────────────
  const [questType, setQuestType] = useState('fetch');
  const [questDifficulty, setQuestDifficulty] = useState('medium');
  const [questSetting, setQuestSetting] = useState('');
  const [questHook, setQuestHook] = useState('');
  const [questTwist, setQuestTwist] = useState('');

  const handleSaveToVault = async (title, content, tags = []) => {
    if (!content) return;
    try {
      await notes.create(title, content, null, tags);
      toast.success('Saved to vault!');
    } catch (err) {
      toast.error('Failed to save: ' + err.message);
    }
  };

  // ── Random Generator ─────────────────────────────────────────────────

  const handleGenerate = async () => {
    if (!prompt.trim() || loading) return;
    setLoading(true);
    setOutput('');
    try {
      const response = await ai.ask(`Generate a ${category} for my world. Keep it vivid and detailed.\n\n${prompt}`);
      setOutput(response.response);
    } catch (err) {
      toast.error('Generation failed: ' + err.message);
      setOutput('');
    } finally {
      setLoading(false);
    }
  };

  // ── NPC Builder ──────────────────────────────────────────────────────

  const handleGenerateNPC = async () => {
    if (loading) return;
    setLoading(true);
    setOutput('');

    const parts = ['Create a detailed, memorable character with the following details:'];
    if (npcName) parts.push(`Name: ${npcName}`);
    if (npcRace) parts.push(`Race: ${npcRace}`);
    if (npcClass) parts.push(`Class/Occupation: ${npcClass}`);
    parts.push(`Role: ${npcRole}`);
    if (npcTraits) parts.push(`Personality Traits: ${npcTraits}`);
    if (npcBackstory) parts.push(`Backstory Notes: ${npcBackstory}`);
    parts.push('');
    parts.push('Include: appearance, personality, motivations, secrets, relationships, and a memorable quote.');

    try {
      const response = await ai.ask(parts.join('\n'));
      setOutput(response.response);
    } catch (err) {
      toast.error('NPC generation failed: ' + err.message);
    } finally {
      setLoading(false);
    }
  };

  // ── Quest Designer ───────────────────────────────────────────────────

  const handleGenerateQuest = async () => {
    if (loading) return;
    setLoading(true);
    setOutput('');

    const parts = [`Design a ${questDifficulty} difficulty story arc or quest of type: ${questType}`];
    if (questSetting) parts.push(`Setting: ${questSetting}`);
    if (questHook) parts.push(`Hook/Premise: ${questHook}`);
    if (questTwist) parts.push(`Twist/Complication: ${questTwist}`);
    parts.push('');
    parts.push('Include: title, hook, objectives, key locations, characters involved, obstacles or conflicts, rewards, and possible complications or twists.');

    try {
      const response = await ai.ask(parts.join('\n'));
      setOutput(response.response);
    } catch (err) {
      toast.error('Quest generation failed: ' + err.message);
    } finally {
      setLoading(false);
    }
  };

  // ════════════════════════════════════════════════════════════════════════
  // RENDER
  // ════════════════════════════════════════════════════════════════════════

  return (
    <div className="p-6 space-y-4 flex flex-col h-full">
      <SectionHeader title="✨ Create" subtitle="Build your world with AI-powered tools." />

      {/* Tab Bar */}
      <div className="flex gap-1">
        {TABS.map((tab) => (
          <button
            key={tab.id}
            onClick={() => { setActiveTab(tab.id); setOutput(''); }}
            className={`px-5 py-2.5 rounded-lg font-medium transition ${
              activeTab === tab.id ? 'bg-card text-accent' : 'text-txt-muted hover:text-txt'
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* Main content area */}
      <div className="flex gap-4 flex-1 overflow-hidden min-h-0">

        {/* ── Left: Input form ──────────────────────────────────────── */}
        <Card className="w-96 flex-shrink-0 p-5 overflow-y-auto space-y-4">

          {/* Random Generator */}
          {activeTab === 'random' && (
            <>
              <h3 className="text-sm font-bold text-txt uppercase tracking-wider">🎲 Random Generator</h3>
              <TextArea
                label="Describe what you want"
                placeholder="A wanderer with a hidden past..."
                value={prompt}
                onChange={(e) => setPrompt(e.target.value)}
              />
              <div>
                <label className="block text-txt-muted text-sm mb-1.5 font-medium">Category</label>
                <select
                  value={category}
                  onChange={(e) => setCategory(e.target.value)}
                  className="w-full bg-elevated rounded-xl px-4 py-3 text-txt border-2 border-transparent focus:border-accent focus:outline-none transition"
                >
                  <option value="character">Character</option>
                  <option value="location">Location</option>
                  <option value="item">Artifact / Item</option>
                  <option value="faction">Faction / Organization</option>
                  <option value="plot hook">Plot Hook</option>
                  <option value="event">Historical Event</option>
                  <option value="creature">Creature / Monster</option>
                  <option value="settlement">Town / Settlement</option>
                </select>
              </div>
              <Button variant="primary" onClick={handleGenerate} disabled={loading || !prompt.trim()} className="w-full">
                {loading ? 'Generating...' : 'Generate'}
              </Button>
            </>
          )}

          {/* NPC Builder */}
          {activeTab === 'npc' && (
            <>
              <h3 className="text-sm font-bold text-txt uppercase tracking-wider">👤 NPC Builder</h3>
              <Input label="Name (optional)" placeholder="Leave blank for random" value={npcName} onChange={(e) => setNpcName(e.target.value)} />
              <div className="grid grid-cols-2 gap-3">
                <Input label="Species / Type" placeholder="Human, Elf, Android..." value={npcRace} onChange={(e) => setNpcRace(e.target.value)} />
                <Input label="Class / Job" placeholder="Scholar, Guard, Merchant..." value={npcClass} onChange={(e) => setNpcClass(e.target.value)} />
              </div>
              <div>
                <label className="block text-txt-muted text-sm mb-1.5 font-medium">Role</label>
                <select value={npcRole} onChange={(e) => setNpcRole(e.target.value)} className="w-full bg-elevated rounded-xl px-4 py-3 text-txt border-2 border-transparent focus:border-accent focus:outline-none transition">
                  <option value="ally">Ally</option>
                  <option value="enemy">Enemy / Villain</option>
                  <option value="neutral">Neutral</option>
                  <option value="quest-giver">Quest Giver</option>
                  <option value="merchant">Merchant</option>
                  <option value="companion">Companion</option>
                  <option value="mysterious">Mysterious / Ambiguous</option>
                </select>
              </div>
              <Input label="Personality Traits" placeholder="Stubborn, witty, paranoid..." value={npcTraits} onChange={(e) => setNpcTraits(e.target.value)} />
              <TextArea label="Backstory Notes (optional)" placeholder="Any specific details to include..." value={npcBackstory} onChange={(e) => setNpcBackstory(e.target.value)} />
              <Button variant="primary" onClick={handleGenerateNPC} disabled={loading} className="w-full">
                {loading ? 'Building NPC...' : 'Generate NPC'}
              </Button>
            </>
          )}

          {/* Quest Designer */}
          {activeTab === 'quest' && (
            <>
              <h3 className="text-sm font-bold text-txt uppercase tracking-wider">⚔️ Quest Designer</h3>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-txt-muted text-sm mb-1.5 font-medium">Quest Type</label>
                  <select value={questType} onChange={(e) => setQuestType(e.target.value)} className="w-full bg-elevated rounded-xl px-4 py-3 text-txt border-2 border-transparent focus:border-accent focus:outline-none transition">
                    <option value="fetch">Fetch / Retrieve</option>
                    <option value="escort">Escort / Protect</option>
                    <option value="investigate">Investigate / Mystery</option>
                    <option value="exploration">Exploration</option>
                    <option value="hunt">Hunt / Track</option>
                    <option value="diplomacy">Diplomacy / Negotiation</option>
                    <option value="heist">Heist / Infiltration</option>
                    <option value="survival">Survival</option>
                    <option value="rescue">Rescue</option>
                  </select>
                </div>
                <div>
                  <label className="block text-txt-muted text-sm mb-1.5 font-medium">Difficulty</label>
                  <select value={questDifficulty} onChange={(e) => setQuestDifficulty(e.target.value)} className="w-full bg-elevated rounded-xl px-4 py-3 text-txt border-2 border-transparent focus:border-accent focus:outline-none transition">
                    <option value="easy">Low Stakes</option>
                    <option value="medium">Moderate Stakes</option>
                    <option value="hard">High Stakes</option>
                    <option value="deadly">World-Changing</option>
                  </select>
                </div>
              </div>
              <Input label="Setting" placeholder="Haunted forest, ancient ruins..." value={questSetting} onChange={(e) => setQuestSetting(e.target.value)} />
              <TextArea label="Quest Hook (optional)" placeholder="What draws the party in..." value={questHook} onChange={(e) => setQuestHook(e.target.value)} />
              <Input label="Twist / Complication (optional)" placeholder="Nothing is as it seems..." value={questTwist} onChange={(e) => setQuestTwist(e.target.value)} />
              <Button variant="primary" onClick={handleGenerateQuest} disabled={loading} className="w-full">
                {loading ? 'Designing Quest...' : 'Generate Quest'}
              </Button>
            </>
          )}

          {/* Map Maker */}
          {activeTab === 'map' && (
            <>
              <h3 className="text-sm font-bold text-txt uppercase tracking-wider">🗺️ Map Maker</h3>
              <div className="flex flex-col items-center justify-center py-10 space-y-4">
                <div className="text-5xl">🗺️</div>
                <p className="text-txt font-semibold text-center">Map Maker coming in a future update</p>
                <p className="text-txt-muted text-sm text-center">
                  For now, use the Random Generator to create rich location descriptions.
                </p>
                <Button variant="secondary" size="sm" onClick={() => { setActiveTab('random'); setCategory('location'); }}>
                  Generate a Location
                </Button>
              </div>
            </>
          )}
        </Card>

        {/* ── Right: Output ─────────────────────────────────────────── */}
        <Card className="flex-1 p-0 overflow-hidden flex flex-col">
          <div className="px-5 py-3 border-b border-txt-muted/10 flex justify-between items-center">
            <h3 className="text-sm font-bold text-txt">Output</h3>
            {output && (
              <Button
                variant="secondary"
                size="sm"
                onClick={() => {
                  const title = activeTab === 'npc'
                    ? `NPC — ${npcName || 'Generated'}`
                    : activeTab === 'quest'
                      ? `Quest — ${questType} (${questDifficulty})`
                      : `${category.charAt(0).toUpperCase() + category.slice(1)} — ${prompt.slice(0, 40)}`;
                  const tags = activeTab === 'npc' ? ['npc', 'character'] : activeTab === 'quest' ? ['quest'] : [category];
                  handleSaveToVault(title, output, tags);
                }}
              >
                Save to Vault
              </Button>
            )}
          </div>

          <div className="flex-1 overflow-y-auto p-5">
            {output ? (
              <div className="text-txt whitespace-pre-wrap text-sm leading-relaxed">{output}</div>
            ) : (
              <div className="h-full flex items-center justify-center">
                <div className="text-center space-y-2">
                  <div className="text-4xl">
                    {activeTab === 'random' ? '🎲' : activeTab === 'npc' ? '👤' : activeTab === 'quest' ? '⚔️' : '🗺️'}
                  </div>
                  <p className="text-txt-muted text-sm">
                    {loading ? 'Generating...' : 'Your generated content will appear here'}
                  </p>
                </div>
              </div>
            )}
          </div>
        </Card>
      </div>
    </div>
  );
}
