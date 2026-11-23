// T037 (P-07, P-14, P-19): the Run page shows every SA 8.2 section; agent and person text is
// literal; a blocked run explains itself; an unknown run says so.
import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http } from "msw";
import { describe, expect, it } from "vitest";

import { fixtures, HOSTILE, runDetail, type RunDetail } from "../../test/fixtures";
import { apiUrl, json, refusal, signedIn } from "../../test/msw-handlers";
import { server } from "../../test/msw-server";
import { renderWithApp } from "../../test/render";
import { RunPage } from "./run-page";

const RUN = fixtures.runDetail.run.run_id;
const route = `/run?run=${encodeURIComponent(RUN)}`;

function serve(detail: RunDetail) {
  server.use(
    signedIn(),
    http.get(apiUrl(`/runs/${encodeURIComponent(RUN)}`), () => json(detail)),
    http.get(apiUrl(`/dashboard/runs/${encodeURIComponent(RUN)}/timeline`), () =>
      json(fixtures.timeline),
    ),
  );
}

describe("Run page", () => {
  it("shows the summary bar", async () => {
    serve(runDetail((d) => (d.timer.overdue = true)));
    renderWithApp(<RunPage />, { route });
    const bar = await screen.findByRole("region", { name: "Run summary" });
    expect(within(bar).getByText(RUN)).toBeInTheDocument();
    expect(
      within(bar).getByText(`Version ${String(fixtures.runDetail.run.version)}`),
    ).toBeInTheDocument();
    expect(
      within(bar).getByText(`T1 · spec ${fixtures.runDetail.spec.version}`),
    ).toBeInTheDocument();
    expect(within(bar).getByText("Awaiting sign-off")).toBeInTheDocument();
    expect(within(bar).getByText("Overdue")).toBeInTheDocument();
    expect(within(bar).getByText("$0.0000")).toBeInTheDocument();
  });

  it("has every section, with counts on tabs that have content", async () => {
    serve(runDetail());
    renderWithApp(<RunPage />, { route });
    expect(
      await screen.findByRole("heading", { name: "Reviewer recommendation" }),
    ).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Control results" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Decision" })).toBeInTheDocument();
    const tabs = screen.getAllByRole("tab").map((t) => t.textContent);
    expect(tabs).toEqual([
      "Prerequisites (3)",
      "Citations",
      "Prior rework",
      "Clarifications",
      "Approvals",
      "Waiver",
      "Activity",
      "Timeline",
      "Evidence",
    ]);
  });

  it("shows agent and person text literally (P-07)", async () => {
    const [script, image] = HOSTILE;
    serve(
      runDetail((d) => {
        d.recommendation = { ...d.recommendation, reason: script, findings: [image] };
        d.prior_rework = [
          {
            run_id: "UC-0001/T1/run-0",
            person: "p",
            signed_at: "2026-11-23T09:00:00Z",
            comment: script,
            root_cause: null,
          },
        ];
      }),
    );
    const { container } = renderWithApp(<RunPage />, { route });
    expect(await screen.findByText(script)).toBeInTheDocument();
    expect(screen.getByText(image)).toBeInTheDocument();
    const user = userEvent.setup();
    await user.click(screen.getByRole("tab", { name: "Prior rework (1)" }));
    expect(screen.getAllByText(script).length).toBeGreaterThanOrEqual(2);
    expect(container.querySelector("script, img[src='x'], b")).toBeNull();
  });

  it("after a decision the page says so and shows the reloaded run", async () => {
    let version = fixtures.runDetail.run.version;
    server.use(
      signedIn(),
      http.get(apiUrl(`/runs/${encodeURIComponent(RUN)}`), () =>
        json(runDetail((d) => (d.run.version = version))),
      ),
      http.post(apiUrl(`/runs/${encodeURIComponent(RUN)}/decisions`), () => {
        version += 1;
        return json(fixtures.runSummary);
      }),
    );
    renderWithApp(<RunPage />, { route });
    const user = userEvent.setup();
    await user.click(await screen.findByRole("radio", { name: "pass" }));
    await user.click(screen.getByRole("button", { name: "Submit decision" }));
    expect(await screen.findByText("Decision recorded")).toBeInTheDocument();
    expect(await screen.findByText(`Version ${String(version)}`)).toBeInTheDocument();
  });

  it("a stale answer reloads the run with the message (P-06)", async () => {
    let version = fixtures.runDetail.run.version;
    server.use(
      signedIn(),
      http.get(apiUrl(`/runs/${encodeURIComponent(RUN)}`), () =>
        json(runDetail((d) => (d.run.version = version))),
      ),
      http.post(apiUrl(`/runs/${encodeURIComponent(RUN)}/decisions`), () => {
        version += 1; // someone else changed it meanwhile
        return refusal(409, "stale", "the run changed");
      }),
    );
    renderWithApp(<RunPage />, { route });
    const user = userEvent.setup();
    await user.click(await screen.findByRole("radio", { name: "pass" }));
    await user.click(screen.getByRole("button", { name: "Submit decision" }));
    expect(
      await screen.findByText(
        "This run changed since you opened it. It has been reloaded; check it and act again.",
      ),
    ).toBeInTheDocument();
    expect(await screen.findByText(`Version ${String(version)}`)).toBeInTheDocument();
    expect(screen.queryByText("Decision recorded")).toBeNull();
  });

  it("a blocked run says why and offers terminate (P-14)", async () => {
    serve(
      runDetail((d) => {
        d.run.state = "blocked";
        d.form.can_decide = false;
        d.form.can_terminate = true;
      }),
    );
    renderWithApp(<RunPage />, { route });
    expect(
      await screen.findByText(
        "Blocked by an unmet prerequisite (see Prerequisites). Supply the evidence, or terminate the run below.",
      ),
    ).toBeInTheDocument();
    expect(screen.getByRole("radio", { name: "terminate" })).toBeInTheDocument();
  });

  it("the evidence tab lists checks, checklist, versions and the ledger record (P-19)", async () => {
    serve(runDetail((d) => (d.ledger_record = { record_hash: "abc", previous_hash: null })));
    renderWithApp(<RunPage />, { route });
    const user = userEvent.setup();
    await user.click(await screen.findByRole("tab", { name: "Evidence" }));
    const panel = screen.getByRole("tabpanel");
    expect(within(panel).getByText("Checks")).toBeInTheDocument();
    expect(within(panel).getByText("Artifact versions")).toBeInTheDocument();
    expect(within(panel).getByText(/"record_hash": "abc"/)).toBeInTheDocument();
  });

  it("the timeline tab loads the run's steps and attempts", async () => {
    serve(runDetail());
    renderWithApp(<RunPage />, { route });
    const user = userEvent.setup();
    await user.click(await screen.findByRole("tab", { name: "Timeline" }));
    const attempts = await screen.findAllByText(/attempt 1 ·/);
    expect(attempts.map((a) => a.textContent.split(" attempt")[0])).toEqual(
      fixtures.timeline.attempts.map((a) => a.kind.slice(0, 1).toUpperCase() + a.kind.slice(1)),
    );
  });

  it("an unknown run says it was not found", async () => {
    server.use(
      signedIn(),
      http.get(apiUrl(`/runs/${encodeURIComponent("UC-9999/T1/run-1")}`), () =>
        refusal(404, "not_found", "no run UC-9999/T1/run-1"),
      ),
    );
    renderWithApp(<RunPage />, { route: `/run?run=${encodeURIComponent("UC-9999/T1/run-1")}` });
    expect(await screen.findByRole("alert")).toHaveTextContent("not found");
    expect(screen.getByRole("link", { name: "Open the Inbox" })).toBeInTheDocument();
  });

  it("without a run in the address it says where to open one", async () => {
    server.use(signedIn());
    renderWithApp(<RunPage />, { route: "/run" });
    expect(
      await screen.findByText("Open a run from your inbox or a use case."),
    ).toBeInTheDocument();
  });
});
