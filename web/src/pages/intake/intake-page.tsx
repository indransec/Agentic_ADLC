// New use case (T051): the intake form. A refusal about a field is shown beside it (FR-008).
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState, type SyntheticEvent } from "react";
import { useNavigate } from "react-router";

import { api, call } from "../../api/client";
import { pagePath } from "../../nav/navigate";
import { ErrorMessage, fieldError } from "../../ui/error-message";
import { PageHeader } from "../../ui/page-header";

export function IntakePage() {
  const [name, setName] = useState("");
  const [text, setText] = useState("");
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const submit = useMutation({
    mutationFn: () => call(api.POST("/usecases", { body: { name, intake_text: text } })),
    onSuccess: (answer) => {
      void queryClient.invalidateQueries({ queryKey: ["usecases"] });
      void navigate(pagePath("use-cases", { usecase: answer.usecase_id }), {
        state: { submitted: answer.usecase_id },
      });
    },
  });
  const nameError = fieldError(submit.error, "name");
  const textError = fieldError(submit.error, "intake_text");

  function onSubmit(event: SyntheticEvent) {
    event.preventDefault();
    submit.mutate();
  }

  return (
    <>
      <PageHeader
        title="New use case"
        caption="Describe the problem in your own words. The first terminal turns it into a scoped use case and asks you if anything is missing."
      />
      <div className="two-columns">
        <form onSubmit={onSubmit}>
          <label htmlFor="intake-name">Name</label>
          <input
            id="intake-name"
            maxLength={200}
            placeholder="A short name for the use case"
            value={name}
            onChange={(e) => {
              setName(e.target.value);
            }}
            aria-describedby={nameError === undefined ? undefined : "intake-name-error"}
          />
          {nameError !== undefined && (
            <p id="intake-name-error" className="field-error">
              {nameError}
            </p>
          )}
          <label htmlFor="intake-text">
            Describe the problem, the people involved and the outcome you want
          </label>
          <textarea
            id="intake-text"
            maxLength={20_000}
            rows={12}
            value={text}
            onChange={(e) => {
              setText(e.target.value);
            }}
            aria-describedby={textError === undefined ? undefined : "intake-text-error"}
          />
          {textError !== undefined && (
            <p id="intake-text-error" className="field-error">
              {textError}
            </p>
          )}
          <p>
            <button type="submit" className="primary" disabled={submit.isPending}>
              Submit
            </button>
          </p>
          {submit.error !== null && nameError === undefined && textError === undefined && (
            <ErrorMessage error={submit.error} />
          )}
        </form>
        <aside className="card">
          <p className="caption">A good description says</p>
          <ul>
            <li>who has the problem today</li>
            <li>what they do now, and what goes wrong</li>
            <li>the data or systems involved</li>
            <li>what a good outcome looks like</li>
          </ul>
        </aside>
      </div>
    </>
  );
}
