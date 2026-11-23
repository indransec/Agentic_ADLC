// @vitest-environment node
// P-27 (research R-11): the lint rules that hold the safety and boundary rules really fire.
import path from "node:path";

import { ESLint } from "eslint";
import { describe, expect, it } from "vitest";

const FIXTURES = path.resolve(import.meta.dirname, "test/lint-fixtures");

async function ruleIds(file: string): Promise<string[]> {
  const eslint = new ESLint({ cwd: path.resolve(import.meta.dirname, ".."), ignore: false });
  const [result] = await eslint.lintFiles([path.join(FIXTURES, file)]);
  return (result?.messages ?? []).map((m) => m.ruleId ?? "");
}

describe("lint guard", () => {
  it.each([
    ["raw-html.tsx", "react/no-danger"],
    ["inner-html.ts", "no-restricted-properties"],
    ["fetch-call.ts", "no-restricted-globals"],
    ["xhr-call.ts", "no-restricted-globals"],
    ["typed-client-import.ts", "no-restricted-imports"],
    ["BadName.tsx", "unicorn/filename-case"],
  ])(
    "%s is reported by %s",
    async (file, rule) => {
      expect(await ruleIds(file)).toContain(rule);
    },
    30_000,
  );

  it("a clean component passes", async () => {
    expect(await ruleIds("clean.tsx")).toEqual([]);
  }, 30_000);
});
