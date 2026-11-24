import type { CellValue } from "../types/api";

export type ChartType = "bar" | "line" | "pie";

export interface ChartPlan {
  type: ChartType;
  alternatives: ChartType[];
  labelKey: string;
  valueKeys: string[];
  data: Record<string, string | number>[];
  reason: string;
  truncated: boolean;
}

const MAX_POINTS = 30;
const DATE_NAME = /(date|month|day|week|year|time|period|quarter)/i;
const ID_NAME = /(^|_)id$/i;
const PIE_LABEL = /(status|method|type|category|state|segment|channel)/i;
const ISO_DATE = /^\d{4}-\d{2}(-\d{2})?([T ][\d:.+Z-]*)?$/;

function isNumeric(v: CellValue): boolean {
  return typeof v === "number" && Number.isFinite(v);
}

/** Recommend a chart for a result set, or null when a chart would not be meaningful. */
export function recommendChart(columns: string[], rows: CellValue[][]): ChartPlan | null {
  if (columns.length < 2 || rows.length < 2) return null;

  const kind = columns.map((name, i) => {
    const vals = rows.map((r) => r[i]).filter((v) => v !== null && v !== undefined);
    if (vals.length === 0) return "empty" as const;
    const numeric = vals.filter(isNumeric).length / vals.length >= 0.95;
    if (numeric) return ID_NAME.test(name) ? ("id" as const) : ("number" as const);
    const dateLike = vals.every((v) => typeof v === "string" && ISO_DATE.test(v));
    if (dateLike || (DATE_NAME.test(name) && vals.every((v) => typeof v === "string" && !Number.isNaN(Date.parse(String(v)))))) {
      return "date" as const;
    }
    return "category" as const;
  });

  const labelIdx = kind.findIndex((k) => k === "date") !== -1 ? kind.indexOf("date") : kind.indexOf("category");
  const fallbackLabel = labelIdx === -1 ? kind.indexOf("id") : labelIdx;
  const measureIdx = kind.map((k, i) => (k === "number" && i !== fallbackLabel ? i : -1)).filter((i) => i !== -1).slice(0, 3);
  if (fallbackLabel === -1 || measureIdx.length === 0) return null;

  const isDate = kind[fallbackLabel] === "date";
  // too many distinct categories is unreadable; too few rows on a date axis is better as bars
  const limited = rows.slice(0, MAX_POINTS);
  const labels = limited.map((r) => String(r[fallbackLabel]));
  if (!isDate && new Set(labels).size < labels.length * 0.6 && measureIdx.length === 1) return null; // repeated labels: not a clean series

  const labelKey = columns[fallbackLabel];
  const valueKeys = measureIdx.map((i) => columns[i]);
  const data = limited.map((r) => {
    const point: Record<string, string | number> = { [labelKey]: isDate ? String(r[fallbackLabel]).slice(0, 10) : String(r[fallbackLabel]) };
    measureIdx.forEach((i) => {
      point[columns[i]] = Number(r[i] ?? 0);
    });
    return point;
  });

  const positive = valueKeys.length === 1 && data.every((d) => Number(d[valueKeys[0]]) > 0);
  const pieOk = !isDate && positive && data.length <= 8;
  const alternatives: ChartType[] = isDate ? ["line", "bar"] : pieOk ? ["bar", "pie"] : ["bar"];

  let type: ChartType;
  let reason: string;
  if (isDate && data.length >= 3) {
    type = "line";
    reason = `"${labelKey}" is a time axis, so a line chart shows the trend.`;
  } else if (pieOk && data.length <= 6 && PIE_LABEL.test(labelKey)) {
    type = "pie";
    reason = `A few categories of "${labelKey}" with positive values read well as shares of a whole.`;
  } else {
    type = "bar";
    reason = `Comparing "${valueKeys.join('", "')}" across "${labelKey}".`;
  }
  return { type, alternatives, labelKey, valueKeys, data, reason, truncated: rows.length > MAX_POINTS };
}
