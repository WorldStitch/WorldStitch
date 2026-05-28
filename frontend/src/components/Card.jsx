import clsx from 'clsx';

const Card = ({ children, className, accent }) => {
  return (
    <div
      className={clsx(
        'bg-card rounded-xl shadow-card',
        accent && `border-t-4`,
        className
      )}
      style={accent ? { borderTopColor: accent } : {}}
    >
      {children}
    </div>
  );
};

export default Card;
