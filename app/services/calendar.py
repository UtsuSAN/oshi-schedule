"""Google Calendar template URLs and RFC 5545 calendar files.

Event dates and SQL ``Time`` values in this project are Japan-local wall time,
so they are combined directly with Asia/Tokyo rather than converted from UTC.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

from app.models import Appearance, Event

JAPAN = ZoneInfo("Asia/Tokyo")
GOOGLE_CALENDAR_TEMPLATE_URL = "https://calendar.google.com/calendar/render"
DEFAULT_EVENT_DURATION = timedelta(hours=2)
DEFAULT_APPEARANCE_DURATION = timedelta(minutes=30)
DEFAULT_BENEFIT_DURATION = timedelta(minutes=60)
ICS_UID_DOMAIN = "oshi-schedule"


@dataclass(frozen=True)
class CalendarEntry:
    uid: str
    title: str
    start: datetime | date
    end: datetime | date
    all_day: bool
    location: str
    description: str


def _display_time(value: time | None) -> str | None:
    return value.strftime("%H:%M") if value else None


def _join_date_time(day: date, value: time) -> datetime:
    # SQL Time values have no zone; they represent Asia/Tokyo local time.
    return datetime.combine(day, value.replace(tzinfo=None), tzinfo=JAPAN)


def _with_overnight_end(day: date, start: datetime, end_time: time) -> datetime:
    end = _join_date_time(day, end_time)
    if end <= start:
        end += timedelta(days=1)
    return end


def _urls(event: Event) -> list[str]:
    values: list[str] = []
    for value in (event.ticket_url, event.official_url):
        if value and value not in values:
            values.append(value)
    for source in event.sources:
        if source.source_url and source.source_url not in values:
            values.append(source.source_url)
    return values


def _artists(event: Event) -> list[str]:
    names = []
    for appearance in event.appearances:
        artist = appearance.artist
        name = (artist.display_name or artist.name) if artist else ""
        if name and name not in names:
            names.append(name)
    return names


def _event_description(event: Event) -> str:
    lines = [event.title]
    artists = _artists(event)
    if artists:
        lines.append("出演: " + "、".join(artists))
    for appearance in event.appearances:
        artist = appearance.artist
        name = (artist.display_name or artist.name) if artist else None
        if name and (appearance.appearance_start_at or appearance.appearance_end_at):
            start = _display_time(appearance.appearance_start_at)
            end = _display_time(appearance.appearance_end_at)
            lines.append(f"{name} 出演: {'〜'.join(v for v in (start, end) if v)}")
        if name and (appearance.benefit_start_at or appearance.benefit_end_at):
            start = _display_time(appearance.benefit_start_at)
            end = _display_time(appearance.benefit_end_at)
            lines.append(f"{name} 特典会: {'〜'.join(v for v in (start, end) if v)}")
    if event.venue_name:
        lines.append("会場: " + event.venue_name)
    lines.extend(_urls(event))
    return "\n".join(lines)


def _appearance_title(event: Event, appearance: Appearance, benefit: bool) -> str:
    artist = appearance.artist
    name = (artist.display_name or artist.name) if artist else "出演"
    return f"{name} {'特典会' if benefit else '出演'}｜{event.title}"


def _entry_for_appearance(event: Event, appearance: Appearance, benefit: bool) -> CalendarEntry | None:
    start_time = appearance.benefit_start_at if benefit else appearance.appearance_start_at
    end_time = appearance.benefit_end_at if benefit else appearance.appearance_end_at
    if start_time is None:
        return None
    start = _join_date_time(event.event_date, start_time)
    if end_time is not None:
        end = _with_overnight_end(event.event_date, start, end_time)
    else:
        duration = DEFAULT_BENEFIT_DURATION if benefit else DEFAULT_APPEARANCE_DURATION
        end = start + duration
    artist = appearance.artist
    artist_name = (artist.display_name or artist.name) if artist else ""
    kind = "特典会" if benefit else "出演"
    lines = [event.title]
    if artist_name:
        lines.append(f"Artist: {artist_name}")
    lines.append(f"{kind}: {start.strftime('%H:%M')}〜{end.strftime('%H:%M')}")
    if event.venue_name:
        lines.append("会場: " + event.venue_name)
    lines.extend(_urls(event))
    return CalendarEntry(
        uid=f"{'benefit' if benefit else 'appearance'}-{appearance.id}@{ICS_UID_DOMAIN}",
        title=_appearance_title(event, appearance, benefit),
        start=start,
        end=end,
        all_day=False,
        location=", ".join(v for v in (event.venue_name, event.venue_address) if v),
        description="\n".join(lines),
    )


def _event_entry(event: Event) -> CalendarEntry:
    start_time = event.open_at or event.start_at
    if start_time is None:
        day_after = event.event_date + timedelta(days=1)
        return CalendarEntry(
            uid=f"event-{event.id}@{ICS_UID_DOMAIN}",
            title=event.title,
            start=event.event_date,
            end=day_after,
            all_day=True,
            location=", ".join(v for v in (event.venue_name, event.venue_address) if v),
            description=_event_description(event),
        )
    start = _join_date_time(event.event_date, start_time)
    if event.end_at is not None:
        end = _with_overnight_end(event.event_date, start, event.end_at)
    else:
        end = start + DEFAULT_EVENT_DURATION
    return CalendarEntry(
        uid=f"event-{event.id}@{ICS_UID_DOMAIN}",
        title=event.title,
        start=start,
        end=end,
        all_day=False,
        location=", ".join(v for v in (event.venue_name, event.venue_address) if v),
        description=_event_description(event),
    )


def _ticket_release_entry(event: Event) -> CalendarEntry | None:
    if event.ticket_release_date is None:
        return None
    if event.ticket_release_time is None:
        return CalendarEntry(
            uid=f"ticket-release-{event.id}@{ICS_UID_DOMAIN}",
            title=f"チケット発売｜{event.title}",
            start=event.ticket_release_date,
            end=event.ticket_release_date + timedelta(days=1),
            all_day=True,
            location="",
            description=_event_description(event),
        )
    start = _join_date_time(event.ticket_release_date, event.ticket_release_time)
    return CalendarEntry(
        uid=f"ticket-release-{event.id}@{ICS_UID_DOMAIN}",
        title=f"チケット発売｜{event.title}",
        start=start,
        end=start + timedelta(minutes=30),
        all_day=False,
        location="",
        description=_event_description(event),
    )


def _google_datetime(value: datetime) -> str:
    return value.astimezone(JAPAN).strftime("%Y%m%dT%H%M%S")


def _google_url(entry: CalendarEntry) -> str:
    if entry.all_day:
        start = entry.start.strftime("%Y%m%d")
        end = entry.end.strftime("%Y%m%d")
    else:
        start = _google_datetime(entry.start)
        end = _google_datetime(entry.end)
    params = urlencode({
        "action": "TEMPLATE",
        "text": entry.title,
        "dates": f"{start}/{end}",
        "details": entry.description,
        "location": entry.location,
        "ctz": "Asia/Tokyo",
    })
    return f"{GOOGLE_CALENDAR_TEMPLATE_URL}?{params}"


def _ics_escape(value: str) -> str:
    return (value.replace("\\", "\\\\").replace("\r\n", "\\n")
            .replace("\r", "\\n").replace("\n", "\\n")
            .replace(",", "\\,").replace(";", "\\;"))


def _fold_ics_line(line: str) -> str:
    """Fold one content line at 75 UTF-8 octets without splitting characters."""
    parts: list[str] = []
    current = ""
    octets = 0
    limit = 75
    for char in line:
        size = len(char.encode("utf-8"))
        if octets + size > limit and current:
            parts.append(current)
            current = char
            octets = 1 + size  # continuation whitespace
            limit = 75
        else:
            current += char
            octets += size
    parts.append(current)
    return "\r\n ".join(parts)


def _ics_datetime(value: datetime) -> str:
    return value.astimezone(JAPAN).strftime("%Y%m%dT%H%M%S")


def _ics_timestamp(event: Event) -> str:
    value = event.updated_at
    if value is None:
        value = datetime.now(timezone.utc)
    elif value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _ics(entry: CalendarEntry, stamp: str) -> str:
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Oshi Schedule//Calendar//JA",
        "CALSCALE:GREGORIAN",
        "BEGIN:VTIMEZONE",
        "TZID:Asia/Tokyo",
        "X-LIC-LOCATION:Asia/Tokyo",
        "BEGIN:STANDARD",
        "DTSTART:19700101T000000",
        "TZOFFSETFROM:+0900",
        "TZOFFSETTO:+0900",
        "TZNAME:JST",
        "END:STANDARD",
        "END:VTIMEZONE",
        "BEGIN:VEVENT",
        f"UID:{entry.uid}",
        f"DTSTAMP:{stamp}",
    ]
    if entry.all_day:
        lines.extend((f"DTSTART;VALUE=DATE:{entry.start.strftime('%Y%m%d')}",
                      f"DTEND;VALUE=DATE:{entry.end.strftime('%Y%m%d')}"))
    else:
        lines.extend((f"DTSTART;TZID=Asia/Tokyo:{_ics_datetime(entry.start)}",
                      f"DTEND;TZID=Asia/Tokyo:{_ics_datetime(entry.end)}"))
    lines.extend((f"SUMMARY:{_ics_escape(entry.title)}",))
    if entry.location:
        lines.append(f"LOCATION:{_ics_escape(entry.location)}")
    if entry.description:
        lines.append(f"DESCRIPTION:{_ics_escape(entry.description)}")
    lines.extend(("END:VEVENT", "END:VCALENDAR"))
    return "\r\n".join(_fold_ics_line(line) for line in lines) + "\r\n"


class CalendarService:
    """Build calendar URLs and files independently of the HTML presentation."""

    def build_event_calendar_url(self, event: Event) -> str:
        return _google_url(_event_entry(event))

    def build_ticket_release_calendar_url(self, event: Event) -> str | None:
        entry = _ticket_release_entry(event)
        return _google_url(entry) if entry else None

    def build_appearance_calendar_url(self, event: Event, appearance: Appearance) -> str | None:
        entry = _entry_for_appearance(event, appearance, benefit=False)
        return _google_url(entry) if entry else None

    def build_benefit_calendar_url(self, event: Event, appearance: Appearance) -> str | None:
        entry = _entry_for_appearance(event, appearance, benefit=True)
        return _google_url(entry) if entry else None

    def build_event_ics(self, event: Event) -> str:
        return _ics(_event_entry(event), _ics_timestamp(event))

    def build_appearance_ics(self, event: Event, appearance: Appearance) -> str | None:
        entry = _entry_for_appearance(event, appearance, benefit=False)
        return _ics(entry, _ics_timestamp(event)) if entry else None

    def build_benefit_ics(self, event: Event, appearance: Appearance) -> str | None:
        entry = _entry_for_appearance(event, appearance, benefit=True)
        return _ics(entry, _ics_timestamp(event)) if entry else None
