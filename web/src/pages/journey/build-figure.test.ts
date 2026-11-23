// T057 (P-22): the journey figure from the platform's answer: lanes in the answer's order, a bar
// per run, an arrow per non-pass arrow with its kind; a cause is escaped, never markup.
import { describe, expect, it } from "vitest";

import type { components } from "../../api/schema";
import { fixtures, HOSTILE } from "../../test/fixtures";
import { buildJourneyFigure, outcomeOf } from "./build-figure";

type J = components["schemas"]["Journey"];

function journeyWithRework(): J {
  const journey: J = structuredClone(fixtures.journey);
  const t1 = journey.lanes.find((l) => l.terminal_id === "T1");
  const bar = t1?.runs[0];
  if (t1 === undefined || bar === undefined) throw new Error("fixture changed");
  t1.runs = [
    {
      ...bar,
      run_id: "UC-0001/T1/run-1",
      closed_at: "2026-11-23T10:00:00Z",
      final_status: "rework",
    },
    {
      ...bar,
      run_id: "UC-0001/T1/run-2",
      opened_at: "2026-11-23T10:00:01Z",
      closed_at: null,
      final_status: null,
    },
  ];
  journey.arrows = [
    ...journey.arrows,
    {
      from_run: "UC-0001/T1/run-1",
      to_run: "UC-0001/T1/run-2",
      kind: "rework",
      event_type: "T1.rework.requirements",
      cause: { comment: HOSTILE[0] },
      actor: "product_owner-person",
      at: "2026-11-23T10:00:01Z",
    },
  ];
  return journey;
}

describe("journey figure", () => {
  it("has a lane per terminal, in the answer's order (top first)", () => {
    const figure = buildJourneyFigure(fixtures.journey);
    const lanes = fixtures.journey.lanes.map((l) => l.terminal_id);
    expect(figure.layout.yaxis?.categoryarray).toEqual([...lanes].reverse());
    expect(figure.layout.height).toBe(110 + 44 * lanes.length);
    expect(figure.layout.yaxis).toMatchObject({ type: "category", automargin: true });
    expect(figure.layout.xaxis).toMatchObject({ type: "date", automargin: true });
  });

  it("has a bar per run, coloured and named by outcome", () => {
    const figure = buildJourneyFigure(journeyWithRework());
    const bars = figure.data.filter((d) => d.type === "bar");
    const runs = journeyWithRework().lanes.flatMap((l) => l.runs);
    expect(bars).toHaveLength(runs.length);
    expect(bars.map((b) => b.name)).toContain("Rework");
    expect(bars.map((b) => b.name)).toContain("In progress");
  });

  it("draws rework arrows and not plain passes; the cause is escaped", () => {
    const journey = journeyWithRework();
    const runs = new Set(journey.lanes.flatMap((l) => l.runs.map((b) => b.run_id)));
    const drawable = journey.arrows.filter(
      (a) => a.kind !== "pass" && runs.has(a.from_run) && runs.has(a.to_run),
    );
    const arrows = buildJourneyFigure(journey).layout.annotations ?? [];
    expect(arrows).toHaveLength(drawable.length);
    expect(journey.arrows.some((a) => a.kind === "pass")).toBe(true); // passes are not drawn
    const ours = arrows.find((a) => String(a.hovertext).includes("&lt;script&gt;"));
    expect(ours?.text).toBe("rework");
    for (const arrow of arrows) expect(String(arrow.hovertext)).not.toContain("<script>");
  });

  it("names outcomes", () => {
    const [bar] = journeyWithRework().lanes.flatMap((l) => l.runs);
    expect(bar && outcomeOf({ ...bar, collapsed: 3 })).toBe("collapsed");
  });
});
