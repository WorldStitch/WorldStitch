const SectionHeader = ({ title, subtitle }) => {
  return (
    <div className="mb-2">
      <h1 className="text-2xl font-bold text-txt">{title}</h1>
      {subtitle && (
        <p className="text-sm text-txt-secondary mt-1">{subtitle}</p>
      )}
    </div>
  );
};

export default SectionHeader;
