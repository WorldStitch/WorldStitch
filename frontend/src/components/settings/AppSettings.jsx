import Button from '@/components/Button';
import { THEMES, applyTheme } from '@/theme';

export default function AppSettings({ theme, setTheme, fontSize, setFontSize, autosave, setAutosave, onSave }) {
  return (
    <div className="space-y-6">
      <div>
        <h3 className="text-lg font-bold text-txt mb-4">Appearance</h3>
        <div className="space-y-4">
          <div>
            <label className="block text-txt-muted text-sm mb-2 font-medium">Theme</label>
            <div className="grid grid-cols-1 gap-2">
              {THEMES.map((t) => (
                <button
                  key={t.id}
                  onClick={() => { setTheme(t.id); applyTheme(t.id); }}
                  className={`flex items-center gap-3 px-4 py-3 rounded-xl border-2 transition text-left ${
                    theme === t.id ? 'border-accent bg-accent/5' : 'border-transparent bg-elevated hover:bg-hover'
                  }`}
                >
                  <div className="flex gap-1 flex-shrink-0">
                    <span className="w-5 h-5 rounded-full border border-txt-muted/20" style={{ background: t.preview.bg }} />
                    <span className="w-5 h-5 rounded-full border border-txt-muted/20" style={{ background: t.preview.card }} />
                    <span className="w-5 h-5 rounded-full border border-txt-muted/20" style={{ background: t.preview.accent }} />
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className="text-txt text-sm font-semibold">{t.label}</p>
                    <p className="text-txt-muted text-xs truncate">{t.description}</p>
                  </div>
                  {theme === t.id && <span className="text-accent text-sm flex-shrink-0">&#10003;</span>}
                </button>
              ))}
            </div>
          </div>

          <div>
            <label className="block text-txt-muted text-sm mb-2 font-medium">Font Size</label>
            <select
              value={fontSize}
              onChange={(e) => setFontSize(e.target.value)}
              className="w-full bg-elevated rounded-xl px-4 py-3 text-txt border-2 border-transparent focus:border-accent focus:outline-none transition"
            >
              <option value="small">Small</option>
              <option value="medium">Medium</option>
              <option value="large">Large</option>
            </select>
          </div>
        </div>
      </div>

      <div className="border-t border-txt-muted/20 pt-6">
        <h3 className="text-lg font-bold text-txt mb-4">Behavior</h3>
        <label className="flex items-center gap-3 cursor-pointer">
          <input
            type="checkbox"
            checked={autosave}
            onChange={(e) => setAutosave(e.target.checked)}
            className="w-4 h-4 rounded bg-elevated border-2 border-txt-muted accent-accent"
          />
          <span className="text-txt">Enable autosave</span>
        </label>
      </div>

      <Button variant="primary" onClick={onSave} className="w-full">Save Settings</Button>
    </div>
  );
}
