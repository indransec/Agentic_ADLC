// A clarification (T053; D-9): an agent needs facts it could not find; the person answers each
// question and the same run resumes. Questions and answers are literal text.
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { api, call } from "../../api/client";
import { keys } from "../../api/queries";
import { ErrorMessage } from "../../ui/error-message";
import { Literal } from "../../ui/literal";
import type { RunDetail } from "../run/types";
import { RequestFrame } from "./request-frame";

const list = (value: unknown): unknown[] => (Array.isArray(value) ? value : []);

function Clarification({ detail, id }: { detail: RunDetail; id: string }) {
  const queryClient = useQueryClient();
  const found = detail.clarifications.find((c) => c["clarification_id"] === id);
  const questions = list(found?.["questions"]);
  const [answers, setAnswers] = useState<string[]>(() => questions.map(() => ""));
  const [sent, setSent] = useState(false);
  const send = useMutation({
    mutationFn: () =>
      call(
        api.POST("/clarifications/{clarification_id}/answers", {
          params: { path: { clarification_id: id } },
          body: { answers },
        }),
      ),
    onSuccess: () => {
      setSent(true);
      void queryClient.invalidateQueries({ queryKey: keys.inbox });
      void queryClient.invalidateQueries({ queryKey: keys.run(detail.run.run_id) });
    },
  });
  if (found === undefined) {
    return <p className="empty">This clarification is not on the run.</p>;
  }
  const answeredBy = found["answered_by"];
  const answered = answeredBy !== null && answeredBy !== undefined;
  const given = list(found["answers"]);
  return (
    <>
      <div className="card fields">
        <div>
          <span className="caption">Asked by</span>
          <Literal as="div" value={found["asked_by"]} />
        </div>
        <div>
          <span className="caption">Addressed to</span>
          <Literal as="div" value={found["addressed_role"]} />
        </div>
        <div>
          <span className="caption">Already looked in</span>
          <Literal as="div" value={list(found["looked_in"]).map(String).join(", ")} />
        </div>
      </div>
      {questions.map((question, n) => (
        <div key={n} className="card">
          <p className="caption">Question {n + 1}</p>
          <Literal as="p" value={question} />
          {answered ? (
            <>
              <p className="caption">Answer</p>
              <Literal as="p" value={given[n]} />
            </>
          ) : (
            <>
              <label htmlFor={`answer-${String(n)}`}>Answer to question {n + 1}</label>
              <textarea
                id={`answer-${String(n)}`}
                value={answers[n] ?? ""}
                onChange={(e) => {
                  setAnswers(answers.map((a, i) => (i === n ? e.target.value : a)));
                }}
              />
            </>
          )}
        </div>
      ))}
      {answered ? (
        <p>
          <span className="caption">Answered by </span>
          <Literal value={answeredBy} />
        </p>
      ) : (
        !sent && (
          <p>
            <button
              type="button"
              className="primary"
              disabled={send.isPending}
              onClick={() => {
                send.mutate();
              }}
            >
              Send answers
            </button>
          </p>
        )
      )}
      {sent && <p className="message success">Answers sent</p>}
      <ErrorMessage error={send.error} />
    </>
  );
}

export function ClarificationPage() {
  return (
    <RequestFrame
      title="Clarification"
      caption="An agent needs facts it could not find. Your answers go back to the run."
      openFrom="Open a clarification from your inbox."
      needs={["id"]}
    >
      {(detail, params) => <Clarification detail={detail} id={params.get("id") ?? ""} />}
    </RequestFrame>
  );
}
