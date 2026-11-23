// Every page of the application, in sidebar order (FR-002; contracts/pages.md). The router, the
// sidebar and navigate() are all built from this one table; a later mode (the 019 console) would
// add a field here and filter on it, nothing else.
import type { ComponentType } from "react";

export type Section = "Work" | "Delivery" | "Insights" | "Operations";

export interface PageEntry {
  /** kebab-case, unique */
  id: string;
  /** The page title (platform words) */
  title: string;
  /** The sidebar section; null for pages opened from another page */
  section: Section | null;
  /** The address path; ids travel as query parameters (run ids contain "/") */
  path: string;
  /** Icon name for the sidebar */
  icon: string;
  inSidebar: boolean;
  /** Query parameters this page keeps in the address (FR-003) */
  params: readonly string[];
  component: ComponentType;
}

export const SECTIONS: readonly Section[] = ["Work", "Delivery", "Insights", "Operations"];

type Entry = Omit<PageEntry, "component"> & { component?: ComponentType };

const ENTRIES: readonly Entry[] = [
  {
    id: "inbox",
    title: "Inbox",
    section: "Work",
    path: "/inbox",
    icon: "inbox",
    inSidebar: true,
    params: [],
  },
  {
    id: "new-use-case",
    title: "New use case",
    section: "Work",
    path: "/usecases/new",
    icon: "add",
    inSidebar: true,
    params: [],
  },
  {
    id: "use-cases",
    title: "Use cases",
    section: "Delivery",
    path: "/usecases",
    icon: "folder",
    inSidebar: true,
    params: ["mine", "usecase"],
  },
  {
    id: "journey",
    title: "Journey",
    section: "Delivery",
    path: "/journey",
    icon: "timeline",
    inSidebar: true,
    params: ["usecase"],
  },
  {
    id: "activity",
    title: "Activity",
    section: "Delivery",
    path: "/activity",
    icon: "history",
    inSidebar: true,
    params: ["usecase", "terminal", "actor", "step"],
  },
  {
    id: "portfolio",
    title: "Portfolio",
    section: "Insights",
    path: "/portfolio",
    icon: "insights",
    inSidebar: true,
    params: ["tier", "status"],
  },
  {
    id: "dead-letters",
    title: "Dead letters",
    section: "Operations",
    path: "/dead-letters",
    icon: "report",
    inSidebar: true,
    params: ["event"],
  },
  {
    id: "run",
    title: "Run",
    section: null,
    path: "/run",
    icon: "play",
    inSidebar: false,
    params: ["run"],
  },
  {
    id: "clarification",
    title: "Clarification",
    section: null,
    path: "/clarification",
    icon: "help",
    inSidebar: false,
    params: ["run", "id"],
  },
  {
    id: "escalation",
    title: "Escalation",
    section: null,
    path: "/escalation",
    icon: "priority",
    inSidebar: false,
    params: ["run"],
  },
  {
    id: "waiver",
    title: "Waiver",
    section: null,
    path: "/waiver",
    icon: "gpp",
    inSidebar: false,
    params: ["run", "id"],
  },
];

/** Components are attached by pages/index.ts, so this table stays free of page imports. */
const components = new Map<string, ComponentType>();

export function registerPage(id: string, component: ComponentType): void {
  if (!ENTRIES.some((e) => e.id === id)) throw new Error(`no page ${id} in the registry`);
  components.set(id, component);
}

export function pages(placeholder: (title: string) => ComponentType): PageEntry[] {
  return ENTRIES.map((e) => ({ ...e, component: components.get(e.id) ?? placeholder(e.title) }));
}

export function pageEntry(id: string): Entry {
  const found = ENTRIES.find((e) => e.id === id);
  if (found === undefined) throw new Error(`no page ${id} in the registry`);
  return found;
}

export const ENTRY_LIST = ENTRIES;
