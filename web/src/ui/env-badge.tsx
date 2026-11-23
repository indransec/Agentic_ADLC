// Which environment this is, so nobody mistakes a development stack for the demo.
import { useConfig } from "../config";

const NAMES = { dev: "Development", demo: "Demo" } as const;

export function EnvBadge() {
  const { env } = useConfig();
  if (env === null) return null;
  return <span className={`env-badge env-${env}`}>{NAMES[env]}</span>;
}
