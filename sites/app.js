import {
  addDays,
  buildEventCalendarUrl,
  buildTicketReleaseCalendarUrl,
  escapeHtml,
  filterEvents,
  formatGeneratedAt,
  isDateKey,
  japanDateKey,
  monthGrid,
  monthRange,
  safeExternalUrl,
  validateSnapshot,
  weekRange,
} from "./schedule-core.mjs";

const root = document.querySelector("#app");
let snapshot = null;

function routeState() {
  const raw = location.hash.replace(/^#\/?/, "");
  const [path, query = ""] = raw.split("?");
  const params = new URLSearchParams(query);
  const segments = path.split("/").filter(Boolean);
  return { view: segments[0] || "today", value: segments[1] || "", artistId: params.get("artist_id") || "all", month: params.get("month") || "" };
}

function href(path, state, extra = {}) {
  const params = new URLSearchParams();
  const artistId = extra.artistId ?? state.artistId;
  if (artistId !== "all") params.set("artist_id", artistId);
  const month = extra.month ?? "";
  if (month) params.set("month", month);
  const query = params.toString();
  return `#/${path}${query ? `?${query}` : ""}`;
}

function displayDate(dateKey, options = { month: "long", day: "numeric", weekday: "long" }) {
  const [year, month, day] = dateKey.split("-").map(Number);
  return new Intl.DateTimeFormat("ja-JP", { timeZone: "UTC", ...options }).format(new Date(Date.UTC(year, month - 1, day, 12)));
}

function timeRange(start, end) {
  if (start && end) return `${escapeHtml(start)} – ${escapeHtml(end)}`;
  return escapeHtml(start || end || "");
}

function statusBadge(status) {
  const labels = { scheduled: "予定", changed: "変更あり", cancelled: "中止" };
  return `<span class="status status-${status}">${labels[status]}</span>`;
}

function externalLink(label, value) {
  const url = safeExternalUrl(value);
  if (!url) return "";
  return `<a class="external-link" href="${escapeHtml(url)}" target="_blank" rel="noopener noreferrer">${escapeHtml(label)} <span aria-hidden="true">↗</span><span class="sr-only">（新しいタブで開く）</span></a>`;
}

function appearanceMarkup(appearance, detailed = false) {
  const time = timeRange(appearance.appearance_start_at, appearance.appearance_end_at);
  const benefit = timeRange(appearance.benefit_start_at, appearance.benefit_end_at);
  return `<li class="appearance"><div class="appearance-heading"><strong>${escapeHtml(appearance.artist_name)}</strong>${time ? `<span class="performance-time">${time}</span>` : ""}</div>${benefit ? `<div class="benefit-time"><span>特典会</span> ${benefit}</div>` : ""}${detailed && appearance.stage_name ? `<div class="muted">ステージ: ${escapeHtml(appearance.stage_name)}</div>` : ""}${detailed && appearance.notes ? `<p>${escapeHtml(appearance.notes)}</p>` : ""}</li>`;
}

function eventCard(event, state) {
  const artists = event.appearances.length ? `<ul class="appearance-list">${event.appearances.map((appearance) => appearanceMarkup(appearance)).join("")}</ul>` : `<p class="muted">出演情報はありません</p>`;
  return `<article class="event-card"><div class="event-date">${escapeHtml(displayDate(event.event_date))}</div><div class="event-title-row">${statusBadge(event.status)}<h3><a href="${href(`event/${event.id}`, state)}">${escapeHtml(event.title)}</a></h3></div>${artists}${event.venue_name ? `<p class="venue">📍 <span>${escapeHtml(event.venue_name)}</span></p>` : ""}${event.open_at || event.start_at ? `<p class="event-times">${event.open_at ? `OPEN ${escapeHtml(event.open_at)}` : ""}${event.open_at && event.start_at ? "　" : ""}${event.start_at ? `START ${escapeHtml(event.start_at)}` : ""}</p>` : ""}</article>`;
}

function ticketCard(event, state) {
  const release = event.ticket_release_date;
  const time = event.ticket_release_time ? `<strong class="performance-time">${escapeHtml(event.ticket_release_time)}</strong>` : "時刻未定";
  const calendar = buildTicketReleaseCalendarUrl(event);
  return `<article class="event-card ticket-card"><div class="event-date">${escapeHtml(displayDate(release))}</div><div class="event-title-row"><span class="status">チケット発売</span><h3><a href="${href(`event/${event.id}`, state)}">${escapeHtml(event.title)}</a></h3></div><p class="venue">発売開始 ${time}</p>${calendar ? `<a class="calendar-link" href="${escapeHtml(calendar)}" target="_blank" rel="noopener noreferrer">Google Calendarに追加 <span aria-hidden="true">↗</span></a>` : ""}</article>`;
}

function scheduleItems(state) {
  return filtered(state).flatMap((event) => [
    { kind: "event", date: event.event_date, event },
    ...(isDateKey(event.ticket_release_date) && event.status !== "cancelled" ? [{ kind: "ticket", date: event.ticket_release_date, event }] : []),
  ]).sort((a, b) => a.date.localeCompare(b.date) || String(a.kind === "ticket" ? a.event.ticket_release_time || "" : a.event.start_at || "").localeCompare(String(b.kind === "ticket" ? b.event.ticket_release_time || "" : b.event.start_at || "")));
}

function scheduleCard(item, state) {
  return item.kind === "ticket" ? ticketCard(item.event, state) : eventCard(item.event, state);
}

function artistFilter(state) {
  const artistId = snapshot.artists.some((artist) => String(artist.id) === state.artistId) ? state.artistId : "all";
  const options = snapshot.artists.map((artist) => `<option value="${artist.id}" ${String(artist.id) === artistId ? "selected" : ""}>${escapeHtml(artist.display_name)}</option>`).join("");
  return `<div class="filter-wrap"><label for="artist-filter">Artist</label><select id="artist-filter" aria-label="Artistで予定を絞り込む"><option value="all" ${artistId === "all" ? "selected" : ""}>すべて</option>${options}</select></div>`;
}

function updateStamp() {
  return `<p class="updated">最終更新: <time datetime="${escapeHtml(snapshot.generated_at)}">${formatGeneratedAt(snapshot.generated_at)}</time></p>`;
}

function pageShell(content, state, activeView) {
  const tabs = [["today", "今日"], ["week", "今週"], ["month", "今月"]].map(([view, label]) => `<a class="nav-tab ${activeView === view ? "active" : ""}" href="${href(view, state)}" ${activeView === view ? 'aria-current="page"' : ""}>${label}</a>`).join("");
  root.innerHTML = `<button class="skip-link" type="button">本文へ移動</button><header class="site-header"><div class="header-inner"><a class="brand" href="${href("today", state)}">推し活スケジュール</a>${updateStamp()}</div><nav class="view-tabs" aria-label="表示期間">${tabs}</nav></header><main id="main" class="page-content" tabindex="-1">${content}</main><footer class="site-footer">Public Snapshotの予定を表示しています</footer>`;
  root.querySelector(".skip-link").addEventListener("click", () => root.querySelector("#main").focus());
  root.querySelector("#artist-filter")?.addEventListener("change", (event) => {
    const next = routeState();
    location.hash = href(`${next.view}${next.value ? `/${next.value}` : ""}`, next, { artistId: event.target.value, month: next.month });
  });
}

function filtered(state) {
  return filterEvents(snapshot.events, state.artistId).slice().sort((a, b) => a.event_date.localeCompare(b.event_date) || (a.start_at || "99:99").localeCompare(b.start_at || "99:99") || a.title.localeCompare(b.title, "ja"));
}

function listPage(title, events, state, activeView, subheading = "") {
  const cards = events.map((item) => scheduleCard(item, state)).join("");
  const empty = snapshot.events.length === 0 ? "現在公開中の予定はありません" : "この期間に予定はありません";
  pageShell(`<div class="page-heading"><div><p class="eyebrow">SCHEDULE</p><h1>${title}</h1>${subheading ? `<p class="subheading">${subheading}</p>` : ""}</div>${artistFilter(state)}</div>${cards ? `<div class="event-list">${cards}</div>` : `<p class="empty-state">${empty}</p>`}`, state, activeView);
}

function showToday(state) {
  const today = japanDateKey();
  listPage("今日の予定", scheduleItems(state).filter((item) => item.date === today), state, "today", displayDate(today));
}

function showWeek(state) {
  const today = japanDateKey();
  if (snapshot.events.length === 0) return listPage("今週の予定", [], state, "week");
  const { start, end } = weekRange(today);
  const events = scheduleItems(state).filter((item) => item.date >= start && item.date <= end);
  const content = `<div class="page-heading"><div><p class="eyebrow">SCHEDULE</p><h1>今週の予定</h1><p class="subheading">${escapeHtml(displayDate(start, { month: "numeric", day: "numeric" }))} – ${escapeHtml(displayDate(end, { month: "numeric", day: "numeric", year: "numeric" }))}</p></div>${artistFilter(state)}</div><div class="week-list">${Array.from({ length: 7 }, (_, i) => {
    const key = addDays(start, i);
    const daily = events.filter((item) => item.date === key);
    return `<section class="week-day ${key === today ? "is-today" : ""}"><h2><a href="${href(`day/${key}`, state)}"><time datetime="${key}">${escapeHtml(displayDate(key, { month: "numeric", day: "numeric", weekday: "short" }))}</time></a>${key === today ? '<span class="today-label">今日</span>' : ""}</h2>${daily.length ? daily.map((item) => scheduleCard(item, state)).join("") : '<p class="day-empty">予定なし</p>'}</section>`;
  }).join("")}</div>`;
  pageShell(content, state, "week");
}

function showMonth(state) {
  const currentMonth = /^\d{4}-\d{2}$/.test(state.month) ? state.month : japanDateKey().slice(0, 7);
  const { start, end } = monthRange(currentMonth);
  const events = scheduleItems(state).filter((item) => item.date >= start && item.date <= end);
  const [year, month] = currentMonth.split("-").map(Number);
  const previous = new Date(Date.UTC(year, month - 2, 1));
  const next = new Date(Date.UTC(year, month, 1));
  const monthKey = (date) => `${date.getUTCFullYear()}-${String(date.getUTCMonth() + 1).padStart(2, "0")}`;
  const buckets = new Map();
  for (const item of events) buckets.set(item.date, [...(buckets.get(item.date) || []), item]);
  const cells = monthGrid(currentMonth).map((day) => {
    if (!day) return '<div class="calendar-cell outside" aria-hidden="true"></div>';
    const daily = buckets.get(day) || [];
    const preview = daily.length === 1 ? `<span class="calendar-title">${escapeHtml(daily[0].kind === "ticket" ? `発売 ${daily[0].event.title}` : daily[0].event.title)}</span>` : daily.length > 1 ? `<span class="calendar-count">${daily.length}件</span>` : "";
    return `<a class="calendar-cell ${day === japanDateKey() ? "is-today" : ""}" href="${href(`day/${day}`, state)}" aria-label="${escapeHtml(displayDate(day))}${daily.length ? `、${daily.length}件の予定` : "、予定なし"}"><span class="calendar-day">${Number(day.slice(-2))}</span>${preview}</a>`;
  }).join("");
  pageShell(`<div class="page-heading"><div><p class="eyebrow">SCHEDULE</p><h1>今月の予定</h1></div>${artistFilter(state)}</div>${snapshot.events.length === 0 ? '<p class="empty-state">現在公開中の予定はありません</p>' : ""}<div class="month-heading"><a class="month-arrow" href="${href("month", state, { month: monthKey(previous) })}" aria-label="前の月">‹</a><h2>${year}年${month}月</h2><a class="month-arrow" href="${href("month", state, { month: monthKey(next) })}" aria-label="次の月">›</a></div><div class="calendar" role="group" aria-label="${year}年${month}月"><div class="weekday">月</div><div class="weekday">火</div><div class="weekday">水</div><div class="weekday">木</div><div class="weekday">金</div><div class="weekday weekend">土</div><div class="weekday weekend">日</div>${cells}</div>`, state, "month");
}

function showDay(state) {
  if (!isDateKey(state.value)) return showNotFound();
  listPage("日別の予定", scheduleItems(state).filter((item) => item.date === state.value), state, "", displayDate(state.value));
}

function showEvent(state) {
  const event = snapshot.events.find((item) => String(item.id) === state.value);
  if (!event) return showNotFound();
  const sources = event.sources.map((source) => externalLink(source.source_type === "x" ? "元情報（X）" : "元情報", source.source_url)).filter(Boolean).join("");
  const artists = event.appearances.length ? `<ul class="appearance-list detail-appearances">${event.appearances.map((appearance) => appearanceMarkup(appearance, true)).join("")}</ul>` : '<p class="muted">出演情報はありません</p>';
  const release = isDateKey(event.ticket_release_date) ? `${displayDate(event.ticket_release_date)}${event.ticket_release_time ? ` ${event.ticket_release_time}` : ""}` : null;
  const metadata = [["開催日", displayDate(event.event_date)], ["チケット発売", release], ["OPEN", event.open_at], ["START", event.start_at], ["END", event.end_at], ["会場", event.venue_name], ["住所", event.venue_address]].filter(([, value]) => value);
  const links = [externalLink("チケット", event.ticket_url), externalLink("公式サイト", event.official_url), sources].filter(Boolean).join("");
  const googleUrl = buildEventCalendarUrl(event);
  const ticketCalendarUrl = event.status === "cancelled" ? null : buildTicketReleaseCalendarUrl(event);
  pageShell(`<a class="back-link" href="${href("today", state)}">← 予定一覧へ</a><article class="detail-card"><div class="event-title-row">${statusBadge(event.status)}<h1>${escapeHtml(event.title)}</h1></div><dl class="event-meta">${metadata.map(([label, value]) => `<div><dt>${label}</dt><dd>${escapeHtml(value)}</dd></div>`).join("")}</dl><section class="detail-section"><h2>出演Artist</h2>${artists}</section>${links ? `<section class="detail-section"><h2>関連リンク</h2><div class="link-list">${links}</div></section>` : ""}<a class="calendar-link" href="${escapeHtml(googleUrl)}" target="_blank" rel="noopener noreferrer">イベントをGoogle Calendarに追加 <span aria-hidden="true">↗</span></a>${ticketCalendarUrl ? `<a class="calendar-link" href="${escapeHtml(ticketCalendarUrl)}" target="_blank" rel="noopener noreferrer">チケット発売をGoogle Calendarに追加 <span aria-hidden="true">↗</span></a>` : ""}</article>`, state, "");
}

function showNotFound() {
  const state = routeState();
  pageShell('<section class="empty-state"><h1>予定が見つかりません</h1><a href="#/today">今日の予定へ</a></section>', state, "");
}

function render() {
  if (!snapshot) return;
  const state = routeState();
  switch (state.view) {
    case "today": showToday(state); break;
    case "week": showWeek(state); break;
    case "month": showMonth(state); break;
    case "day": showDay(state); break;
    case "event": showEvent(state); break;
    default: showNotFound();
  }
}

async function start() {
  try {
    const configuredPath = new URLSearchParams(location.search).get("snapshot") || "./public_schedule.example.json";
    const snapshotUrl = new URL(configuredPath, location.href);
    if (snapshotUrl.origin !== location.origin || !["http:", "https:"].includes(snapshotUrl.protocol)) throw new Error("Snapshot must be a same-origin web file");
    const response = await fetch(snapshotUrl, { cache: "no-store" });
    if (!response.ok) throw new Error("fixture could not be loaded");
    const result = validateSnapshot(await response.json());
    if (!result.ok) {
      root.innerHTML = `<main class="fatal-message" role="alert"><h1>${result.reason === "version" ? "データ形式に対応していません" : "予定データを読み込めません"}</h1><p>${result.reason === "version" ? "このサイトが対応するSnapshot schema_versionは1.0です。データを更新してください。" : "Snapshotの形式またはタイムゾーンを確認してください。"}</p></main>`;
      return;
    }
    snapshot = result.value;
    window.addEventListener("hashchange", render);
    render();
  } catch {
    root.innerHTML = '<main class="fatal-message" role="alert"><h1>予定データを読み込めません</h1><p>サイトをローカルWebサーバーから開き、example JSONが利用できるか確認してください。</p></main>';
  }
}

start();
