// US4 end to end (T055; P-01, D-1): a business owner submits a use case and follows it.
import { expect, signIn, test } from "./fixtures";

test("submit a use case and follow it", async ({ page }) => {
  await page.goto("/");
  await signIn(page, "business_owner");
  await page.getByRole("link", { name: "New use case" }).click();
  await page.getByLabel("Name").fill("Fraud screening");
  await page
    .getByLabel("Describe the problem, the people involved and the outcome you want")
    .fill("Analysts screen every claim by hand. ".repeat(10));
  await page.getByRole("button", { name: "Submit" }).click();
  await expect(page).toHaveURL(/\/usecases\?usecase=UC-\d+$/);
});
