// The only module that talks to the platform (FR-018; ESLint allows fetch here and nowhere
// else). Every call goes to /api on this origin with the browser's session cookie; the session
// token itself is never visible here (FR-013). Changing requests carry the CSRF value held in
// memory (research R-02).
import createClient, { type Middleware } from "openapi-fetch";

import { ApiError, fromBody, UNAVAILABLE } from "./errors";
import type { paths } from "./schema";

const SAFE_METHODS = new Set(["GET", "HEAD", "OPTIONS"]);
export const CSRF_HEADER = "X-ADLC-CSRF";
/** The fixed value cookie-mode sign-in sends: it has no session yet (blocks login CSRF). */
export const SIGN_IN_CSRF = "sign-in";

let csrfToken: string | null = null;
let sessionEnded: (() => void) | null = null;

/** Set by the session when it learns the value (sign-in, /auth/me); cleared at sign-out. */
export function setCsrfToken(value: string | null): void {
  csrfToken = value;
}

/** Called once per expired or revoked session answer (401), unless a call opts out. */
export function onSessionEnded(handler: (() => void) | null): void {
  sessionEnded = handler;
}

const csrf: Middleware = {
  onRequest({ request }) {
    if (!SAFE_METHODS.has(request.method) && csrfToken !== null) {
      request.headers.set(CSRF_HEADER, csrfToken);
    }
    return request;
  },
};

export const api = createClient<paths>({
  baseUrl: new URL("/api", window.location.origin).href,
  credentials: "same-origin",
  // Look the global up per call, so test mocks installed after import still apply.
  fetch: (request: Request) => fetch(request),
});
api.use(csrf);

interface Answer<T> {
  data?: T;
  error?: unknown;
  response: Response;
}

export interface CallOptions {
  /** A 401 is an expected answer here (sign-in, the start-up session check). */
  quietSignedOut?: boolean;
}

/** The answer's data, or an ApiError for any failure (a network failure is "unavailable"). */
export async function call<T>(request: Promise<Answer<T>>, options: CallOptions = {}): Promise<T> {
  let answer: Answer<T>;
  try {
    answer = await request;
  } catch {
    throw UNAVAILABLE();
  }
  if (answer.response.ok) {
    return answer.data as T;
  }
  const error =
    answer.response.status === 0 ? UNAVAILABLE() : fromBody(answer.response.status, answer.error);
  if (error.kind === "not_signed_in" && options.quietSignedOut !== true) {
    sessionEnded?.();
  }
  throw error;
}

/** Offer an attachment for download only (FR-012): never shown inline, whatever its type. */
export async function downloadAttachment(
  runId: string,
  contentHash: string,
  fileName: string,
): Promise<void> {
  const blob = await call(
    api.GET("/runs/{run_id}/attachments/{content_hash}", {
      params: { path: { run_id: runId, content_hash: contentHash } },
      parseAs: "blob",
    }),
  );
  const bytes = new Blob([blob], { type: "application/octet-stream" });
  const url = URL.createObjectURL(bytes);
  const link = document.createElement("a");
  link.href = url;
  link.download = fileName;
  link.rel = "noopener";
  document.body.append(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

export interface RuntimeConfig {
  env: "dev" | "demo" | null;
  dashboard_refresh_seconds: number;
}

/** The page's runtime settings from adlc-web (research R-12): no secret, read once at start. */
export async function loadConfig(): Promise<RuntimeConfig> {
  try {
    const answer = await fetch(new URL("/config.json", window.location.origin), {
      credentials: "same-origin",
    });
    if (answer.ok) {
      return (await answer.json()) as RuntimeConfig;
    }
  } catch {
    // fall through to the defaults: the page still works, without the badge
  }
  return { env: null, dashboard_refresh_seconds: 10 };
}

export { ApiError };
