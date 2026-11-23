// T058 (P-25): portfolio KPIs by risk tier and status; time per terminal.
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http } from "msw";
import { describe, expect, it, vi } from "vitest";

import { fixtures } from "../../test/fixtures";
import { apiUrl, json, signedIn } from "../../test/msw-handlers";
import { server } from "../../test/msw-server";
import { renderWithApp } from "../../test/render";
import { buildSplitFigure } from "./build-split";
import { PortfolioPage } from "./portfolio-page";

vi.mock("../../ui/plot", async (original) => ({
  ...(await original<typeof import("../../ui/plot")>()),
  Plot: (await import("../../test/plot-mock")).MockPlot,
}));

describe("Portfolio page", () => {
  it("shows the KPIs and filters by risk tier (in the address)", async () => {
    const seen: string[] = [];
    server.use(
      signedIn(),
      http.get(apiUrl("/dashboard/portfolio"), ({ request }) => {
        const tier = new URL(request.url).searchParams.get("risk_tier");
        seen.push(tier ?? "");
        return json({ ...fixtures.portfolio, usecases: tier === "low" ? 1 : 2 });
      }),
    );
    renderWithApp(<PortfolioPage />, { route: "/portfolio" });
    expect(await screen.findByText("2 use case(s)")).toBeInTheDocument();
    expect(screen.getAllByText("First-pass yield").length).toBeGreaterThan(0);
    expect(screen.getByRole("img", { name: /Time per terminal/ })).toBeInTheDocument();
    const user = userEvent.setup();
    await user.selectOptions(screen.getByLabelText("Risk tier"), "low");
    expect(await screen.findByText("1 use case(s)")).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getByTestId("where")).toHaveTextContent("/portfolio?tier=low");
    });
    expect(seen).toEqual(["", "low"]);
  });

  it("stacks time per terminal by category, in hours", () => {
    const figure = buildSplitFigure({ T0: { agent: 3600, people: 7200 }, T1: { agent: 1800 } });
    expect(figure.data.map((d) => d.name)).toEqual(["Agent", "People"]);
    expect(figure.data[1]).toMatchObject({ x: ["T0", "T1"], y: [2, 0] });
  });
});
