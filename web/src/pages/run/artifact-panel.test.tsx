// T044 (P-09, P-10, P-11; FR-007, FR-012): editing, saving, the 1,000-row limit, uploads,
// attachments as downloads only, history. The grid itself is replaced by a stand-in here (it
// needs a real browser to lay out; e2e/artifacts.spec.ts drives the real one).
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http } from "msw";
import { describe, expect, it, vi } from "vitest";

import { fixtures, HOSTILE, runDetail, type RunDetail } from "../../test/fixtures";
import { apiUrl, json, refusal, signedIn } from "../../test/msw-handlers";
import { server } from "../../test/msw-server";
import { renderWithApp } from "../../test/render";
import { api } from "../../api/client";
import { ArtifactPanel, MAX_EDIT_ROWS } from "./artifact-panel";

vi.mock("./artifact-grid", () => ({
  // Shows each row's first cell as text; "Change first row" edits it, as a person would.
  ArtifactGrid: ({
    artifactId,
    rows,
    editable,
    onChange,
  }: {
    artifactId: string;
    rows: Record<string, unknown>[];
    editable: boolean;
    onChange?: (rows: Record<string, unknown>[]) => void;
  }) => (
    <div
      data-testid={`grid-${artifactId}`}
      data-editable={String(editable)}
      data-rows={rows.length}
    >
      {rows.slice(0, 3).map((row, i) => (
        <span key={i}>{String(Object.values(row)[0])}</span>
      ))}
      {editable && onChange !== undefined && (
        <button
          type="button"
          onClick={() => {
            const [first, ...rest] = rows;
            onChange([{ ...first, [Object.keys(first ?? {})[0] ?? "x"]: "changed" }, ...rest]);
          }}
        >
          Change first row
        </button>
      )}
    </div>
  ),
}));

const RUN = fixtures.runDetail.run.run_id;
const base = `/runs/${encodeURIComponent(RUN)}/artifacts`;
const first = fixtures.runDetail.artifacts[0];
const AID = first?.id ?? "";

function rowsOf(count: number): Record<string, unknown>[] {
  return Array.from({ length: count }, (_, i) => ({
    req_id: `FR-${String(i).padStart(4, "0")}`,
    note: "n",
  }));
}

function show(detail: RunDetail, onStale: () => void = () => undefined) {
  server.use(signedIn());
  renderWithApp(<ArtifactPanel detail={detail} onStale={onStale} onChanged={() => undefined} />);
}

