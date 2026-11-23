// T056 (P-19): use cases ("only mine" in the address), one use case's runs, opening a run or the
// journey view, and ledger verification.
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http } from "msw";
import { describe, expect, it } from "vitest";

import type { components } from "../../api/schema";
import { fixtures, HOSTILE } from "../../test/fixtures";
import { apiUrl, json, signedIn } from "../../test/msw-handlers";
import { server } from "../../test/msw-server";
import { renderWithApp } from "../../test/render";
import { UseCasesPage } from "./use-cases-page";

function serve(verification: components["schemas"]["Verification"] = fixtures.verification) {
  const mine: string[] = [];
  server.use(
    signedIn(),
    http.get(apiUrl("/usecases"), ({ request }) => {
      mine.push(new URL(request.url).searchParams.get("mine") ?? "");
      return json(fixtures.usecases);
    }),
    http.get(apiUrl("/usecases/UC-0001"), () =>
      json({
        ...fixtures.usecaseJourney,
        usecase: { ...fixtures.usecaseJourney.usecase, intake_text: HOSTILE[0] },
      }),
    ),
    http.post(apiUrl("/usecases/UC-0001/verify"), () => json(verification)),
  );
  return mine;
}

describe("Use cases page", () => {
  it("lists only mine by default, and all when asked (kept in the address)", async () => {
    const mine = serve();
    renderWithApp(<UseCasesPage />, { route: "/usecases" });
    const toggle = await screen.findByRole("checkbox", { name: "Only mine" });
    expect(toggle).toBeChecked();
    const user = userEvent.setup();
    await user.click(toggle);
    await waitFor(() => {
      expect(screen.getByTestId("where")).toHaveTextContent("/usecases?mine=0");
    });
    await waitFor(() => {
      expect(mine).toEqual(["true", "false"]);
    });
  });

  it("shows the use case's runs; the description is literal text", async () => {
    serve();
    const { container } = renderWithApp(<UseCasesPage />, { route: "/usecases?usecase=UC-0001" });
    expect(await screen.findByRole("cell", { name: "UC-0001/T1/run-1" })).toBeInTheDocument();
    expect(screen.getByText(HOSTILE[0])).toBeInTheDocument();
    expect(container.querySelector("script, b")).toBeNull();
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "Open UC-0001/T1/run-1" }));
    await waitFor(() => {
      expect(screen.getByTestId("where")).toHaveTextContent("/run?run=UC-0001%2FT1%2Frun-1");
    });
  });

  it("opens the journey view for the use case", async () => {
    serve();
    renderWithApp(<UseCasesPage />, { route: "/usecases" });
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "Open the journey view" }));
    await waitFor(() => {
      expect(screen.getByTestId("where")).toHaveTextContent("/journey?usecase=UC-0001");
    });
  });

  it("verifies the ledger (P-19)", async () => {
    serve({ ...fixtures.verification, records_checked: 7 });
    renderWithApp(<UseCasesPage />, { route: "/usecases" });
    const user = userEvent.setup();
    await user.click(
      await screen.findByRole("button", { name: "Verify the ledger for this use case" }),
    );
    expect(await screen.findByText("Verified: 7 records, no breaks")).toBeInTheDocument();
  });

  it("reports breaks", async () => {
    serve({
      ...fixtures.verification,
      verified: false,
      breaks: [{ record: 3, reason: "hash mismatch" }],
    });
    renderWithApp(<UseCasesPage />, { route: "/usecases" });
    const user = userEvent.setup();
    await user.click(
      await screen.findByRole("button", { name: "Verify the ledger for this use case" }),
    );
    expect(await screen.findByText("1 break(s) found")).toBeInTheDocument();
    expect(screen.getByText("hash mismatch")).toBeInTheDocument();
  });
});
