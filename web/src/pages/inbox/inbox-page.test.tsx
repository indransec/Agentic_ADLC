// T049 (P-04, P-08, P-20, P-21, N-05): the Inbox groups items by kind, marks controls being re-run,
// opens each item on its page, decides change requests and proposed events, and refreshes every
// 30 s and on demand without touching what the person is typing.
import { act, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http } from "msw";
import { afterEach, describe, expect, it, vi } from "vitest";

import { fixtures, HOSTILE } from "../../test/fixtures";
import { apiUrl, json, signedIn } from "../../test/msw-handlers";
import { server } from "../../test/msw-server";
import { renderWithApp } from "../../test/render";
import { INBOX_REFRESH_MS, InboxPage } from "./inbox-page";

const [signOff] = fixtures.inbox;
const item = (kind: string, id: string, extra: Record<string, unknown> = {}) => ({
  ...signOff,
  kind,
  id,
  title: `${kind} ${id}`,
  ...extra,
});

afterEach(() => {
  vi.useRealTimers();
});

describe("Inbox", () => {
  it("groups by kind, counts, and marks controls being re-run (P-08)", async () => {
    server.use(
      signedIn(),
      http.get(apiUrl("/inbox"), () =>
        json([
          item("sign_off", "UC-0001/T1/run-1", { controls_pending: true }),
          item("clarification", "UC-0002/T2/run-1/clar-1"),
          item("sign_off", "UC-0003/T1/run-1"),
        ]),
      ),
    );
    renderWithApp(<InboxPage />, { route: "/inbox" });
    expect(await screen.findByRole("heading", { name: "Sign-offs" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Clarifications" })).toBeInTheDocument();
    const signOffs = screen.getByRole("region", { name: "Sign-offs" });
    expect(within(signOffs).getAllByRole("row")).toHaveLength(3);
    expect(within(signOffs).getByText("controls being re-run")).toBeInTheDocument();
  });

  it.each([
    ["sign_off", "UC-0001/T1/run-1", "/run?run=UC-0001%2FT1%2Frun-1"],
    ["blocked", "UC-0001/T1/run-1", "/run?run=UC-0001%2FT1%2Frun-1"],
    ["escalation", "UC-0001/T1/run-1", "/escalation?run=UC-0001%2FT1%2Frun-1"],
    [
      "clarification",
      "UC-0001/T1/run-1/clar-1",
      "/clarification?run=UC-0001%2FT1%2Frun-1&id=UC-0001%2FT1%2Frun-1%2Fclar-1",
    ],
    ["waiver", "WVR-0001", "/waiver?run=UC-0001%2FT1%2Frun-1&id=WVR-0001"],
  ])("opens a %s on its page (P-04)", async (kind, id, path) => {
    server.use(
      signedIn(),
      http.get(apiUrl("/inbox"), () => json([item(kind, id)])),
    );
    renderWithApp(<InboxPage />, { route: "/inbox" });
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: `Open ${kind} ${id}` }));
    await waitFor(() => {
      expect(screen.getByTestId("where")).toHaveTextContent(path);
    });
  });

  it("says when nothing is waiting", async () => {
    server.use(signedIn());
    renderWithApp(<InboxPage />, { route: "/inbox" });
    expect(await screen.findByText("Nothing is waiting for you.")).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Change requests" })).toBeNull(); // P-21
  });

  it("an approver decides a change request (P-20)", async () => {
    let changes = fixtures.changes;
    const seen: { body?: unknown } = {};
    server.use(
      signedIn(),
      http.get(apiUrl("/changes"), () => json(changes)),
      http.post(apiUrl("/changes/CHG-1/decision"), async ({ request }) => {
        seen.body = await request.json();
        changes = [];
        return json({ ...fixtures.changes[0], state: "approved" });
      }),
    );
    renderWithApp(<InboxPage />, { route: "/inbox" });
    const section = await screen.findByRole("region", { name: "Change requests" });
    const user = userEvent.setup();
    await user.type(within(section).getByLabelText("Comment"), "window agreed");
    await user.click(within(section).getByRole("button", { name: "Record decision" }));
    expect(await within(section).findByText("CHG-1 approved")).toBeInTheDocument();
    expect(seen.body).toEqual({ approve: true, comment: "window agreed" });
  });

  it("decides a proposed event; agent-written values stay out of labels", async () => {
    const [proposal] = fixtures.proposedEvents;
    let proposals = [{ ...proposal, event_id: HOSTILE[0] }];
    let decidedPath = "";
    server.use(
      signedIn(),
      http.get(apiUrl("/events/proposed"), () => json(proposals)),
      http.post(apiUrl("/events/proposed/:usecase/:terminal/:run/:event"), ({ request }) => {
        decidedPath = new URL(request.url).pathname;
        proposals = [];
        return json({
          event_id: HOSTILE[0],
          event_type: "drift",
          confirmed: false,
          by: "x",
          comment: "",
        });
      }),
    );
    const { container } = renderWithApp(<InboxPage />, { route: "/inbox" });
    const section = await screen.findByRole("region", { name: "Proposed events" });
    expect(within(section).getAllByText(HOSTILE[0]).length).toBeGreaterThan(0);
    for (const option of within(section).getAllByRole("option")) {
      expect(option.textContent).not.toContain("<script>");
    }
    expect(container.querySelector("script, b")).toBeNull();
    const user = userEvent.setup();
    await user.click(within(section).getByRole("radio", { name: "dismiss" }));
    await user.click(within(section).getByRole("button", { name: "Record event decision" }));
    expect(await within(section).findByText("Event dismissed")).toBeInTheDocument();
    expect(decidedPath).toBe(
      `/api/events/proposed/UC-0001/T8/run-1/${encodeURIComponent(HOSTILE[0])}`,
    );
  });

  it("refreshes every 30 s and on demand, keeping what is typed (N-05)", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    let calls = 0;
    server.use(
      signedIn(),
      http.get(apiUrl("/inbox"), () => {
        calls += 1;
        return json([item("sign_off", `UC-000${String(calls)}/T1/run-1`)]);
      }),
      http.get(apiUrl("/changes"), () => json(fixtures.changes)),
    );
    renderWithApp(<InboxPage />, { route: "/inbox" });
    const section = await screen.findByRole("region", { name: "Change requests" });
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    await user.type(within(section).getByLabelText("Comment"), "half typed");
    const before = calls;
    await act(async () => {
      await vi.advanceTimersByTimeAsync(INBOX_REFRESH_MS + 100);
    });
    await waitFor(() => {
      expect(calls).toBeGreaterThan(before);
    });
    await user.click(screen.getByRole("button", { name: "Refresh" }));
    await waitFor(() => {
      expect(calls).toBeGreaterThan(before + 1);
    });
    expect(within(section).getByLabelText("Comment")).toHaveValue("half typed");
  });
});
