// US7 (T067, P-13, SC-005): text written by people and agents, with markup and script in it, is
// shown literally on every page that shows it; no script runs, nothing becomes an element, and
// the CSP is never violated (the console guard in fixtures.ts fails the test otherwise).
import type { Page } from "@playwright/test";

import { expect, runPath, signIn, stack, test } from "./fixtures";

async function nothingRan(page: Page) {
  expect(
    await page.evaluate(() => (window as unknown as { __pwned?: number }).__pwned),
  ).toBeUndefined();
  await expect(page.locator("main b, main img[src='x'], main script")).toHaveCount(0);
}

test("intake and the use case's name (Use cases, Journey)", async ({ page }) => {
  const { hostile_usecase: usecase, script } = stack();
  await page.goto(`/usecases?mine=0&usecase=${usecase}`);
  await signIn(page, "sre");
  await page.getByText("Description").click();
  await expect(page.getByText(`${script} ${script}`, { exact: false }).first()).toBeVisible();
  await nothingRan(page);
  await page.goto(`/journey?usecase=${usecase}`);
  await expect(page.getByText(`${script.slice(0, 60)} case`)).toBeVisible();
  await nothingRan(page);
});

test("artifact cells and an attachment's name (Run)", async ({ page }) => {
  const { hostile_run: run, script, file_name } = stack();
  await page.goto(runPath(run));
  await signIn(page, "sre");
  await expect(page.locator(".ag-cell", { hasText: script }).first()).toBeVisible();
  await expect(page.getByText(file_name)).toBeVisible();
  await nothingRan(page);
});

test("a rework comment (Run, prior rework)", async ({ page }) => {
  const { hostile_reworked_run: run, script } = stack();
  test.skip(run === null, "the seeded rework did not reopen the terminal");
  await page.goto(runPath(run ?? ""));
  await signIn(page, "sre");
  await page.getByRole("tab", { name: /Prior rework/ }).click();
  await expect(page.getByRole("tabpanel").getByText(script).first()).toBeVisible();
  await nothingRan(page);
});

test("a clarification question (Clarification)", async ({ page }) => {
  const { hostile_clarification_run: run, hostile_clarification: id, script } = stack();
  await page.goto(`/clarification?run=${encodeURIComponent(run)}&id=${encodeURIComponent(id)}`);
  await signIn(page, "engineering_lead");
  await expect(page.getByText(script)).toBeVisible();
  await nothingRan(page);
});
