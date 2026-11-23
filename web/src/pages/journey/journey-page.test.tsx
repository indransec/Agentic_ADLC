// T057 (P-22, P-23, N-05): the Journey page: use case card, KPI strip ("no data" where undefined),
// the chart, the panel; refreshes every configured interval and keeps the chosen use case.
import { act, screen, waitFor } from "@testing-library/react";
import { http } from "msw";
import { afterEach, describe, expect, it, vi } from "vitest";

import { fixtures } from "../../test/fixtures";
import { apiUrl, json, signedIn } from "../../test/msw-handlers";
import { server } from "../../test/msw-server";
import { renderWithApp } from "../../test/render";
import { JourneyPage } from "./journey-page";

vi.mock("../../ui/plot", async (original) => ({
  ...(await original<typeof import("../../ui/plot")>()),
  Plot: (await import("../../test/plot-mock")).MockPlot,
}));

afterEach(() => {
  vi.useRealTimers();
});

const usecases = [
  { ...fixtures.usecases[0], usecase_id: "UC-0001" },
  { ...fixtures.usecases[0], usecase_id: "UC-0002" },
];

function serve() {
  let calls = 0;
  server.use(
    signedIn(),
    http.get(apiUrl("/usecases"), () => json(usecases)),
    http.get(apiUrl("/dashboard/usecases/:id/journey"), ({ params }) => {
      calls += 1;
      return json({
        ...fixtures.journey,
        usecase: { ...fixtures.journey.usecase, usecase_id: params["id"] },
      });
    }),
    http.get(apiUrl("/dashboard/usecases/:id/kpis"), () =>
      json({
        kpis: fixtures.kpis.kpis.map((k, i) =>
          i === 0 ? { ...k, headline: true, value: null } : k,
        ),
      }),
    ),
  );
  return () => calls;
}

describe("Journey page", () => {
  it("draws the chart, the KPI strip and the panel (P-22)", async () => {
    serve();
    renderWithApp(<JourneyPage />, { route: "/journey?usecase=UC-0002" });
    expect(await screen.findByRole("figure", { name: /Journey of UC-0002/ })).toBeInTheDocument();
    expect(screen.getByLabelText("Use case")).toHaveValue("UC-0002");
    expect(screen.getAllByText("no data").length).toBeGreaterThan(0);
    expect(screen.getByRole("heading", { name: "Escalations and exceptions" })).toBeInTheDocument();
    expect(screen.getByText("No escalations or exceptions on this use case.")).toBeInTheDocument();
  });

  it("refreshes on the configured interval, keeping the use case (P-23, N-05)", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const calls = serve();
    renderWithApp(<JourneyPage />, {
      route: "/journey?usecase=UC-0002",
      config: { env: null, dashboard_refresh_seconds: 7 },
    });
    await screen.findByRole("figure", { name: /Journey of UC-0002/ });
    const before = calls();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(7_100);
    });
    await waitFor(() => {
      expect(calls()).toBeGreaterThan(before);
    });
    expect(screen.getByLabelText("Use case")).toHaveValue("UC-0002");
  });
});
