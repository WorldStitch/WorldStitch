import Button from '@/components/Button';

const GITHUB_REPO = 'https://github.com/sike-ward/WorldStitch';

export default function HelpSettings() {
  const open = (url) => window.open(url, '_blank');

  return (
    <div className="space-y-6">
      <div>
        <h3 className="text-lg font-bold text-txt mb-4">About WorldStitch</h3>
        <div className="space-y-4 text-txt-secondary">
          <p>
            WorldStitch is a world-building and creative project management tool
            designed for storytellers, creators, and writers.
          </p>
          <p>Version: 1.0.0</p>
        </div>
      </div>

      <div className="border-t border-txt-muted/20 pt-6">
        <h3 className="text-lg font-bold text-txt mb-4">Resources</h3>
        <div className="space-y-2">
          <Button variant="secondary" className="w-full justify-start" onClick={() => open(`${GITHUB_REPO}`)}>
            📁 GitHub Repository
          </Button>
          <Button variant="secondary" className="w-full justify-start" onClick={() => open(`${GITHUB_REPO}/issues/new`)}>
            🐛 Report a Bug
          </Button>
          <Button variant="secondary" className="w-full justify-start" onClick={() => open(`${GITHUB_REPO}/issues`)}>
            💬 View Known Issues
          </Button>
          <Button variant="secondary" className="w-full justify-start" onClick={() => open(`${GITHUB_REPO}/blob/main/HOW_TO_BUILD_FOR_TESTERS.md`)}>
            🔧 Build Instructions
          </Button>
        </div>
      </div>
    </div>
  );
}
