// A waiver (T053; D-5): an exception was proposed for a failed control; its approver approves
// or rejects it. The proposal's values were typed by a person: literal text.
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { api, call } from "../../api/client";
import { keys } from "../../api/queries";
import { ErrorMessage } from "../../ui/error-message";
import { label } from "../../ui/format";
import { Literal } from "../../ui/literal";
import type { RunDetail } from "../run/types";
import { RequestFrame } from "./request-frame";

const SHOWN = [
  "waiver_id",
  "status",
  "proposed_by",
  "waiver_owner",
  "compensating_control",
  "expiry",
];
const NOT_REQUIREMENTS = new Set(["waiver_id", "status", "proposed_by"]);

function Waiver({ detail, id }: { detail: RunDetail; id: string }) {
  const queryClient = useQueryClient();
  const [decision, setDecision] = useState<"approve" | "reject">("approve");
  const [comment, setComment] = useState("");
  const [done, setDone] = useState(false);
  const record = useMutation({
    mutationFn: () =>
      call(
        api.POST("/waivers/{waiver_id}/decision", {
          params: { path: { waiver_id: id } },
          body: { approve: decision === "approve", comment: comment === "" ? null : comment },
        }),
      ),
    onSuccess: () => {
      setDone(true);
      void queryClient.invalidateQueries({ queryKey: keys.inbox });
    },
  });
  const waiver = detail.waiver;
  if (done) return <p className="message success">Waiver decision recorded</p>;
  if (waiver === null || waiver["waiver_id"] !== id) {
    return <p className="empty">This waiver is no longer pending.</p>;
  }
  const requires = (waiver["requires"] ?? {}) as Record<string, unknown>;
  const more = Object.entries(requires)
    .filter(([name]) => waiver[name] === undefined || waiver[name] === null)
    .filter(([name]) => !NOT_REQUIREMENTS.has(name))
    .sort(([a], [b]) => a.localeCompare(b));
  return (
    <>
      <div className="card fields">
        {[...SHOWN.map((name) => [name, waiver[name]] as const), ...more].map(([name, value]) => (
          <div key={name}>
            <span className="caption">{label(name)}</span>
            <Literal as="div" value={value} />
          </div>
        ))}
      </div>
      <div className="card">
        <fieldset>
          <legend>Decision</legend>
          {(["approve", "reject"] as const).map((d) => (
            <label key={d} className="inline">
              <input
                type="radio"
                name="waiver-decision"
                value={d}
                checked={decision === d}
                onChange={() => {
                  setDecision(d);
                }}
              />{" "}
              {d}
            </label>
          ))}
        </fieldset>
        <label htmlFor="waiver-comment">Comment</label>
        <textarea
          id="waiver-comment"
          value={comment}
          onChange={(e) => {
            setComment(e.target.value);
          }}
        />
        <p>
          <button
            type="button"
            className="primary"
            disabled={record.isPending}
            onClick={() => {
              record.mutate();
            }}
          >
            Record waiver decision
          </button>
        </p>
      </div>
      <ErrorMessage error={record.error} />
    </>
  );
}

export function WaiverPage() {
  return (
    <RequestFrame
      title="Waiver"
      caption="An exception was proposed for a failed control. Approve it or reject it."
      openFrom="Open a waiver from your inbox."
      needs={["id"]}
    >
      {(detail, params) => <Waiver detail={detail} id={params.get("id") ?? ""} />}
    </RequestFrame>
  );
}
