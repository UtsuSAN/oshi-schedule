import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import {
  addDays,
  buildTicketReleaseCalendarUrl,
  buildEventCalendarUrl,
  filterEvents,
  formatGeneratedAt,
  japanDateKey,
  monthGrid,
  safeExternalUrl,
  validateSnapshot,
  weekRange,
} from "../schedule-core.mjs";

const fixtureUrl = new URL("../../examples/public_schedule.example.json", import.meta.url);
const fixture = JSON.parse(await readFile(fixtureUrl, "utf8"));

test("standalone Sites fixture matches the canonical example", async () => {
  const localFixture = await readFile(new URL("../public_schedule.example.json", import.meta.url), "utf8");
  assert.deepEqual(JSON.parse(localFixture), fixture);
});

test("example snapshot validates and unsupported schema gets a dedicated reason", () => {
  assert.equal(validateSnapshot(fixture).ok, true);
  assert.equal(validateSnapshot({ ...fixture, events: [] }).ok, true);
  assert.deepEqual(validateSnapshot({ ...fixture, schema_version: "2.0" }), { ok: false, reason: "version" });
  assert.equal(validateSnapshot({ ...fixture, timezone: "UTC" }).reason, "invalid");
});

test("week is Monday through Sunday across year boundaries", () => {
  assert.deepEqual(weekRange("2027-01-01"), { start: "2026-12-28", end: "2027-01-03" });
  assert.equal(addDays("2026-09-30", 1), "2026-10-01");
});

test("monthly calendar grid starts Monday and only includes valid dates", () => {
  const september = monthGrid("2026-09");
  assert.equal(september.length % 7, 0);
  assert.equal(september[0], null);
  assert.equal(september[1], "2026-09-01");
  assert.equal(september.at(-1), null);
});

test("artist filter preserves only events with a matching appearance", () => {
  const events = [
    { id: 1, appearances: [{ artist_id: 10 }] },
    { id: 2, appearances: [{ artist_id: 20 }] },
    { id: 3, appearances: [] },
  ];
  assert.deepEqual(filterEvents(events, "10").map(({ id }) => id), [1]);
  assert.deepEqual(filterEvents(events, "all").map(({ id }) => id), [1, 2, 3]);
});

test("generated timestamp is converted to Japan time", () => {
  assert.equal(formatGeneratedAt("2026-09-25T11:00:00Z"), "2026/09/25 20:00");
  assert.equal(japanDateKey(new Date("2026-09-24T16:00:00Z")), "2026-09-25");
});

test("external URLs reject local and credential-bearing links", () => {
  assert.equal(safeExternalUrl("https://tickets.example.invalid/event"), "https://tickets.example.invalid/event");
  assert.equal(safeExternalUrl("file:///C:/private/file"), null);
  assert.equal(safeExternalUrl("http://127.0.0.1:8000/admin"), null);
  assert.equal(safeExternalUrl("http://printer.local/status"), null);
  assert.equal(safeExternalUrl("http://10.0.0.4/private"), null);
  assert.equal(safeExternalUrl("https://user:pass@example.invalid/"), null);
  assert.equal(safeExternalUrl("https://example.invalid/?token=private"), null);
});

test("calendar link follows the existing OPEN, all-day, and overnight rules", () => {
  const makeUrl = (event) => new URL(buildEventCalendarUrl({
    id: 11, event_date: "2026-09-27", title: "架空ライブ", open_at: null, start_at: null, end_at: null,
    venue_name: null, venue_address: null, ticket_url: null, official_url: null, appearances: [], sources: [], ...event,
  }));
  assert.equal(makeUrl({ open_at: "17:00", start_at: "17:30", end_at: "19:00" }).searchParams.get("dates"), "20260927T170000/20260927T190000");
  assert.equal(makeUrl({ start_at: "23:00", end_at: "01:00" }).searchParams.get("dates"), "20260927T230000/20260928T010000");
  assert.equal(makeUrl({}).searchParams.get("dates"), "20260927/20260928");
  assert.equal(makeUrl({ start_at: "23:00" }).searchParams.get("dates"), "20260927T230000/20260928T010000");
});

test("sample includes both states required to review status presentation", () => {
  assert.ok(fixture.events.some((event) => event.status === "cancelled"));
  assert.ok(fixture.events.some((event) => event.status === "changed"));
});

test("ticket release calendar supports time and date only", () => {
  const timed = new URL(buildTicketReleaseCalendarUrl({ title: "架空ライブ", ticket_release_date: "2026-10-01", ticket_release_time: "10:00" }));
  assert.equal(timed.searchParams.get("dates"), "20261001T100000/20261001T103000");
  assert.equal(timed.searchParams.get("ctz"), "Asia/Tokyo");
  const dateOnly = new URL(buildTicketReleaseCalendarUrl({ title: "架空ライブ", ticket_release_date: "2026-10-05", ticket_release_time: null }));
  assert.equal(dateOnly.searchParams.get("dates"), "20261005/20261006");
  assert.equal(buildTicketReleaseCalendarUrl({ title: "架空ライブ", ticket_release_date: null }), null);
});
