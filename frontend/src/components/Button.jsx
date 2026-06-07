import clsx from 'clsx';

const Button = ({
  variant = 'primary',
  size = 'md',
  children,
  className,
  disabled = false,
  ...rest
}) => {
  const baseClasses = 'rounded-xl transition-all cursor-pointer font-medium';

  const variantClasses = {
    primary: clsx(
      'bg-accent text-white hover:bg-accent-hover',
      'hover:shadow-glow',
      disabled && 'opacity-50 cursor-not-allowed hover:bg-accent hover:shadow-none'
    ),
    secondary: clsx(
      'bg-elevated text-txt-muted hover:bg-hover hover:text-txt',
      disabled && 'opacity-50 cursor-not-allowed'
    ),
    danger: clsx(
      'text-danger hover:bg-danger hover:text-white border-2 border-danger',
      'bg-transparent hover:bg-danger',
      disabled && 'opacity-50 cursor-not-allowed'
    ),
    success: clsx(
      'bg-green text-white hover:bg-green/90',
      disabled && 'opacity-50 cursor-not-allowed hover:bg-green'
    ),
    ghost: clsx(
      'text-txt hover:bg-hover',
      disabled && 'opacity-50 cursor-not-allowed'
    ),
  };

  const sizeClasses = {
    sm: 'px-3 py-1.5 text-sm',
    md: 'px-4 py-2.5 text-base',
    lg: 'px-6 py-3 text-lg',
  };

  return (
    <button
      className={clsx(
        baseClasses,
        variantClasses[variant],
        sizeClasses[size],
        className
      )}
      disabled={disabled}
      {...rest}
    >
      {children}
    </button>
  );
};

export default Button;
