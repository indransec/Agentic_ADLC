// The control results (T039): counts as platform words, then the results.
import { DataTable } from "../../ui/data-table";
import type { RunDetail } from "./types";

export function ControlResults({ results }: { results: RunDetail["control_results"] }) {
  const passed = results.filter((r) => r["passed"] === true).length;
  const blocking = results.filter((r) => r["blocking"] === true && r["passed"] !== true).length;
  return (
    <section aria-labelledby="controls-heading">
      <h2 id="controls-heading">Control results</h2>
      {results.length > 0 && (
        <p>
          <span className={`badge ${passed === results.length ? "good" : "warn"}`}>
            {passed} of {results.length} passed
          </span>{" "}
          {blocking > 0 && <span className="badge bad">{blocking} blocking failed</span>}
        </p>
      )}
      <DataTable rows={results} emptyText="No controls have run yet." />
    </section>
  );
}
