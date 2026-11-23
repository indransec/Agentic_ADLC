// Platform answers for component tests, taken from the API's golden answers
// (tests/integration/api/golden, values made realistic). Each is checked against the generated
// schema, so a fixture that stops matching the platform fails the type check (T026).
import type { components } from "../api/schema";

import artifactsAttach from "./fixtures/artifacts-attach.json";
import artifactsHistory from "./fixtures/artifacts-history.json";
import artifactsSave from "./fixtures/artifacts-save.json";
import changesList from "./fixtures/changes-list.json";
import dashboardActivity from "./fixtures/dashboard-activity.json";
import dashboardJourney from "./fixtures/dashboard-journey.json";
import dashboardKpis from "./fixtures/dashboard-kpis.json";
import dashboardPortfolio from "./fixtures/dashboard-portfolio.json";
import dashboardTimeline from "./fixtures/dashboard-timeline.json";
import deadLettersDetail from "./fixtures/dead-letters-detail.json";
import deadLettersList from "./fixtures/dead-letters-list.json";
import eventsProposed from "./fixtures/events-proposed.json";
import inbox from "./fixtures/inbox.json";
import runsDecision from "./fixtures/runs-decision.json";
import runsDetail from "./fixtures/runs-detail.json";
import usecasesDetail from "./fixtures/usecases-detail.json";
import usecasesList from "./fixtures/usecases-list.json";
import usecasesVerify from "./fixtures/usecases-verify.json";

type S = components["schemas"];

export const fixtures = {
  person: {
    account_name: "product_owner-person",
    display_name: "Product Owner",
    roles: ["product_owner"],
  } satisfies S["PersonOut"],
  runDetail: runsDetail satisfies S["RunDetail"],
  runSummary: runsDecision satisfies S["RunSummary"],
  artifactSaved: artifactsSave satisfies S["ArtifactSaved"],
  runChanged: artifactsAttach satisfies S["RunChanged"],
  artifactHistory: artifactsHistory satisfies S["ArtifactHistoryEntry"][],
  inbox: inbox satisfies S["InboxItem"][],
  changes: changesList satisfies S["ChangeRequest"][],
  proposedEvents: eventsProposed satisfies S["ProposedEvent"][],
  usecases: usecasesList satisfies S["UseCaseListItem"][],
  usecaseJourney: usecasesDetail satisfies S["UseCaseJourney"],
  verification: usecasesVerify satisfies S["Verification"],
  journey: dashboardJourney satisfies S["Journey"],
  kpis: dashboardKpis satisfies S["Kpis"],
  portfolio: dashboardPortfolio satisfies S["Portfolio"],
  activity: dashboardActivity satisfies S["ActivityEntry"][],
  timeline: dashboardTimeline satisfies S["RunTimeline"],
  deadLetters: deadLettersList satisfies S["DeadLetter"][],
  deadLetter: deadLettersDetail satisfies S["DeadLetterDetail"],
};

/** Markup and script that must always be shown as literal text (from the 007 rendering test). */
export const HOSTILE = [
  "<script>alert(1)</script><b>bold</b>[click](http://evil.example)",
  "<img src=x onerror=alert(1)>[c](javascript:x).md",
] as const;
