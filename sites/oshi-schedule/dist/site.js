(() => {
  "use strict";

  const SNAPSHOT_URL = "/data/public_snapshot.json";
  const JST = "Asia/Tokyo";
  const state = { range: "week", artistId: "all", snapshot: null };
  const list = document.getElementById("event-list");
  const artistSelect = document.getElementById("artist-select");
  const countNode = document.getElementById("result-count");
  const updatedNode = document.getElementById("snapshot-updated");
  const snapshotStatus = document.getElementById("snapshot-status");
  const rangeLabel = document.getElementById("range-label");
  const sectionTitle = document.getElementById("events-title");

  const rangeNames = {
    today: { label: "TODAY", title: "今日の予定" },
    week: { label: "THIS WEEK", title: "今週の予定" },
    month: { label: "THIS MONTH", title: "今月の予定" }
  };

  function escapeHtml(value) {
    return String(value ?? "").replace(/[&<>"']/g, (char) => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
    })[char]);
  }

  function safeUrl(value) {
    if (typeof value !== "string" || !value.trim()) return "";
    try {
      const url = new URL(value, window.location.origin);
      return ["http:", "https:"].includes(url.protocol) ? url.href : "";
    } catch {
      return "";
    }
  }

  function jstDateKey(date = new Date()) {
    const parts = new Intl.DateTimeFormat("en-CA", {
      timeZone: JST, year: "numeric", month: "2-digit", day: "2-digit"
    }).formatToParts(date);
    const values = Object.fromEntries(parts.map((part) => [part.type, part.value]));
    return `${values.year}-${values.month}-${values.day}`;
  }

  function dateKeyParts(value) {
    const match = String(value ?? "").match(/^(\d{4})-(\d{2})-(\d{2})/);
    return match ? { year: Number(match[1]), month: Number(match[2]), day: Number(match[3]), key: `${match[1]}-${match[2]}-${match[3]}` } : null;
  }

  function weekBounds(todayKey) {
    const p = dateKeyParts(todayKey);
    const date = new Date(Date.UTC(p.year, p.month - 1, p.day));
    const weekday = date.getUTCDay();
    const from = new Date(date);
    from.setUTCDate(from.getUTCDate() - ((weekday + 6) % 7));
    const to = new Date(from);
    to.setUTCDate(to.getUTCDate() + 6);
    return { from: from.toISOString().slice(0, 10), to: to.toISOString().slice(0, 10) };
  }

  function inSelectedRange(eventDate, todayKey) {
    const date = dateKeyParts(eventDate);
    const today = dateKeyParts(todayKey);
    if (!date || !today) return false;
    if (state.range === "today") return date.key === today.key;
    if (state.range === "month") return date.year === today.year && date.month === today.month;
    const bounds = weekBounds(today.key);
    return date.key >= bounds.from && date.key <= bounds.to;
  }

  function formatDay(value) {
    const p = dateKeyParts(value);
    if (!p) return { month: "—", day: "—", weekday: "" };
    const date = new Date(Date.UTC(p.year, p.month - 1, p.day));
    return {
      month: `${p.month}月`,
      day: String(p.day).padStart(2, "0"),
      weekday: new Intl.DateTimeFormat("ja-JP", { weekday: "short", timeZone: "UTC" }).format(date)
    };
  }

  function formatTimestamp(value) {
    if (!value) return "";
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return String(value);
    return new Intl.DateTimeFormat("ja-JP", {
      timeZone: JST, year: "numeric", month: "numeric", day: "numeric", hour: "2-digit", minute: "2-digit"
    }).format(date);
  }

  function formatTime(value) {
    if (!value) return "";
    const raw = String(value);
    const timeOnly = raw.match(/^(\d{1,2}):(\d{2})(?::\d{2})?$/);
    if (timeOnly) return `${timeOnly[1].padStart(2, "0")}:${timeOnly[2]}`;
    const date = new Date(raw);
    if (Number.isNaN(date.getTime())) return raw;
    return new Intl.DateTimeFormat("ja-JP", { timeZone: JST, hour: "2-digit", minute: "2-digit" }).format(date);
  }

  function formatRange(start, end) {
    const from = formatTime(start);
    const to = formatTime(end);
    if (!from && !to) return "時間未定";
    if (from && to) return `${from}–${to}`;
    return from || to;
  }

  function ticketRelease(event) {
    const rawDate = String(event?.ticket_release_date ?? "");
    const match = rawDate.match(/^(\d{4})-(\d{2})-(\d{2})$/);
    if (!match) return null;
    const year = Number(match[1]);
    const month = Number(match[2]);
    const day = Number(match[3]);
    const date = new Date(Date.UTC(year, month - 1, day));
    if (date.getUTCFullYear() !== year || date.getUTCMonth() !== month - 1 || date.getUTCDate() !== day) return null;

    const rawTime = String(event?.ticket_release_time ?? "");
    const timeMatch = rawTime.match(/^(\d{1,2}):(\d{2})(?::\d{2})?$/);
    const hour = timeMatch ? Number(timeMatch[1]) : -1;
    const minute = timeMatch ? Number(timeMatch[2]) : -1;
    const time = timeMatch && hour >= 0 && hour <= 23 && minute >= 0 && minute <= 59
      ? `${String(hour).padStart(2, "0")}:${String(minute).padStart(2, "0")}` : "";
    return { year, month, day, time, label: `${year}/${String(month).padStart(2, "0")}/${String(day).padStart(2, "0")}${time ? ` ${time}` : ""}` };
  }

  function calendarDate(date) {
    return `${date.getUTCFullYear()}${String(date.getUTCMonth() + 1).padStart(2, "0")}${String(date.getUTCDate()).padStart(2, "0")}`;
  }

  function ticketCalendarUrl(event, release) {
    if (!release) return "";
    const start = new Date(Date.UTC(release.year, release.month - 1, release.day));
    const params = new URLSearchParams({
      action: "TEMPLATE",
      text: `チケット発売：${event.title || "イベント"}`,
      ctz: JST
    });
    if (release.time) {
      const [hour, minute] = release.time.split(":").map(Number);
      start.setUTCHours(hour, minute, 0, 0);
      const end = new Date(start.getTime() + 30 * 60 * 1000);
      const dateTime = (value) => `${calendarDate(value)}T${String(value.getUTCHours()).padStart(2, "0")}${String(value.getUTCMinutes()).padStart(2, "0")}00`;
      params.set("dates", `${dateTime(start)}/${dateTime(end)}`);
    } else {
      const end = new Date(start);
      end.setUTCDate(end.getUTCDate() + 1);
      params.set("dates", `${calendarDate(start)}/${calendarDate(end)}`);
    }
    if (event.ticket_url) {
      const ticketUrl = safeUrl(event.ticket_url);
      if (ticketUrl) params.set("details", `チケット情報: ${ticketUrl}`);
    }
    return `https://calendar.google.com/calendar/render?${params.toString()}`;
  }

  function ticketReleaseHtml(event, { calendarLink = false } = {}) {
    const release = ticketRelease(event);
    if (!release) return "";
    const action = calendarLink && event.status !== "cancelled"
      ? `<a class="source-link ticket-calendar-link" href="${escapeHtml(ticketCalendarUrl(event, release))}" target="_blank" rel="noopener noreferrer">発売予定をGoogle Calendarに追加</a>`
      : "";
    return `<div class="ticket-release"><span class="ticket-release-label">チケット発売</span><span class="ticket-release-value">${escapeHtml(release.label)}</span>${action}</div>`;
  }

  function eventTime(event) {
    return event.start_at || event.open_at || "";
  }

  function compareEvents(a, b) {
    const dateCompare = String(a.scheduleDate ?? "").localeCompare(String(b.scheduleDate ?? ""));
    if (dateCompare) return dateCompare;
    const firstTime = a.kind === "ticket" ? ticketRelease(a.event)?.time || "" : eventTime(a.event);
    const secondTime = b.kind === "ticket" ? ticketRelease(b.event)?.time || "" : eventTime(b.event);
    return String(firstTime).localeCompare(String(secondTime));
  }

  function updateArtistOptions(artists) {
    const current = state.artistId;
    const sorted = [...artists].filter((artist) => artist && artist.id != null && artist.display_name)
      .sort((a, b) => String(a.display_name).localeCompare(String(b.display_name), "ja"));
    artistSelect.innerHTML = '<option value="all">すべて</option>' + sorted.map((artist) =>
      `<option value="${escapeHtml(artist.id)}">${escapeHtml(artist.display_name)}</option>`
    ).join("");
    const keep = sorted.some((artist) => String(artist.id) === current) ? current : "all";
    state.artistId = keep;
    artistSelect.value = keep;
    artistSelect.disabled = sorted.length === 0;
  }

  function getAppearances(event) {
    return Array.isArray(event.appearances) ? event.appearances.filter(Boolean) : [];
  }

  function eventMatchesArtist(event) {
    if (state.artistId === "all") return true;
    return getAppearances(event).some((appearance) => String(appearance.artist_id ?? "") === state.artistId);
  }

  function textLink(label, value) {
    const url = safeUrl(value);
    return url ? `<a class="source-link" href="${escapeHtml(url)}" target="_blank" rel="noopener noreferrer">${escapeHtml(label)}</a>` : "";
  }

  function eventLinks(event) {
    const links = [];
    if (event.ticket_url) links.push(textLink("チケット情報", event.ticket_url));
    if (event.official_url) links.push(textLink("イベント公式", event.official_url));
    const sources = Array.isArray(event.sources) ? event.sources : [];
    sources.forEach((source) => {
      const type = String(source?.source_type ?? "");
      const label = ({ official: "公式情報", x: "Xの告知", ticket: "チケット情報" })[type.toLowerCase()] || (type ? `出典 · ${type}` : "出典を開く");
      links.push(textLink(label, source?.source_url));
    });
    return [...new Set(links.filter(Boolean))];
  }

  function appearanceHtml(appearance) {
    const name = appearance.artist_name || "アーティスト";
    const parts = [];
    const stage = appearance.stage_name ? `<span>${escapeHtml(appearance.stage_name)}</span>` : "";
    const appearanceTimes = appearance.appearance_start_at || appearance.appearance_end_at
      ? `<span>出演 <span class="appearance-time">${escapeHtml(formatRange(appearance.appearance_start_at, appearance.appearance_end_at))}</span></span>` : "";
    const benefitTimes = appearance.benefit_start_at || appearance.benefit_end_at
      ? `<span>特典会 <span class="appearance-time">${escapeHtml(formatRange(appearance.benefit_start_at, appearance.benefit_end_at))}</span></span>` : "";
    const notes = appearance.notes ? `<span class="appearance-note">${escapeHtml(appearance.notes)}</span>` : "";
    parts.push(`<div class="appearance-row"><span class="appearance-name">${escapeHtml(name)}</span>${stage}${appearanceTimes}${benefitTimes}${notes}</div>`);
    return parts.join("");
  }

  function eventCardHtml(event) {
    const date = formatDay(event.event_date);
    const appearances = getAppearances(event);
    const artists = appearances.map((a) => a.artist_name).filter(Boolean);
    const time = event.start_at ? `開演 ${formatTime(event.start_at)}` : event.open_at ? `開場 ${formatTime(event.open_at)}` : "時間未定";
    const venue = event.venue_name || "会場未定";
    const address = event.venue_address ? `<div><span class="detail-fact-label">住所</span><span class="detail-fact-value">${escapeHtml(event.venue_address)}</span></div>` : "";
    const updated = event.updated_at ? `<div><span class="detail-fact-label">情報更新</span><span class="detail-fact-value">${escapeHtml(formatTimestamp(event.updated_at))}</span></div>` : "";
    const status = event.status ? `<span class="status-pill">${escapeHtml(event.status)}</span>` : "";
    const links = eventLinks(event);
    const details = [
      ticketReleaseHtml(event, { calendarLink: true }),
      `<div class="appearance-list">${appearances.length ? appearances.map(appearanceHtml).join("") : '<div class="detail-fact-value">出演情報は未登録です。</div>'}</div>`,
      `<div class="detail-facts">${address}${updated}</div>`,
      links.length ? `<div class="link-list">${links.join("")}</div>` : ""
    ].filter(Boolean).join("");
    return `<article class="event-card">
      <div class="date-tile" aria-label="${escapeHtml(event.event_date)}">
        <span class="date-tile-month">${escapeHtml(date.month)}</span>
        <span class="date-tile-day">${escapeHtml(date.day)}</span>
        <span class="date-tile-weekday">${escapeHtml(date.weekday)}</span>
      </div>
      <div class="event-main">
        <div class="event-topline">
          <h3 class="event-title">${escapeHtml(event.title || "イベント名未設定")}</h3>${status}
        </div>
        <div class="event-meta">
          <span class="event-meta-item"><span class="meta-icon" aria-hidden="true">◷</span>${escapeHtml(time)}</span>
          <span class="event-meta-item"><span class="meta-icon" aria-hidden="true">⌖</span>${escapeHtml(venue)}</span>
        </div>
        ${ticketReleaseHtml(event)}
        ${artists.length ? `<div class="artist-list">${[...new Set(artists)].map((name) => `<span class="artist-chip">${escapeHtml(name)}</span>`).join("")}</div>` : ""}
        <details class="event-details">
          <summary>出演・会場・公式リンクを見る</summary>
          <div class="details-content">${details}</div>
        </details>
      </div>
    </article>`;
  }

  function ticketCardHtml(event) {
    const release = ticketRelease(event);
    if (!release) return "";
    const releaseDate = `${release.year}-${String(release.month).padStart(2, "0")}-${String(release.day).padStart(2, "0")}`;
    const date = formatDay(releaseDate);
    return `<article class="event-card ticket-card"><div class="date-tile"><span class="date-tile-month">${escapeHtml(date.month)}</span><span class="date-tile-day">${escapeHtml(date.day)}</span><span class="date-tile-weekday">${escapeHtml(date.weekday)}</span></div><div class="event-main"><div class="event-topline"><h3 class="event-title">チケット発売｜${escapeHtml(event.title || "イベント")}</h3></div>${ticketReleaseHtml(event, { calendarLink: true })}</div></article>`;
  }

  function renderEmpty(title, message, icon = "＋") {
    list.innerHTML = `<div class="empty-state"><span class="empty-icon" aria-hidden="true">${icon}</span><h3>${escapeHtml(title)}</h3><p>${escapeHtml(message)}</p></div>`;
  }

  function render() {
    const snapshot = state.snapshot;
    if (!snapshot) return;
    const today = jstDateKey();
    const events = (Array.isArray(snapshot.events) ? snapshot.events : [])
      .filter((event) => event && eventMatchesArtist(event))
      .flatMap((event) => [
        { event, kind: "event", scheduleDate: event.event_date },
        ...(event.status !== "cancelled" && ticketRelease(event) ? [{ event, kind: "ticket", scheduleDate: String(event.ticket_release_date) }] : [])
      ])
      .filter((item) => inSelectedRange(item.scheduleDate, today))
      .sort(compareEvents);
    rangeLabel.textContent = rangeNames[state.range].label;
    sectionTitle.textContent = rangeNames[state.range].title;
    countNode.innerHTML = `<strong>${events.length}</strong> 件`;
    if (events.length) {
      list.innerHTML = events.map((item) => item.kind === "ticket" ? ticketCardHtml(item.event) : eventCardHtml(item.event)).join("");
    } else if (!Array.isArray(snapshot.events) || snapshot.events.length === 0) {
      renderEmpty("公開データはまだありません", "ローカルアプリで公開用Snapshotを作成し、サイトへ反映すると予定が表示されます。", "＋");
    } else {
      renderEmpty("この期間の予定はありません", "別の期間を選ぶか、アーティストの絞り込みを「すべて」に戻してください。", "⌕");
    }
    list.setAttribute("aria-busy", "false");
  }

  function validateSnapshot(snapshot) {
    if (!snapshot || typeof snapshot !== "object" || Array.isArray(snapshot)) throw new Error("invalid snapshot");
    if (snapshot.schema_version !== "1.0" || typeof snapshot.generated_at !== "string") throw new Error("unsupported snapshot version");
    if (!Array.isArray(snapshot.artists) || !Array.isArray(snapshot.events)) throw new Error("invalid snapshot arrays");
    if (snapshot.timezone !== JST) throw new Error("unexpected timezone");
    return snapshot;
  }

  async function loadSnapshot() {
    list.setAttribute("aria-busy", "true");
    try {
      const response = await fetch(`${SNAPSHOT_URL}?_=${Date.now()}`, { cache: "no-store" });
      if (!response.ok) throw new Error(`snapshot response ${response.status}`);
      const snapshot = validateSnapshot(await response.json());
      state.snapshot = snapshot;
      updateArtistOptions(snapshot.artists);
      const updated = formatTimestamp(snapshot.generated_at);
      updatedNode.textContent = updated ? `更新 ${updated} JST` : "公開データを読み込みました";
      snapshotStatus.classList.remove("is-error");
      snapshotStatus.classList.add("is-ready");
      render();
    } catch {
      state.snapshot = null;
      snapshotStatus.classList.remove("is-ready");
      snapshotStatus.classList.add("is-error");
      updatedNode.textContent = "公開データを読み込めません";
      countNode.textContent = "— 件";
      list.innerHTML = `<div class="error-state"><span class="empty-icon" aria-hidden="true">!</span><h3>予定を表示できません</h3><p>公開データの読み込みに失敗しました。時間をおいてもう一度お試しください。</p><button class="retry-button" type="button" id="retry-load">再読み込み</button></div>`;
      list.setAttribute("aria-busy", "false");
      document.getElementById("retry-load")?.addEventListener("click", loadSnapshot, { once: true });
    }
  }

  document.querySelectorAll(".date-tab").forEach((button) => {
    button.addEventListener("click", () => {
      state.range = button.dataset.range;
      document.querySelectorAll(".date-tab").forEach((tab) => {
        const active = tab === button;
        tab.classList.toggle("is-active", active);
        tab.setAttribute("aria-selected", String(active));
      });
      render();
    });
  });

  artistSelect.addEventListener("change", () => {
    state.artistId = artistSelect.value;
    render();
  });

  loadSnapshot();
})();
