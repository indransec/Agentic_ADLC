// A KPI or count tile: the platform's name and value; its definition on hover and to screen
// readers.
export function Metric({
  name,
  value,
  definition,
}: {
  name: string;
  value: string;
  definition?: string;
}) {
  return (
    <div className="metric card" title={definition}>
      <span className="caption">{name}</span>
      <strong>{value}</strong>
      {definition !== undefined && <span className="visually-hidden">{definition}</span>}
    </div>
  );
}
