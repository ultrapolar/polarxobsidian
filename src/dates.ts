// Date helpers. Pure; no obsidian import so they can be unit-tested with node.

export function toIsoDate(date: Date): string {
  const y = date.getFullYear();
  const m = String(date.getMonth() + 1).padStart(2, "0");
  const d = String(date.getDate()).padStart(2, "0");
  return `${y}-${m}-${d}`;
}

export function isValidIsoDate(value: string): boolean {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) return false;
  const parsed = new Date(`${value}T00:00:00`);
  return !Number.isNaN(parsed.getTime()) && toIsoDate(parsed) === value;
}

/** Today and the `count - 1` days before it, newest first. */
export function recentDates(count: number, now: Date = new Date()): string[] {
  const out: string[] = [];
  for (let i = 0; i < Math.max(1, count); i++) {
    const day = new Date(now);
    day.setDate(day.getDate() - i);
    out.push(toIsoDate(day));
  }
  return out;
}

/**
 * Parse an ISO 8601 duration such as "PT1H2M3.5S" or "PT45M" into seconds.
 * Returns null for anything it does not understand.
 */
export function parseIsoDuration(value: string | null | undefined): number | null {
  if (!value) return null;
  const m = /^P(?:(\d+(?:\.\d+)?)D)?(?:T(?:(\d+(?:\.\d+)?)H)?(?:(\d+(?:\.\d+)?)M)?(?:(\d+(?:\.\d+)?)S)?)?$/.exec(
    value.trim()
  );
  if (!m) return null;
  const [, d, h, min, s] = m;
  if (d == null && h == null && min == null && s == null) return null;
  return (
    (Number(d ?? 0) * 86400) +
    (Number(h ?? 0) * 3600) +
    (Number(min ?? 0) * 60) +
    Number(s ?? 0)
  );
}

/** "1h 02m" style, or "—" when unknown. */
export function formatMinutes(totalMinutes: number | null | undefined): string {
  if (totalMinutes == null || !Number.isFinite(totalMinutes)) return "—";
  const rounded = Math.round(totalMinutes);
  const h = Math.floor(rounded / 60);
  const m = rounded % 60;
  return h > 0 ? `${h}h ${String(m).padStart(2, "0")}m` : `${m}m`;
}

/** The local calendar date of an AccessLink timestamp ("2026-05-30T07:12:34.000"). */
export function localDateOf(timestamp: string | null | undefined): string | null {
  if (!timestamp || timestamp.length < 10) return null;
  const date = timestamp.slice(0, 10);
  return isValidIsoDate(date) ? date : null;
}
