// A Plotly chart, loaded on first use (the basic bundle: no WebGL, no eval; research R-06).
// The figure comes from a pure builder; text from people or agents must go through plotText().
import type { Data, Layout } from "plotly.js";
import { useEffect, useRef } from "react";

export interface Figure {
  data: Data[];
  layout: Partial<Layout>;
}

/** Plotly reads some HTML tags in its text; escaped, a person's or an agent's text stays text. */
export function plotText(value: unknown): string {
  const text = typeof value === "string" ? value : JSON.stringify(value);
  return text.replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;");
}

export function Plot({ figure, label }: { figure: Figure; label: string }) {
  const element = useRef<HTMLDivElement>(null);
  useEffect(() => {
    let live = true;
    const node = element.current;
    void import("plotly.js-basic-dist-min").then(({ default: Plotly }) => {
      if (live && node !== null) {
        void Plotly.react(node, figure.data, figure.layout, {
          displaylogo: false,
          responsive: true,
        });
      }
    });
    return () => {
      live = false;
    };
  }, [figure]);
  return <div ref={element} className="plot" role="img" aria-label={label} />;
}
