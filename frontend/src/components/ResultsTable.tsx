import { ArrowDown, ArrowUp, ChevronLeft, ChevronRight, Download } from "lucide-react";
import { useMemo, useState } from "react";
import type { CellValue, ExecuteResponse } from "../types/api";
import { downloadCsv } from "../utils/csv";
import { cn, formatMs, formatNumber } from "../utils/format";
import { Badge, Button } from "./ui";

const PAGE_SIZES = [10, 25, 50, 100];

function compare(a: CellValue, b: CellValue): number {
  if (a === b) return 0;
  if (a === null) return 1;
  if (b === null) return -1;
  if (typeof a === "number" && typeof b === "number") return a - b;
  return String(a).localeCompare(String(b), undefined, { numeric: true });
}

export function ResultsTable({ result }: { result: ExecuteResponse }) {
  const [page, setPage] = useState(0);
  const [pageSize, setPageSize] = useState(25);
  const [sort, setSort] = useState<{ col: number; dir: 1 | -1 } | null>(null);

  const rows = useMemo(() => {
    if (!sort) return result.rows;
    return [...result.rows].sort((a, b) => sort.dir * compare(a[sort.col], b[sort.col]));
  }, [result.rows, sort]);

  const pages = Math.max(1, Math.ceil(rows.length / pageSize));
  const current = Math.min(page, pages - 1);
  const slice = rows.slice(current * pageSize, (current + 1) * pageSize);

  function toggleSort(col: number) {
    setPage(0);
    setSort((s) => (s?.col === col ? (s.dir === 1 ? { col, dir: -1 } : null) : { col, dir: 1 }));
  }

  return (
    <div>
      <div className="flex flex-wrap items-center justify-between gap-2 px-4 py-3">
        <div className="flex flex-wrap items-center gap-2 text-sm text-slate-600">
          <span data-testid="row-count" className="font-medium text-slate-900">
            {result.row_count.toLocaleString()} {result.row_count === 1 ? "row" : "rows"}
          </span>
          <span className="text-slate-400">·</span>
          <span data-testid="exec-time">{formatMs(result.execution_time_ms)}</span>
          {result.truncated && (
            <Badge tone="amber" title="The server returns at most this many rows">
              limited to {result.max_rows.toLocaleString()} rows
            </Badge>
          )}
        </div>
        <Button
          variant="secondary"
          icon={<Download className="h-4 w-4" />}
          onClick={() => downloadCsv("querymind-results.csv", result.columns, result.rows)}
          disabled={result.rows.length === 0}
        >
          Download CSV
        </Button>
      </div>

      {result.rows.length === 0 ? (
        <p className="border-t border-slate-100 px-4 py-8 text-center text-sm text-slate-500">The query ran successfully and returned no rows.</p>
      ) : (
        <>
          <div className="max-h-[28rem] overflow-auto border-t border-slate-100">
            <table className="min-w-full text-left text-sm">
              <thead className="sticky top-0 bg-slate-50 text-xs uppercase tracking-wide text-slate-500">
                <tr>
                  <th className="w-10 px-3 py-2 text-right font-medium text-slate-400">#</th>
                  {result.columns.map((c, i) => (
                    <th key={`${c}-${i}`} scope="col" className="whitespace-nowrap px-3 py-2 font-medium">
                      <button type="button" className="inline-flex items-center gap-1 hover:text-slate-900" onClick={() => toggleSort(i)} aria-label={`Sort by ${c}`}>
                        {c}
                        {sort?.col === i && (sort.dir === 1 ? <ArrowUp className="h-3 w-3" /> : <ArrowDown className="h-3 w-3" />)}
                      </button>
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {slice.map((row, r) => (
                  <tr key={r} className="hover:bg-slate-50">
                    <td className="px-3 py-1.5 text-right text-xs text-slate-400">{current * pageSize + r + 1}</td>
                    {row.map((cell, c) => (
                      <td key={c} className={cn("whitespace-nowrap px-3 py-1.5", typeof cell === "number" && "text-right tabular-nums")}>
                        {cell === null ? <span className="text-slate-400">NULL</span> : typeof cell === "number" ? formatNumber(cell) : String(cell)}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="flex flex-wrap items-center justify-between gap-2 border-t border-slate-100 px-4 py-2 text-sm text-slate-600">
            <label className="flex items-center gap-2">
              Rows per page
              <select
                className="rounded-md border border-slate-300 bg-white px-2 py-1 text-sm"
                value={pageSize}
                onChange={(e) => {
                  setPageSize(Number(e.target.value));
                  setPage(0);
                }}
              >
                {PAGE_SIZES.map((n) => (
                  <option key={n} value={n}>
                    {n}
                  </option>
                ))}
              </select>
            </label>
            <div className="flex items-center gap-2">
              <span data-testid="page-indicator">
                Page {current + 1} of {pages}
              </span>
              <Button variant="ghost" aria-label="Previous page" disabled={current === 0} onClick={() => setPage(current - 1)} icon={<ChevronLeft className="h-4 w-4" />} />
              <Button variant="ghost" aria-label="Next page" disabled={current >= pages - 1} onClick={() => setPage(current + 1)} icon={<ChevronRight className="h-4 w-4" />} />
            </div>
          </div>
        </>
      )}
    </div>
  );
}
