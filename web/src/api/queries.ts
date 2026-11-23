// Query keys and the query client (research R-07). Reads are cached per key; a mutation
// invalidates what it changed. Polling stops while the tab is hidden, and only one refresh runs
// at a time per key (TanStack Query's default de-duplication).
import { QueryClient } from "@tanstack/react-query";

import { isApiError } from "./errors";

export const keys = {
  me: ["me"] as const,
  inbox: ["inbox"] as const,
  changes: ["changes"] as const,
  proposedEvents: ["events", "proposed"] as const,
  usecases: (mine: boolean) => ["usecases", { mine }] as const,
  usecase: (usecaseId: string) => ["usecase", usecaseId] as const,
  run: (runId: string) => ["run", runId] as const,
  artifactHistory: (runId: string, artifactId: string) =>
    ["run", runId, "history", artifactId] as const,
  runTimeline: (runId: string) => ["run", runId, "timeline"] as const,
  journey: (usecaseId: string) => ["journey", usecaseId] as const,
  kpis: (usecaseId: string) => ["kpis", usecaseId] as const,
  portfolio: (filters: Record<string, string>) => ["portfolio", filters] as const,
  activity: (filters: Record<string, string>) => ["activity", filters] as const,
  deadLetters: ["dead-letters"] as const,
  deadLetter: (eventId: string) => ["dead-letters", eventId] as const,
};

/** Retry once on "unavailable" only: every other answer is the platform's decision. */
export function createQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: {
        retry: (failures, error) =>
          failures < 1 && isApiError(error) && error.kind === "unavailable",
        refetchOnWindowFocus: false,
        refetchIntervalInBackground: false,
        staleTime: 5_000,
      },
      mutations: { retry: false },
    },
  });
}
