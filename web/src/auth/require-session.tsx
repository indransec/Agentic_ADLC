// Every page needs a session; without one, sign-in opens and brings the person back here.
import type { ReactNode } from "react";
import { Navigate, useLocation } from "react-router";

import { useSession } from "./session-context";

export function RequireSession({ children }: { children: ReactNode }) {
  const { status, signedOutByChoice } = useSession();
  const location = useLocation();
  if (status === "checking") {
    return <p className="caption">Checking your session…</p>;
  }
  if (status === "signed-out") {
    if (signedOutByChoice) return <Navigate to="/sign-in" replace />;
    const next = encodeURIComponent(`${location.pathname}${location.search}`);
    return <Navigate to={`/sign-in?next=${next}`} replace />;
  }
  return children;
}
