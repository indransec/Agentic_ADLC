// Use cases (T059; P-19): "only mine" or all, one use case's runs with times and cost, opening a
// run or the journey view, and verifying the use case's ledger (D-6). The choices are in the
// address (?mine=0, ?usecase=).
import { useMutation, useQuery } from "@tanstack/react-query";
import { useLocation, useSearchParams } from "react-router";

import { api, call } from "../../api/client";
import { keys } from "../../api/queries";
import { useOpenPage } from "../../nav/navigate";
import { DataTable } from "../../ui/data-table";
import { ErrorMessage } from "../../ui/error-message";
import { duration, money, when } from "../../ui/format";
import { Literal, literalText } from "../../ui/literal";
import { PageHeader } from "../../ui/page-header";
import { knownStatus } from "../../ui/status";
import { StatusBadge } from "../../ui/status-badge";

const word = (value: unknown): string =>
  knownStatus(value)?.[0] ?? (value === null || value === undefined ? "" : literalText(value));

function Journey({ usecaseId }: { usecaseId: string }) {
  const open = useOpenPage();
  const found = useQuery({
    queryKey: keys.usecase(usecaseId),
    queryFn: () =>
      call(api.GET("/usecases/{usecase_id}", { params: { path: { usecase_id: usecaseId } } })),
  });
  const verify = useMutation({
    mutationFn: () =>
      call(
        api.POST("/usecases/{usecase_id}/verify", { params: { path: { usecase_id: usecaseId } } }),
      ),
  });
  if (found.error !== null) return <ErrorMessage error={found.error} />;
  if (found.data === undefined) return <p className="caption">Loading…</p>;
  const { usecase, runs, summary, cost } = found.data;
  const bySummary = new Map(summary.map((s) => [s.terminal_id, s]));
  const report = verify.data;
  return (
    <>
      <h2>Journey</h2>
      <div className="card fields">
        <div>
          <span className="caption">Name</span>
          <Literal as="div" value={usecase.name} />
        </div>
        <div>
          <span className="caption">Submitted by</span>
          <Literal as="div" value={usecase.submitted_by} />
        </div>
        <div>
          <span className="caption">Risk tier</span>
          <div>
            <StatusBadge value={usecase.risk_tier} />
          </div>
        </div>
        <div>
          <span className="caption">Total cost</span>
          <div>{money(cost.total.cost_usd)}</div>
        </div>
        <details className="span-all">
          <summary>Description</summary>
          <Literal as="p" value={usecase.intake_text} />
        </details>
      </div>
      {runs.length === 0 ? (
        <p className="empty">No runs yet: the first terminal opens shortly after submission.</p>
      ) : (
        <div className="table-wrap">
          <table className="data-table">
            <thead>
              <tr>
                {[
                  "Run",
                  "Terminal",
                  "State",
                  "Status",
                  "Opened",
                  "Closed",
                  "Automatic",
                  "Waiting",
                  "Cost",
                  "",
                ].map((h, i) => (
                  <th key={i} scope="col">
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {runs.map((run) => {
                const s = bySummary.get(run.terminal_id);
                return (
                  <tr key={run.run_id}>
                    <td>{run.run_id}</td>
                    <td>{run.terminal_id}</td>
                    <td>{word(run.state)}</td>
                    <td>{word(run.final_status)}</td>
                    <td>{when(run.opened_at)}</td>
                    <td>{when(run.closed_at)}</td>
                    <td>{duration(s?.automatic_seconds ?? 0)}</td>
                    <td>{duration(s?.waiting_seconds ?? 0)}</td>
                    <td>{money(cost.terminals[run.terminal_id]?.cost_usd)}</td>
                    <td>
                      <button
                        type="button"
                        onClick={() => {
                          open("run", { run: run.run_id });
                        }}
                      >
                        Open <span className="visually-hidden">{run.run_id}</span>
                      </button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
      <p>
        <button
          type="button"
          onClick={() => {
            open("journey", { usecase: usecaseId });
          }}
        >
          Open the journey view
        </button>
      </p>
      <h2>Evidence</h2>
      <div className="card">
        <p className="caption">Check this use case&apos;s ledger records for breaks.</p>
        <button
          type="button"
          disabled={verify.isPending}
          onClick={() => {
            verify.mutate();
          }}
        >
          Verify the ledger for this use case
        </button>
        {report?.verified === true && (
          <p className="message success">Verified: {report.records_checked} records, no breaks</p>
        )}
        {report?.verified === false && (
          <>
            <p className="message error">{report.breaks.length} break(s) found</p>
            <DataTable rows={report.breaks} />
          </>
        )}
        <ErrorMessage error={verify.error} />
      </div>
    </>
  );
}

export function UseCasesPage() {
  const [params, setParams] = useSearchParams();
  const location = useLocation();
  const submitted = (location.state as { submitted?: string } | null)?.submitted;
  const mine = params.get("mine") !== "0";
  const found = useQuery({
    queryKey: keys.usecases(mine),
    queryFn: () => call(api.GET("/usecases", { params: { query: { mine } } })),
  });
  const ids = (found.data ?? []).map((u) => u.usecase_id);
  const wanted = params.get("usecase");
  const chosen = wanted !== null && ids.includes(wanted) ? wanted : ids[0];

  function set(changes: Record<string, string | null>) {
    const next = new URLSearchParams(params);
    for (const [key, value] of Object.entries(changes)) {
      if (value === null) next.delete(key);
      else next.set(key, value);
    }
    setParams(next, { replace: true });
  }

  return (
    <>
      <PageHeader
        title="Use cases"
        caption="Every use case, its runs through the terminals, and its evidence."
      />
      {submitted !== undefined && (
        <p className="message success" role="status">
          Submitted <span>{submitted}</span>
        </p>
      )}
      <label className="inline">
        <input
          type="checkbox"
          checked={mine}
          onChange={(e) => {
            set({ mine: e.target.checked ? null : "0" });
          }}
        />{" "}
        Only mine
      </label>
      <ErrorMessage error={found.error} />
      {found.data !== undefined && (
        <DataTable
          rows={found.data.map((u) => ({
            "use case": u.usecase_id,
            name: u.name,
            "submitted by": u.submitted_by,
            status: word(u.status),
            "open runs": u.open_runs,
          }))}
          emptyText={mine ? "You have not submitted a use case yet." : "No use cases yet."}
        />
      )}
      {chosen !== undefined && (
        <>
          <label htmlFor="usecase-pick">Use case</label>
          <select
            id="usecase-pick"
            value={chosen}
            onChange={(e) => {
              set({ usecase: e.target.value });
            }}
          >
            {ids.map((id) => (
              <option key={id} value={id}>
                {id}
              </option>
            ))}
          </select>
          <Journey key={chosen} usecaseId={chosen} />
        </>
      )}
    </>
  );
}
