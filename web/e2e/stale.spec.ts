// US2 end to end (T043; P-06, FR-006): the run changes behind the page; deciding records nothing,
// and the page reloads the run with the stale message.
import { bearer, expect, runPath, signIn, stack, test } from "./fixtures";

interface Detail {
  run: { version: number };
  artifacts: { id: string; rows: unknown }[];
  approvals: unknown[];
}

test("a decision on a changed run is refused and the run reloads", async ({ page, request }) => {
  const run = stack().stale_run;
  await page.goto(runPath(run));
  await signIn(page, "product_owner");
  await expect(page.getByRole("heading", { name: "Decision" })).toBeVisible();
  const version = page.getByRole("region", { name: "Run summary" }).getByText(/^Version \d+$/);
  const shown = await version.textContent();

  // Another person edits an artifact through the platform API meanwhile.
  const token = await bearer(request, "product_owner");
  const auth = { Authorization: `Bearer ${token}` };
  const url = `${stack().api_url}/runs/${run}`;
  const detail = (await (await request.get(url, { headers: auth })).json()) as Detail;
  const table = detail.artifacts.find((a) => Array.isArray(a.rows) && a.rows.length > 0);
  expect(table).toBeDefined();
  // A real change: the first text cell of the first row gets a suffix (an identical table is
  // not a new version).
  const rows = structuredClone(table?.rows) as Record<string, unknown>[];
  const first = rows[0] ?? {};
  const column = Object.keys(first).find((k) => typeof first[k] === "string") ?? "";
  first[column] = `${String(first[column])} (edited elsewhere)`;
  const edited = await request.put(`${url}/artifacts/${table?.id ?? ""}`, {
    headers: auth,
    data: { rows, expected_version: detail.run.version },
  });
  expect(edited.status()).toBe(200);
  expect(((await edited.json()) as { changed: boolean }).changed).toBe(true);

  await page.getByRole("radio", { name: "pass" }).check();
  await page.getByRole("button", { name: "Submit decision" }).click();
  await expect(
    page.getByText(
      "This run changed since you opened it. It has been reloaded; check it and act again.",
    ),
  ).toBeVisible();
  await expect(version).not.toHaveText(shown ?? "");
  const after = (await (await request.get(url, { headers: auth })).json()) as Detail;
  expect(after.approvals).toEqual([]); // nothing was recorded
});
