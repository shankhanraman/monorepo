export function Spinner({ label }: { label: string }) {
  return (
    <p className="spinner-row" role="status">
      <span className="spinner" aria-hidden="true" />
      {label}
    </p>
  );
}
