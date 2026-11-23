// Renders a component the way the application does: inside the router and the query client.
// Each call gets a fresh query client with retries off, so a test sees an error at once.
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, type RenderResult } from "@testing-library/react";
import type { ReactElement } from "react";
import { MemoryRouter } from "react-router";

export interface RenderOptions {
  /** The address the page opens at, e.g. "/run?run=UC-0001/T0/run-1". */
  route?: string;
}

export function freshQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
}

export function renderWithApp(ui: ReactElement, options: RenderOptions = {}): RenderResult {
  const client = freshQueryClient();
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[options.route ?? "/"]}>{ui}</MemoryRouter>
    </QueryClientProvider>,
  );
}
