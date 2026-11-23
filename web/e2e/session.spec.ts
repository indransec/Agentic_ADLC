// US1 end to end (P-02, N-01, N-02, N-03): the session is an HttpOnly cookie no script can
// read; sign-out and expiry return to sign-in; a deep link survives sign-in; a cross-site change
// is refused.
import { expect, signIn, stack, test } from "./fixtures";

const runPath = (run: string) => `/run?run=${encodeURIComponent(run)}`;

test("the session cannot be read by the page (N-01)", async ({ page, context }) => {
  await page.goto("/");
  await signIn(page, "product_owner");
  await expect(page).toHaveURL(/\/inbox$/);
  await expect(page.getByText("Product Owner")).toBeVisible();

  const cookies = await context.cookies();
  const session = cookies.find((c) => c.name === "adlc_session");
  expect(session?.httpOnly).toBe(true);
  expect(session?.sameSite).toBe("Strict");

  const visible = await page.evaluate(() => ({
    cookie: document.cookie,
    local: JSON.stringify(Object.keys(window.localStorage).map((k) => localStorage.getItem(k))),
    session: JSON.stringify(
      Object.keys(window.sessionStorage).map((k) => sessionStorage.getItem(k)),
    ),
  }));
  expect(visible.cookie).not.toContain("adlc_session");
  expect(visible.local).not.toContain(session?.value ?? "-");
  expect(visible.session).not.toContain(session?.value ?? "-");
  expect(page.url()).not.toContain(session?.value ?? "-");
});

test("sign-out returns to sign-in and ends the session (P-02)", async ({ page, context }) => {
  await page.goto("/");
  await signIn(page, "product_owner");
  await page.getByRole("button", { name: "Sign out" }).click();
  await expect(page).toHaveURL(/\/sign-in$/);
  expect((await context.cookies()).find((c) => c.name === "adlc_session")).toBeUndefined();
  await page.goto("/inbox");
  await expect(page).toHaveURL(/\/sign-in\?next=%2Finbox$/);
});

test("an expired session returns to sign-in with the address kept (P-02)", async ({
  page,
  context,
  request,
}) => {
  await page.goto("/");
  await signIn(page, "product_owner");
  await expect(page).toHaveURL(/\/inbox$/);
  const token = (await context.cookies()).find((c) => c.name === "adlc_session")?.value ?? "";
  // The session ends on the platform (revoked with the token as a bearer client would).
  const revoked = await request.post(`${stack().api_url}/auth/sign-out`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  expect(revoked.status()).toBe(204);
  await page.getByRole("link", { name: "Use cases" }).click();
  await page.reload();
  await expect(page).toHaveURL(/\/sign-in\?next=%2Fusecases$/);
});

test("a run link opens after sign-in (N-03)", async ({ page }) => {
  const run = stack().sign_off_run;
  await page.goto(`/?run=${encodeURIComponent(run)}`);
  await expect(page).toHaveURL(/\/sign-in\?next=/);
  await signIn(page, "product_owner");
  await expect(page).toHaveURL(new RegExp(`${runPath(run).replace(/[?]/g, "\\?")}$`));
});

test("a change sent from another site is refused (N-02)", async ({ page, pageProblems }) => {
  await page.goto("/");
  await signIn(page, "business_owner");
  await expect(page).toHaveURL(/\/inbox$/);
  const before = await page.evaluate(async () => {
    const answer = await window.fetch("/api/usecases?mine=false");
    return ((await answer.json()) as unknown[]).length;
  });

  const target = `${stack().base_url}/api/usecases`;
  const attacker = "http://127.0.0.1:8699/attack.html";
  await page.route(attacker, (route) =>
    route.fulfill({
      contentType: "text/html",
      body: `<form id="f" method="post" action="${target}" enctype="text/plain">
               <input name='{"name":"x","intake_text":"' value='y"}'></form>
             <script>document.getElementById("f").submit()</script>`,
    }),
  );
  const answer = page.waitForResponse((r) => r.url() === target);
  await page.goto(attacker);
  const refused = await answer;
  expect(refused.status()).toBe(403);
  expect(await refused.json()).toEqual({
    kind: "not_allowed",
    detail: "cross-site request refused",
  });

  await page.goto("/inbox");
  const after = await page.evaluate(async () => {
    const reply = await window.fetch("/api/usecases?mine=false");
    return ((await reply.json()) as unknown[]).length;
  });
  expect(after).toBe(before);
  // The browser logs the refused form post (403) on the attacker's page; that is the point here.
  pageProblems.splice(0, pageProblems.length);
});
