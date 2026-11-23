// Activity (T061; D-8): what agents, reviewers, people and the orchestrator did, newest first,
// filterable by use case, terminal, actor and step. The filters live in the address, so they
// survive refreshes, reloads and shared links; the feed refreshes every dashboard interval.
import { useQuery } from "@tanstack/react-query";
import { useSearchParams } from "react-router";

import { api, call } from "../../api/client";
import { keys } from "../../api/queries";
import { useConfig } from "../../config";
import { DataTable } from "../../ui/data-table";
import { ErrorMessage } from "../../ui/error-message";
import { PageHeader } from "../../ui/page-header";

// The platform's actor types and run steps (run_activity), as the previous application offered them
const ACTORS = ["agent", "reviewer", "human", "orchestrator", "system"];
const STEPS = [
  "prerequisites",
  "build",
  "controls",
  "review",
  "clarification",
  "sign_off",
  "waiver",
  "escalation",
  "close",
  "route",
  "timer",
];
const words = (value: string) =>
  `${value.slice(0, 1).toUpperCase()}${value.slice(1).replaceAll("_", " ")}`;

export function ActivityPage() {
  const [params, setParams] = useSearchParams();
  const { dashboard_refresh_seconds: refresh } = useConfig();
  const filters = {
    usecase: params.get("usecase") ?? "",
    terminal: params.get("terminal") ?? "",
    actor: params.get("actor") ?? "",
    step: params.get("step") ?? "",
  };
  const usecases = useQuery({
    queryKey: keys.usecases(false),
    queryFn: () => call(api.GET("/usecases", { params: { query: { mine: false } } })),
  });
  const feed = useQuery({
    queryKey: keys.activity(filters),
    queryFn: () =>
      call(
        api.GET("/dashboard/activity", {
          params: {
            query: {
              ...(filters.usecase !== "" ? { usecase_id: filters.usecase } : {}),
              ...(filters.terminal.trim() !== "" ? { terminal_id: filters.terminal.trim() } : {}),
              ...(filters.actor !== "" ? { actor_type: filters.actor } : {}),
              ...(filters.step !== "" ? { step: filters.step } : {}),
            },
          },
        }),
      ),
    refetchInterval: refresh * 1000,
    refetchIntervalInBackground: false,
    placeholderData: (previous) => previous,
  });

  function set(key: keyof typeof filters, value: string) {
    const next = new URLSearchParams(params);
    if (value === "") next.delete(key);
    else next.set(key, value);
    setParams(next, { replace: true });
  }

  return (
    <>
      <PageHeader
        title="Activity"
        caption="What agents, reviewers, people and the orchestrator did, newest first."
      />
      <div className="card filters">
        <div>
          <label htmlFor="activity-usecase">Use case</label>
          <select
            id="activity-usecase"
            value={filters.usecase}
            onChange={(e) => {
              set("usecase", e.target.value);
            }}
          >
            <option value="">Any</option>
            {(usecases.data ?? []).map((u) => (
              <option key={u.usecase_id} value={u.usecase_id}>
                {u.usecase_id}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label htmlFor="activity-terminal">Terminal</label>
          <input
            id="activity-terminal"
            placeholder="Any terminal"
            value={filters.terminal}
            onChange={(e) => {
              set("terminal", e.target.value);
            }}
          />
        </div>
        <div>
          <label htmlFor="activity-actor">Actor</label>
          <select
            id="activity-actor"
            value={filters.actor}
            onChange={(e) => {
              set("actor", e.target.value);
            }}
          >
            <option value="">Any</option>
            {ACTORS.map((a) => (
              <option key={a} value={a}>
                {words(a)}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label htmlFor="activity-step">Step</label>
          <select
            id="activity-step"
            value={filters.step}
            onChange={(e) => {
              set("step", e.target.value);
            }}
          >
            <option value="">Any</option>
            {STEPS.map((s) => (
              <option key={s} value={s}>
                {words(s)}
              </option>
            ))}
          </select>
        </div>
      </div>
      <ErrorMessage error={feed.error} />
      {feed.data !== undefined &&
        (feed.data.length === 0 ? (
          <p className="empty">No activity matches these filters.</p>
        ) : (
          <>
            <p className="caption">{feed.data.length} action(s)</p>
            <DataTable rows={feed.data} />
          </>
        ))}
    </>
  );
}
