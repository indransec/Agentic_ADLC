// Sign-in (T034): account and password; afterwards the page that sent the person here, if it is
// on this site (FR-013, N-03).
import { useState, type SyntheticEvent } from "react";
import { Navigate, useNavigate, useSearchParams } from "react-router";

import { safeNext } from "../nav/navigate";
import { EnvBadge } from "../ui/env-badge";
import { ErrorMessage } from "../ui/error-message";
import { useSession } from "./session-context";

export function SignInPage() {
  const { status, problem, signIn } = useSession();
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const next = safeNext(params.get("next"));
  const [account, setAccount] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);

  if (status === "signed-in") {
    return <Navigate to={next} replace />;
  }

  async function submit(event: SyntheticEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await signIn(account, password);
      void navigate(next, { replace: true });
    } catch (failure) {
      setError(failure);
      setBusy(false);
    }
  }

  return (
    <main className="sign-in">
      <img src="/logo.svg" alt="ADLC" width={168} />
      <h1>Sign in</h1>
      <p className="caption">Agentic delivery lifecycle: agents build, people decide.</p>
      <EnvBadge />
      <form onSubmit={(event) => void submit(event)}>
        <label htmlFor="account">Account</label>
        <input
          id="account"
          name="account"
          autoComplete="username"
          value={account}
          onChange={(e) => {
            setAccount(e.target.value);
          }}
          required
        />
        <label htmlFor="password">Password</label>
        <input
          id="password"
          name="password"
          type="password"
          autoComplete="current-password"
          value={password}
          onChange={(e) => {
            setPassword(e.target.value);
          }}
          required
        />
        <p>
          <button type="submit" className="primary" disabled={busy}>
            Sign in
          </button>
        </p>
      </form>
      <ErrorMessage error={error ?? problem} />
    </main>
  );
}
