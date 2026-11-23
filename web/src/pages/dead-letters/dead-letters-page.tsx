// Dead letters (T064; SA 8.1, 013 US5): events the platform could not deliver after its retries,
// with the payload and re-queue history on request, and re-queue. Who may see them is the
// platform's answer (403 for anyone else), never a role named here. The event is in the address.
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useSearchParams } from "react-router";

import { api, call } from "../../api/client";
import { isApiError } from "../../api/errors";
import { keys } from "../../api/queries";
import { DataTable } from "../../ui/data-table";
import { ErrorMessage } from "../../ui/error-message";
import { Literal } from "../../ui/literal";
import { PageHeader } from "../../ui/page-header";

function Detail({ eventId }: { eventId: string }) {
  const found = useQuery({
    queryKey: keys.deadLetter(eventId),
    queryFn: () =>
      call(api.GET("/dead-letters/{event_id}", { params: { path: { event_id: eventId } } })),
  });
  if (found.error !== null) return <ErrorMessage error={found.error} />;
  if (found.data === undefined) return <p className="caption">Loading…</p>;
  return (
    <>
      <h3>Payload</h3>
      <pre className="json">
        <Literal value={JSON.stringify(found.data.payload ?? {}, null, 2)} />
      </pre>
      <h3>Re-queue history</h3>
      <DataTable rows={found.data.history} emptyText="Never re-queued." />
    </>
  );
}

export function DeadLettersPage() {
  const queryClient = useQueryClient();
  const [params, setParams] = useSearchParams();
  const [shown, setShown] = useState<string | null>(null);
  const [done, setDone] = useState(false);
  const found = useQuery({
    queryKey: keys.deadLetters,
    queryFn: () => call(api.GET("/dead-letters")),
  });
  const ids = (found.data ?? []).map((d) => d.event_id);
  const wanted = params.get("event");
  const pick = wanted !== null && ids.includes(wanted) ? wanted : ids[0];
  const requeue = useMutation({
    mutationFn: (eventId: string) =>
      call(
        api.POST("/dead-letters/{event_id}/requeue", { params: { path: { event_id: eventId } } }),
      ),
    onSuccess: () => {
      setDone(true);
      setShown(null);
      void queryClient.invalidateQueries({ queryKey: keys.deadLetters });
      void queryClient.invalidateQueries({ queryKey: keys.inbox });
    },
  });

  const header = (
    <PageHeader
      title="Dead letters"
      caption="Events the platform could not deliver after its retries. Inspect them, then re-queue."
    />
  );
  if (isApiError(found.error) && found.error.kind === "not_allowed") {
    return (
      <>
        {header}
        <p className="message notice">Dead letters are handled by the CoE role.</p>
      </>
    );
  }
  return (
    <>
      {header}
      <ErrorMessage error={found.error} />
      {done && <p className="message success">Re-queued</p>}
      {found.data !== undefined && (
        <DataTable rows={found.data} emptyText="No dead letters: every event was delivered." />
      )}
      {pick !== undefined && (
        <div className="card">
          <label htmlFor="dead-pick">Event</label>
          <select
            id="dead-pick"
            value={pick}
            onChange={(e) => {
              setParams({ event: e.target.value }, { replace: true });
              setShown(null);
            }}
          >
            {ids.map((id) => (
              <option key={id} value={id}>
                {id}
              </option>
            ))}
          </select>
          <p>
            <button
              type="button"
              aria-expanded={shown === pick}
              onClick={() => {
                setShown(shown === pick ? null : pick);
              }}
            >
              Show payload and history
            </button>{" "}
            <button
              type="button"
              className="primary"
              disabled={requeue.isPending}
              onClick={() => {
                setDone(false);
                requeue.mutate(pick);
              }}
            >
              Re-queue
            </button>
          </p>
          {shown === pick && <Detail eventId={pick} />}
          <ErrorMessage error={requeue.error} />
        </div>
      )}
    </>
  );
}
