// US7 (T065, N-04, FR-003): back, forward and reload keep the page, the run, the use case and
// the filters; unknown addresses say so.
import { expect, runPath, signIn, stack, test } from "./fixtures";

test("back and forward move between pages and keep their state", async ({ page }) => {
  await page.goto(`/usecases?mine=0&usecase=${stack().usecase}`);
  await signIn(page, "sre");
  await page.getByRole("button", { name: "Open the journey view" }).click();
  await expect(page).toHaveURL(new RegExp(`/journey\\?usecase=${stack().usecase}$`));
  await page.goBack();
  await expect(page).toHaveURL(/\/usecases\?mine=0&usecase=/);
  await expect(page.getByLabel("Use case")).toHaveValue(stack().usecase);
  await expect(page.getByRole("checkbox", { name: "Only mine" })).not.toBeChecked();
  await page.goForward();
  await expect(page.getByLabel("Use case")).toHaveValue(stack().usecase);
});

test("reload keeps the run and the filters", async ({ page }) => {
  await page.goto(runPath(stack().sign_off_run));
  await signIn(page, "sre");
  const summary = page.getByRole("region", { name: "Run summary" });
  await expect(summary.getByText(stack().sign_off_run)).toBeVisible();
  await page.reload();
  await expect(summary.getByText(stack().sign_off_run)).toBeVisible();

  await page.goto("/activity?actor=human&step=sign_off");
  await page.reload();
  await expect(page.getByLabel("Actor")).toHaveValue("human");
  await expect(page.getByLabel("Step")).toHaveValue("sign_off");
});

test("unknown addresses say so", async ({ page }) => {
  await page.goto("/no-such-page");
  await signIn(page, "sre");
  await expect(page.getByRole("heading", { name: "Page not found" })).toBeVisible();
  await page.goto("/run");
  await expect(page.getByText("Open a run from your inbox or a use case.")).toBeVisible();
  await page.goto(runPath("UC-9999/T1/run-1"));
  await expect(page.getByRole("alert")).toContainText("not found");
});
