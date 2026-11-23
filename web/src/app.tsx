// The application: providers, then routes built from the page registry (FR-002).
import { QueryClientProvider } from "@tanstack/react-query";
import { Suspense, useMemo, useState, type ComponentType } from "react";
import { BrowserRouter, Navigate, Outlet, Route, Routes, useSearchParams } from "react-router";

import { createQueryClient } from "./api/queries";
import { RequireSession } from "./auth/require-session";
import { SessionProvider } from "./auth/session-context";
import { SignInPage } from "./auth/sign-in-page";
import { ConfigProvider } from "./config";
import { pagePath } from "./nav/navigate";
import { pages } from "./nav/registry";
import { Sidebar } from "./nav/sidebar";
import "./pages";
import { PlaceholderPage } from "./pages/placeholder/placeholder-page";
import { PageHeader } from "./ui/page-header";

function placeholder(title: string): ComponentType {
  const Page = () => <PlaceholderPage title={title} />;
  Page.displayName = `Placeholder(${title})`;
  return Page;
}

function Shell() {
  return (
    <RequireSession>
      <div className="shell">
        <Sidebar />
        <main>
          <Suspense fallback={<p className="caption">Loading…</p>}>
            <Outlet />
          </Suspense>
        </main>
      </div>
    </RequireSession>
  );
}

/** "/" opens the Inbox, or the run of an old evidence link (?run=). */
function Home() {
  const [params] = useSearchParams();
  const run = params.get("run");
  return <Navigate to={run !== null ? pagePath("run", { run }) : pagePath("inbox")} replace />;
}

function NotFound() {
  return (
    <>
      <PageHeader title="Page not found" />
      <p>
        <a href={pagePath("inbox")}>Open the Inbox</a>
      </p>
    </>
  );
}

export function AppRoutes() {
  const entries = useMemo(() => pages(placeholder), []);
  return (
    <SessionProvider>
      <Routes>
        <Route path="/sign-in" element={<SignInPage />} />
        <Route path="/" element={<Home />} />
        <Route element={<Shell />}>
          {entries.map(({ id, path, component: Page }) => (
            <Route key={id} path={path} element={<Page />} />
          ))}
          <Route path="*" element={<NotFound />} />
        </Route>
      </Routes>
    </SessionProvider>
  );
}

export function App() {
  const [client] = useState(createQueryClient);
  return (
    <QueryClientProvider client={client}>
      <ConfigProvider>
        <BrowserRouter>
          <AppRoutes />
        </BrowserRouter>
      </ConfigProvider>
    </QueryClientProvider>
  );
}
