// The runtime settings (environment badge, dashboard refresh), loaded once (research R-12).
import { createContext, use, useEffect, useState, type ReactNode } from "react";

import { loadConfig, type RuntimeConfig } from "./api/client";

const DEFAULT: RuntimeConfig = { env: null, dashboard_refresh_seconds: 10 };
const ConfigContext = createContext<RuntimeConfig>(DEFAULT);

export function ConfigProvider({
  children,
  value,
}: {
  children: ReactNode;
  /** Tests pass a fixed value instead of loading /config.json. */
  value?: RuntimeConfig;
}) {
  const [config, setConfig] = useState<RuntimeConfig>(value ?? DEFAULT);
  useEffect(() => {
    if (value !== undefined) return;
    let live = true;
    void loadConfig().then((loaded) => {
      if (live) setConfig(loaded);
    });
    return () => {
      live = false;
    };
  }, [value]);
  return <ConfigContext value={config}>{children}</ConfigContext>;
}

export function useConfig(): RuntimeConfig {
  return use(ConfigContext);
}
