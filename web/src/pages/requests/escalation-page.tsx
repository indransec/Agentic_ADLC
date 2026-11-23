// An escalation (T053; D-4): the agents could not finish the run; an accountable person supplies
// the artifacts in the grid and the run goes to normal sign-off. The run's other sections follow.
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { api, call } from "../../api/client";
import { isApiError } from "../../api/errors";
import { keys } from "../../api/queries";
import { DataTable } from "../../ui/data-table";
import { ErrorMessage } from "../../ui/error-message";
import { ArtifactGrid, type Row } from "../run/artifact-grid";
import { MAX_EDIT_ROWS } from "../run/artifact-panel";
import { ControlResults } from "../run/control-results";
import { DetailTabs } from "../run/detail-tabs";
import { ReviewPanel } from "../run/review-panel";
import { STALE_MESSAGE } from "../run/run-page";
import type { RunDetail } from "../run/types";
import { RequestFrame } from "./request-frame";

const rowsOf = (value: unknown): Row[] =>
  Array.isArray(value) ? value.filter((r): r is Row => typeof r === "object" && r !== null) : [];

function Sections({ detail }: { detail: RunDetail }) {
  return (
    <>
      <ReviewPanel recommendation={detail.recommendation} />
      <ControlResults results={detail.control_results} />
      <DetailTabs detail={detail} />
    </>
  );
}

interface EscalationProps {
  detail: RunDetail;
  /** Kept by the page: the run reloads (a new version) once the escalation is completed. */
  completed: boolean;
  onCompleted: () => void;
}

function Escalation({ detail, completed: done, onCompleted }: EscalationProps) {
  const queryClient = useQueryClient();
  const runId = detail.run.run_id;
  const [completed, setCompleted] = useState<Record<string, Row[]>>(() =>
    Object.fromEntries(
      detail.artifacts
        .filter((a) => rowsOf(a.rows).length <= MAX_EDIT_ROWS)
        .map((a) => [a.id, rowsOf(a.rows)]),
    ),
  );
  const [stale, setStale] = useState(false);
  const complete = useMutation({
    mutationFn: () =>
      call(
        api.POST("/runs/{run_id}/escalation", {
          params: { path: { run_id: runId } },
          body: { artifacts: completed, expected_version: detail.run.version },
        }),
      ),
    onSuccess: () => {
      onCompleted();
      void queryClient.invalidateQueries({ queryKey: keys.inbox });
      void queryClient.invalidateQueries({ queryKey: keys.run(runId) });
    },
    onError: (error) => {
      if (isApiError(error) && error.kind === "stale") {
        setStale(true);
        void queryClient.invalidateQueries({ queryKey: keys.run(runId) });
      }
    },
  });
  if (done) {
    return (
      <>
        <p className="message success">Escalation completed</p>
        <Sections detail={detail} />
      </>
    );
  }
  if (!detail.form.can_complete_escalation) {
    return (
      <>
        <p className="message notice">You cannot complete this run.</p>
        <Sections detail={detail} />
      </>
    );
  }
  return (
    <>
      {stale && <p className="message notice">{STALE_MESSAGE}</p>}
      <h2>Artifacts to complete</h2>
      {detail.artifacts.map((artifact) => {
        const rows = rowsOf(artifact.rows);
        const columns =
          artifact.columns.length > 0 ? artifact.columns : [...new Set(rows.flatMap(Object.keys))];
        return (
          <section key={artifact.id} className="card" aria-label={artifact.id}>
            <h3>{artifact.id}</h3>
            {rows.length > MAX_EDIT_ROWS ? (
              <DataTable rows={rows} rawLabels />
            ) : (
              <ArtifactGrid
                key={`${artifact.id}:${String(detail.run.version)}`}
                artifactId={artifact.id}
                rows={rows.length > 0 ? rows : [Object.fromEntries(columns.map((c) => [c, ""]))]}
                columns={columns}
                editable
                onChange={(next) => {
                  setCompleted({ ...completed, [artifact.id]: next });
                }}
              />
            )}
          </section>
        );
      })}
      <p>
        <button
          type="button"
          className="primary"
          disabled={complete.isPending}
          onClick={() => {
            complete.mutate();
          }}
        >
          Complete escalation
        </button>
      </p>
      {complete.error !== null &&
        !(isApiError(complete.error) && complete.error.kind === "stale") && (
          <ErrorMessage error={complete.error} />
        )}
      <Sections detail={detail} />
    </>
  );
}

export function EscalationPage() {
  const [completed, setCompleted] = useState(false);
  return (
    <RequestFrame
      title="Escalation"
      caption="The agents could not finish this run. Supply the artifacts; the run then goes to normal sign-off."
      openFrom="Open an escalation from your inbox."
    >
      {(detail) => (
        <Escalation
          key={detail.run.version}
          detail={detail}
          completed={completed}
          onCompleted={() => {
            setCompleted(true);
          }}
        />
      )}
    </RequestFrame>
  );
}
