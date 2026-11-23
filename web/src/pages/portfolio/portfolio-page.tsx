// Portfolio (T061; D-8): the delivery KPIs across use cases (counts and times summed, rates
// pooled), by risk tier and status; time per terminal as a stacked chart. Filters in the address.
import { useQuery } from "@tanstack/react-query";
import { useMemo } from "react";
import { useSearchParams } from "react-router";

import { api, call } from "../../api/client";
import { keys } from "../../api/queries";
import { DataTable } from "../../ui/data-table";
import { ErrorMessage } from "../../ui/error-message";
import { kpiValue } from "../../ui/format";
import { Metric } from "../../ui/metric";
import { PageHeader } from "../../ui/page-header";
import { Plot } from "../../ui/plot";
import { asPerTerminal, buildSplitFigure } from "./build-split";

// The platform's risk tiers and use-case statuses, as the previous application offered them
const TIERS = ["low", "medium", "high"];
const STATUSES = ["active", "closed", "terminated"];
const word = (value: string) => `${value.slice(0, 1).toUpperCase()}${value.slice(1)}`;

export function PortfolioPage() {
  const [params, setParams] = useSearchParams();
  const tier = params.get("tier") ?? "";
  const status = params.get("status") ?? "";
  const found = useQuery({
    queryKey: keys.portfolio({ tier, status }),
    queryFn: () =>
      call(
        api.GET("/dashboard/portfolio", {
          params: {
            query: {
              ...(tier !== "" ? { risk_tier: tier } : {}),
              ...(status !== "" ? { status } : {}),
            },
          },
        }),
      ),
    placeholderData: (previous) => previous,
  });
  const kpis = (found.data?.kpis ?? []).filter((k) => k.unit !== "split");
  const { split, recorded, figure } = useMemo(() => {
    const perTerminal = asPerTerminal(
      found.data?.kpis.find((k) => k.id === "time_split")?.per_terminal,
    );
    return {
      split: perTerminal,
      recorded: Object.values(perTerminal).some((v) => Object.values(v).some((s) => s > 0)),
      figure: buildSplitFigure(perTerminal),
    };
  }, [found.data]);

  function set(key: string, value: string) {
    const next = new URLSearchParams(params);
    if (value === "") next.delete(key);
    else next.set(key, value);
    setParams(next, { replace: true });
  }

  return (
    <>
      <PageHeader
        title="Portfolio"
        caption="The delivery KPIs across use cases: counts and times summed, rates pooled."
      />
      <div className="card filters">
        <div>
          <label htmlFor="portfolio-tier">Risk tier</label>
          <select
            id="portfolio-tier"
            value={tier}
            onChange={(e) => {
              set("tier", e.target.value);
            }}
          >
            <option value="">Any</option>
            {TIERS.map((t) => (
              <option key={t} value={t}>
                {word(t)}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label htmlFor="portfolio-status">Status</label>
          <select
            id="portfolio-status"
            value={status}
            onChange={(e) => {
              set("status", e.target.value);
            }}
          >
            <option value="">Any</option>
            {STATUSES.map((s) => (
              <option key={s} value={s}>
                {word(s)}
              </option>
            ))}
          </select>
        </div>
      </div>
      <ErrorMessage error={found.error} />
      {found.data !== undefined && (
        <>
          <p className="caption">{found.data.usecases} use case(s)</p>
          <div className="metrics">
            {kpis.map((k) => (
              <Metric key={k.id} name={k.name} value={kpiValue(k)} definition={k.definition} />
            ))}
          </div>
          <h2>Time per terminal</h2>
          {recorded ? (
            <>
              <div className="card">
                <Plot figure={figure} label="Time per terminal, stacked by category, in hours" />
              </div>
              <details>
                <summary>Time per terminal as a table (seconds)</summary>
                <DataTable
                  rows={Object.entries(split).map(([terminal, v]) => ({ terminal, ...v }))}
                />
              </details>
            </>
          ) : (
            <p className="empty">No run time recorded yet.</p>
          )}
          <details>
            <summary>All KPIs as a table, with their definitions</summary>
            <DataTable
              rows={kpis.map((k) => ({
                KPI: k.name,
                value: kpiValue(k),
                definition: k.definition,
              }))}
            />
          </details>
        </>
      )}
    </>
  );
}
