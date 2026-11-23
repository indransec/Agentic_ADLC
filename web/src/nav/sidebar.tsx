// The sidebar: sections in registry order, the environment badge, who is signed in, sign-out.
import { NavLink } from "react-router";

import { useSession } from "../auth/session-context";
import { EnvBadge } from "../ui/env-badge";
import { ENTRY_LIST, SECTIONS } from "./registry";

export function Sidebar() {
  const { person, signOut } = useSession();
  return (
    <nav className="sidebar" aria-label="Pages">
      <div>
        <img src="/logo.svg" alt="ADLC" width={120} /> <EnvBadge />
      </div>
      {SECTIONS.map((section) => {
        const entries = ENTRY_LIST.filter((e) => e.inSidebar && e.section === section);
        if (entries.length === 0) return null;
        return (
          <div key={section}>
            <h2>{section}</h2>
            <ul>
              {entries.map((entry) => (
                <li key={entry.id}>
                  <NavLink to={entry.path}>{entry.title}</NavLink>
                </li>
              ))}
            </ul>
          </div>
        );
      })}
      {person !== null && (
        <div className="person">
          <p>
            Signed in as <span>{person.display_name}</span>
          </p>
          <p>{person.roles.join(", ")}</p>
          <button type="button" onClick={() => void signOut()}>
            Sign out
          </button>
        </div>
      )}
    </nav>
  );
}
