// An artifact table in AG Grid Community (T045): editable cells, add and remove rows, keyboard
// navigation and virtualised rows for large tables; read-only when not editable. Cells use AG
// Grid's text rendering only (no HTML renderers), so cell text is never interpreted (FR-010).
import { AllCommunityModule, ModuleRegistry, type ColDef, type GridApi } from "ag-grid-community";
import { AgGridReact } from "ag-grid-react";
import { useMemo, useRef, useState } from "react";

import { literalText } from "../../ui/literal";

ModuleRegistry.registerModules([AllCommunityModule]);

export type Row = Record<string, unknown>;

export interface ArtifactGridProps {
  artifactId: string;
  rows: readonly Row[];
  /** The spec's columns, in order; default: every key, in first-seen order. */
  columns: readonly string[];
  editable: boolean;
  /** Called with the whole table after each change (edit, add, remove). */
  onChange?: (rows: Row[]) => void;
}

const AUTO_HEIGHT_ROWS = 15;

export function ArtifactGrid({ artifactId, rows, columns, editable, onChange }: ArtifactGridProps) {
  const [data, setData] = useState<Row[]>(() => rows.map((r) => ({ ...r })));
  const grid = useRef<GridApi<Row> | null>(null);
  const shown = useMemo(
    () => (columns.length > 0 ? columns : [...new Set(rows.flatMap((r) => Object.keys(r)))]),
    [columns, rows],
  );
  const columnDefs = useMemo<ColDef<Row>[]>(
    () =>
      shown.map((field) => ({
        field,
        headerName: field, // the spec's names, as they are
        editable,
        valueFormatter: ({ value }: { value: unknown }) =>
          value === null || value === undefined ? "" : literalText(value),
      })),
    [shown, editable],
  );

  function publish(next: Row[]) {
    setData(next);
    onChange?.(next);
  }

  const large = data.length > AUTO_HEIGHT_ROWS;
  return (
    <div>
      <div
        className="artifact-grid"
        style={large ? { height: 420 } : undefined}
        aria-label={`${artifactId} table`}
        role="group"
      >
        <AgGridReact<Row>
          rowData={data}
          columnDefs={columnDefs}
          defaultColDef={{ resizable: true, sortable: false, minWidth: 110 }}
          domLayout={large ? "normal" : "autoHeight"}
          {...(editable ? { rowSelection: { mode: "multiRow" as const } } : {})}
          stopEditingWhenCellsLoseFocus
          // One Tab stop per grid (the ARIA grid pattern): arrow keys move between cells, Tab
          // leaves the grid, so the decision is not hundreds of Tab presses away (FR-028).
          tabToNextCell={() => false}
          onGridReady={(event) => {
            grid.current = event.api;
          }}
          onCellValueChanged={() => {
            const next: Row[] = [];
            grid.current?.forEachNode((node) => {
              if (node.data !== undefined) next.push({ ...node.data });
            });
            publish(next);
          }}
        />
      </div>
      {editable && (
        <p className="grid-actions">
          <button
            type="button"
            onClick={() => {
              publish([...data, Object.fromEntries(shown.map((c) => [c, ""]))]);
            }}
          >
            Add row to {artifactId}
          </button>{" "}
          <button
            type="button"
            onClick={() => {
              const selected = new Set(grid.current?.getSelectedRows() ?? []);
              if (selected.size > 0) publish(data.filter((row) => !selected.has(row)));
            }}
          >
            Remove selected rows from {artifactId}
          </button>
        </p>
      )}
    </div>
  );
}
