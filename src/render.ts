// Shapes the AccessLink responses into one record per day and renders it.
// Pure; no obsidian import so it can be unit-tested with node.
import { formatMinutes, localDateOf, parseIsoDuration } from "./dates";
import { wrapSection } from "./notes";

// --- AccessLink response shapes (the fields this plugin reads; others are ignored) ---

export interface PolarSleepNight {
  date: string;
  sleep_start_time?: string;
  sleep_end_time?: string;
  sleep_score?: number;
  sleep_charge?: number;
  sleep_rating?: number;
  light_sleep?: number; // seconds
  deep_sleep?: number;
  rem_sleep?: number;
  unrecognized_sleep_stage?: number;
  total_interruption_duration?: number;
  sleep_cycles?: number;
  continuity?: number;
  device_id?: string;
}

export interface PolarRecharge {
  date: string;
  heart_rate_avg?: number;
  beat_to_beat_avg?: number;
  heart_rate_variability_avg?: number;
  breathing_rate_avg?: number;
  nightly_recharge_status?: number; // -2 .. 2 (Polar's scale); some payloads use 1..6
  ans_charge?: number;
  ans_charge_status?: number;
  sleep_charge?: number;
}

export interface PolarExercise {
  id?: string;
  start_time?: string;
  start_time_utc_offset?: number;
  duration?: string; // ISO 8601
  sport?: string;
  detailed_sport_info?: string;
  distance?: number; // metres
  calories?: number;
  training_load?: number;
  heart_rate?: { average?: number; maximum?: number };
  device?: string;
  has_route?: boolean;
}

export interface PolarDay {
  date: string;
  sleep: PolarSleepNight | null;
  recharge: PolarRecharge | null;
  exercises: PolarExercise[];
}

export interface RenderedDay {
  frontmatter: Record<string, string | number | null>;
  markdown: string;
}

const sec2min = (s: number | null | undefined): number | null =>
  s == null || !Number.isFinite(s) ? null : Math.round(s / 60);

const round1 = (n: number | null | undefined): number | null =>
  n == null || !Number.isFinite(n) ? null : Math.round(n * 10) / 10;

/** Group raw responses into per-day records for the requested dates (newest first). */
export function groupByDate(
  dates: string[],
  nights: PolarSleepNight[],
  recharges: PolarRecharge[],
  exercises: PolarExercise[]
): PolarDay[] {
  const sleepByDate = new Map(nights.filter((n) => n && n.date).map((n) => [n.date, n]));
  const rechargeByDate = new Map(recharges.filter((r) => r && r.date).map((r) => [r.date, r]));
  const exByDate = new Map<string, PolarExercise[]>();
  for (const ex of exercises) {
    const date = localDateOf(ex?.start_time);
    if (!date) continue;
    const list = exByDate.get(date) ?? [];
    list.push(ex);
    exByDate.set(date, list);
  }
  return dates.map((date) => ({
    date,
    sleep: sleepByDate.get(date) ?? null,
    recharge: rechargeByDate.get(date) ?? null,
    exercises: (exByDate.get(date) ?? []).slice().sort((a, b) =>
      String(a.start_time ?? "").localeCompare(String(b.start_time ?? ""))
    ),
  }));
}

export function hasAnyData(day: PolarDay): boolean {
  return day.sleep !== null || day.recharge !== null || day.exercises.length > 0;
}

function sleepTotalMin(s: PolarSleepNight): number | null {
  const parts = [s.light_sleep, s.deep_sleep, s.rem_sleep].filter(
    (v): v is number => v != null && Number.isFinite(v)
  );
  return parts.length ? Math.round(parts.reduce((a, b) => a + b, 0) / 60) : null;
}

function timeOfDay(timestamp: string | undefined): string {
  if (!timestamp || timestamp.length < 16) return "—";
  return timestamp.slice(11, 16);
}

function rechargeLabel(status: number | undefined): string {
  if (status == null) return "—";
  // Polar documents nightly_recharge_status as -2..2; older payloads used 1..6.
  const scale5: Record<number, string> = {
    [-2]: "very poor", [-1]: "poor", 0: "compromised", 1: "ok", 2: "good",
  };
  const scale6: Record<number, string> = {
    1: "very poor", 2: "poor", 3: "compromised", 4: "ok", 5: "good", 6: "very good",
  };
  return status >= -2 && status <= 2 ? scale5[status] : scale6[status] ?? String(status);
}

function fmt(n: number | null | undefined, unit = ""): string {
  return n == null || !Number.isFinite(n) ? "—" : `${n}${unit}`;
}

function sportLabel(ex: PolarExercise): string {
  const detailed = (ex.detailed_sport_info || "").replace(/_/g, " ").toLowerCase();
  const sport = (ex.sport || "").replace(/_/g, " ").toLowerCase();
  return detailed || sport || "exercise";
}

