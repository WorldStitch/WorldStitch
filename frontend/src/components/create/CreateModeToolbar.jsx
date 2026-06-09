import { Wand2 } from 'lucide-react';

export default function CreateModeToolbar({ aiEnabled, onToggleAI, subMode, onSubModeChange }) {
  return (
    <div className="flex items-center gap-1.5 ml-auto">
      {/* AI on/off toggle */}
      <button
        type="button"
        onMouseDown={(e) => { e.preventDefault(); onToggleAI(!aiEnabled); }}
        title={aiEnabled ? 'Disable AI co-pilot' : 'Enable AI co-pilot'}
        className={`flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-xs font-semibold transition-all ${
          aiEnabled
            ? 'bg-accent/20 text-accent border border-accent/30 shadow-sm'
            : 'text-txt-muted hover:text-txt hover:bg-hover border border-transparent'
        }`}
      >
        <Wand2 size={13} />
        AI
      </button>

      {/* Co-pilot | Chat sub-toggle — only visible when AI is on */}
      {aiEnabled && (
        <div className="flex items-center rounded-lg bg-elevated/70 border border-txt-muted/10 p-0.5">
          <button
            type="button"
            onMouseDown={(e) => { e.preventDefault(); onSubModeChange('copilot'); }}
            className={`px-2.5 py-0.5 rounded text-xs font-medium transition-all ${
              subMode === 'copilot'
                ? 'bg-accent/20 text-accent'
                : 'text-txt-muted hover:text-txt'
            }`}
          >
            Co-pilot
          </button>
          <button
            type="button"
            onMouseDown={(e) => { e.preventDefault(); onSubModeChange('chat'); }}
            className={`px-2.5 py-0.5 rounded text-xs font-medium transition-all ${
              subMode === 'chat'
                ? 'bg-accent/20 text-accent'
                : 'text-txt-muted hover:text-txt'
            }`}
          >
            Chat
          </button>
        </div>
      )}
    </div>
  );
}
