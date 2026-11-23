// The Inbox (T052; FR-004, 007 FR-006): everything waiting for the person, oldest first,
// grouped by kind, refreshed every 30 s and on demand; change requests and proposed events
// with their decisions. Refreshing never touches what the person is typing.
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { api, call } from "../../api/client";
import { keys } from "../../api/queries";
import type { components } from "../../api/schema";
import { useOpenPage } from "../../nav/navigate";
import { DataTable } from "../../ui/data-table";
import { ErrorMessage } from "../../ui/error-message";
import { parseTime, when } from "../../ui/format";
import { Literal } from "../../ui/literal";
import { PageHeader } from "../../ui/page-header";

export const INBOX_REFRESH_MS = 30_000;

type Item = components["schemas"]["InboxItem"];
type Change = components["schemas"]["ChangeRequest"];
type Proposal = components["schemas"]["ProposedEvent"];

const KIND_TITLES: Record<string, string> = {
  sign_off: "Sign-offs",
  clarification: "Clarifications",
  escalation: "Escalations",
  waiver: "Waivers",
  blocked: "Blocked runs",
  dead_letter: "Dead letters",
};

export const kindTitle = (kind: string): string =>
  KIND_TITLES[kind] ?? `${kind.slice(0, 1).toUpperCase()}${kind.slice(1).replaceAll("_", " ")}`;

const poll = { refetchInterval: INBOX_REFRESH_MS, refetchIntervalInBackground: false } as const;

