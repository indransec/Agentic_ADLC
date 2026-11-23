// A read-only table of rows (a semantic <table>: accessible and keyboard-friendly). Every cell is
// literal text (FR-010). As in the previous application: a column whose values are all times
// reads as UTC times, a numeric cost column as dollars, nested values as JSON text, and column
// names as words (unless rawLabels: an artifact's columns are the spec's names).
import { label, money, parseTime, when } from "./format";
import { literalText } from "./literal";

export interface DataTableProps {
  rows: readonly unknown[];
  /** Columns to show, in order; default: every key, in first-seen order. */
  columns?: readonly string[] | undefined;
  /** Platform words shown when there are no rows. */
  emptyText?: string;
  /** Keep column names as they are (artifact columns). */
  rawLabels?: boolean;
  caption?: string;
}

type Row = Readonly<Record<string, unknown>>;

const isRow = (value: unknown): value is Row =>
  typeof value === "object" && value !== null && !Array.isArray(value);

function columnFormat(rows: readonly Row[], column: string): (value: unknown) => string {
  const values = rows
    .map((r) => r[column])
    .filter((v) => v !== null && v !== undefined && v !== "");
  if (values.length > 0 && values.every((v) => parseTime(v) !== null)) return when;
  if (
    values.length > 0 &&
    column.toLowerCase().includes("cost") &&
    values.every((v) => typeof v === "number")
  ) {
    return money;
  }
  return literalText;
}

export function DataTable({
  rows,
  columns,
  emptyText = "None.",
  rawLabels = false,
  caption,
}: DataTableProps) {
  const data = rows.map((r) => (isRow(r) ? r : { value: r }));
  if (data.length === 0) {
    return <p className="empty">{emptyText}</p>;
  }
  const shown = columns ?? [...new Set(data.flatMap((r) => Object.keys(r)))];
  const formats = new Map(shown.map((c) => [c, columnFormat(data, c)]));
  return (
    <div className="table-wrap">
      <table className="data-table">
        {caption !== undefined && <caption>{caption}</caption>}
        <thead>
          <tr>
            {shown.map((column) => (
              <th key={column} scope="col">
                {rawLabels ? column : label(column)}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {data.map((row, index) => (
            // Rows have no stable id in general; their order is the platform's.
            <tr key={index}>
              {shown.map((column) => (
                <td key={column}>{(formats.get(column) ?? literalText)(row[column])}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
