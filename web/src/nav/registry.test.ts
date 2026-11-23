// FR-002, FR-003: one table drives the sidebar and the addresses.
import { describe, expect, it } from "vitest";

import { pagePath, safeNext } from "./navigate";
import { ENTRY_LIST } from "./registry";

describe("registry", () => {
  it("lists the Phase 1 pages, none of the console's", () => {
    expect(ENTRY_LIST.map((e) => e.id)).toEqual([
      "inbox",
      "new-use-case",
      "use-cases",
      "journey",
      "activity",
      "portfolio",
      "dead-letters",
      "run",
      "clarification",
      "escalation",
      "waiver",
    ]);
  });

  it("opens Run and the request pages from other pages only", () => {
    const hidden = ENTRY_LIST.filter((e) => !e.inSidebar).map((e) => e.id);
    expect(hidden).toEqual(["run", "clarification", "escalation", "waiver"]);
    expect(ENTRY_LIST.filter((e) => e.inSidebar).every((e) => e.section !== null)).toBe(true);
  });

  it("has unique ids and paths, all kebab-case", () => {
    expect(new Set(ENTRY_LIST.map((e) => e.id)).size).toBe(ENTRY_LIST.length);
    expect(new Set(ENTRY_LIST.map((e) => e.path)).size).toBe(ENTRY_LIST.length);
    for (const entry of ENTRY_LIST) expect(entry.id).toMatch(/^[a-z]+(-[a-z]+)*$/);
  });

  it("keeps ids in the query, so run ids with slashes survive", () => {
    expect(pagePath("run", { run: "UC-0001/T1/run-2" })).toBe("/run?run=UC-0001%2FT1%2Frun-2");
    expect(pagePath("inbox")).toBe("/inbox");
    expect(pagePath("activity", { usecase: "UC-0001", actor: undefined })).toBe(
      "/activity?usecase=UC-0001",
    );
  });

  it("follows only same-origin paths after sign-in", () => {
    expect(safeNext("/run?run=UC-0001%2FT1%2Frun-2")).toBe("/run?run=UC-0001%2FT1%2Frun-2");
    for (const bad of [
      null,
      "//evil.example",
      "https://evil.example",
      "/\\evil.example",
      "inbox",
    ]) {
      expect(safeNext(bad)).toBe("/inbox");
    }
  });
});
