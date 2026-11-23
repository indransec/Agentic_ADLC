// The run's artifacts (T046; FR-007, FR-012): an editor changes a table in place and saves it,
// uploads a spreadsheet or attaches a file, and sees the history. Tables up to MAX_EDIT_ROWS are
// editable in the page; larger ones are read-only, with upload offered. Every save and upload
// sends the run version shown; a stale answer records nothing and the page reloads the run.
// Attachments are offered for download only.
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { api, call, downloadAttachment } from "../../api/client";
import { isApiError } from "../../api/errors";
import { keys } from "../../api/queries";
import { DataTable } from "../../ui/data-table";
import { ErrorMessage } from "../../ui/error-message";
import { Literal } from "../../ui/literal";
import { ArtifactGrid, type Row } from "./artifact-grid";
import type { RunDetail } from "./types";

/** The editor's limit (007 research R-11): a platform-wide value, not a terminal's. */
export const MAX_EDIT_ROWS = 1000;

type Artifact = RunDetail["artifacts"][number];

interface Props {
  detail: RunDetail;
  onStale: () => void;
  /** The run changed through this panel (it reloads). */
  onChanged: () => void;
}

const isRows = (value: unknown): value is Row[] =>
  Array.isArray(value) &&
  value.every((r) => typeof r === "object" && r !== null && !Array.isArray(r));

function History({ runId, artifactId }: { runId: string; artifactId: string }) {
  const found = useQuery({
    queryKey: keys.artifactHistory(runId, artifactId),
    queryFn: () =>
      call(
        api.GET("/runs/{run_id}/artifacts/{artifact_id}/history", {
          params: { path: { run_id: runId, artifact_id: artifactId } },
        }),
      ),
  });
  if (found.error !== null) return <ErrorMessage error={found.error} />;
  if (found.data === undefined) return <p className="caption">Loading…</p>;
  return <DataTable rows={found.data} />;
}

