export function formatMs(ms: number | null | undefined): string {
  if (ms === null || ms === undefined) return "n/a";
  return ms >= 1000 ? `${(ms / 1000).toFixed(2)} s` : `${ms.toFixed(ms < 10 ? 1 : 0)} ms`;
}

export function formatPct(x: number | null | undefined, digits = 1): string {
  return x === null || x === undefined ? "n/a" : `${(x * 100).toFixed(digits)}%`;
}

export function formatNumber(v: unknown): string {
  if (typeof v !== "number") return String(v);
  if (Number.isInteger(v)) return v.toLocaleString("en-IN");
  return v.toLocaleString("en-IN", { maximumFractionDigits: 2 });
}

export function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return "never";
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
}

export function cn(...parts: (string | false | null | undefined)[]): string {
  return parts.filter(Boolean).join(" ");
}
