import clsx from 'clsx';

const Avatar = ({ name, size = 36 }) => {
  const bgColors = [
    'bg-accent',
    'bg-green',
    'bg-danger',
    'bg-warning',
    'bg-accent-hover',
    'bg-green-hover',
    'bg-danger-hover',
    'bg-txt-muted',
  ];

  // Simple hash function to pick consistent color from name
  const hashCode = (str) => {
    let hash = 0;
    for (let i = 0; i < str.length; i++) {
      const char = str.charCodeAt(i);
      hash = (hash << 5) - hash + char;
      hash = hash & hash; // Convert to 32bit integer
    }
    return Math.abs(hash);
  };

  const colorIndex = hashCode(name) % bgColors.length;
  const bgColor = bgColors[colorIndex];

  // Get initials (first 1-2 letters)
  const initials = name
    .trim()
    .split(/\s+/)
    .slice(0, 2)
    .map((word) => word[0])
    .join('')
    .toUpperCase()
    .slice(0, 2);

  return (
    <div
      className={clsx(
        'rounded-full flex items-center justify-center',
        'text-white font-bold',
        bgColor
      )}
      style={{
        width: `${size}px`,
        height: `${size}px`,
        fontSize: `${size * 0.4}px`,
      }}
    >
      {initials}
    </div>
  );
};

export default Avatar;
