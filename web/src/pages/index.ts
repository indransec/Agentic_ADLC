// Pages register their components here as they are rebuilt (US2 to US6). Each loads on first
// use, so a page's heavy parts (the grid, the charts) load only where they are needed.
import { lazy } from "react";

import { registerPage } from "../nav/registry";

registerPage(
  "run",
  lazy(() => import("./run/run-page").then((m) => ({ default: m.RunPage }))),
);
registerPage(
  "inbox",
  lazy(() => import("./inbox/inbox-page").then((m) => ({ default: m.InboxPage }))),
);
registerPage(
  "new-use-case",
  lazy(() => import("./intake/intake-page").then((m) => ({ default: m.IntakePage }))),
);
registerPage(
  "clarification",
  lazy(() =>
    import("./requests/clarification-page").then((m) => ({ default: m.ClarificationPage })),
  ),
);
registerPage(
  "escalation",
  lazy(() => import("./requests/escalation-page").then((m) => ({ default: m.EscalationPage }))),
);
registerPage(
  "waiver",
  lazy(() => import("./requests/waiver-page").then((m) => ({ default: m.WaiverPage }))),
);
