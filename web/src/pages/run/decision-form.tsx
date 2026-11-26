// The decision (T041; FR-005, FR-006): built only from the run's `form` (outcomes, root causes,
// owning terminals, required and typed fields, alternatives, the reviewer's recommendation), so
// no outcome, terminal or role is named here. The version the person saw goes with the decision;
// a stale answer records nothing and the page reloads the run.
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState, type SyntheticEvent } from "react";

import { api, call } from "../../api/client";
import { isApiError } from "../../api/errors";
import { keys } from "../../api/queries";
import { ErrorMessage } from "../../ui/error-message";
import type { DecisionBody, RunDetail } from "./types";

const words = (name: string) => name.replaceAll("_", " ");

export interface DecisionFormProps {
  detail: RunDetail;
  /** The run changed since the person saw it: nothing was recorded; reload it. */
  onStale: () => void;
  /** The decision was recorded (the page says so; the run reloads with its new version). */
  onRecorded: () => void;
}

export function DecisionForm({ detail, onStale, onRecorded }: DecisionFormProps) {
  const { form, run } = detail;
  const queryClient = useQueryClient();
  const [decision, setDecision] = useState<string>("");
  const [comment, setComment] = useState("");
  const [rootCause, setRootCause] = useState(form.root_causes[0] ?? "");
  const [target, setTarget] = useState(form.target_terminals[0] ?? "");
  const [reason, setReason] = useState("");
  const [alternative, setAlternative] = useState("");
  const [fields, setFields] = useState<Record<string, string>>({});

  const decide = useMutation({
    mutationFn: (body: DecisionBody) =>
      call(
        api.POST("/runs/{run_id}/decisions", { params: { path: { run_id: run.run_id } }, body }),
      ),
    onSuccess: () => {
      onRecorded();
      void queryClient.invalidateQueries({ queryKey: keys.run(run.run_id) });
      void queryClient.invalidateQueries({ queryKey: keys.inbox });
    },
    onError: (error) => {
      if (isApiError(error) && error.kind === "stale") onStale();
    },
  });

  const header = <h2 id="decision-heading">Decision</h2>;
  const notices = (
    <>
      {form.controls_pending && (
        <p className="message notice">
          Controls are being re-run after an edit; deciding is possible once they finish.
        </p>
      )}
      {form.waiver_pending && (
        <p className="message notice">A waiver is pending its approver&apos;s decision.</p>
      )}
    </>
  );
  if (!(form.can_decide || form.can_terminate)) {
    return (
      <section aria-labelledby="decision-heading">
        {header}
        {notices}
        <p className="empty">You have no decision to make on this run.</p>
      </section>
    );
  }

  const outcomes = form.can_decide ? form.outcomes : ["terminate"];
  const recommended = form.reason_required_unless;
  const needsReason =
    recommended !== null && decision !== "" && decision !== recommended && decision !== "terminate";
  const required = form.requires[decision] ?? [];
  const typed = form.typed_fields[decision] ?? [];

  function fieldInput(name: string) {
    return (
      <div key={name}>
        <label htmlFor={`field-${name}`}>{words(name)}</label>
        <input
          id={`field-${name}`}
          value={fields[name] ?? ""}
          onChange={(e) => {
            setFields({ ...fields, [name]: e.target.value });
          }}
        />
      </div>
    );
  }

  function submit(event: SyntheticEvent) {
    event.preventDefault();
    if (decision === "") return;
    const body: DecisionBody = {
      decision: decision as DecisionBody["decision"],
      expected_version: run.version,
      fields: {},
    };
    const sent: Record<string, string> = {};
    for (const name of [...required, ...typed]) sent[name] = fields[name] ?? "";
    if (decision === "pass" && alternative !== "") sent["alternative"] = alternative;
    body.fields = sent;
    if ((decision === "rework" || decision === "terminate") && comment !== "")
      body.comment = comment;
    if (decision === "rework") {
      body.root_cause = rootCause;
      if (form.target_terminal_for.includes(rootCause)) body.target_terminal = target;
    }
    if (needsReason && reason !== "") body.reason = reason;
    decide.mutate(body);
  }

  return (
    <section aria-labelledby="decision-heading">
      {header}
      {notices}
      <form className="card" onSubmit={submit}>
        <fieldset>
          <legend>Outcome</legend>
          {outcomes.map((outcome) => (
            <label key={outcome} className="inline">
              <input
                type="radio"
                name="decision"
                value={outcome}
                checked={decision === outcome}
                onChange={() => {
                  setDecision(outcome);
                }}
              />{" "}
              {outcome}
            </label>
          ))}
        </fieldset>
        {(decision === "rework" || decision === "terminate") && (
          <>
            <label htmlFor="decision-comment">Comment</label>
            <textarea
              id="decision-comment"
              value={comment}
              onChange={(e) => {
                setComment(e.target.value);
              }}
            />
          </>
        )}
        {decision === "rework" && (
          <>
            <label htmlFor="decision-cause">Root cause</label>
            <select
              id="decision-cause"
              value={rootCause}
              onChange={(e) => {
                setRootCause(e.target.value);
              }}
            >
              {form.root_causes.map((cause) => (
                <option key={cause} value={cause}>
                  {cause}
                </option>
              ))}
            </select>
            {form.target_terminal_for.includes(rootCause) && (
              <>
                <label htmlFor="decision-target">Owning terminal</label>
                <select
                  id="decision-target"
                  value={target}
                  onChange={(e) => {
                    setTarget(e.target.value);
                  }}
                >
                  {form.target_terminals.map((terminal) => (
                    <option key={terminal} value={terminal}>
                      {terminal}
                    </option>
                  ))}
                </select>
              </>
            )}
          </>
        )}
        {required.map(fieldInput)}
        {typed.map(fieldInput)}
        {decision === "pass" && form.alternatives.length > 0 && (
          <>
            <label htmlFor="decision-alternative">Alternative route</label>
            <select
              id="decision-alternative"
              value={alternative}
              onChange={(e) => {
                setAlternative(e.target.value);
              }}
            >
              <option value="">None</option>
              {form.alternatives.map((route) => (
                <option key={route} value={route}>
                  {route}
                </option>
              ))}
            </select>
          </>
        )}
        {needsReason && (
          <>
            <p className="caption">The reviewer recommended {recommended}; give your reason.</p>
            <label htmlFor="decision-reason">Reason</label>
            <textarea
              id="decision-reason"
              value={reason}
              onChange={(e) => {
                setReason(e.target.value);
              }}
            />
          </>
        )}
        <p>
          <button type="submit" className="primary" disabled={decision === "" || decide.isPending}>
            Submit decision
          </button>
        </p>
      </form>
      {decide.error !== null && !(isApiError(decide.error) && decide.error.kind === "stale") && (
        <ErrorMessage error={decide.error} />
      )}
    </section>
  );
}
