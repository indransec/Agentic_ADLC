// Hours per terminal, stacked by time-split category (T061, from adlc.ui.views.portfolio).
// Category names are the dashboard's own; one the platform adds later takes the next spare colour.
import type { Data, Layout } from "plotly.js";

import { duration, label } from "../../ui/format";
import { plotText, type Figure } from "../../ui/plot";
import { COLOURS } from "../../ui/status";
import { FONT, GRID, INK } from "../journey/build-figure";

const SPLIT_COLOURS: Record<string, string> = {
  agent: COLOURS.blue,
  reviewer: COLOURS.violet,
  clarification: "#C9A227",
  people: COLOURS.orange,
  blocked: COLOURS.red,
  other: "#9AA3B2",
};
const SPARE = ["#3F8F8A", "#8C5A3C", "#5B6B8C"];
export const SPLIT_HEIGHT = 340;

export type PerTerminal = Record<string, Record<string, number>>;

export function asPerTerminal(value: unknown): PerTerminal {
  if (typeof value !== "object" || value === null) return {};
  const out: PerTerminal = {};
  for (const [terminal, split] of Object.entries(value as Record<string, unknown>)) {
    if (typeof split !== "object" || split === null) continue;
    out[terminal] = Object.fromEntries(
      Object.entries(split as Record<string, unknown>).map(([k, v]) => [k, Number(v) || 0]),
    );
  }
  return out;
}

export function buildSplitFigure(perTerminal: PerTerminal): Figure {
  const terminals = Object.keys(perTerminal);
  const categories = [...new Set(terminals.flatMap((t) => Object.keys(perTerminal[t] ?? {})))];
  let spare = 0;
  const data: Data[] = categories.map((category) => {
    const seconds = terminals.map((t) => perTerminal[t]?.[category] ?? 0);
    const colour = SPLIT_COLOURS[category] ?? SPARE[spare++ % SPARE.length] ?? COLOURS.gray;
    return {
      type: "bar",
      x: terminals,
      y: seconds.map((s) => s / 3600),
      name: plotText(label(category)),
      marker: { color: colour, line: { width: 0 } },
      hovertext: terminals.map((t, i) =>
        plotText(`${label(category)}: ${t}, ${duration(seconds[i] ?? 0)}`),
      ),
      hoverinfo: "text",
    };
  });
  const layout: Partial<Layout> = {
    barmode: "stack",
    bargap: 0.4,
    font: { family: FONT, color: INK, size: 12 },
    yaxis: { title: { text: "hours" }, gridcolor: GRID, rangemode: "tozero", automargin: true },
    xaxis: { type: "category", automargin: true },
    legend: { orientation: "h", yanchor: "bottom", y: 1.02, x: 0 },
    height: SPLIT_HEIGHT,
    margin: { l: 8, r: 8, t: 36, b: 8 },
    paper_bgcolor: "#FFFFFF",
    plot_bgcolor: "#FFFFFF",
  };
  return { data, layout };
}
