// The platform's refusal in plain words (FR-008): the kind as platform words, the detail as
// literal text (it can echo input), never a stack trace.
import { isApiError, KIND_WORDS } from "../api/errors";
import { Literal } from "./literal";

export function ErrorMessage({ error }: { error: unknown }) {
  if (error === null || error === undefined) return null;
  if (!isApiError(error)) {
    return (
      <div role="alert" className="message error">
        Something went wrong in the page. Reload it and try again.
      </div>
    );
  }
  return (
    <div role="alert" className="message error">
      <p>The platform refused this: {KIND_WORDS[error.kind]}.</p>
      <Literal as="p" value={error.detail} />
    </div>
  );
}

/** A refusal about one field, shown beside that field (FR-008). */
export function fieldError(error: unknown, field: string): string | undefined {
  return isApiError(error) && error.field === field ? error.detail : undefined;
}
