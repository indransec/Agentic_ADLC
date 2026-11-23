// US3 end to end (T047; P-09, P-11, P-12, SC-007): the real grid edits and saves a 1,000-row
// table within 5 s; 1,001 rows are read-only with upload offered; a spreadsheet replaces a
// table; an attachment is offered for download only, never rendered.
import { bearer, expect, runPath, signIn, stack, test } from "./fixtures";

interface Detail {
  artifacts: { id: string; rows: Record<string, unknown>[] }[];
}

async function rowsOf(request: Parameters<typeof bearer>[0], run: string, artifact: string) {
  const token = await bearer(request, "product_owner");
  const answer = await request.get(`${stack().api_url}/runs/${run}`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  const detail = (await answer.json()) as Detail;
  return detail.artifacts.find((a) => a.id === artifact)?.rows ?? [];
}

test("edit a cell of a 1,000-row table and save it within 5 s (P-09, SC-007)", async ({
  page,
  request,
}) => {
  const { large_run: run, table } = stack();
  await page.goto(runPath(run));
  await signIn(page, "product_owner");
  const card = page.getByRole("region", { name: table, exact: true });
  const cell = card.locator('.ag-row[row-index="0"] .ag-cell[col-id="description"]');
  await cell.dblclick();
  await page.keyboard.press("ControlOrMeta+a");
  await page.keyboard.type("Edited in the grid");
  await page.keyboard.press("Enter");
  await expect(cell).toHaveText("Edited in the grid");

  const started = Date.now();
  await card.getByRole("button", { name: `Save ${table}` }).click();
  await expect(card.getByText("Saved")).toBeVisible();
  expect(Date.now() - started).toBeLessThan(5000);

  const rows = await rowsOf(request, run, table);
  expect(rows).toHaveLength(1000);
  expect(rows[0]?.["description"]).toBe("Edited in the grid");
});

test("1,001 rows are read-only, with upload offered (P-11)", async ({ page }) => {
  const { larger_run: run, table } = stack();
  await page.goto(runPath(run));
  await signIn(page, "product_owner");
  const card = page.getByRole("region", { name: table, exact: true });
  await expect(
    card.getByText("More than 1000 rows: upload a spreadsheet to change it."),
  ).toBeVisible();
  await expect(card.getByRole("button", { name: `Save ${table}` })).toHaveCount(0);
  await card.locator('.ag-row[row-index="0"] .ag-cell[col-id="description"]').dblclick();
  await expect(card.locator(".ag-cell-inline-editing")).toHaveCount(0);
  await expect(card.getByText("Upload a spreadsheet or attach a file")).toBeVisible();
});

test("a spreadsheet replaces a table", async ({ page, request }) => {
  const { sheet_run: run, sheet_table: table, spreadsheet } = stack();
  await page.goto(runPath(run));
  await signIn(page, "product_owner");
  const card = page.getByRole("region", { name: table, exact: true });
  await card.getByText("Upload a spreadsheet or attach a file").click();
  await card.getByLabel(`Spreadsheet for ${table}`).setInputFiles(spreadsheet);
  await card.getByRole("button", { name: `Upload spreadsheet to ${table}` }).click();
  await expect(card.getByText("Spreadsheet uploaded")).toBeVisible();
  const rows = await rowsOf(request, run, table);
  expect(rows[0]?.["requirement"]).toBe("p95 latency (from the spreadsheet)");
});

test("an attachment is offered for download only (P-12)", async ({ page, context }) => {
  const { large_run: run, table } = stack();
  await page.goto(runPath(run));
  await signIn(page, "product_owner");
  const card = page.getByRole("region", { name: table, exact: true });
  await card.getByText("Upload a spreadsheet or attach a file").click();
  await card.getByLabel(`Attach a file to ${table}`).setInputFiles({
    name: "diagram.svg",
    mimeType: "image/svg+xml",
    buffer: Buffer.from(
      '<svg xmlns="http://www.w3.org/2000/svg"><script>window.top.__pwned = 1</script></svg>',
    ),
  });
  await card.getByRole("button", { name: `Attach to ${table}` }).click();
  await expect(card.getByText("Attached")).toBeVisible();
  await expect(card.getByText("diagram.svg")).toBeVisible();

  const download = page.waitForEvent("download");
  await card.getByRole("button", { name: "Download" }).click();
  expect((await download).suggestedFilename()).toBe("diagram.svg");
  expect(context.pages()).toHaveLength(1);
  expect(
    await page.evaluate(() => (window as unknown as { __pwned?: number }).__pwned),
  ).toBeUndefined();
  await expect(card.locator("img, iframe, object, embed")).toHaveCount(0);
});
