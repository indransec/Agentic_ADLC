// A badge for a known platform value (its word and colour, FR-011); any other value is plain text.
// The word is always shown, so status is never told by colour alone (FR-028).
import { Literal } from "./literal";
import { COLOURS, knownStatus } from "./status";

export function StatusBadge({ value }: { value: unknown }) {
  const known = knownStatus(value);
  if (known === undefined) {
    return <Literal value={value} />;
  }
  const [word, colour] = known;
  return (
    <span className="badge" style={{ color: COLOURS[colour], borderColor: COLOURS[colour] }}>
      {word}
    </span>
  );
}
