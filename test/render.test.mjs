// Run: npm test  (bundles src/{render,notes,dates}.ts into test/bundle/ first)
import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { groupByDate, hasAnyData, renderDay } from "./bundle/render.mjs";
import { SECTION_END, SECTION_START, mergeManagedSection, renderFrontmatter } from "./bundle/notes.mjs";
import { formatMinutes, isValidIsoDate, localDateOf, parseIsoDuration, recentDates } from "./bundle/dates.mjs";

const NIGHT = {
  date: "2026-05-30",
  sleep_start_time: "2026-05-29T23:12:00.000",
  sleep_end_time: "2026-05-30T06:48:00.000",
  sleep_score: 81,
  sleep_charge: 4,
  light_sleep: 4 * 3600,
  deep_sleep: 3600 + 1800,
  rem_sleep: 5400,
  total_interruption_duration: 900,
  sleep_cycles: 4,
};
const RECHARGE = {
  date: "2026-05-30",
  heart_rate_avg: 52.4,
  beat_to_beat_avg: 1150,
  heart_rate_variability_avg: 61.26,
  breathing_rate_avg: 14.1,
  nightly_recharge_status: 1,
  ans_charge: 1.32,
};
const RUN = {
  id: "abc",
  start_time: "2026-05-30T07:10:00.000",
  duration: "PT45M30S",
  sport: "RUNNING",
  detailed_sport_info: "TRAIL_RUNNING",
  distance: 8250,
  calories: 610,
  training_load: 88.4,
  heart_rate: { average: 148, maximum: 172 },
};
const RIDE = { start_time: "2026-05-29T18:00:00.000", duration: "PT1H2M", sport: "CYCLING", distance: 30000, calories: 700 };

describe("dates", () => {
  it("parses ISO 8601 durations", () => {
    assert.equal(parseIsoDuration("PT45M30S"), 45 * 60 + 30);
    assert.equal(parseIsoDuration("PT1H2M3.5S"), 3723.5);
    assert.equal(parseIsoDuration("P1DT1H"), 90000);
    assert.equal(parseIsoDuration("PT"), null);
    assert.equal(parseIsoDuration("garbage"), null);
    assert.equal(parseIsoDuration(undefined), null);
  });

  it("formats minutes", () => {
    assert.equal(formatMinutes(0), "0m");
    assert.equal(formatMinutes(62), "1h 02m");
    assert.equal(formatMinutes(null), "—");
  });

  it("validates dates and extracts the local date of a timestamp", () => {
    assert.equal(isValidIsoDate("2026-02-29"), false);
    assert.equal(isValidIsoDate("2026-05-30"), true);
    assert.equal(localDateOf("2026-05-30T07:10:00.000"), "2026-05-30");
    assert.equal(localDateOf(undefined), null);
  });

  it("lists recent dates newest first", () => {
    assert.deepEqual(recentDates(3, new Date(2026, 4, 30, 12)), ["2026-05-30", "2026-05-29", "2026-05-28"]);
  });
});

describe("groupByDate", () => {
  it("attaches sleep, recharge and exercises to their day", () => {
    const days = groupByDate(["2026-05-30", "2026-05-29", "2026-05-28"], [NIGHT], [RECHARGE], [RUN, RIDE]);
    assert.equal(days.length, 3);
    assert.equal(days[0].sleep, NIGHT);
    assert.equal(days[0].recharge, RECHARGE);
    assert.deepEqual(days[0].exercises, [RUN]);
    assert.deepEqual(days[1].exercises, [RIDE]);
    assert.equal(days[1].sleep, null);
    assert.equal(hasAnyData(days[0]), true);
    assert.equal(hasAnyData(days[1]), true);
    assert.equal(hasAnyData(days[2]), false);
  });

  it("orders a day's exercises by start time and ignores malformed entries", () => {
    const later = { ...RUN, start_time: "2026-05-30T18:00:00.000" };
    const junk = { start_time: null };
    const [day] = groupByDate(["2026-05-30"], [], [], [later, junk, RUN]);
    assert.deepEqual(day.exercises.map((e) => e.start_time), [RUN.start_time, later.start_time]);
  });
});

