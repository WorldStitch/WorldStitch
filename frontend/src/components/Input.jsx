import clsx from 'clsx';

const Input = ({ label, ...rest }) => {
  return (
    <div>
      {label && (
        <label className="block text-txt-muted text-sm mb-1.5 font-medium">
          {label}
        </label>
      )}
      <input
        className={clsx(
          'w-full bg-elevated rounded-xl px-4 py-3',
          'text-txt border-2 border-transparent',
          'focus:border-accent focus:outline-none transition'
        )}
        {...rest}
      />
    </div>
  );
};

export const TextArea = ({ label, ...rest }) => {
  return (
    <div>
      {label && (
        <label className="block text-txt-muted text-sm mb-1.5 font-medium">
          {label}
        </label>
      )}
      <textarea
        className={clsx(
          'w-full bg-elevated rounded-xl px-4 py-3',
          'text-txt border-2 border-transparent',
          'focus:border-accent focus:outline-none transition',
          'min-h-[100px] resize-vertical'
        )}
        {...rest}
      />
    </div>
  );
};

export default Input;
