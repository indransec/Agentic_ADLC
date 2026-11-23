// The run's artifacts, read-only (US2). US3 replaces this with the editing panel.
import { DataTable } from "../../ui/data-table";
import { Literal } from "../../ui/literal";
import type { RunDetail } from "./types";

export function ArtifactsReadOnly({ detail }: { detail: RunDetail }) {
  return (
    <section aria-labelledby="artifacts-heading">
      <h2 id="artifacts-heading">Artifacts</h2>
      {detail.artifacts.map((artifact) => (
        <div key={artifact.id} className="card">
          <h3>{artifact.id}</h3>
          <p className="caption">
            {artifact.version === null
              ? "Not built yet"
              : `Version ${String(artifact.version.version)}`}
          </p>
          {Array.isArray(artifact.rows) ? (
            <DataTable
              rows={artifact.rows}
              columns={artifact.columns.length > 0 ? artifact.columns : undefined}
              rawLabels
            />
          ) : (
            <Literal as="p" value={artifact.rows} />
          )}
        </div>
      ))}
    </section>
  );
}
