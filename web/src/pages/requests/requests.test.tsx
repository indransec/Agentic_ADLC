// T050 (P-15, P-16, P-17): clarification, escalation and waiver pages.
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http } from "msw";
import { describe, expect, it, vi } from "vitest";

import { fixtures, HOSTILE, runDetail, type RunDetail } from "../../test/fixtures";
import { apiUrl, json, signedIn } from "../../test/msw-handlers";
import { server } from "../../test/msw-server";
import { renderWithApp } from "../../test/render";
import { ClarificationPage } from "./clarification-page";
import { EscalationPage } from "./escalation-page";
import { WaiverPage } from "./waiver-page";

vi.mock("../run/artifact-grid", () => ({
  ArtifactGrid: ({ artifactId }: { artifactId: string }) => (
    <div data-testid={`grid-${artifactId}`} />
  ),
}));

const RUN = fixtures.runDetail.run.run_id;
const at = (page: string, extra = "") => `/${page}?run=${encodeURIComponent(RUN)}${extra}`;
const CLAR = `${RUN}/clar-1`;

function serve(detail: RunDetail) {
  server.use(
    signedIn(),
    http.get(apiUrl(`/runs/${encodeURIComponent(RUN)}`), () => json(detail)),
    http.get(apiUrl(`/dashboard/runs/${encodeURIComponent(RUN)}/timeline`), () =>
      json(fixtures.timeline),
    ),
  );
}

describe("Clarification (P-15)", () => {
  const asked = runDetail((d) => {
    d.clarifications = [
      {
        clarification_id: CLAR,
        asked_by: "t2-design-agent",
        addressed_role: "engineering_lead",
        looked_in: ["knowledge"],
        questions: [HOSTILE[0], "Which channels are in scope?"],
        answers: null,
        answered_by: null,
      },
    ];
  });

  it("answers each question; questions are literal text", async () => {
    serve(asked);
    const seen: { body?: unknown } = {};
    server.use(
      http.post(
        apiUrl(`/clarifications/${encodeURIComponent(CLAR)}/answers`),
        async ({ request }) => {
          seen.body = await request.json();
          return json(fixtures.runSummary);
        },
      ),
    );
    const { container } = renderWithApp(<ClarificationPage />, {
      route: at("clarification", `&id=${encodeURIComponent(CLAR)}`),
    });
    expect(await screen.findByText(HOSTILE[0])).toBeInTheDocument();
    expect(container.querySelector("script, b")).toBeNull();
    const user = userEvent.setup();
    await user.type(screen.getByLabelText("Answer to question 1"), "none");
    await user.type(screen.getByLabelText("Answer to question 2"), "web and email");
    await user.click(screen.getByRole("button", { name: "Send answers" }));
    expect(await screen.findByText("Answers sent")).toBeInTheDocument();
    expect(seen.body).toEqual({ answers: ["none", "web and email"] });
  });

  it("shows the answers once given", async () => {
    serve(
      runDetail((d) => {
        d.clarifications = [
          {
            ...asked.clarifications[0],
            answers: ["none", "web"],
            answered_by: "engineering_lead-person",
          },
        ];
      }),
    );
    renderWithApp(<ClarificationPage />, {
      route: at("clarification", `&id=${encodeURIComponent(CLAR)}`),
    });
    expect(await screen.findByText("engineering_lead-person")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Send answers" })).toBeNull();
  });

  it("without ids it says where to open one", async () => {
    server.use(signedIn());
    renderWithApp(<ClarificationPage />, { route: "/clarification" });
    expect(await screen.findByText("Open a clarification from your inbox.")).toBeInTheDocument();
  });
});

describe("Escalation (P-16)", () => {
  it("completes the escalation with the artifacts and the version shown", async () => {
    serve(runDetail((d) => (d.form.can_complete_escalation = true)));
    const seen: { body?: Record<string, unknown> } = {};
    server.use(
      http.post(apiUrl(`/runs/${encodeURIComponent(RUN)}/escalation`), async ({ request }) => {
        seen.body = (await request.json()) as Record<string, unknown>;
        return json(fixtures.runSummary);
      }),
    );
    renderWithApp(<EscalationPage />, { route: at("escalation") });
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "Complete escalation" }));
    expect(await screen.findByText("Escalation completed")).toBeInTheDocument();
    expect(seen.body?.["expected_version"]).toBe(fixtures.runDetail.run.version);
    expect(Object.keys(seen.body?.["artifacts"] as object)).toEqual(
      fixtures.runDetail.artifacts.map((a) => a.id),
    );
  });

  it("says it was completed after the run reloads with its new version", async () => {
    let version = fixtures.runDetail.run.version;
    let escalated = true;
    server.use(
      signedIn(),
      http.get(apiUrl(`/runs/${encodeURIComponent(RUN)}`), () =>
        json(
          runDetail((d) => {
            d.run.version = version;
            d.form.can_complete_escalation = escalated;
          }),
        ),
      ),
      http.get(apiUrl(`/dashboard/runs/${encodeURIComponent(RUN)}/timeline`), () =>
        json(fixtures.timeline),
      ),
      http.post(apiUrl(`/runs/${encodeURIComponent(RUN)}/escalation`), () => {
        version += 1;
        escalated = false;
        return json(fixtures.runSummary);
      }),
    );
    renderWithApp(<EscalationPage />, { route: at("escalation") });
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "Complete escalation" }));
    expect(await screen.findByText(`Version ${String(version)}`)).toBeInTheDocument();
    expect(screen.getByText("Escalation completed")).toBeInTheDocument();
    expect(screen.queryByText("You cannot complete this run.")).toBeNull();
  });

  it("someone who may not complete it is told so", async () => {
    serve(runDetail((d) => (d.form.can_complete_escalation = false)));
    renderWithApp(<EscalationPage />, { route: at("escalation") });
    expect(await screen.findByText("You cannot complete this run.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Complete escalation" })).toBeNull();
    expect(screen.getByRole("heading", { name: "Reviewer recommendation" })).toBeInTheDocument();
  });
});

