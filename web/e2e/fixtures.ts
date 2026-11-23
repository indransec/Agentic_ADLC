// Shared end-to-end fixtures: the seeded platform's ids, signing in, and a guard that fails any
// test whose page logs an error or a Content-Security-Policy violation (research R-11).
import { readFileSync } from "node:fs";
import path from "node:path";

import { test as base, expect, type APIRequestContext, type Page } from "@playwright/test";

export interface Stack {
  base_url: string;
  api_url: string;
  password: string;
  usecase: string;
  sign_off_run: string;
  rework_run: string;
  stale_run: string;
  large_run: string;
  larger_run: string;
  sheet_run: string;
  table: string;
  sheet_table: string;
  spreadsheet: string;
  escalated_run: string;
  clarification_run: string;
  clarification: string;
  waiver_run: string;
  waiver: string;
  dead_letter: string;
  keyboard_run: string;
  script: string;
  file_name: string;
  hostile_usecase: string;
  hostile_run: string;
  hostile_reworked_run: string | null;
  hostile_clarification_run: string;
  hostile_clarification: string;
}

export function stack(): Stack {
  const file = path.resolve(import.meta.dirname, ".stack.json");
  return JSON.parse(readFileSync(file, "utf8")) as Stack;
}

export async function signIn(page: Page, role: string): Promise<void> {
  await page.getByLabel("Account").fill(`${role}-person`);
  await page.getByLabel("Password").fill(stack().password);
  await page.getByRole("button", { name: "Sign in" }).click();
}

export const runPath = (run: string): string => `/run?run=${encodeURIComponent(run)}`;

/** A bearer session straight to the platform API, as another client would hold. */
export async function bearer(request: APIRequestContext, role: string): Promise<string> {
  const answer = await request.post(`${stack().api_url}/auth/sign-in`, {
    data: { account_name: `${role}-person`, password: stack().password },
  });
  expect(answer.status()).toBe(200);
  return ((await answer.json()) as { token: string }).token;
}

export const test = base.extend<{ pageProblems: string[] }>({
  pageProblems: [
    async ({ page }, use) => {
      const problems: string[] = [];
      page.on("console", (message) => {
        // HTTP statuses (an expected 401 at start-up, a refused change) are asserted by the
        // tests themselves; script errors and CSP violations ("Refused to …") are not expected.
        if (message.type() === "error" && !message.text().startsWith("Failed to load resource")) {
          problems.push(message.text());
        }
      });
      page.on("pageerror", (error) => problems.push(error.message));
      await use(problems);
      expect(problems, "console errors or CSP violations").toEqual([]);
    },
    { auto: true },
  ],
});

export { expect };
