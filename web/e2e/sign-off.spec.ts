// US2 end to end (T043; P-04 from a link, D-1, D-2): an approver passes a run and sends another
// to rework with a comment and root cause; each decision is recorded and the run reloads.
import { expect, runPath, signIn, stack, test } from "./fixtures";

test("pass a run from its link", async ({ page }) => {
  await page.goto(runPath(stack().sign_off_run));
  await signIn(page, "product_owner");
  await expect(page.getByRole("heading", { name: "Decision" })).toBeVisible();
  await page.getByRole("radio", { name: "pass" }).check();
  await page.getByRole("button", { name: "Submit decision" }).click();
  await expect(page.getByText("Decision recorded")).toBeVisible();
  await page.getByRole("tab", { name: /Approvals/ }).click();
  await expect(page.getByRole("tabpanel")).toContainText("product_owner-person");
});

test("send a run to rework with a comment and a root cause", async ({ page }) => {
  await page.goto(runPath(stack().rework_run));
  await signIn(page, "product_owner");
  await page.getByRole("radio", { name: "rework" }).check();
  await page.getByLabel("Comment", { exact: true }).fill("KPI baseline missing");
  await page.getByLabel("Root cause").selectOption({ index: 0 });
  const reason = page.getByLabel("Reason", { exact: true });
  if (await reason.isVisible()) await reason.fill("the baseline must come first");
  await page.getByRole("button", { name: "Submit decision" }).click();
  await expect(page.getByText("Decision recorded")).toBeVisible();
  const summary = page.getByRole("region", { name: "Run summary" });
  await expect(summary.getByText("Closed")).toBeVisible();
  await expect(summary.getByText("Rework")).toBeVisible();
});

test("open a sign-off from the Inbox (P-04)", async ({ page }) => {
  await page.goto("/inbox");
  await signIn(page, "product_owner");
  const signOffs = page.getByRole("region", { name: "Sign-offs", exact: true });
  await signOffs.getByRole("button", { name: /^Open/ }).first().click();
  await expect(page).toHaveURL(/\/run\?run=UC-\d+%2FT\d+%2Frun-\d+$/);
  await expect(page.getByRole("heading", { name: "Decision" })).toBeVisible();
});
