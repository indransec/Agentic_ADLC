// Journey (T060; D-8, SA §12.2): one lane per terminal, a bar per run coloured by its outcome,
// arrows for reworks, reroutes, exceptions, events and re-entry; the KPI strip; escalations and
// exceptions. Refreshes every configured dashboard interval; the use case is in the address.
import { useQuery } from "@tanstack/react-query";
import { useMemo } from "react";
import { useSearchParams } from "react-router";

import { api, call } from "../../api/client";
import { keys } from "../../api/queries";
import { useConfig } from "../../config";
import { useOpenPage } from "../../nav/navigate";
import { DataTable } from "../../ui/data-table";
import { ErrorMessage } from "../../ui/error-message";
import { kpiValue } from "../../ui/format";
import { Literal } from "../../ui/literal";
import { Metric } from "../../ui/metric";
import { PageHeader } from "../../ui/page-header";
import { Plot } from "../../ui/plot";
import { StatusBadge } from "../../ui/status-badge";
import { buildJourneyFigure } from "./build-figure";

function View({ usecaseId, refreshMs }: { usecaseId: string; refreshMs: number }) {
  const open = useOpenPage();
  const poll = { refetchInterval: refreshMs, refetchIntervalInBackground: false } as const;
  const journey = useQuery({
    queryKey: keys.journey(usecaseId),
    queryFn: () =>
      call(
        api.GET("/dashboard/usecases/{usecase_id}/journey", {
          params: { path: { usecase_id: usecaseId } },
        }),
      ),
    ...poll,
  });
  const kpis = useQuery({
    queryKey: keys.kpis(usecaseId),
    queryFn: () =>
      call(
        api.GET("/dashboard/usecases/{usecase_id}/kpis", {
          params: { path: { usecase_id: usecaseId } },
        }),
      ),
    ...poll,
  });
  const data = journey.data;
  const figure = useMemo(() => (data === undefined ? null : buildJourneyFigure(data)), [data]);
  if (journey.error !== null) return <ErrorMessage error={journey.error} />;
  if (data === undefined || figure === null) return <p className="caption">Loading…</p>;
  const runIds = data.lanes
    .flatMap((l) => l.runs.map((b) => b.run_id))
    .filter((r): r is string => r !== null);
  return (
    <>
      <div className="card fields">
        <div>
          <span className="caption">Use case</span>
          <Literal as="div" value={data.usecase.name} />
        </div>
        <div>
          <span className="caption">Status</span>
          <div>
            <StatusBadge value={data.usecase.status} />
          </div>
        </div>
        <div>
          <span className="caption">Risk tier</span>
          <div>
            <StatusBadge value={data.usecase.risk_tier} />
          </div>
        </div>
      </div>
      {data.time_scale !== 1 && (
        <p className="caption">
          Durations are wall-clock time; timers run at scale {data.time_scale}.
        </p>
      )}
      <div className="metrics" aria-label="Key figures">
        {(kpis.data?.kpis ?? [])
          .filter((k) => k.headline)
          .map((k) => (
            <Metric key={k.id} name={k.name} value={kpiValue(k)} definition={k.definition} />
          ))}
      </div>
      <div className="card">
        <Plot
          figure={figure}
          label={`Journey of ${data.usecase.usecase_id}: one lane per terminal, a bar per run`}
        />
      </div>
      <h2>Escalations and exceptions</h2>
      {data.panel.unlinked.length > 0 && (
        <>
          <p className="caption">Runs opened by an event whose source run is unknown:</p>
          <DataTable rows={data.panel.unlinked} />
        </>
      )}
      {data.panel.escalations.length === 0 && data.panel.exceptions.length === 0 ? (
        <p className="empty">No escalations or exceptions on this use case.</p>
      ) : (
        <div className="two-equal">
          <div>
            <h3>Escalations</h3>
            <DataTable
              rows={data.panel.escalations.map((e) => ({
                run: e.run_id,
                terminal: e.terminal_id,
                trigger: e.trigger,
              }))}
            />
          </div>
          <div>
            <h3>Exceptions (waivers)</h3>
            <DataTable
              rows={data.panel.exceptions.map((w) => ({
                waiver: w["waiver_id"],
                run: w["run_id"],
                expiry: w["expiry"],
              }))}
            />
          </div>
        </div>
      )}
      {runIds.length > 0 && (
        <form
          className="inline-form"
          onSubmit={(event) => {
            event.preventDefault();
            const pick = new FormData(event.currentTarget).get("run");
            if (typeof pick === "string") open("run", { run: pick });
          }}
        >
          <label htmlFor="journey-run">Run</label>
          <select id="journey-run" name="run">
            {runIds.map((id) => (
              <option key={id} value={id}>
                {id}
              </option>
            ))}
          </select>
          <button type="submit">Open</button>
        </form>
      )}
    </>
  );
}

export function JourneyPage() {
  const [params, setParams] = useSearchParams();
  const { dashboard_refresh_seconds: refresh } = useConfig();
  const usecases = useQuery({
    queryKey: keys.usecases(false),
    queryFn: () => call(api.GET("/usecases", { params: { query: { mine: false } } })),
  });
  const ids = (usecases.data ?? []).map((u) => u.usecase_id);
  const wanted = params.get("usecase");
  const chosen = wanted !== null && ids.includes(wanted) ? wanted : ids[0];
  return (
    <>
      <PageHeader
        title="Journey"
        caption="Each terminal's runs over time, coloured by outcome, with reworks and reroutes drawn between them."
      />
      <ErrorMessage error={usecases.error} />
      {usecases.data !== undefined && ids.length === 0 && (
        <p className="empty">No use cases yet.</p>
      )}
      {chosen !== undefined && (
        <>
          <label htmlFor="journey-usecase">Use case</label>
          <select
            id="journey-usecase"
            value={chosen}
            onChange={(e) => {
              setParams({ usecase: e.target.value }, { replace: true });
            }}
          >
            {ids.map((id) => (
              <option key={id} value={id}>
                {id}
              </option>
            ))}
          </select>
          <View key={chosen} usecaseId={chosen} refreshMs={refresh * 1000} />
        </>
      )}
    </>
  );
}
