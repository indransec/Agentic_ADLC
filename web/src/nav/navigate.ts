// Opening a page by its registry id, with its query parameters (FR-003).
import { useCallback } from "react";
import { useNavigate } from "react-router";

import { pageEntry } from "./registry";

export type Params = Readonly<Record<string, string | undefined>>;

export function pagePath(id: string, params: Params = {}): string {
  const entry = pageEntry(id);
  const query = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== "") query.set(key, value);
  }
  const text = query.toString();
  return text === "" ? entry.path : `${entry.path}?${text}`;
}

export function useOpenPage(): (id: string, params?: Params) => void {
  const navigate = useNavigate();
  return useCallback(
    (id: string, params: Params = {}) => void navigate(pagePath(id, params)),
    [navigate],
  );
}

/** Only a same-origin path is followed after sign-in (no open redirect). */
export function safeNext(next: string | null): string {
  if (next === null || !next.startsWith("/") || next.startsWith("//") || next.startsWith("/\\")) {
    return pagePath("inbox");
  }
  return next;
}
