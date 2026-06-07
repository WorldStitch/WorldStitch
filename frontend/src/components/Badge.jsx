import clsx from 'clsx';

const Badge = ({ label, variant = 'active' }) => {
  const variantStyles = {
    active: {
      bg: 'bg-green/20',
      text: 'text-green',
    },
    disabled: {
      bg: 'bg-txt-muted/20',
      text: 'text-txt-muted',
    },
    admin: {
      bg: 'bg-accent-soft',
      text: 'text-accent',
    },
    gm: {
      bg: 'bg-warning/20',
      text: 'text-warning',
    },
    player: {
      bg: 'bg-accent/15',
      text: 'text-accent',
    },
    expired: {
      bg: 'bg-danger/20',
      text: 'text-danger',
    },
  };

  const style = variantStyles[variant] || variantStyles.active;

  return (
    <span
      className={clsx(
        'rounded-full px-3 py-1 text-xs font-semibold',
        style.bg,
        style.text
      )}
    >
      {label}
    </span>
  );
};

export default Badge;
