// Pages register their components here as they are rebuilt (US2 to US6). Each loads on first
// use, so a page's heavy parts (the grid, the charts) load only where they are needed.
import { lazy } from "react";

import { registerPage } from "../nav/registry";

registerPage(
  "run",
  lazy(() => import("./run/run-page").then((m) => ({ default: m.RunPage }))),
);
