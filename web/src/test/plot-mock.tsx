// Plotly needs a real browser to lay out; component tests see a labelled stand-in that records
// the figure it was given (the figure builders are tested directly).
import type { Figure } from "../ui/plot";

export const drawn: Figure[] = [];

export function MockPlot({ figure, label }: { figure: Figure; label: string }) {
  drawn.push(figure);
  return <figure aria-label={label} />;
}
