export const JAPAN_TIME_ZONE = "Asia/Tokyo";
export const SUPPORTED_SCHEMA_VERSION = "1.0";

export function validateSnapshot(snapshot) {
  if (!snapshot || typeof snapshot !== "object" || Array.isArray(snapshot)) return { ok: false, reason: "invalid" };
  if (snapshot.schema_version !== SUPPORTED_SCHEMA_VERSION) return { ok: false, reason: "version" };
  if (snapshot.timezone !== JAPAN_TIME_ZONE || !isValidDateTime(snapshot.generated_at) || !Array.isArray(snapshot.artists) || !Array.isArray(snapshot.events)) return { ok: false, reason: "invalid" };
  const validEvent = snapshot.events.every((event) => event && Number.isInteger(event.id) && typeof event.title === "string" && isDateKey(event.event_date) && ["scheduled", "changed", "cancelled"].includes(event.status) && Array.isArray(event.appearances) && event.appearances.every((appearance) => appearance && Number.isInteger(appearance.artist_id) && typeof appearance.artist_name === "string") && Array.isArray(event.sources) && event.sources.every((source) => source && typeof source.source_type === "string"));
  const validArtist = snapshot.artists.every((artist) => artist && Number.isInteger(artist.id) && typeof artist.display_name === "string");
  return validEvent && validArtist ? { ok: true, value: snapshot } : { ok: false, reason: "invalid" };
}

export function isDateKey(value) {
  if (typeof value !== "string" || !/^\d{4}-\d{2}-\d{2}$/.test(value)) return false;
  const [year, month, day] = value.split("-").map(Number);
  const date = new Date(Date.UTC(year, month - 1, day));
  return date.getUTCFullYear() === year && date.getUTCMonth() === month - 1 && date.getUTCDate() === day;
}

export function isValidDateTime(value) {
  return typeof value === "string" && /(?:Z|[+-]\d{2}:\d{2})$/.test(value) && Number.isFinite(Date.parse(value));
}

export function japanDateKey(date = new Date()) {
  const parts = new Intl.DateTimeFormat("en-CA", { timeZone: JAPAN_TIME_ZONE, year: "numeric", month: "2-digit", day: "2-digit" }).formatToParts(date);
  const part = Object.fromEntries(parts.map(({ type, value }) => [type, value]));
  return `${part.year}-${part.month}-${part.day}`;
}

export function addDays(dateKey, amount) {
  const [year, month, day] = dateKey.split("-").map(Number);
  const date = new Date(Date.UTC(year, month - 1, day + amount));
  return `${date.getUTCFullYear()}-${String(date.getUTCMonth() + 1).padStart(2, "0")}-${String(date.getUTCDate()).padStart(2, "0")}`;
}

export function weekRange(dateKey) {
  const [year, month, day] = dateKey.split("-").map(Number);
  const date = new Date(Date.UTC(year, month - 1, day));
  const sinceMonday = (date.getUTCDay() + 6) % 7;
  return { start: addDays(dateKey, -sinceMonday), end: addDays(dateKey, 6 - sinceMonday) };
}

export function monthRange(monthKey) {
  const [year, month] = monthKey.split("-").map(Number);
  const lastDay = new Date(Date.UTC(year, month, 0)).getUTCDate();
  return { start: `${monthKey}-01`, end: `${monthKey}-${String(lastDay).padStart(2, "0")}` };
}

export function monthGrid(monthKey) {
  const [year, month] = monthKey.split("-").map(Number);
  const firstWeekday = (new Date(Date.UTC(year, month - 1, 1)).getUTCDay() + 6) % 7;
  const lastDay = new Date(Date.UTC(year, month, 0)).getUTCDate();
  const cellCount = Math.ceil((firstWeekday + lastDay) / 7) * 7;
  return Array.from({ length: cellCount }, (_, index) => {
    const day = index - firstWeekday + 1;
    return day < 1 || day > lastDay ? null : addDays(`${monthKey}-01`, day - 1);
  });
}

export function filterEvents(events, artistId = "all") {
  if (artistId === "all") return events;
  const wanted = Number(artistId);
  if (!Number.isInteger(wanted)) return [];
  return events.filter((event) => event.appearances.some((appearance) => appearance.artist_id === wanted));
}

