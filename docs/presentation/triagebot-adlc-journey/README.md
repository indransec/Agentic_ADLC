# TriageBot through the ADLC: the journey, the runs and the dashboards

A 39-slide deck for leadership and engineering audiences. It follows the Incident Triage use case
(TriageBot) from submission through T0–T9, the run states inside each terminal, the scenarios they
allow, the platform and agent dashboards, the value case, and an appendix with the architecture
and running cost.

The deck is published as a Slides artifact; present it and export it (PPTX or PDF) from there. The
files in this folder are its source, kept here for review and history.

| Path | What it is |
| --- | --- |
| `deck.json` | Slide order, sections and typefaces |
| `deck.css` | Shared theme, layouts and motion |
| `slides/<id>.html` | One slide each; speaker notes are in the closing `<aside>` |

The editable architecture diagrams behind appendix slides A1 and A2, and the event-processing view,
are in `docs/diagrams/adlc-architecture-on-a-page.drawio`.

## Sections

| Slides | Section |
| --- | --- |
| 1–5 | The problem, what we gain, the ten terminals, the cast |
| 6–7 | How a run works: the run states and the platform parts |
| 8–18 | Lap 1, T0 to T7, in about six weeks |
| 19–24 | Operate, evolve and retire: T8, T9, laps 2 and 3, retirement |
| 25–26 | The whole journey and the scenarios |
| 27–31 | Dashboards and built vs target |
| 32–35 | Before and after, how we prove it, guarantees, next steps |
| 36–39 | Appendix: architecture on a page, Azure reference architecture, running cost |

## Figures

- Lifecycle counts on the journey and lifecycle-KPI slides come from the rehearsed demo run (UC-0034).
- Portfolio, flow, agent-health and cost figures are illustrative or ballpark, and labelled so.
- Placeholders to fill before presenting: `[__]` cells on "Before and after" and "How we will prove it",
  the waiver expiry `[date]`, and the brackets in the closing ask.
