import type { CellValue } from "../types/api";

function escapeCell(v: CellValue): string {
  if (v === null || v === undefined) return "";
  const s = String(v);
  // neutralise spreadsheet formula injection while keeping negative numbers readable
  const safe = /^[=+@\t\r]/.test(s) || (/^-/.test(s) && typeof v === "string" && !/^-?\d/.test(s)) ? `'${s}` : s;
  return /[",\n\r]/.test(safe) ? `"${safe.replace(/"/g, '""')}"` : safe;
}

export function toCsv(columns: string[], rows: CellValue[][]): string {
  const lines = [columns.map((c) => escapeCell(c)).join(",")];
  for (const row of rows) lines.push(row.map(escapeCell).join(","));
  return lines.join("\r\n");
}

export function downloadCsv(filename: string, columns: string[], rows: CellValue[][]): void {
  const blob = new Blob(["﻿" + toCsv(columns, rows)], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}