export function renderDay(day: PolarDay, syncedAt: Date = new Date()): RenderedDay {
  const { date, sleep, recharge, exercises } = day;

  const totalSleepMin = sleep ? sleepTotalMin(sleep) : null;
  const exerciseMinutes = exercises.reduce((sum, ex) => {
    const s = parseIsoDuration(ex.duration);
    return sum + (s ? s / 60 : 0);
  }, 0);
  const exerciseCalories = exercises.reduce((sum, ex) => sum + (ex.calories ?? 0), 0);
  const exerciseKm = exercises.reduce((sum, ex) => sum + (ex.distance ?? 0), 0) / 1000;

  const frontmatter: Record<string, string | number | null> = {
    polar_date: date,
    polar_sleep_score: sleep?.sleep_score ?? null,
    polar_sleep_charge: sleep?.sleep_charge ?? recharge?.sleep_charge ?? null,
    polar_sleep_min: totalSleepMin,
    polar_deep_min: sleep ? sec2min(sleep.deep_sleep) : null,
    polar_rem_min: sleep ? sec2min(sleep.rem_sleep) : null,
    polar_light_min: sleep ? sec2min(sleep.light_sleep) : null,
    polar_interruptions_min: sleep ? sec2min(sleep.total_interruption_duration) : null,
    polar_sleep_start: sleep?.sleep_start_time ?? null,
    polar_sleep_end: sleep?.sleep_end_time ?? null,
    polar_recharge_status: recharge?.nightly_recharge_status ?? null,
    polar_ans_charge: round1(recharge?.ans_charge),
    polar_hr_avg: round1(recharge?.heart_rate_avg),
    polar_hrv_avg: round1(recharge?.heart_rate_variability_avg ?? recharge?.beat_to_beat_avg),
    polar_breathing_rate: round1(recharge?.breathing_rate_avg),
    polar_exercise_count: exercises.length,
    polar_exercise_min: Math.round(exerciseMinutes),
    polar_exercise_kcal: Math.round(exerciseCalories),
    polar_exercise_km: round1(exerciseKm),
  };

  const lines: string[] = [`## Polar — ${date}`, ""];

  lines.push("### Sleep", "");
  if (sleep) {
    lines.push(
      "| | |",
      "|---|---|",
      `| Score | ${fmt(sleep.sleep_score)} |`,
      `| Asleep | ${formatMinutes(totalSleepMin)} (${timeOfDay(sleep.sleep_start_time)} → ${timeOfDay(sleep.sleep_end_time)}) |`,
      `| Deep / REM / Light | ${formatMinutes(sec2min(sleep.deep_sleep))} / ${formatMinutes(sec2min(sleep.rem_sleep))} / ${formatMinutes(sec2min(sleep.light_sleep))} |`,
      `| Interruptions | ${formatMinutes(sec2min(sleep.total_interruption_duration))} |`,
      `| Sleep charge | ${fmt(sleep.sleep_charge ?? recharge?.sleep_charge)} |`
    );
    if (sleep.sleep_cycles != null) lines.push(`| Cycles | ${sleep.sleep_cycles} |`);
    if (sleep.continuity != null) lines.push(`| Continuity | ${sleep.continuity} |`);
  } else {
    lines.push("_No sleep recorded._");
  }

  lines.push("", "### Nightly Recharge", "");
  if (recharge) {
    lines.push(
      "| | |",
      "|---|---|",
      `| Status | ${rechargeLabel(recharge.nightly_recharge_status)} (${fmt(recharge.nightly_recharge_status)}) |`,
      `| ANS charge | ${fmt(round1(recharge.ans_charge))} |`,
      `| Resting HR | ${fmt(round1(recharge.heart_rate_avg), " bpm")} |`,
      `| HRV (RMSSD) | ${fmt(round1(recharge.heart_rate_variability_avg ?? recharge.beat_to_beat_avg), " ms")} |`,
      `| Breathing rate | ${fmt(round1(recharge.breathing_rate_avg), " /min")} |`
    );
  } else {
    lines.push("_No Nightly Recharge for this night._");
  }

  lines.push("", "### Exercises", "");
  if (exercises.length) {
    lines.push("| Start | Sport | Duration | Distance | Avg HR | Max HR | kcal | Load |", "|---|---|---|---|---|---|---|---|");
    for (const ex of exercises) {
      const durMin = parseIsoDuration(ex.duration);
      lines.push(
        `| ${timeOfDay(ex.start_time)} | ${sportLabel(ex)} | ${formatMinutes(durMin == null ? null : durMin / 60)} | ` +
          `${ex.distance != null ? `${round1(ex.distance / 1000)} km` : "—"} | ${fmt(ex.heart_rate?.average)} | ` +
          `${fmt(ex.heart_rate?.maximum)} | ${fmt(ex.calories)} | ${fmt(round1(ex.training_load))} |`
      );
    }
  } else {
    lines.push("_No exercises._");
  }

  lines.push("", `*Synced ${syncedAt.toLocaleString()}*`);
  return { frontmatter, markdown: wrapSection(lines) };
}