describe("Waiver (P-17)", () => {
  const pending = runDetail((d) => {
    d.waiver = {
      waiver_id: "WVR-0001",
      status: "pending",
      proposed_by: "business_owner-person",
      waiver_owner: "product_owner-person",
      compensating_control: HOSTILE[1],
      expiry: "2099-01-01",
      requires: { risk_acceptance: "accepted for the pilot only" },
    };
  });

  it("shows every proposal value literally and records the decision", async () => {
    serve(pending);
    const seen: { body?: unknown } = {};
    server.use(
      http.post(apiUrl("/waivers/WVR-0001/decision"), async ({ request }) => {
        seen.body = await request.json();
        return json(fixtures.runSummary);
      }),
    );
    const { container } = renderWithApp(<WaiverPage />, { route: at("waiver", "&id=WVR-0001") });
    expect(await screen.findByText(HOSTILE[1])).toBeInTheDocument();
    expect(screen.getByText("accepted for the pilot only")).toBeInTheDocument();
    expect(container.querySelector("img[src='x']")).toBeNull();
    const user = userEvent.setup();
    await user.type(screen.getByLabelText("Comment"), "control is credible");
    await user.click(screen.getByRole("button", { name: "Record waiver decision" }));
    expect(await screen.findByText("Waiver decision recorded")).toBeInTheDocument();
    expect(seen.body).toEqual({ approve: true, comment: "control is credible" });
  });

  it("a waiver no longer pending says so", async () => {
    serve(runDetail((d) => (d.waiver = null)));
    renderWithApp(<WaiverPage />, { route: at("waiver", "&id=WVR-0001") });
    expect(await screen.findByText("This waiver is no longer pending.")).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.queryByRole("button", { name: "Record waiver decision" })).toBeNull();
    });
  });
});
