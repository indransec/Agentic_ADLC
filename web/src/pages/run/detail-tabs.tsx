// The other SA 8.2 sections, one tab each, every tab present whether or not it has content
// (T040). A tab's label carries its count when it has rows.
import { useQuery } from "@tanstack/react-query";

import { api, call } from "../../api/client";
import { keys } from "../../api/queries";
import { DataTable } from "../../ui/data-table";
import { ErrorMessage } from "../../ui/error-message";
import { label, money } from "../../ui/format";
import { Literal } from "../../ui/literal";
import { Tabs } from "../../ui/tabs";
import type { RunDetail } from "./types";

const counted = (name: string, rows: readonly unknown[]): string =>
  rows.length > 0 ? `${name} (${String(rows.length)})` : name;

function Timeline({ runId }: { runId: string }) {
  const found = useQuery({
    queryKey: keys.runTimeline(runId),
    queryFn: () =>
      call(api.GET("/dashboard/runs/{run_id}/timeline", { params: { path: { run_id: runId } } })),
  });
  if (found.error !== null) return <ErrorMessage error={found.error} />;
  if (found.data === undefined) return <p className="caption">Loading…</p>;
  return (
    <>
      <DataTable rows={found.data.activity} emptyText="No steps yet." />
      {found.data.attempts.map((a) => (
        <div key={`${a.kind}-${String(a.attempt)}`} className="card">
          <p className="caption">
            {`${a.kind.slice(0, 1).toUpperCase()}${a.kind.slice(1)} attempt ${String(a.attempt)} · `}
            <Literal value={`${a.agent_id} (${a.implementation})`} />
            {` · ${(a.tokens_in ?? 0).toLocaleString("en-US")} in + ${(a.tokens_out ?? 0).toLocaleString("en-US")} out tokens · ${money(a.cost_usd)}`}
          </p>
          <DataTable rows={a.model_calls} emptyText="No model calls." />
          <DataTable rows={a.tool_calls} emptyText="No tool calls." />
        </div>
      ))}
    </>
  );
}

function Evidence({ detail }: { detail: RunDetail }) {
  return (
    <>
      <h3>Checks</h3>
      <DataTable rows={detail.checks} />
      <h3>Checklist results</h3>
      <DataTable rows={detail.checklist_results} />
      <h3>Artifact versions</h3>
      <DataTable rows={detail.artifacts.map((a) => ({ artifact: a.id, ...(a.version ?? {}) }))} />
      <h3>Ledger record</h3>
      {detail.ledger_record === null ? (
        <p className="empty">Not yet recorded: the run is open.</p>
      ) : (
        <pre className="json">
          <Literal value={JSON.stringify(detail.ledger_record, null, 2)} />
        </pre>
      )}
    </>
  );
}

export function DetailTabs({ detail }: { detail: RunDetail }) {
  const citations = detail.artifacts.flatMap((a) =>
    a.citations.map((c) => ({ artifact: a.id, ...c })),
  );
  const waiver = detail.waiver;
  return (
    <Tabs
      label="Run details"
      tabs={[
        {
          label: counted("Prerequisites", detail.prerequisites),
          render: () => <DataTable rows={detail.prerequisites} />,
        },
        { label: counted("Citations", citations), render: () => <DataTable rows={citations} /> },
        {
          label: counted("Prior rework", detail.prior_rework),
          render: () => <DataTable rows={detail.prior_rework} />,
        },
        {
          label: counted("Clarifications", detail.clarifications),
          render: () => <DataTable rows={detail.clarifications} />,
        },
        {
          label: counted("Approvals", detail.approvals),
          render: () => <DataTable rows={detail.approvals} emptyText="No approvals yet." />,
        },
        {
          label: "Waiver",
          render: () =>
            waiver === null ? (
              <p className="empty">No waiver on this run.</p>
            ) : (
              <DataTable
                rows={Object.entries(waiver).map(([field, value]) => ({
                  field: label(field),
                  value,
                }))}
              />
            ),
        },
        { label: "Activity", render: () => <DataTable rows={detail.timeline} /> },
        { label: "Timeline", render: () => <Timeline runId={detail.run.run_id} /> },
        { label: "Evidence", render: () => <Evidence detail={detail} /> },
      ]}
    />
  );
}
