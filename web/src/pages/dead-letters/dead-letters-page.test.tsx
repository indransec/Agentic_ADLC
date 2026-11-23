// T063 (P-18, P-26): dead letters for the CoE; the notice for everyone else (the platform's 403
// decides, not a role name in the page); payload and history on request; re-queue.
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http } from "msw";
import { describe, expect, it } from "vitest";

import { fixtures, HOSTILE } from "../../test/fixtures";
import { apiUrl, json, refusal, signedIn } from "../../test/msw-handlers";
import { server } from "../../test/msw-server";
import { renderWithApp } from "../../test/render";
import { DeadLettersPage } from "./dead-letters-page";

const [dead] = fixtures.deadLetters;
const EVENT = String(dead?.event_id);

describe("Dead letters", () => {
  it("lists them, shows the payload and history on request, and re-queues (P-18, P-26)", async () => {
    let list = fixtures.deadLetters;
    let requeued = 0;
    server.use(
      signedIn(),
      http.get(apiUrl("/dead-letters"), () => json(list)),
      http.get(apiUrl(`/dead-letters/${EVENT}`), () =>
        json({ ...fixtures.deadLetter, payload: { note: HOSTILE[0] } }),
      ),
      http.post(apiUrl(`/dead-letters/${EVENT}/requeue`), () => {
        requeued += 1;
        list = [];
        return new Response(null, { status: 204 });
      }),
    );
    const { container } = renderWithApp(<DeadLettersPage />, { route: "/dead-letters" });
    expect(await screen.findByText("route failed: subscriber unavailable")).toBeInTheDocument();
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "Show payload and history" }));
    expect(await screen.findByText(/"note":/)).toHaveTextContent(HOSTILE[0].replaceAll('"', '\\"'));
    expect(container.querySelector("script, b")).toBeNull();
    expect(screen.getByText("Never re-queued.")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Re-queue" }));
    expect(await screen.findByText("Re-queued")).toBeInTheDocument();
    expect(requeued).toBe(1);
    await waitFor(() => {
      expect(screen.getByText("No dead letters: every event was delivered.")).toBeInTheDocument();
    });
  });

  it("anyone the platform refuses sees the notice and no action", async () => {
    server.use(
      signedIn(),
      http.get(apiUrl("/dead-letters"), () => refusal(403, "not_allowed", "CoE only")),
    );
    renderWithApp(<DeadLettersPage />, { route: "/dead-letters" });
    expect(
      await screen.findByText("Dead letters are handled by the CoE role."),
    ).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Re-queue" })).toBeNull();
  });

  it("keeps the chosen event in the address", async () => {
    server.use(
      signedIn(),
      http.get(apiUrl("/dead-letters"), () => json(fixtures.deadLetters)),
    );
    renderWithApp(<DeadLettersPage />, { route: `/dead-letters?event=${EVENT}` });
    expect(await screen.findByLabelText("Event")).toHaveValue(EVENT);
  });
});
