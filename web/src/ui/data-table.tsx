// A read-only table of rows (a semantic <table>: accessible and keyboard-friendly). Every cell is
// literal text (FR-010); column names are the platform's keys in words. Large or editable tables
// use the artifact grid instead.
import { label } from "./format";
import { literalText } from "./literal";

export interface DataTableProps {
  rows: readonly Readonly<Record<string, unknown>>[];
  /** Columns to show, in order; default: the keys of the first row. */
  columns?: readonly string[];
  /** Platform words shown when there are no rows. */
  emptyText?: string;
  /** Formats a cell for reading (times, money); the result is still shown as text. */
  format?: (column: string, value: unknown) => string;
  caption?: string;
}

export function DataTable({ rows, columns, emptyText = "None.", format, caption }: DataTableProps) {
  if (rows.length === 0) {
    return <p className="empty">{emptyText}</p>;
  }
  const shown = columns ?? Object.keys(rows[0] ?? {});
  return (
    <div className="table-wrap">
      <table className="data-table">
        {caption !== undefined && <caption>{caption}</caption>}
        <thead>
          <tr>
            {shown.map((column) => (
              <th key={column} scope="col">
                {label(column)}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, index) => (
            // Rows have no stable id in general; their order is the platform's.
            <tr key={index}>
              {shown.map((column) => (
                <td key={column}>
                  {format ? format(column, row[column]) : literalText(row[column])}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
