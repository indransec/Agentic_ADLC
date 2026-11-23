// The platform's one error shape, {kind, detail, field?} (adlc.api.errors), and what the
// application does with each kind (data-model "Platform contract").

export type ErrorKind =
  | "not_signed_in"
  | "not_allowed"
  | "not_found"
  | "stale"
  | "wrong_state"
  | "invalid"
  | "unavailable"
  | "unknown";

const KINDS: readonly ErrorKind[] = [
  "not_signed_in",
  "not_allowed",
  "not_found",
  "stale",
  "wrong_state",
  "invalid",
  "unavailable",
];

/** How each kind reads in "The platform refused this: …" (platform words, never the detail). */
export const KIND_WORDS: Record<ErrorKind, string> = {
  not_signed_in: "not signed in",
  not_allowed: "not allowed",
  not_found: "not found",
  stale: "the run changed",
  wrong_state: "wrong state",
  invalid: "invalid input",
  unavailable: "the platform could not be reached",
  unknown: "unexpected answer",
};

export class ApiError extends Error {
  readonly status: number;
  readonly kind: ErrorKind;
  readonly detail: string;
  readonly field: string | undefined;

  constructor(status: number, kind: ErrorKind, detail: string, field?: string) {
    super(`${kind}: ${detail}`);
    this.name = "ApiError";
    this.status = status;
    this.kind = kind;
    this.detail = detail;
    this.field = field;
  }
}

export function isApiError(value: unknown): value is ApiError {
  return value instanceof ApiError;
}

/** An ApiError from an answer body; anything not in the platform's shape is "unknown". */
export function fromBody(status: number, body: unknown): ApiError {
  if (typeof body === "object" && body !== null) {
    const { kind, detail, field } = body as Record<string, unknown>;
    const known = KINDS.find((k) => k === kind);
    if (known !== undefined && typeof detail === "string") {
      return new ApiError(status, known, detail, typeof field === "string" ? field : undefined);
    }
  }
  return new ApiError(status, "unknown", `HTTP ${status}`);
}

export const UNAVAILABLE = (): ApiError =>
  new ApiError(0, "unavailable", "the platform could not be reached");
