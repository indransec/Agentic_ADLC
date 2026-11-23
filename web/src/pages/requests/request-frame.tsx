// What every request page shares: the run (from ?run=), its summary bar, and the states before
// it loads or when it cannot be found.
import type { ReactNode } from "react";
import { useSearchParams } from "react-router";

import { pagePath } from "../../nav/navigate";
import { ErrorMessage } from "../../ui/error-message";
import { PageHeader } from "../../ui/page-header";
import { SummaryBar } from "../run/summary-bar";
import type { RunDetail } from "../run/types";
import { useRun } from "../run/use-run";

export interface RequestFrameProps {
  title: string;
  caption: string;
  /** Shown when the address names no run (or no request). */
  openFrom: string;
  /** Other ids the page needs from the address. */
  needs?: readonly string[];
  children: (detail: RunDetail, params: URLSearchParams) => ReactNode;
}

export function RequestFrame({
  title,
  caption,
  openFrom,
  needs = [],
  children,
}: RequestFrameProps) {
  const [params] = useSearchParams();
  const runId = params.get("run") ?? "";
  const found = useRun(runId);
  if (runId === "" || needs.some((n) => (params.get(n) ?? "") === "")) {
    return (
      <>
        <PageHeader title={title} />
        <p className="empty">{openFrom}</p>
      </>
    );
  }
  if (found.error !== null) {
    return (
      <>
        <PageHeader title={title} />
        <ErrorMessage error={found.error} />
        <p>
          <a href={pagePath("inbox")}>Open the Inbox</a>
        </p>
      </>
    );
  }
  if (found.data === undefined) {
    return (
      <>
        <PageHeader title={title} />
        <p className="caption">Loading…</p>
      </>
    );
  }
  return (
    <>
      <PageHeader title={title} caption={caption} />
      <SummaryBar detail={found.data} />
      {children(found.data, params)}
    </>
  );
}
