// US7 (T068, N-10, SC-007): each page shows its heading and first data within 2 s.
import type { Page } from "@playwright/test";

import { expect, runPath, signIn, stack, test } from "./fixtures";

const LIMIT_MS = 2000;

async function timed(page: Page, path: string, heading: string, data: string) {
  const started = Date.now();
  await page.goto(path);
  await expect(page.getByRole("heading", { name: heading, exact: true, level: 1 })).toBeVisible();
  await expect(page.locator(data).first()).toBeVisible();
  const elapsed = Date.now() - started;
  expect(elapsed, `${path} took ${String(elapsed)} ms`).toBeLessThan(LIMIT_MS);
}

test("every page shows its content within 2 s", async ({ page }) => {
  const s = stack();
  await page.goto("/");
  await signIn(page, "product_owner");
  await expect(page).toHaveURL(/\/inbox$/);
  await timed(page, "/inbox", "Inbox", ".data-table, .empty");
  await timed(page, "/usecases/new", "New use case", "textarea");
  await timed(page, `/usecases?mine=0&usecase=${s.usecase}`, "Use cases", ".data-table");
  await timed(page, `/journey?usecase=${s.usecase}`, "Journey", "svg.main-svg");
  await timed(page, "/activity", "Activity", ".data-table, .empty");
  await timed(page, "/portfolio", "Portfolio", ".metric");
  await timed(page, runPath(s.large_run), "Run", ".ag-row");
  await timed(
    page,
    `/escalation?run=${encodeURIComponent(s.sign_off_run)}`,
    "Escalation",
    ".summary-bar",
  );
});
