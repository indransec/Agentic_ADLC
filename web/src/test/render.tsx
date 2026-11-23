// Renders like the application does: query client, runtime config, router and session. Each call
// gets a fresh query client with retries off, so a test sees an error at once.
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, type RenderResult } from "@testing-library/react";
import type { ReactElement } from "react";
import { MemoryRouter, Route, Routes, useLocation } from "react-router";

import { AppRoutes } from "../app";
import { SessionProvider } from "../auth/session-context";
import { ConfigProvider } from "../config";
import type { RuntimeConfig } from "../api/client";

export const TEST_CONFIG: RuntimeConfig = { env: "dev", dashboard_refresh_seconds: 10 };

export interface RenderOptions {
  /** The address the page opens at, e.g. "/run?run=UC-0001/T0/run-1". */
  route?: string;
  config?: RuntimeConfig;
}

export function freshQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
}

/** Shows where the router is, for assertions on navigation. */
function Where() {
  const location = useLocation();
  return <output data-testid="where">{`${location.pathname}${location.search}`}</output>;
}

/** One component inside the providers (a signed-in session needs the signedIn() handler). */
export function renderWithApp(ui: ReactElement, options: RenderOptions = {}): RenderResult {
  return render(
    <QueryClientProvider client={freshQueryClient()}>
      <ConfigProvider value={options.config ?? TEST_CONFIG}>
        <MemoryRouter initialEntries={[options.route ?? "/"]}>
          <SessionProvider>
            <Routes>
              <Route path="*" element={ui} />
            </Routes>
            <Where />
          </SessionProvider>
        </MemoryRouter>
      </ConfigProvider>
    </QueryClientProvider>,
  );
}

/** The whole application at an address (routes, shell, session guard). */
export function renderApp(options: RenderOptions = {}): RenderResult {
  return render(
    <QueryClientProvider client={freshQueryClient()}>
      <ConfigProvider value={options.config ?? TEST_CONFIG}>
        <MemoryRouter initialEntries={[options.route ?? "/"]}>
          <AppRoutes />
          <Where />
        </MemoryRouter>
      </ConfigProvider>
    </QueryClientProvider>,
  );
}
