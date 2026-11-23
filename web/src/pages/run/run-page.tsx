// The Run page (T042; SA 8.2, FR-005 to FR-007): the summary bar; the artifacts beside the
// reviewer's recommendation, the control results and the decision; the other sections as tabs.
// The run is in the address (?run=). The run is not refreshed in the background, so the version
// on the page is the version the person acts on (research R-08); a stale answer reloads it.
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useSearchParams } from "react-router";

import { api, call } from "../../api/client";
import { keys } from "../../api/queries";
import { pagePath } from "../../nav/navigate";
import { ErrorMessage } from "../../ui/error-message";
import { PageHeader } from "../../ui/page-header";
import { ArtifactsReadOnly } from "./artifacts-read-only";
import { ControlResults } from "./control-results";
import { DecisionForm } from "./decision-form";
import { DetailTabs } from "./detail-tabs";
import { ReviewPanel } from "./review-panel";
import { SummaryBar } from "./summary-bar";

export const STALE_MESSAGE =
  "This run changed since you opened it. It has been reloaded; check it and act again.";

export function RunPage() {
  const [params] = useSearchParams();
  const runId = params.get("run") ?? "";
  const queryClient = useQueryClient();
  const [notice, setNotice] = useState<"stale" | "recorded" | null>(null);
  const found = useQuery({
    queryKey: keys.run(runId),
    queryFn: () => call(api.GET("/runs/{run_id}", { params: { path: { run_id: runId } } })),
    enabled: runId !== "",
    staleTime: Infinity,
  });

  if (runId === "") {
    return (
      <>
        <PageHeader
          title="Run"
          caption="A terminal run: its artifacts, the checks on them and the decision."
        />
        <p className="empty">Open a run from your inbox or a use case.</p>
      </>
    );
  }
  if (found.error !== null) {
    return (
      <>
        <PageHeader title="Run" />
        <ErrorMessage error={found.error} />
        <p>
          <a href={pagePath("inbox")}>Open the Inbox</a>
        </p>
      </>
    );
  }
  const detail = found.data;
  if (detail === undefined) {
    return (
      <>
        <PageHeader title="Run" />
        <p className="caption">Loading…</p>
      </>
    );
  }

  function reloadStale() {
    setNotice("stale");
    void queryClient.invalidateQueries({ queryKey: keys.run(runId) });
  }

  return (
    <>
      <PageHeader title="Run" />
      {notice === "stale" && (
        <p className="message notice" role="status">
          {STALE_MESSAGE}
        </p>
      )}
      {notice === "recorded" && (
        <p className="message success" role="status">
          Decision recorded
        </p>
      )}
      <SummaryBar detail={detail} />
      {detail.run.state === "blocked" && (
        <p className="message error">
          Blocked by an unmet prerequisite (see Prerequisites). Supply the evidence, or terminate
          the run below.
        </p>
      )}
      <div className="run-columns">
        <div>
          <ArtifactsReadOnly detail={detail} />
        </div>
        <div>
          <ReviewPanel recommendation={detail.recommendation} />
          <ControlResults results={detail.control_results} />
          <DecisionForm
            key={detail.run.version}
            detail={detail}
            onStale={reloadStale}
            onRecorded={() => {
              setNotice("recorded");
            }}
          />
        </div>
      </div>
      <DetailTabs detail={detail} />
    </>
  );
}
