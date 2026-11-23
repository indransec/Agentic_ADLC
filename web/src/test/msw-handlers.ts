// API mocks for component tests (MSW). Paths are the platform's, under /api on this origin.
// Tests add what they need with server.use(...); a request nobody planned for fails the test.
import { http, HttpResponse, type JsonBodyType, type RequestHandler } from "msw";

import { fixtures } from "./fixtures";

// The page's origin (jsdom's), or a fixed one in the node environment (the lint-guard test)
const ORIGIN = typeof window === "undefined" ? "http://localhost" : window.location.origin;

export const apiUrl = (path: string): string => new URL(`/api${path}`, ORIGIN).href;

export const json = (body: unknown, status = 200) =>
  HttpResponse.json(body as JsonBodyType, { status });

export const refusal = (status: number, kind: string, detail: string, field?: string) =>
  json(field === undefined ? { kind, detail } : { kind, detail, field }, status);

export const CSRF = "csrf-for-tests";

/** /auth/me answers this person (cookie session, with its CSRF value). */
export const signedIn = (person = fixtures.person): RequestHandler =>
  http.get(apiUrl("/auth/me"), () => json({ ...person, csrf_token: CSRF }));

/** /auth/me answers 401: nobody is signed in. */
export const signedOut = (): RequestHandler =>
  http.get(apiUrl("/auth/me"), () => refusal(401, "not_signed_in", "not authenticated"));

export const handlers: RequestHandler[] = [
  http.get(new URL("/config.json", ORIGIN).href, () =>
    json({ env: "dev", dashboard_refresh_seconds: 10 }),
  ),
  // An empty Inbox, so any test that lands on it needs no setup of its own
  http.get(apiUrl("/inbox"), () => json([])),
  http.get(apiUrl("/changes"), () => json([])),
  http.get(apiUrl("/events/proposed"), () => json([])),
];
