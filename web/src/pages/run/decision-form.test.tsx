// T036 (P-05, P-06; FR-005, FR-006): the decision form is built only from what the platform
// returns for the run, sends the version the person saw, and a stale answer records nothing.
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http } from "msw";
import { describe, expect, it } from "vitest";

import { fixtures, runDetail, type RunDetail } from "../../test/fixtures";
import { apiUrl, json, refusal, signedIn } from "../../test/msw-handlers";
import { server } from "../../test/msw-server";
import { renderWithApp } from "../../test/render";
import { DecisionForm } from "./decision-form";

const RUN = fixtures.runDetail.run.run_id;

function capture() {
  const seen: { body?: Record<string, unknown> } = {};
  server.use(
    signedIn(),
    http.post(apiUrl(`/runs/${encodeURIComponent(RUN)}/decisions`), async ({ request }) => {
      seen.body = (await request.json()) as Record<string, unknown>;
      return json(fixtures.runSummary);
    }),
  );
  return seen;
}

function show(
  detail: RunDetail,
  onStale: () => void = () => undefined,
  onRecorded: () => void = () => undefined,
) {
  renderWithApp(<DecisionForm detail={detail} onStale={onStale} onRecorded={onRecorded} />);
}

describe("decision form", () => {
  it("offers exactly the platform's outcomes", async () => {
    capture();
    show(runDetail((d) => (d.form.outcomes = ["pass", "rework"])));
    const radios = await screen.findAllByRole("radio");
    expect(radios.map((r) => r.getAttribute("value"))).toEqual(["pass", "rework"]);
  });

  it("offers only terminate when the person may terminate but not decide", async () => {
    capture();
    show(
      runDetail((d) => {
        d.form.can_decide = false;
        d.form.can_terminate = true;
      }),
    );
    const radios = await screen.findAllByRole("radio");
    expect(radios.map((r) => r.getAttribute("value"))).toEqual(["terminate"]);
  });

  it("says when the person has no decision to make", async () => {
    capture();
    show(
      runDetail((d) => {
        d.form.can_decide = false;
        d.form.can_terminate = false;
      }),
    );
    expect(
      await screen.findByText("You have no decision to make on this run."),
    ).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Submit decision" })).toBeNull();
  });

  it("passes with the version the person saw", async () => {
    const seen = capture();
    const detail = runDetail();
    let recorded = 0;
    show(detail, undefined, () => {
      recorded += 1;
    });
    const user = userEvent.setup();
    await user.click(await screen.findByRole("radio", { name: "pass" }));
    await user.click(screen.getByRole("button", { name: "Submit decision" }));
    await waitFor(() => {
      expect(seen.body).toEqual({
        decision: "pass",
        expected_version: detail.run.version,
        fields: {},
      });
    });
    await waitFor(() => {
      expect(recorded).toBe(1);
    });
  });

  it("rework asks for a comment, a root cause, the required fields and a reason (P-05)", async () => {
    const seen = capture();
    const detail = runDetail((d) => {
      d.form.root_causes = ["requirements", "implementation"];
      d.form.target_terminal_for = ["implementation"];
      d.form.target_terminals = ["T3", "T4"];
      d.form.requires = { ...d.form.requires, rework: ["evidence_ref"] };
      d.form.reason_required_unless = "pass";
    });
    show(detail);
    const user = userEvent.setup();
    await user.click(await screen.findByRole("radio", { name: "rework" }));
    expect(
      screen.getByText("The reviewer recommended pass; give your reason."),
    ).toBeInTheDocument();
    expect(screen.queryByLabelText("Owning terminal")).toBeNull();
    await user.selectOptions(screen.getByLabelText("Root cause"), "implementation");
    await user.selectOptions(screen.getByLabelText("Owning terminal"), "T4");
    await user.type(screen.getByLabelText("Comment"), "KPI baseline missing");
    await user.type(screen.getByLabelText("evidence ref"), "T1.kpis");
    await user.type(screen.getByLabelText("Reason"), "the baseline must come first");
    await user.click(screen.getByRole("button", { name: "Submit decision" }));
    await waitFor(() => {
      expect(seen.body).toEqual({
        decision: "rework",
        expected_version: detail.run.version,
        comment: "KPI baseline missing",
        root_cause: "implementation",
        target_terminal: "T4",
        reason: "the baseline must come first",
        fields: { evidence_ref: "T1.kpis" },
      });
    });
  });

  it("no reason is asked when the decision follows the recommendation", async () => {
    capture();
    show(runDetail((d) => (d.form.reason_required_unless = "pass")));
    const user = userEvent.setup();
    await user.click(await screen.findByRole("radio", { name: "pass" }));
    expect(screen.queryByLabelText("Reason")).toBeNull();
  });

  it("pass asks for typed fields and offers alternative routes", async () => {
    const seen = capture();
    const detail = runDetail((d) => {
      d.form.typed_fields = ["risk_tier"];
      d.form.alternatives = ["T2b"];
    });
    show(detail);
    const user = userEvent.setup();
    await user.click(await screen.findByRole("radio", { name: "pass" }));
    await user.type(screen.getByLabelText("risk tier"), "medium");
    await user.selectOptions(screen.getByLabelText("Alternative route"), "T2b");
    await user.click(screen.getByRole("button", { name: "Submit decision" }));
    await waitFor(() => {
      expect(seen.body).toMatchObject({ fields: { risk_tier: "medium", alternative: "T2b" } });
    });
  });

  it("says when controls are being re-run or a waiver is pending", async () => {
    capture();
    show(
      runDetail((d) => {
        d.form.controls_pending = true;
        d.form.waiver_pending = true;
      }),
    );
    expect(
      await screen.findByText(
        "Controls are being re-run after an edit; deciding is possible once they finish.",
      ),
    ).toBeInTheDocument();
    expect(screen.getByText("A waiver is pending its approver's decision.")).toBeInTheDocument();
  });

  it("a stale answer records nothing and reloads the run (P-06)", async () => {
    server.use(
      signedIn(),
      http.post(apiUrl(`/runs/${encodeURIComponent(RUN)}/decisions`), () =>
        refusal(409, "stale", "the run changed"),
      ),
    );
    let stale = 0;
    show(runDetail(), () => {
      stale += 1;
    });
    const user = userEvent.setup();
    await user.click(await screen.findByRole("radio", { name: "pass" }));
    await user.click(screen.getByRole("button", { name: "Submit decision" }));
    await waitFor(() => {
      expect(stale).toBe(1);
    });
    expect(screen.queryByRole("alert")).toBeNull(); // the page says it reloaded instead
  });

  it("another refusal is shown in plain words", async () => {
    server.use(
      signedIn(),
      http.post(apiUrl(`/runs/${encodeURIComponent(RUN)}/decisions`), () =>
        refusal(422, "invalid", "the reviewer recommended pass; a reason is required"),
      ),
    );
    show(runDetail());
    const user = userEvent.setup();
    await user.click(await screen.findByRole("radio", { name: "pass" }));
    await user.click(screen.getByRole("button", { name: "Submit decision" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("a reason is required");
  });
});
