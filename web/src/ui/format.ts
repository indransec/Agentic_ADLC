// How values read on screen (ported from adlc.ui.format): durations, money, times in UTC, KPI
// values and column names.
import { literalText, MISSING } from "./literal";

const ISO_TIME = /^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}/;
const UPPER: Record<string, string> = { id: "ID", usd: "USD", kpi: "KPI", sla: "SLA", url: "URL" };
const WORDS: Record<string, string> = { usecase: "use case" };
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

export function duration(seconds: number): string {
  const whole = Math.trunc(seconds);
  const sec = whole % 60;
  const minutes = Math.trunc(whole / 60) % 60;
  const hours = Math.trunc(whole / 3600) % 24;
  const days = Math.trunc(whole / 86400);
  const parts = [days ? `${days}d` : "", hours ? `${hours}h` : "", minutes ? `${minutes}m` : ""];
  return parts.filter(Boolean).join(" ") || `${sec}s`;
}

export function money(value: unknown): string {
  if (value === null || value === undefined || value === "") return MISSING;
  const amount = typeof value === "number" ? value : Number(value);
  if (Number.isNaN(amount)) return literalText(value);
  const digits = Math.abs(amount) < 1 ? 4 : 2;
  return `$${amount.toLocaleString("en-US", { minimumFractionDigits: digits, maximumFractionDigits: digits })}`;
}

export function parseTime(value: unknown): Date | null {
  if (typeof value !== "string" || !ISO_TIME.test(value)) return null;
  let text = value.replace(" ", "T");
  if (!/(Z|[+-]\d{2}:?\d{2})$/.test(text)) text += "Z";
  const parsed = new Date(text);
  return Number.isNaN(parsed.getTime()) ? null : parsed;
}

const pad = (n: number) => String(n).padStart(2, "0");

/** A time as people read it, in UTC: 19 Nov 2026, 14:05 UTC. */
export function when(value: unknown): string {
  const parsed = parseTime(value);
  if (parsed === null) {
    return literalText(value);
  }
  const month = MONTHS[parsed.getUTCMonth()] ?? "";
  return `${parsed.getUTCDate()} ${month} ${parsed.getUTCFullYear()}, ${pad(parsed.getUTCHours())}:${pad(parsed.getUTCMinutes())} UTC`;
}

/** How long ago (or how far ahead) a time is: 5m ago, in 2h. */
export function ago(value: unknown, now: Date = new Date()): string {
  const parsed = parseTime(value);
  if (parsed === null) return MISSING;
  const seconds = (now.getTime() - parsed.getTime()) / 1000;
  if (Math.abs(seconds) < 60) return "just now";
  return seconds > 0 ? `${duration(Math.abs(seconds))} ago` : `in ${duration(-seconds)}`;
}

export function kpiValue(kpi: { value?: unknown; unit?: unknown }): string {
  const { value, unit } = kpi;
  if (value === null || value === undefined) return "no data";
  if (typeof value === "number" && unit === "ratio") return `${(value * 100).toFixed(0)}%`;
  if (typeof value === "number" && unit === "seconds") return duration(value);
  return literalText(value);
}

/** A column name for people: usecase_id reads "Use case ID". */
export function label(key: string): string {
  const words = key
    .replaceAll("_", " ")
    .split(/\s+/)
    .filter(Boolean)
    .map((word) => UPPER[word.toLowerCase()] ?? WORDS[word.toLowerCase()] ?? word);
  const text = words.join(" ");
  return text.slice(0, 1).toUpperCase() + text.slice(1);
}
