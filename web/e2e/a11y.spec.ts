// US7 (T066, N-07, FR-028): no serious or critical accessibility problem on any page, and the
// core flow works with the keyboard alone; focus moves to the page heading on each page.
import AxeBuilder from "@axe-core/playwright";
import type { Page } from "@playwright/test";

import { expect, runPath, signIn, stack, test } from "./fixtures";

async function axe(page: Page, where: string) {
  const result = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa"]).analyze();
  const serious = result.violations
    .filter((v) => v.impact === "serious" || v.impact === "critical")
    .map((v) => `${v.id}: ${v.nodes.map((n) => n.target.join(" ")).join(", ")}`);
  expect(serious, where).toEqual([]);
}

test("no serious accessibility problems on any page", async ({ page }) => {
  const s = stack();
  await page.goto("/sign-in");
  await axe(page, "sign-in");
  await signIn(page, "product_owner");
  await expect(page).toHaveURL(/\/inbox$/);
  const pages: [string, string][] = [
    ["/inbox", "Inbox"],
    ["/usecases/new", "New use case"],
    [`/usecases?mine=0&usecase=${s.usecase}`, "Use cases"],
    [`/journey?usecase=${s.usecase}`, "Journey"],
    ["/activity", "Activity"],
    ["/portfolio", "Portfolio"],
    ["/dead-letters", "Dead letters"],
    [runPath(s.large_run), "Run"],
    [
      `/clarification?run=${encodeURIComponent(s.clarification_run)}&id=${encodeURIComponent(s.clarification)}`,
      "Clarification",
    ],
    [`/escalation?run=${encodeURIComponent(s.sign_off_run)}`, "Escalation"],
    [`/waiver?run=${encodeURIComponent(s.waiver_run)}&id=${s.waiver}`, "Waiver"],
  ];
  for (const [path, heading] of pages) {
    await page.goto(path);
    await expect(page.getByRole("heading", { name: heading, exact: true, level: 1 })).toBeVisible();
    await page.waitForLoadState("networkidle");
    await axe(page, path);
  }
});

// Safari moves Tab between text fields only by default; Option+Tab reaches every control
let TAB = "Tab";

async function tabTo(
  page: Page,
  matches: (el: { tag: string; text: string; type: string }) => boolean,
) {
  for (let i = 0; i < 120; i++) {
    await page.keyboard.press(TAB);
    const focused = await page.evaluate(() => {
      const el = document.activeElement as HTMLElement | null;
      return {
        tag: el?.tagName.toLowerCase() ?? "",
        text: (el?.textContent ?? "").trim(),
        type: el?.getAttribute("type") ?? "",
        value: (el as HTMLInputElement | null)?.value ?? "",
      };
    });
    if (matches(focused)) return;
  }
  throw new Error("not reachable with Tab");
}

test("sign in, open an Inbox item and pass a run with the keyboard only", async ({
  page,
  browserName,
}) => {
  TAB = browserName === "webkit" ? "Alt+Tab" : "Tab";
  const s = stack();
  await page.goto("/sign-in");
  await page.getByLabel("Account").focus();
  await page.keyboard.type("product_owner-person");
  await page.keyboard.press("Tab");
  await page.keyboard.type(s.password);
  await page.keyboard.press("Enter");
  await expect(page).toHaveURL(/\/inbox$/);
  await expect(page.getByRole("heading", { name: "Inbox", level: 1 })).toBeFocused();

  await expect(page.getByRole("button", { name: /^Open/ }).first()).toBeVisible();
  await tabTo(page, (el) => el.tag === "button" && el.text.startsWith("Open"));
  await page.keyboard.press("Enter");
  await expect(page).toHaveURL(/\/(run|escalation|waiver|clarification)\?run=/);
  await expect(page.locator("h1")).toBeFocused();

  await page.goto(runPath(s.keyboard_run));
  await expect(page.getByRole("heading", { name: "Run", level: 1 })).toBeFocused();
  await tabTo(page, (el) => el.tag === "input" && el.type === "radio");
  // the first outcome is focused; arrow keys move within the group, Space chooses
  for (let i = 0; i < 4; i++) {
    if (
      await page.getByRole("radio", { name: "pass" }).evaluate((r) => r === document.activeElement)
    )
      break;
    await page.keyboard.press("ArrowRight");
  }
  await page.keyboard.press("Space");
  await expect(page.getByRole("radio", { name: "pass" })).toBeChecked();
  await tabTo(page, (el) => el.tag === "button" && el.text === "Submit decision");
  await page.keyboard.press("Enter");
  await expect(page.getByText("Decision recorded")).toBeVisible();
});
