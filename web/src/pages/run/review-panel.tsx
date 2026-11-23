// What the sign-off rests on besides the artifacts (T038, SA 8.2): the reviewer's
// recommendation. Its reason, root cause and findings were written by an agent: literal text.
import { DataTable } from "../../ui/data-table";
import { Literal } from "../../ui/literal";
import { knownStatus } from "../../ui/status";
import { StatusBadge } from "../../ui/status-badge";
import type { RunDetail } from "./types";

const asList = (value: unknown): unknown[] => (Array.isArray(value) ? value : []);

export function ReviewPanel({ recommendation }: { recommendation: RunDetail["recommendation"] }) {
  return (
    <section aria-labelledby="recommendation-heading">
      <h2 id="recommendation-heading">Reviewer recommendation</h2>
      {recommendation === null ? (
        <p className="empty">No recommendation yet.</p>
      ) : (
        <div className="card">
          <p>
            <span className="caption">Recommends </span>
            {knownStatus(recommendation["status"]) !== undefined ? (
              <StatusBadge value={recommendation["status"]} />
            ) : (
              <Literal value={recommendation["status"]} />
            )}
          </p>
          <p className="caption">Reason</p>
          <Literal as="p" value={recommendation["reason"]} />
          {recommendation["root_cause"] !== null && recommendation["root_cause"] !== undefined && (
            <>
              <p className="caption">Root cause</p>
              <Literal as="p" value={recommendation["root_cause"]} />
            </>
          )}
          {asList(recommendation["items"]).length > 0 && (
            <>
              <p className="caption">Checklist</p>
              <DataTable rows={asList(recommendation["items"])} />
            </>
          )}
          {asList(recommendation["findings"]).length > 0 && (
            <>
              <p className="caption">Findings</p>
              <ul>
                {asList(recommendation["findings"]).map((finding, index) => (
                  <li key={index}>
                    <Literal value={finding} />
                  </li>
                ))}
              </ul>
            </>
          )}
        </div>
      )}
    </section>
  );
}
