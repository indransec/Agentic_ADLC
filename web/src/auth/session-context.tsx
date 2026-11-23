// The signed-in person (T033). The session itself is an HttpOnly cookie the page cannot read;
// this holds only the person and the CSRF value, in memory (FR-013). Any 401 from the platform
// ends the session here and opens sign-in, keeping the address to come back to.
import { useQueryClient } from "@tanstack/react-query";
import {
  createContext,
  use,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { useLocation, useNavigate } from "react-router";

import { api, call, CSRF_HEADER, onSessionEnded, setCsrfToken, SIGN_IN_CSRF } from "../api/client";
import { isApiError } from "../api/errors";
import type { components } from "../api/schema";

export type Person = components["schemas"]["PersonOut"];
export type SessionStatus = "checking" | "signed-in" | "signed-out";

export interface Session {
  status: SessionStatus;
  person: Person | null;
  /** Why the start-up check failed, when it was not simply "not signed in". */
  problem: unknown;
  /** True once the person signed out on purpose: sign-in then opens without a page to return to. */
  signedOutByChoice: boolean;
  signIn: (account: string, password: string) => Promise<void>;
  signOut: () => Promise<void>;
}

const SessionContext = createContext<Session | null>(null);

export function SessionProvider({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<SessionStatus>("checking");
  const [person, setPerson] = useState<Person | null>(null);
  const [problem, setProblem] = useState<unknown>(null);
  const [signedOutByChoice, setSignedOutByChoice] = useState(false);
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const location = useLocation();
  const here = useRef("");
  // Once the person signs in (or out), the start-up check's late answer must not override it.
  const settled = useRef(false);
  useEffect(() => {
    here.current = `${location.pathname}${location.search}`;
  }, [location]);

  const forget = useCallback(() => {
    setCsrfToken(null);
    setPerson(null);
    setStatus("signed-out");
    queryClient.clear();
  }, [queryClient]);

  useEffect(() => {
    onSessionEnded(() => {
      forget();
      const next = here.current.startsWith("/sign-in")
        ? ""
        : `?next=${encodeURIComponent(here.current)}`;
      void navigate(`/sign-in${next}`, { replace: true });
    });
    return () => {
      onSessionEnded(null);
    };
  }, [forget, navigate]);

  useEffect(() => {
    let live = true;
    call(api.GET("/auth/me"), { quietSignedOut: true })
      .then((me) => {
        if (!live || settled.current) return;
        setCsrfToken(me.csrf_token ?? null);
        setPerson({
          account_name: me.account_name,
          display_name: me.display_name,
          roles: me.roles,
        });
        setStatus("signed-in");
      })
      .catch((error: unknown) => {
        if (!live || settled.current) return;
        if (!(isApiError(error) && error.kind === "not_signed_in")) setProblem(error);
        setStatus("signed-out");
      });
    return () => {
      live = false;
    };
  }, []);

  const signIn = useCallback(async (account: string, password: string) => {
    const answer = await call(
      api.POST("/auth/sign-in", {
        body: { account_name: account, password, session: "cookie" },
        headers: { [CSRF_HEADER]: SIGN_IN_CSRF },
      }),
      { quietSignedOut: true },
    );
    if (!("csrf_token" in answer)) {
      throw new Error("the platform answered a bearer session to a cookie sign-in");
    }
    settled.current = true;
    setCsrfToken(answer.csrf_token);
    setPerson(answer.person);
    setProblem(null);
    setSignedOutByChoice(false);
    setStatus("signed-in");
  }, []);

  const signOut = useCallback(async () => {
    try {
      await call(api.POST("/auth/sign-out"), { quietSignedOut: true });
    } catch {
      // signed out either way: the cookie is gone or the session already ended
    }
    settled.current = true;
    setSignedOutByChoice(true);
    forget(); // the session guard then opens sign-in, without a page to come back to
  }, [forget]);

  const value = useMemo<Session>(
    () => ({ status, person, problem, signedOutByChoice, signIn, signOut }),
    [status, person, problem, signedOutByChoice, signIn, signOut],
  );
  return <SessionContext value={value}>{children}</SessionContext>;
}

export function useSession(): Session {
  const session = use(SessionContext);
  if (session === null) throw new Error("useSession outside SessionProvider");
  return session;
}
