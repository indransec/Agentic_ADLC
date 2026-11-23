// The platform's own words and colours for known states, outcomes, statuses and risk tiers
// (ported from adlc.ui.render.STATUS). Nothing terminal- or use-case-specific.

export type Colour = "blue" | "green" | "orange" | "red" | "violet" | "gray";

export const COLOURS: Record<Colour, string> = {
  blue: "#2F5DAA",
  green: "#2E7D4F",
  orange: "#B8621B",
  red: "#B83B3B",
  violet: "#6E4BB8",
  gray: "#6B7588",
};

/** Chart fills (lighter grey than the badge text grey, as in the Streamlit charts). */
export const CHART_COLOURS: Record<Colour, string> = { ...COLOURS, gray: "#9AA3B2" };

export const STATUS: Readonly<Record<string, readonly [string, Colour]>> = {
  // run states
  opened: ["Opened", "blue"],
  blocked: ["Blocked", "red"],
  building: ["Building", "blue"],
  awaiting_clarification: ["Awaiting clarification", "orange"],
  checking: ["Checking", "blue"],
  reviewing: ["Reviewing", "blue"],
  awaiting_sign_off: ["Awaiting sign-off", "orange"],
  escalated: ["Escalated", "red"],
  closed: ["Closed", "gray"],
  // outcomes
  pass: ["Passed", "green"],
  rework: ["Rework", "orange"],
  exception: ["Exception", "violet"],
  terminate: ["Terminated", "red"],
  // use case status
  active: ["Active", "blue"],
  terminated: ["Terminated", "red"],
  // risk tiers
  low: ["Low risk", "green"],
  medium: ["Medium risk", "orange"],
  high: ["High risk", "red"],
};

export function knownStatus(value: unknown): readonly [string, Colour] | undefined {
  return typeof value === "string" && Object.hasOwn(STATUS, value) ? STATUS[value] : undefined;
}

export function statusColour(value: unknown): string {
  return CHART_COLOURS[knownStatus(value)?.[1] ?? "gray"];
}