describe("renderDay", () => {
  const [day] = groupByDate(["2026-05-30"], [NIGHT], [RECHARGE], [RUN]);
  const rendered = renderDay(day, new Date(2026, 4, 30, 8, 0));

  it("produces flat frontmatter for Dataview", () => {
    const fm = rendered.frontmatter;
    assert.equal(fm.polar_sleep_score, 81);
    assert.equal(fm.polar_sleep_min, 240 + 90 + 90);
    assert.equal(fm.polar_deep_min, 90);
    assert.equal(fm.polar_interruptions_min, 15);
    assert.equal(fm.polar_hr_avg, 52.4);
    assert.equal(fm.polar_hrv_avg, 61.3);
    assert.equal(fm.polar_recharge_status, 1);
    assert.equal(fm.polar_exercise_count, 1);
    assert.equal(fm.polar_exercise_min, 46);
    assert.equal(fm.polar_exercise_km, 8.3);
    assert.equal(fm.polar_exercise_kcal, 610);
  });

  it("wraps the markdown in the managed markers", () => {
    assert.ok(rendered.markdown.startsWith(SECTION_START));
    assert.ok(rendered.markdown.endsWith(SECTION_END));
    assert.match(rendered.markdown, /\| Score \| 81 \|/);
    assert.match(rendered.markdown, /7h 00m \(23:12 → 06:48\)/);
    assert.match(rendered.markdown, /\| Status \| ok \(1\) \|/);
    assert.match(rendered.markdown, /\| 07:10 \| trail running \| 46m \| 8.3 km \| 148 \| 172 \| 610 \| 88.4 \|/);
  });

  it("says so when a section has no data", () => {
    const [emptyDay] = groupByDate(["2026-05-28"], [], [], []);
    const r = renderDay(emptyDay);
    assert.match(r.markdown, /_No sleep recorded._/);
    assert.match(r.markdown, /_No Nightly Recharge for this night._/);
    assert.match(r.markdown, /_No exercises._/);
    assert.equal(r.frontmatter.polar_sleep_score, null);
    assert.equal(r.frontmatter.polar_exercise_count, 0);
  });

  it("falls back to beat_to_beat_avg when HRV is missing", () => {
    const [d] = groupByDate(["2026-05-30"], [], [{ ...RECHARGE, heart_rate_variability_avg: undefined }], []);
    assert.equal(renderDay(d).frontmatter.polar_hrv_avg, 1150);
  });
});

describe("notes", () => {
  it("appends a managed section to a note that has none", () => {
    const out = mergeManagedSection("# My day\n\nsome thoughts\n", `${SECTION_START}\nX\n${SECTION_END}`);
    assert.equal(out, `# My day\n\nsome thoughts\n\n${SECTION_START}\nX\n${SECTION_END}\n`);
  });

  it("replaces only the managed section, preserving text around it", () => {
    const before = `intro\n\n${SECTION_START}\nold\n${SECTION_END}\n\nmy notes after\n`;
    const out = mergeManagedSection(before, `${SECTION_START}\nnew\n${SECTION_END}`);
    assert.equal(out, `intro\n\n${SECTION_START}\nnew\n${SECTION_END}\n\nmy notes after\n`);
  });

  it("handles an empty note", () => {
    assert.equal(mergeManagedSection("", `${SECTION_START}\nX\n${SECTION_END}`), `${SECTION_START}\nX\n${SECTION_END}\n`);
  });

  it("renders frontmatter with quoted strings, bare numbers, and no nulls", () => {
    const fm = renderFrontmatter({ polar_date: "2026-05-30", polar_sleep_score: 81, polar_hr_avg: null, note: 'say "hi"' });
    assert.equal(fm, `---\npolar_date: "2026-05-30"\npolar_sleep_score: 81\nnote: "say \\"hi\\""\n---`);
  });
});
