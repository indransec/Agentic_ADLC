// T048 (P-01, P-03): submit a use case and follow it; a refusal shows its reason beside the field.
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http } from "msw";
import { describe, expect, it } from "vitest";

import { apiUrl, json, refusal, signedIn } from "../../test/msw-handlers";
import { server } from "../../test/msw-server";
import { renderWithApp } from "../../test/render";
import { IntakePage } from "./intake-page";

describe("New use case", () => {
  it("submits a name and description, then opens the use case (P-01)", async () => {
    const seen: { body?: unknown } = {};
    server.use(
      signedIn(),
      http.post(apiUrl("/usecases"), async ({ request }) => {
        seen.body = await request.json();
        return json({ usecase_id: "UC-0007" }, 201);
      }),
    );
    renderWithApp(<IntakePage />, { route: "/usecases/new" });
    const user = userEvent.setup();
    await user.type(await screen.findByLabelText("Name"), "Claims triage");
    await user.type(
      screen.getByLabelText("Describe the problem, the people involved and the outcome you want"),
      "Handlers spend too long on claims.",
    );
    await user.click(screen.getByRole("button", { name: "Submit" }));
    await waitFor(() => {
      expect(screen.getByTestId("where")).toHaveTextContent("/usecases?usecase=UC-0007");
    });
    expect(seen.body).toEqual({
      name: "Claims triage",
      intake_text: "Handlers spend too long on claims.",
    });
  });

  it("shows a refusal about a field beside that field (P-03)", async () => {
    server.use(
      signedIn(),
      http.post(apiUrl("/usecases"), () =>
        refusal(422, "invalid", "String should have at least 1 character", "name"),
      ),
    );
    renderWithApp(<IntakePage />, { route: "/usecases/new" });
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "Submit" }));
    const name = screen.getByLabelText("Name");
    expect(await screen.findByText("String should have at least 1 character")).toHaveAttribute(
      "id",
      name.getAttribute("aria-describedby"),
    );
    expect(screen.getByTestId("where")).toHaveTextContent("/usecases/new");
  });
});
