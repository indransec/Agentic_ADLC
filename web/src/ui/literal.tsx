// Text written by agents or people (FR-010): always a plain text node, never markup, wrapped so a
// long line cannot break the layout. Empty values read as a dash.
import type { CSSProperties } from "react";

export const MISSING = "—";

const STYLE: CSSProperties = { whiteSpace: "pre-wrap", overflowWrap: "anywhere" };

export interface LiteralProps {
  value: unknown;
  as?: "span" | "p" | "div";
  className?: string;
}

export function literalText(value: unknown): string {
  if (value === null || value === undefined || value === "") return MISSING;
  if (typeof value === "string") return value;
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  return JSON.stringify(value);
}

export function Literal({ value, as = "span", className }: LiteralProps) {
  const Tag = as;
  return (
    <Tag className={className} style={STYLE}>
      {literalText(value)}
    </Tag>
  );
}
