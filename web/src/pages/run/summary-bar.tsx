// The run at a glance (T038): which run, its state, when it is due and what it has cost.
import { money, when } from "../../ui/format";
import { Literal } from "../../ui/literal";
import { StatusBadge } from "../../ui/status-badge";
import type { RunDetail } from "./types";

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="field">
      <span className="caption">{label}</span>
      <div>{children}</div>
    </div>
  );
}

export function SummaryBar({ detail }: { detail: RunDetail }) {
  const { run, timer, spec, cost } = detail;
  return (
    <section className="summary-bar" aria-label="Run summary">
      <Field label="Run">
        <Literal value={run.run_id} />
        <div className="caption">Version {run.version}</div>
      </Field>
      <Field label="Terminal">
        <Literal value={`${run.terminal_id} · spec ${spec.version}`} />
      </Field>
      <Field label="State">
        <StatusBadge value={run.state} />{" "}
        {run.final_status !== null && <StatusBadge value={run.final_status} />}
        {run.controls_pending && <div className="caption">Controls are being re-run</div>}
      </Field>
      <Field label="Due">
        <span>{when(timer.due_at)}</span>{" "}
        {timer.overdue && <span className="badge overdue">Overdue</span>}
      </Field>
      <Field label="Model cost">{money(cost.cost_usd)}</Field>
    </section>
  );
}
