// T058 (P-24): the activity feed, filtered by use case, terminal, actor and step; the filters are
// in the address and survive a refresh.
import { act, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http } from "msw";
import { afterEach, describe, expect, it, vi } from "vitest";

import { fixtures } from "../../test/fixtures";
import { apiUrl, json, signedIn } from "../../test/msw-handlers";
import { server } from "../../test/msw-server";
import { renderWithApp } from "../../test/render";
import { ActivityPage } from "./activity-page";

afterEach(() => {
  vi.useRealTimers();
});

describe("Activity page", () => {
  it("filters by actor; the filter is in the address and survives a refresh (P-24)", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const queries: string[] = [];
    server.use(
      signedIn(),
      http.get(apiUrl("/usecases"), () => json(fixtures.usecases)),
      http.get(apiUrl("/dashboard/activity"), ({ request }) => {
        const query = new URL(request.url).searchParams;
        queries.push(query.toString());
        const actor = query.get("actor_type");
        return json(
          actor === null
            ? fixtures.activity
            : fixtures.activity.filter((a) => a.actor_type === actor),
        );
      }),
    );
    renderWithApp(<ActivityPage />, {
      route: "/activity",
      config: { env: null, dashboard_refresh_seconds: 5 },
    });
    expect(
      await screen.findByText(`${String(fixtures.activity.length)} action(s)`),
    ).toBeInTheDocument();
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    await user.selectOptions(screen.getByLabelText("Actor"), "human");
    await waitFor(() => {
      expect(screen.getByTestId("where")).toHaveTextContent("/activity?actor=human");
    });
    const before = queries.length;
    await act(async () => {
      await vi.advanceTimersByTimeAsync(5_100);
    });
    await waitFor(() => {
      expect(queries.length).toBeGreaterThan(before);
    });
    expect(queries.at(-1)).toBe("actor_type=human");
    expect(screen.getByLabelText("Actor")).toHaveValue("human");
  });

  it("says when nothing matches", async () => {
    server.use(
      signedIn(),
      http.get(apiUrl("/usecases"), () => json(fixtures.usecases)),
      http.get(apiUrl("/dashboard/activity"), () => json([])),
    );
    renderWithApp(<ActivityPage />, { route: "/activity?step=waiver" });
    expect(await screen.findByText("No activity matches these filters.")).toBeInTheDocument();
    expect(screen.getByLabelText("Step")).toHaveValue("waiver");
  });
});