describe("artifact panel", () => {
  it("an editor changes a table and saves it with the version shown (P-09)", async () => {
    const seen: { body?: unknown } = {};
    server.use(
      http.put(apiUrl(`${base}/${AID}`), async ({ request }) => {
        seen.body = await request.json();
        return json(fixtures.artifactSaved);
      }),
    );
    const detail = runDetail((d) => (d.form.can_edit = true));
    show(detail);
    const card = await screen.findByRole("region", { name: AID });
    const user = userEvent.setup();
    await user.click(within(card).getByRole("button", { name: "Change first row" }));
    await user.click(within(card).getByRole("button", { name: `Save ${AID}` }));
    await waitFor(() => {
      expect(seen.body).toMatchObject({ expected_version: detail.run.version });
    });
    const sent = seen.body as { rows: Record<string, unknown>[] };
    expect(Object.values(sent.rows[0] ?? {})[0]).toBe("changed");
    expect(sent.rows).toHaveLength((first?.rows as unknown[]).length);
    expect(await within(card).findByText("Saved")).toBeInTheDocument();
  });

  it("non-editors get read-only tables with no upload (P-10)", async () => {
    show(runDetail((d) => (d.form.can_edit = false)));
    const card = await screen.findByRole("region", { name: AID });
    expect(within(card).queryByRole("button", { name: `Save ${AID}` })).toBeNull();
    expect(within(card).queryByText("Upload a spreadsheet or attach a file")).toBeNull();
  });

  it(`up to ${String(MAX_EDIT_ROWS)} rows are editable; more are read-only with upload (P-11)`, async () => {
    show(
      runDetail((d) => {
        d.form.can_edit = true;
        const [a, b] = d.artifacts;
        if (a !== undefined) a.rows = rowsOf(MAX_EDIT_ROWS);
        if (b !== undefined) b.rows = rowsOf(MAX_EDIT_ROWS + 1);
      }),
    );
    const [a, b] = fixtures.runDetail.artifacts;
    const editable = await screen.findByTestId(`grid-${a?.id ?? ""}`);
    expect(editable).toHaveAttribute("data-editable", "true");
    expect(editable).toHaveAttribute("data-rows", String(MAX_EDIT_ROWS));
    const large = screen.getByTestId(`grid-${b?.id ?? ""}`);
    expect(large).toHaveAttribute("data-editable", "false");
    const card = screen.getByRole("region", { name: b?.id ?? "" });
    expect(
      within(card).getByText(
        `More than ${String(MAX_EDIT_ROWS)} rows: upload a spreadsheet to change it.`,
      ),
    ).toBeInTheDocument();
    expect(within(card).getByText("Upload a spreadsheet or attach a file")).toBeInTheDocument();
  });

  it("says when an artifact is not built yet, and shows text artifacts as text", async () => {
    show(
      runDetail((d) => {
        const [a, b] = d.artifacts;
        if (a !== undefined) {
          a.version = null;
          a.rows = null;
        }
        if (b !== undefined) b.rows = HOSTILE[0];
      }),
    );
    const [a, b] = fixtures.runDetail.artifacts;
    expect(
      await within(await screen.findByRole("region", { name: a?.id ?? "" })).findByText(
        "Not built yet",
      ),
    ).toBeInTheDocument();
    const text = within(screen.getByRole("region", { name: b?.id ?? "" })).getByText(HOSTILE[0]);
    expect(text.querySelector("script, b")).toBeNull();
  });

  // jsdom's FormData cannot travel through Node's fetch in tests, so the uploads are checked at
  // the typed client: the form the panel builds (the browser test sends it for real).
  function spyUploads() {
    const sent: { path: string; version: FormDataEntryValue | null; name: string }[] = [];
    vi.spyOn(api, "POST").mockImplementation((path: string, init: { body: FormData }) => {
      const file = init.body.get("file") as File;
      sent.push({ path, version: init.body.get("expected_version"), name: file.name });
      return Promise.resolve({
        data: fixtures.runChanged,
        response: new Response(null, { status: 200 }),
      });
    });
    return sent;
  }

  it("uploads a spreadsheet with the version shown", async () => {
    const sent = spyUploads();
    const detail = runDetail((d) => (d.form.can_edit = true));
    show(detail);
    const card = await screen.findByRole("region", { name: AID });
    const user = userEvent.setup();
    await user.click(within(card).getByText("Upload a spreadsheet or attach a file"));
    await user.upload(
      within(card).getByLabelText(`Spreadsheet for ${AID}`),
      new File(["x"], "sheet.xlsx", {
        type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
      }),
    );
    await user.click(within(card).getByRole("button", { name: `Upload spreadsheet to ${AID}` }));
    await waitFor(() => {
      expect(sent).toEqual([
        {
          path: "/runs/{run_id}/artifacts/{artifact_id}/spreadsheet",
          version: String(detail.run.version),
          name: "sheet.xlsx",
        },
      ]);
    });
    expect(await within(card).findByText("Spreadsheet uploaded")).toBeInTheDocument();
  });

  it("attaches a file, and lists attachments by name with a download button only", async () => {
    const sent = spyUploads();
    show(
      runDetail((d) => {
        d.form.can_edit = true;
        const [a] = d.artifacts;
        if (a !== undefined)
          a.attachments = [
            {
              name: HOSTILE[1],
              content_hash: "c".repeat(64),
              media_type: "image/svg+xml",
              size: 10,
            },
          ];
      }),
    );
    const card = await screen.findByRole("region", { name: AID });
    expect(within(card).getByText(HOSTILE[1])).toBeInTheDocument();
    expect(within(card).getByRole("button", { name: "Download" })).toBeInTheDocument();
    expect(card.querySelector("img, iframe, object, embed")).toBeNull();
    const user = userEvent.setup();
    await user.click(within(card).getByText("Upload a spreadsheet or attach a file"));
    await user.upload(
      within(card).getByLabelText(`Attach a file to ${AID}`),
      new File(["n"], "notes.md", { type: "text/markdown" }),
    );
    await user.click(within(card).getByRole("button", { name: `Attach to ${AID}` }));
    await waitFor(() => {
      expect(sent.map((s) => [s.path, s.name])).toEqual([
        ["/runs/{run_id}/artifacts/{artifact_id}/attachments", "notes.md"],
      ]);
    });
    expect(await within(card).findByText("Attached")).toBeInTheDocument();
  });

  it("shows the history on request", async () => {
    server.use(http.get(apiUrl(`${base}/${AID}/history`), () => json(fixtures.artifactHistory)));
    show(runDetail());
    const card = await screen.findByRole("region", { name: AID });
    const user = userEvent.setup();
    await user.click(within(card).getByRole("button", { name: "Show history" }));
    expect(await within(card).findByRole("table")).toBeInTheDocument();
  });

  it("a stale save records nothing and asks the page to reload", async () => {
    server.use(http.put(apiUrl(`${base}/${AID}`), () => refusal(409, "stale", "the run changed")));
    let stale = 0;
    show(
      runDetail((d) => (d.form.can_edit = true)),
      () => {
        stale += 1;
      },
    );
    const card = await screen.findByRole("region", { name: AID });
    const user = userEvent.setup();
    await user.click(within(card).getByRole("button", { name: "Change first row" }));
    await user.click(within(card).getByRole("button", { name: `Save ${AID}` }));
    await waitFor(() => {
      expect(stale).toBe(1);
    });
    expect(within(card).queryByText("Saved")).toBeNull();
  });

  it("a terminal without artifacts says so", async () => {
    show(runDetail((d) => (d.artifacts = [])));
    expect(await screen.findByText("This terminal produces no artifacts.")).toBeInTheDocument();
  });
});
