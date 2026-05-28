import { useNavigate } from 'react-router-dom';
import Button from '@/components/Button';

export default function NotFound() {
  const navigate = useNavigate();

  return (
    <div className="h-full flex items-center justify-center p-10">
      <div className="text-center max-w-md space-y-4">
        <div className="text-6xl">🧭</div>
        <h2 className="text-2xl font-bold text-txt">Page Not Found</h2>
        <p className="text-txt-secondary text-sm">
          This realm doesn't exist — perhaps the map was drawn wrong.
        </p>
        <Button variant="primary" onClick={() => navigate('/')}>
          Return to Dashboard
        </Button>
      </div>
    </div>
  );
}