function ArtifactCard({ artifact, detail, onStale, onChanged }: Props & { artifact: Artifact }) {
  const runId = detail.run.run_id;
  const version = detail.run.version;
  const editable = detail.form.can_edit;
  const queryClient = useQueryClient();
  const [edited, setEdited] = useState<Row[] | null>(null);
  const [done, setDone] = useState<string | null>(null);
  const [history, setHistory] = useState(false);
  const [sheet, setSheet] = useState<File | null>(null);
  const [file, setFile] = useState<File | null>(null);
  const path = { run_id: runId, artifact_id: artifact.id };

  function settled(message: string) {
    setEdited(null);
    setDone(message);
    onChanged();
    void queryClient.invalidateQueries({ queryKey: keys.run(runId) });
  }

  const change = useMutation({
    mutationFn: async (action: { kind: "save" | "sheet" | "attach"; message: string }) => {
      if (action.kind === "save") {
        await call(
          api.PUT("/runs/{run_id}/artifacts/{artifact_id}", {
            params: { path },
            body: { rows: edited, expected_version: version },
          }),
        );
      } else {
        const form = new FormData();
        const chosen = action.kind === "sheet" ? sheet : file;
        if (chosen === null) return action.message;
        form.append("file", chosen, chosen.name);
        form.append("expected_version", String(version));
        const body = form as unknown as { file: string; expected_version: number };
        await call(
          action.kind === "sheet"
            ? api.POST("/runs/{run_id}/artifacts/{artifact_id}/spreadsheet", {
                params: { path },
                body,
              })
            : api.POST("/runs/{run_id}/artifacts/{artifact_id}/attachments", {
                params: { path },
                body,
              }),
        );
      }
      return action.message;
    },
    onSuccess: settled,
    onError: (error) => {
      setDone(null);
      if (isApiError(error) && error.kind === "stale") onStale();
    },
  });

  const rows = artifact.rows;
  const table = isRows(rows) ? rows : null;
  const inPage = table !== null && table.length <= MAX_EDIT_ROWS;
  const headingId = `artifact-${artifact.id}`;
  return (
    <section className="card" aria-labelledby={headingId}>
      <h3 id={headingId}>{artifact.id}</h3>
      <p className="caption">
        {artifact.version === null
          ? "Not built yet"
          : `Version ${String(artifact.version.version)}`}
      </p>
      {table === null ? (
        <Literal as="p" value={rows} />
      ) : (
        <ArtifactGrid
          key={`${artifact.id}:${String(version)}`}
          artifactId={artifact.id}
          rows={table}
          columns={artifact.columns}
          editable={editable && inPage}
          onChange={(next) => {
            setEdited(next);
            setDone(null);
          }}
        />
      )}
      {editable && table !== null && !inPage && (
        <p className="caption">
          More than {MAX_EDIT_ROWS} rows: upload a spreadsheet to change it.
        </p>
      )}
      {editable && inPage && (
        <p>
          <button
            type="button"
            className="primary"
            disabled={edited === null || change.isPending}
            onClick={() => {
              change.mutate({ kind: "save", message: "Saved" });
            }}
          >
            Save {artifact.id}
          </button>
        </p>
      )}
      {artifact.attachments.length > 0 && (
        <ul className="attachments">
          {artifact.attachments.map((a) => {
            const name = typeof a["name"] === "string" ? a["name"] : "attachment";
            const hash = typeof a["content_hash"] === "string" ? a["content_hash"] : "";
            return (
              <li key={hash}>
                <Literal value={name} />{" "}
                <button
                  type="button"
                  onClick={() => {
                    void downloadAttachment(runId, hash, name);
                  }}
                >
                  Download
                </button>
              </li>
            );
          })}
        </ul>
      )}
      {editable && (
        <details>
          <summary>Upload a spreadsheet or attach a file</summary>
          <label htmlFor={`${headingId}-sheet`}>Spreadsheet for {artifact.id}</label>
          <input
            id={`${headingId}-sheet`}
            type="file"
            accept=".xlsx"
            onChange={(e) => {
              setSheet(e.target.files?.[0] ?? null);
            }}
          />
          <p>
            <button
              type="button"
              disabled={sheet === null || change.isPending}
              onClick={() => {
                change.mutate({ kind: "sheet", message: "Spreadsheet uploaded" });
              }}
            >
              Upload spreadsheet to {artifact.id}
            </button>
          </p>
          <label htmlFor={`${headingId}-file`}>Attach a file to {artifact.id}</label>
          <input
            id={`${headingId}-file`}
            type="file"
            onChange={(e) => {
              setFile(e.target.files?.[0] ?? null);
            }}
          />
          <p>
            <button
              type="button"
              disabled={file === null || change.isPending}
              onClick={() => {
                change.mutate({ kind: "attach", message: "Attached" });
              }}
            >
              Attach to {artifact.id}
            </button>
          </p>
        </details>
      )}
      <p>
        <button
          type="button"
          aria-expanded={history}
          onClick={() => {
            setHistory(!history);
          }}
        >
          {history ? "Hide history" : "Show history"}
        </button>
      </p>
      {history && <History runId={runId} artifactId={artifact.id} />}
      {done !== null && <p className="message success">{done}</p>}
      {change.error !== null && !(isApiError(change.error) && change.error.kind === "stale") && (
        <ErrorMessage error={change.error} />
      )}
    </section>
  );
}

export function ArtifactPanel(props: Props) {
  const { detail } = props;
  return (
    <section aria-labelledby="artifacts-heading">
      <h2 id="artifacts-heading">Artifacts</h2>
      {detail.artifacts.length === 0 && (
        <p className="empty">This terminal produces no artifacts.</p>
      )}
      {detail.artifacts.map((artifact) => (
        <ArtifactCard key={artifact.id} artifact={artifact} {...props} />
      ))}
    </section>
  );
}
