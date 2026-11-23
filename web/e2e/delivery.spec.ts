// US5 in the browser (D-8): the delivery views render on the seeded platform, the charts draw
// under the strict CSP (any CSP violation or script error fails the test), and verification
// works. Every assertion here is about the real page; the component tests cover the details.
import { expect, signIn, stack, test } from "./fixtures";

test("Use cases: the journey of a use case and its ledger verification (D-6)", async ({ page }) => {
  await page.goto(`/usecases?mine=0&usecase=${stack().usecase}`);
  await signIn(page, "sre");
  await expect(page.getByRole("heading", { name: "Journey" })).toBeVisible();
  await page.getByRole("button", { name: "Verify the ledger for this use case" }).click();
  await expect(page.getByText(/^Verified: \d+ records, no breaks$/)).toBeVisible();
});

test("Journey: lanes and bars are drawn (D-8)", async ({ page }) => {
  await page.goto(`/journey?usecase=${stack().usecase}`);
  await signIn(page, "sre");
  const chart = page.getByRole("img", { name: new RegExp(`Journey of ${stack().usecase}`) });
  await expect(chart.locator("svg.main-svg").first()).toBeVisible();
  await expect(chart.locator(".barlayer .point").first()).toBeVisible();
  await expect(page.getByRole("heading", { name: "Escalations and exceptions" })).toBeVisible();
});

test("Activity: the feed, filtered by actor in the address", async ({ page }) => {
  await page.goto("/activity?actor=human");
  await signIn(page, "sre");
  await expect(page.getByLabel("Actor")).toHaveValue("human");
  await expect(page.getByText(/^\d+ action\(s\)$/)).toBeVisible();
});

test("Portfolio: KPIs and time per terminal", async ({ page }) => {
  await page.goto("/portfolio");
  await signIn(page, "adlc_coe");
  await expect(page.getByText(/^\d+ use case\(s\)$/)).toBeVisible();
  const chart = page.getByRole("img", { name: /Time per terminal/ });
  await expect(chart.locator("svg.main-svg").first()).toBeVisible();
});

test("Dead letters: the CoE inspects and re-queues; others see the notice", async ({ page }) => {
  await page.goto(`/dead-letters?event=${stack().dead_letter}`);
  await signIn(page, "adlc_coe");
  await expect(page.getByLabel("Event")).toHaveValue(stack().dead_letter);
  await page.getByRole("button", { name: "Show payload and history" }).click();
  await expect(page.getByText("Never re-queued.")).toBeVisible();
  await page.getByRole("button", { name: "Re-queue" }).click();
  await expect(page.getByText("Re-queued")).toBeVisible();
  await page.getByRole("button", { name: "Sign out" }).click();
  await page.goto("/dead-letters");
  await signIn(page, "sre");
  await expect(page.getByText("Dead letters are handled by the CoE role.")).toBeVisible();
});
