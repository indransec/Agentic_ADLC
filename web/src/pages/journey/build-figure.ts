// The journey figure (T060, from adlc.ui.views.journey.figure): one lane per terminal in the
// answer's order, a bar per run coloured by its outcome, and arrows for reworks, reroutes,
// exceptions, events and re-entry (plain passes follow the lane order and are not drawn). No
// terminal is named here; a cause (a person's comment, a monitor's value) is escaped.
import type { Annotations, Data, Layout } from "plotly.js";

import type { components } from "../../api/schema";
import { COLOURS, knownStatus, statusColour } from "../../ui/status";
import { plotText, type Figure } from "../../ui/plot";

type Journey = components["schemas"]["Journey"];
type Bar = components["schemas"]["LaneBar"];

const ARROW_COLOURS: Record<string, string> = {
  rework: COLOURS.orange,
  reroute: COLOURS.orange,
  exception: COLOURS.violet,
};
const OUTCOME_NAMES: Record<string, string> = { open: "In progress", collapsed: "Collapsed" };
export const FONT =
  "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif";
export const GRID = "#E4E8EE";
export const INK = "#1B2430";
const MUTED = "#6B7588";

const at = (value: string | null, now: Date): Date => (value === null ? now : new Date(value));

export function outcomeOf(bar: Bar): string {
  if (bar.collapsed !== null && bar.collapsed !== undefined) return "collapsed";
  return bar.closed_at !== null ? (bar.final_status ?? "closed") : "open";
}

export const outcomeName = (outcome: string): string =>
  OUTCOME_NAMES[outcome] ?? knownStatus(outcome)?.[0] ?? outcome;

const outcomeColour = (outcome: string): string =>
  outcome === "open" ? COLOURS.blue : statusColour(outcome);

export function buildJourneyFigure(journey: Journey, now: Date = new Date()): Figure {
  const lanes = journey.lanes.map((l) => l.terminal_id);
  const starts = new Map<string, [Date, string]>();
  const ends = new Map<string, [Date, string]>();
  const shown = new Set<string>();
  const data: Data[] = [];
  const opened = journey.lanes.flatMap((l) => l.runs.map((b) => at(b.opened_at, now)));
  if (lanes.length > 0) {
    // every terminal's lane, including those no run has reached yet
    const first = opened.length > 0 ? new Date(Math.min(...opened.map((d) => d.getTime()))) : now;
    data.push({
      type: "scatter",
      mode: "markers",
      y: lanes,
      x: lanes.map(() => first.toISOString()),
      marker: { opacity: 0 },
      hoverinfo: "skip",
      showlegend: false,
    });
  }
  for (const lane of journey.lanes) {
    for (const bar of lane.runs) {
      const start = at(bar.opened_at, now);
      const end = at(bar.closed_at, now);
      const outcome = outcomeOf(bar);
      data.push({
        type: "bar",
        orientation: "h",
        y: [lane.terminal_id],
        x: [Math.max(end.getTime() - start.getTime(), 1000)],
        base: [start.toISOString()],
        marker: { color: outcomeColour(outcome), line: { width: 0 } },
        name: outcomeName(outcome),
        legendgroup: outcome,
        showlegend: !shown.has(outcome),
        hovertext: plotText(
          `${bar.run_id ?? bar.final_status ?? ""}\n${outcomeName(outcome)}\nowner: ${bar.owner ?? "-"}`,
        ).replaceAll("\n", "<br>"),
        hoverinfo: "text",
      } as Data);
      shown.add(outcome);
      if (bar.run_id !== null) {
        starts.set(bar.run_id, [start, lane.terminal_id]);
        ends.set(bar.run_id, [end, lane.terminal_id]);
      }
    }
  }
  const annotations: Partial<Annotations>[] = [];
  for (const arrow of journey.arrows) {
    const from = ends.get(arrow.from_run);
    const to = starts.get(arrow.to_run);
    if (arrow.kind === "pass" || from === undefined || to === undefined) continue;
    const colour = ARROW_COLOURS[arrow.kind] ?? COLOURS.blue;
    // ax and ay are times here (axref "x" on a date axis), which the types do not allow for
    annotations.push({
      x: to[0].toISOString(),
      y: to[1],
      ax: from[0].toISOString(),
      ay: from[1],
      xref: "x",
      yref: "y",
      axref: "x",
      ayref: "y",
      showarrow: true,
      arrowhead: 3,
      arrowwidth: 1.5,
      arrowcolor: colour,
      text: plotText(arrow.kind),
      font: { color: colour, size: 11 },
      hovertext: plotText(arrow.cause),
    } as unknown as Partial<Annotations>);
  }
  const layout: Partial<Layout> = {
    barmode: "overlay",
    bargap: 0.35,
    font: { family: FONT, color: INK, size: 12 },
    // automargin: room for the tick labels (Python Plotly's template set it; Plotly.js does not)
    xaxis: { type: "date", gridcolor: GRID, tickfont: { color: MUTED }, automargin: true },
    yaxis: {
      type: "category",
      categoryorder: "array",
      categoryarray: [...lanes].reverse(),
      gridcolor: GRID,
      automargin: true,
    },
    legend: { orientation: "h", yanchor: "bottom", y: 1.02, x: 0 },
    height: 110 + 44 * lanes.length,
    margin: { l: 8, r: 8, t: 36, b: 8 },
    annotations,
    paper_bgcolor: "#FFFFFF",
    plot_bgcolor: "#FFFFFF",
  };
  return { data, layout };
}
