from __future__ import annotations

import re
from datetime import date, datetime, time, timedelta

from app.extractors.base import ParseContext, ParsedEventCandidate
from app.services.events import JAPAN, japan_today

SLASH_DATE = re.compile(r"(?<!\d)(?:(?P<year>\d{4})[/-])?(?P<month>\d{1,2})[/-](?P<day>\d{1,2})(?!\d)")
JAPANESE_DATE = re.compile(r"(?<!\d)(?P<month>\d{1,2})月(?P<day>\d{1,2})日")
WEEKDAY = re.compile(r"^\s*[（(]([月火水木金土日])[）)]")
CLOCK = r"(?:[01]?\d|2[0-3]):[0-5]\d"
RANGE = re.compile(rf"(?P<start>{CLOCK})\s*(?:[〜～~\-–—]|→|->)\s*(?P<end>{CLOCK})")
OPEN = re.compile(rf"(?:OPEN|開場)\s*[:：]?\s*(?P<value>{CLOCK})", re.IGNORECASE)
START = re.compile(rf"(?:START|開演)\s*[:：]?\s*(?P<value>{CLOCK})", re.IGNORECASE)
VENUE = re.compile(r"^(?:会場|VENUE)\s*[:：]?\s*(?P<value>.*)$", re.IGNORECASE)
URL = re.compile(r"https?://[^\s<>]+", re.IGNORECASE)
BENEFIT = re.compile(r"特典会|物販")
APPEARANCE = re.compile(r"出演|LIVE|ライブ", re.IGNORECASE)
WEEKDAYS = "月火水木金土日"
GENERIC_TITLE = re.compile(r"こちら|よろしく|詳細|お知らせ|予約|チケット|告知|情報解禁")


def _clock(value: str) -> time:
    return time.fromisoformat(value)


def _date_from_text(text: str, context: ParseContext, warnings: list[str]) -> date | None:
    matches = [(match.start(), match, False) for match in SLASH_DATE.finditer(text)]
    matches.extend((match.start(), match, True) for match in JAPANESE_DATE.finditer(text))
    if not matches:
        warnings.append("開催日を特定できませんでした")
        return None
    _, match, _ = min(matches, key=lambda item: item[0])
    month, day = int(match.group("month")), int(match.group("day"))
    explicit_year = match.groupdict().get("year")
    if context.published_at:
        published = context.published_at
        reference = published.astimezone(JAPAN).date() if published.tzinfo else published.date()
    else:
        reference = context.reference_date or japan_today()
    year = int(explicit_year) if explicit_year else reference.year
    try:
        result = date(year, month, day)
        if not explicit_year:
            if result < reference - timedelta(days=90):
                result = date(year + 1, month, day)
                warnings.append("年跨ぎの可能性があるため翌年と推定しました")
            else:
                warnings.append("年を投稿日時または現在日付から推定しました")
    except ValueError:
        warnings.append("日付の形式を確認してください")
        return None
    weekday = WEEKDAY.match(text[match.end():match.end() + 8])
    if weekday and WEEKDAYS[result.weekday()] != weekday.group(1):
        warnings.append("曜日と日付が一致しません")
    return result


def _range_on_line(lines: list[str], index: int) -> tuple[time, time] | None:
    match = RANGE.search(lines[index])
    if not match and index + 1 < len(lines):
        match = RANGE.search(lines[index + 1])
    return (_clock(match.group("start")), _clock(match.group("end"))) if match else None


def _extract_ranges(lines: list[str], warnings: list[str]) -> tuple[tuple[time, time] | None, tuple[time, time] | None]:
    benefit: tuple[time, time] | None = None
    benefit_indices: set[int] = set()
    for index, line in enumerate(lines):
        if BENEFIT.search(line):
            found = _range_on_line(lines, index)
            if found:
                benefit = benefit or found
                benefit_indices.add(index)
                if index + 1 < len(lines) and RANGE.search(lines[index + 1]):
                    benefit_indices.add(index + 1)
    candidates: list[tuple[int, tuple[time, time], bool]] = []
    for index, line in enumerate(lines):
        match = RANGE.search(line)
        if not match or index in benefit_indices or BENEFIT.search(line) or OPEN.search(line) or START.search(line):
            continue
        value = (_clock(match.group("start")), _clock(match.group("end")))
        candidates.append((index, value, bool(APPEARANCE.search(line))))
    labelled = [value for _, value, is_labelled in candidates if is_labelled]
    if len(labelled) == 1:
        appearance = labelled[0]
    elif len(candidates) == 1:
        appearance = candidates[0][1]
    else:
        appearance = None
        if candidates:
            warnings.append("複数の時間帯が見つかりました。出演時間を確認してください")
    return appearance, benefit