function Items({ found, now }: { found: Item[]; now: Date }) {
  const open = useOpenPage();
  if (found.length === 0) {
    return <p className="card empty">Nothing is waiting for you.</p>;
  }
  const kinds = [...new Set(found.map((i) => i.kind))];
  const overdue = (i: Item) => {
    const due = parseTime(i.due_at);
    return due !== null && due < now;
  };
  function openItem(item: Item) {
    const run = item.run_id ?? undefined;
    if (item.kind === "clarification") open("clarification", { run, id: item.id });
    else if (item.kind === "waiver") open("waiver", { run, id: item.id });
    else if (item.kind === "escalation") open("escalation", { run });
    else if (item.kind === "dead_letter") open("dead-letters", { event: item.id });
    else open("run", { run });
  }
  return (
    <>
      <div className="metrics">
        <div className="metric card">
          <span className="caption">Waiting</span>
          <strong>{found.length}</strong>
        </div>
        {kinds.map((kind) => {
          const mine = found.filter((i) => i.kind === kind);
          const late = mine.filter(overdue).length;
          return (
            <div key={kind} className="metric card">
              <span className="caption">{kindTitle(kind)}</span>
              <strong>{mine.length}</strong>
              {late > 0 && <span className="badge overdue">{late} overdue</span>}
            </div>
          );
        })}
      </div>
      {kinds.map((kind) => (
        <section key={kind} aria-labelledby={`kind-${kind}`}>
          <h2 id={`kind-${kind}`}>{kindTitle(kind)}</h2>
          <div className="table-wrap">
            <table className="data-table">
              <thead>
                <tr>
                  {[
                    "Title",
                    "Use case",
                    "Terminal",
                    "As role",
                    "Arrived",
                    "Due",
                    "",
                    "Note",
                    "",
                  ].map((h, i) => (
                    <th key={i} scope="col">
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {found
                  .filter((i) => i.kind === kind)
                  .map((item) => (
                    <tr key={`${item.kind}:${item.id}`}>
                      <td>{item.title}</td>
                      <td>{item.usecase_id ?? "—"}</td>
                      <td>{item.terminal_id ?? "—"}</td>
                      <td>{(item.role ?? "").replaceAll("_", " ")}</td>
                      <td>{when(item.arrived_at)}</td>
                      <td>{when(item.due_at)}</td>
                      <td>{overdue(item) && <span className="badge overdue">Overdue</span>}</td>
                      <td>{item.controls_pending ? "controls being re-run" : ""}</td>
                      <td>
                        <button
                          type="button"
                          onClick={() => {
                            openItem(item);
                          }}
                        >
                          Open <span className="visually-hidden">{item.title}</span>
                        </button>
                      </td>
                    </tr>
                  ))}
              </tbody>
            </table>
          </div>
        </section>
      ))}
    </>
  );
}

function Changes({ found }: { found: Change[] }) {
  const queryClient = useQueryClient();
  const [pick, setPick] = useState(found[0]?.change_id ?? "");
  const [decision, setDecision] = useState<"approve" | "reject">("approve");
  const [comment, setComment] = useState("");
  const [done, setDone] = useState<string | null>(null);
  const chosen = found.find((c) => c.change_id === pick) ?? found[0];
  const record = useMutation({
    mutationFn: (changeId: string) =>
      call(
        api.POST("/changes/{change_id}/decision", {
          params: { path: { change_id: changeId } },
          body: { approve: decision === "approve", comment },
        }),
      ),
    onSuccess: (answer) => {
      setDone(`${answer.change_id} ${decision === "approve" ? "approved" : "rejected"}`);
      setComment("");
      void queryClient.invalidateQueries({ queryKey: keys.changes });
    },
  });
  if (found.length === 0 && done === null) return null;
  return (
    <section aria-labelledby="changes-heading">
      <h2 id="changes-heading">Change requests</h2>
      <DataTable
        rows={found.map((c) => ({
          change: c.change_id,
          "use case": c.usecase_id,
          summary: c["summary"],
          window: `${when(c["window_start"])} to ${when(c["window_end"])}`,
          risk: c["risk"],
        }))}
        emptyText="No change requests are waiting."
      />
      {chosen !== undefined && (
        <div className="card">
          <label htmlFor="change-pick">Change</label>
          <select
            id="change-pick"
            value={chosen.change_id}
            onChange={(e) => {
              setPick(e.target.value);
            }}
          >
            {found.map((c) => (
              <option key={c.change_id} value={c.change_id}>
                {c.change_id}
              </option>
            ))}
          </select>
          {chosen["plan"] !== undefined && chosen["plan"] !== "" && (
            <>
              <p className="caption">Plan</p>
              <Literal as="p" value={chosen["plan"]} />
            </>
          )}
          <fieldset>
            <legend>Decision</legend>
            {(["approve", "reject"] as const).map((d) => (
              <label key={d} className="inline">
                <input
                  type="radio"
                  name="change-decision"
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
          <label htmlFor="change-comment">Comment</label>
          <textarea
            id="change-comment"
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
                setDone(null);
                record.mutate(chosen.change_id);
              }}
            >
              Record decision
            </button>
          </p>
        </div>
      )}
      {done !== null && <p className="message success">{done}</p>}
      <ErrorMessage error={record.error} />
    </section>
  );
}

function Proposals({ found }: { found: Proposal[] }) {
  const queryClient = useQueryClient();
  const [pick, setPick] = useState(0);
  const [decision, setDecision] = useState<"confirm" | "dismiss">("confirm");
  const [comment, setComment] = useState("");
  const [done, setDone] = useState<string | null>(null);
  const chosen = found[Math.min(pick, found.length - 1)];
  const record = useMutation({
    mutationFn: (proposal: Proposal) => {
      const [usecase = "", terminal = "", run = ""] = proposal.run_id.split("/");
      return call(
        api.POST("/events/proposed/{usecase_id}/{terminal_id}/{run_number}/{event_id}", {
          params: {
            path: {
              usecase_id: usecase,
              terminal_id: terminal,
              run_number: run,
              event_id: String(proposal.event_id),
            },
          },
          body: { confirm: decision === "confirm", comment },
        }),
      );
    },
    onSuccess: () => {
      setDone(decision === "confirm" ? "Event confirmed" : "Event dismissed");
      setComment("");
      setPick(0);
      void queryClient.invalidateQueries({ queryKey: keys.proposedEvents });
    },
  });
  if (found.length === 0 && done === null) return null;
  return (
    <section aria-labelledby="events-heading">
      <h2 id="events-heading">Proposed events</h2>
      <DataTable
        rows={found.map((e) => ({
          event: e.event_id,
          type: e.event_type,
          "use case": e.usecase_id,
          run: e.run_id,
          "routed to": e.routed_to ?? "",
        }))}
        emptyText="No proposed events are waiting."
      />
      {chosen !== undefined && (
        <div className="card">
          <label htmlFor="event-pick">Event</label>
          <select
            id="event-pick"
            value={String(pick)}
            onChange={(e) => {
              setPick(Number(e.target.value));
            }}
          >
            {/* Platform words only: the event's own id and type were written by an agent. */}
            {found.map((e, index) => (
              <option key={`${e.run_id}:${String(index)}`} value={String(index)}>
                {`Proposal ${String(index + 1)} · ${e.run_id}`}
              </option>
            ))}
          </select>
          <p>
            <span className="caption">Event </span>
            <Literal value={chosen.event_id} /> <span className="caption"> type </span>
            <Literal value={chosen.event_type} />
          </p>
          <fieldset>
            <legend>Decision</legend>
            {(["confirm", "dismiss"] as const).map((d) => (
              <label key={d} className="inline">
                <input
                  type="radio"
                  name="event-decision"
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
          <label htmlFor="event-comment">Comment</label>
          <textarea
            id="event-comment"
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
                setDone(null);
                record.mutate(chosen);
              }}
            >
              Record event decision
            </button>
          </p>
        </div>
      )}
      {done !== null && <p className="message success">{done}</p>}
      <ErrorMessage error={record.error} />
    </section>
  );
}

export function InboxPage() {
  const inbox = useQuery({
    queryKey: keys.inbox,
    queryFn: () => call(api.GET("/inbox")),
    ...poll,
  });
  const changes = useQuery({
    queryKey: keys.changes,
    queryFn: () => call(api.GET("/changes")),
    ...poll,
  });
  const proposals = useQuery({
    queryKey: keys.proposedEvents,
    queryFn: () => call(api.GET("/events/proposed")),
    ...poll,
  });
  const updated = inbox.dataUpdatedAt > 0 ? new Date(inbox.dataUpdatedAt) : null;
  return (
    <>
      <div className="title-row">
        <PageHeader title="Inbox" caption="Decisions and requests waiting for you, oldest first." />
        <button
          type="button"
          onClick={() => {
            void inbox.refetch();
            void changes.refetch();
            void proposals.refetch();
          }}
        >
          Refresh
        </button>
      </div>
      {updated !== null && (
        <p className="caption">Updated {updated.toISOString().slice(11, 19)} UTC</p>
      )}
      <ErrorMessage error={inbox.error ?? changes.error ?? proposals.error} />
      {inbox.data !== undefined && <Items found={inbox.data} now={new Date()} />}
      {changes.data !== undefined && <Changes found={changes.data} />}
      {proposals.data !== undefined && <Proposals found={proposals.data} />}
    </>
  );
}