export function formatGeneratedAt(value) {
  if (!isValidDateTime(value)) return "";
  const parts = new Intl.DateTimeFormat("en-GB", { timeZone: JAPAN_TIME_ZONE, year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", hourCycle: "h23" }).formatToParts(new Date(value));
  const part = Object.fromEntries(parts.map(({ type, value: text }) => [type, text]));
  return `${part.year}/${part.month}/${part.day} ${part.hour}:${part.minute}`;
}

export function safeExternalUrl(value) {
  if (typeof value !== "string") return null;
  try {
    const url = new URL(value);
    if (!new Set(["http:", "https:"]).has(url.protocol) || url.username || url.password) return null;
    const host = url.hostname.toLowerCase();
    if (["localhost", "local", "localdomain", "internal", "lan", "home.arpa"].some((suffix) => host === suffix || host.endsWith(`.${suffix}`))) return null;
    if (!host.includes(".") && !host.startsWith("[")) return null;
    if (/^\d{1,3}(?:\.\d{1,3}){3}$/.test(host)) {
      const octets = host.split(".").map(Number);
      const [a, b] = octets;
      if (octets.some((octet) => octet > 255) || a === 0 || a === 10 || a === 127 || a >= 224 || (a === 169 && b === 254) || (a === 172 && b >= 16 && b <= 31) || (a === 192 && b === 168) || (a === 100 && b >= 64 && b <= 127) || (a === 198 && (b === 18 || b === 19))) return null;
    }
    const ipv6 = host.startsWith("[") ? host.slice(1, -1).toLowerCase() : "";
    if (ipv6 === "::" || ipv6 === "::1" || /^f[cd]/.test(ipv6) || /^fe[89ab]/.test(ipv6) || /^::ffff:(?:0:)?(?:127\.|10\.|192\.168\.|169\.254\.)/.test(ipv6)) return null;
    if (/[?&](?:api_key|apikey|token|access_token|auth|authorization|secret|password|signature|sig)=/i.test(value)) return null;
    return url.href;
  } catch { return null; }
}

export function buildEventCalendarUrl(event) {
  const startTime = event.open_at || event.start_at;
  const ymd = (key) => key.replaceAll("-", "");
  let dates;
  if (!startTime) {
    dates = `${ymd(event.event_date)}/${ymd(addDays(event.event_date, 1))}`;
  } else {
    const [startHour, startMinute] = startTime.split(":").map(Number);
    const startTotal = startHour * 60 + startMinute;
    let endKey = event.event_date;
    let endTime = event.end_at;
    if (endTime) {
      const [endHour, endMinute] = endTime.split(":").map(Number);
      if (endHour * 60 + endMinute <= startTotal) endKey = addDays(endKey, 1);
    } else {
      const total = startTotal + 120;
      endKey = addDays(endKey, Math.floor(total / 1440));
      endTime = `${String(Math.floor((total % 1440) / 60)).padStart(2, "0")}:${String(total % 60).padStart(2, "0")}`;
    }
    const dateTime = (key, time) => `${ymd(key)}T${time.replace(":", "")}00`;
    dates = `${dateTime(event.event_date, startTime)}/${dateTime(endKey, endTime)}`;
  }
  const links = [event.ticket_url, event.official_url, ...(event.sources || []).map((source) => source.source_url)]
    .map(safeExternalUrl).filter(Boolean).filter((url, index, all) => all.indexOf(url) === index);
  const artists = [...new Set((event.appearances || []).map(({ artist_name }) => artist_name).filter(Boolean))];
  const description = [event.title, ...(artists.length ? [`出演: ${artists.join("、")}`] : [])];
  for (const appearance of event.appearances || []) {
    if (appearance.artist_name && (appearance.appearance_start_at || appearance.appearance_end_at)) description.push(`${appearance.artist_name} 出演: ${[appearance.appearance_start_at, appearance.appearance_end_at].filter(Boolean).join("〜")}`);
    if (appearance.artist_name && (appearance.benefit_start_at || appearance.benefit_end_at)) description.push(`${appearance.artist_name} 特典会: ${[appearance.benefit_start_at, appearance.benefit_end_at].filter(Boolean).join("〜")}`);
  }
  if (event.venue_name) description.push(`会場: ${event.venue_name}`);
  description.push(...links);
  const params = new URLSearchParams({
    action: "TEMPLATE",
    text: event.title,
    dates,
    details: description.join("\n"),
    location: [event.venue_name, event.venue_address].filter(Boolean).join(", "),
    ctz: JAPAN_TIME_ZONE,
  });
  return `https://calendar.google.com/calendar/render?${params}`;
}

export function buildTicketReleaseCalendarUrl(event) {
  if (!isDateKey(event.ticket_release_date)) return null;
  const datePart = event.ticket_release_date.replaceAll("-", "");
  let dates;
  if (event.ticket_release_time) {
    const [hour, minute] = event.ticket_release_time.split(":").map(Number);
    if (!Number.isInteger(hour) || !Number.isInteger(minute) || hour > 23 || minute > 59) return null;
    const endTotal = hour * 60 + minute + 30;
    const endKey = addDays(event.ticket_release_date, Math.floor(endTotal / 1440)).replaceAll("-", "");
    const endTime = `${String(Math.floor((endTotal % 1440) / 60)).padStart(2, "0")}${String(endTotal % 60).padStart(2, "0")}`;
    dates = `${datePart}T${event.ticket_release_time.replace(":", "")}00/${endKey}T${endTime}00`;
  } else {
    dates = `${datePart}/${addDays(event.ticket_release_date, 1).replaceAll("-", "")}`;
  }
  const params = new URLSearchParams({
    action: "TEMPLATE",
    text: `チケット発売｜${event.title}`,
    dates,
    details: [event.title, event.ticket_url, event.official_url].filter(Boolean).join("\n"),
    ctz: JAPAN_TIME_ZONE,
  });
  return `https://calendar.google.com/calendar/render?${params}`;
}

export function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[char]);
}