def _extract_venue(lines: list[str]) -> str | None:
    for index, line in enumerate(lines):
        match = VENUE.match(line.strip())
        if match:
            value = match.group("value").strip()
            if not value and index + 1 < len(lines):
                value = lines[index + 1].strip()
            return value[:300] or None
        if line.lstrip().startswith("@"):
            value = line.lstrip()[1:].strip()
            if re.search(r"[一-龯ぁ-んァ-ン]", value) or " " in value:
                return value[:300]
    return None


def _extract_urls(lines: list[str], warnings: list[str]) -> tuple[str | None, str | None]:
    ticket = official = None
    unknown = False
    for index, line in enumerate(lines):
        context = line + " " + (lines[index - 1] if index else "")
        for match in URL.finditer(line):
            value = match.group().rstrip("。、，,.)）]」")
            if ("チケット" in context or "ticket" in context.lower()) and ticket is None:
                ticket = value
            elif ("公式" in context or "official" in context.lower()) and official is None:
                official = value
            else:
                unknown = True
    if unknown:
        warnings.append("用途不明のURLがあります。リンク先を確認してください")
    return ticket, official


def _extract_title(lines: list[str], artist_name: str | None) -> str | None:
    for line in lines:
        value = URL.sub("", line).strip()
        value = SLASH_DATE.sub("", value, count=1)
        value = JAPANESE_DATE.sub("", value, count=1)
        value = re.sub(r"^[（(][月火水木金土日][）)]", "", value).strip(" ：:・!！/\t")
        value = re.sub(r"(?:出演決定|出演します)[!！。]*$", "", value).strip()
        if not value or value == artist_name or GENERIC_TITLE.search(value):
            continue
        if VENUE.match(value) or OPEN.search(value) or START.search(value) or RANGE.search(value):
            continue
        if BENEFIT.search(value) or value in ("出演", "LIVE", "ライブ"):
            continue
        if re.fullmatch(r"[（(]?[月火水木金土日][）)]?", value):
            continue
        return value[:300]
    return None


class RuleBasedParser:
    version = "rule-based-v1"

    def parse(self, text: str, context: ParseContext) -> ParsedEventCandidate:
        warnings: list[str] = []
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        event_date = _date_from_text(text, context, warnings)
        open_match = OPEN.search(text)
        start_match = START.search(text)
        appearance, benefit = _extract_ranges(lines, warnings)
        title = _extract_title(lines, context.artist_name)
        venue = _extract_venue(lines)
        ticket, official = _extract_urls(lines, warnings)
        if title is None:
            warnings.append("イベント名を特定できませんでした")
        elif not event_date:
            warnings.append("イベント名の信頼度が低いです")
        weights = ((event_date, .25), (title, .15), (open_match, .08), (start_match, .08),
                   (venue, .12), (appearance, .14), (benefit, .10), (ticket or official, .08))
        confidence = round(min(1.0, .1 + sum(weight for value, weight in weights if value)), 2)
        return ParsedEventCandidate(
            title=title, event_date=event_date,
            open_at=_clock(open_match.group("value")) if open_match else None,
            start_at=_clock(start_match.group("value")) if start_match else None,
            venue=venue, ticket_url=ticket, official_url=official,
            appearance_start=appearance[0] if appearance else None,
            appearance_end=appearance[1] if appearance else None,
            benefit_start=benefit[0] if benefit else None,
            benefit_end=benefit[1] if benefit else None,
            confidence=confidence, warnings=warnings, parser_version=self.version,
        )
