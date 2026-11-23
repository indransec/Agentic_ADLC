// US1 (P-02, N-03): sign-in, the wrong password, the next address, sign-out and expiry.
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http } from "msw";
import { describe, expect, it } from "vitest";

import { CSRF_HEADER } from "../api/client";
import { fixtures } from "../test/fixtures";
import { apiUrl, CSRF, json, refusal, signedIn, signedOut } from "../test/msw-handlers";
import { server } from "../test/msw-server";
import { renderApp } from "../test/render";

function signInAnswers(seen: { body?: unknown; csrf?: string | null }) {
  return http.post(apiUrl("/auth/sign-in"), async ({ request }) => {
    seen.body = await request.json();
    seen.csrf = request.headers.get(CSRF_HEADER);
    return json({ expires_at: "2026-11-23T17:00:00Z", person: fixtures.person, csrf_token: CSRF });
  });
}

async function signInWith(account: string, password: string) {
  const user = userEvent.setup();
  await user.type(await screen.findByLabelText("Account"), account);
  await user.type(screen.getByLabelText("Password"), password);
  await user.click(screen.getByRole("button", { name: "Sign in" }));
}

describe("sign-in", () => {
  it("signs in with a cookie session and opens the Inbox", async () => {
    const seen: { body?: unknown; csrf?: string | null } = {};
    server.use(signedOut(), signInAnswers(seen));
    renderApp({ route: "/" });
    await signInWith("product_owner-person", "secret");
    await waitFor(() => {
      expect(screen.getByTestId("where")).toHaveTextContent("/inbox");
    });
    expect(seen.body).toEqual({
      account_name: "product_owner-person",
      password: "secret",
      session: "cookie",
    });
    expect(seen.csrf).toBe("sign-in");
    expect(await screen.findByText("Product Owner")).toBeInTheDocument();
  });

  it("says the account or password is wrong, without saying which", async () => {
    server.use(
      signedOut(),
      http.post(apiUrl("/auth/sign-in"), () =>
        refusal(401, "not_signed_in", "invalid credentials"),
      ),
    );
    renderApp({ route: "/sign-in" });
    await signInWith("product_owner-person", "wrong");
    expect(await screen.findByRole("alert")).toHaveTextContent("invalid credentials");
    expect(screen.getByTestId("where")).toHaveTextContent("/sign-in");
  });

  it("returns to the run that sent the person to sign in (N-03)", async () => {
    server.use(signedOut(), signInAnswers({}));
    renderApp({ route: "/run?run=UC-0001%2FT1%2Frun-1" });
    await waitFor(() => {
      expect(screen.getByTestId("where")).toHaveTextContent("/sign-in?next=");
    });
    await signInWith("product_owner-person", "secret");
    await waitFor(() => {
      expect(screen.getByTestId("where")).toHaveTextContent("/run?run=UC-0001%2FT1%2Frun-1");
    });
  });

  it("an old evidence link (/?run=) opens the Run page", async () => {
    server.use(signedIn());
    renderApp({ route: "/?run=UC-0001%2FT1%2Frun-1" });
    await waitFor(() => {
      expect(screen.getByTestId("where")).toHaveTextContent("/run?run=UC-0001%2FT1%2Frun-1");
    });
  });

  it.each(["//evil.example/x", "https://evil.example/x"])("ignores next=%s", async (next) => {
    server.use(signedOut(), signInAnswers({}));
    renderApp({ route: `/sign-in?next=${encodeURIComponent(next)}` });
    await signInWith("product_owner-person", "secret");
    await waitFor(() => {
      expect(screen.getByTestId("where")).toHaveTextContent(/^\/inbox$/);
    });
  });

  it("signs out and returns to sign-in", async () => {
    let signedOutCalls = 0;
    server.use(
      signedIn(),
      http.post(apiUrl("/auth/sign-out"), ({ request }) => {
        signedOutCalls += request.headers.get(CSRF_HEADER) === CSRF ? 1 : 0;
        return new Response(null, { status: 204 });
      }),
    );
    renderApp({ route: "/inbox" });
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "Sign out" }));
    await waitFor(() => {
      expect(screen.getByTestId("where")).toHaveTextContent("/sign-in");
    });
    expect(signedOutCalls).toBe(1); // with the session's CSRF value
  });

  it("an expired session returns to sign-in, keeping the address", async () => {
    server.use(
      signedIn(),
      http.get(apiUrl("/usecases"), () => refusal(401, "not_signed_in", "expired")),
    );
    renderApp({ route: "/inbox" });
    expect(await screen.findByText("Product Owner")).toBeInTheDocument();
    const { api, call } = await import("../api/client");
    await call(api.GET("/usecases")).catch(() => undefined);
    await waitFor(() => {
      expect(screen.getByTestId("where")).toHaveTextContent("/sign-in?next=%2Finbox");
    });
  });

  it("checks the session once at start; signed out, any page goes to sign-in", async () => {
    server.use(signedOut());
    renderApp({ route: "/dead-letters?event=abc" });
    await waitFor(() => {
      expect(screen.getByTestId("where")).toHaveTextContent(
        "/sign-in?next=%2Fdead-letters%3Fevent%3Dabc",
      );
    });
    expect(await screen.findByRole("heading", { name: "Sign in" })).toBeInTheDocument();
  });
});
