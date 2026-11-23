// US4 end to end (T055; P-15 to P-17; D-4, D-5, D-9): a clarification, an escalation and a
// waiver are answered from the Inbox, and each leaves it.
import { expect, signIn, test } from "./fixtures";

async function openFirst(page: import("@playwright/test").Page, section: string) {
  const region = page.getByRole("region", { name: section, exact: true });
  await region.getByRole("button", { name: /^Open/ }).first().click();
}

test("answer a clarification (D-9)", async ({ page }) => {
  await page.goto("/inbox");
  await signIn(page, "engineering_lead");
  const waiting = page.getByRole("region", { name: "Clarifications", exact: true });
  await expect(waiting.getByRole("button", { name: /^Open/ }).first()).toBeVisible();
  const before = await waiting.getByRole("button", { name: /^Open/ }).count();
  await openFirst(page, "Clarifications");
  await expect(page).toHaveURL(/\/clarification\?run=.+&id=.+/);
  await expect(page.getByText("Which channels are in scope?")).toBeVisible();
  await page.getByLabel("Answer to question 1").fill("web and email");
  await page.getByRole("button", { name: "Send answers" }).click();
  await expect(page.getByText("Answers sent")).toBeVisible();
  await page.getByRole("link", { name: "Inbox" }).click();
  await expect(page.getByRole("heading", { name: "Inbox" })).toBeVisible();
  // the answered clarification has left the Inbox (others, seeded for other tests, may remain)
  await expect(waiting.getByRole("button", { name: /^Open/ })).toHaveCount(before - 1);
});

test("complete an escalation (D-4)", async ({ page }) => {
  await page.goto("/inbox");
  await signIn(page, "product_owner");
  await openFirst(page, "Escalations");
  await expect(page).toHaveURL(/\/escalation\?run=/);
  await page.getByRole("button", { name: "Complete escalation" }).click();
  await expect(page.getByText("Escalation completed")).toBeVisible();
  await page.getByRole("link", { name: "Inbox" }).click();
  await expect(page.getByRole("heading", { name: "Inbox" })).toBeVisible();
  await expect(page.getByRole("region", { name: "Escalations", exact: true })).toHaveCount(0);
});

test("decide a waiver (D-5)", async ({ page }) => {
  await page.goto("/inbox");
  await signIn(page, "product_owner");
  await openFirst(page, "Waivers");
  await expect(page).toHaveURL(/\/waiver\?run=.+&id=WVR-/);
  await expect(page.getByText("weekly manual review")).toBeVisible();
  await expect(page.getByText("accepted for the pilot only")).toBeVisible();
  await page.getByLabel("Comment").fill("control is credible");
  await page.getByRole("button", { name: "Record waiver decision" }).click();
  await expect(page.getByText("Waiver decision recorded")).toBeVisible();
  await page.getByRole("link", { name: "Inbox" }).click();
  await expect(page.getByRole("heading", { name: "Inbox" })).toBeVisible();
  await expect(page.getByRole("region", { name: "Waivers", exact: true })).toHaveCount(0);
});
