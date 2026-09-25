from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timezone
from typing import Mapping
from urllib.parse import urlsplit

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.models import Appearance, Artist, Event, Source
from app.services.events import JAPAN, japan_today

EVENT_STATUSES = ("scheduled", "changed", "cancelled", "unknown")
SOURCE_TYPES = ("manual", "x", "official_site", "other")


class InputError(Exception):
    def __init__(self, errors: dict[str, str]):
        self.errors = errors
        super().__init__("入力内容を確認してください")


def _text(values: Mapping[str, str], key: str, errors: dict[str, str], label: str,
          *, required: bool = False, limit: int | None = None) -> str | None:
    value = (values.get(key) or "").strip()
    if required and not value:
        errors[key] = f"{label}を入力してください"
    elif limit is not None and len(value) > limit:
        errors[key] = f"{label}は{limit}文字以内で入力してください"
    return value or None


def _url(values: Mapping[str, str], key: str, errors: dict[str, str], label: str) -> str | None:
    value = _text(values, key, errors, label, limit=2048)
    if value:
        try:
            parsed = urlsplit(value)
            valid = parsed.scheme in ("http", "https") and bool(parsed.netloc)
        except ValueError:
            valid = False
        if not valid:
            errors[key] = f"{label}はhttpまたはhttpsのURLを入力してください"
    return value


def _date(values: Mapping[str, str], key: str, errors: dict[str, str], label: str,
          *, required: bool = True) -> date | None:
    value = _text(values, key, errors, label, required=required)
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        errors[key] = f"{label}を正しい日付で入力してください"
        return None


def _time(values: Mapping[str, str], key: str, errors: dict[str, str], label: str) -> time | None:
    value = _text(values, key, errors, label)
    if not value:
        return None
    try:
        result = time.fromisoformat(value)
        if result.tzinfo is not None:
            raise ValueError
        return result
    except ValueError:
        errors[key] = f"{label}を正しい時刻で入力してください"
        return None


def _published_at(values: Mapping[str, str], errors: dict[str, str]) -> datetime | None:
    value = _text(values, "published_at", errors, "投稿日時")
    if not value:
        return None
    try:
        local = datetime.fromisoformat(value)
        if local.tzinfo is not None:
            raise ValueError
        return local.replace(tzinfo=JAPAN).astimezone(timezone.utc).replace(tzinfo=None)
    except ValueError:
        errors["published_at"] = "投稿日時を正しい日時で入力してください"
        return None


def _artist_id(values: Mapping[str, str], errors: dict[str, str]) -> int | None:
    raw = _text(values, "artist_id", errors, "出演者", required=True)
    if not raw:
        return None
    try:
        artist_id = int(raw)
        if artist_id <= 0:
            raise ValueError
        return artist_id
    except ValueError:
        errors["artist_id"] = "出演者を選択してください"
        return None


@dataclass(frozen=True)
class ArtistData:
    name: str
    display_name: str | None
    x_username: str | None
    x_user_id: str | None
    official_url: str | None
    enabled: bool


@dataclass(frozen=True)
class EventData:
    title: str
    event_date: date
    open_at: time | None
    start_at: time | None
    end_at: time | None
    venue_name: str | None
    venue_address: str | None
    ticket_url: str | None
    official_url: str | None
    status: str
    ticket_release_date: date | None = None
    ticket_release_time: time | None = None


@dataclass(frozen=True)
class AppearanceData:
    artist_id: int
    appearance_start_at: time | None
    appearance_end_at: time | None
    benefit_start_at: time | None
    benefit_end_at: time | None
    stage_name: str | None
    notes: str | None


@dataclass(frozen=True)
class SourceData:
    source_type: str
    source_url: str | None
    source_account: str | None
    source_text: str | None
    published_at: datetime | None


def parse_artist(values: Mapping[str, str]) -> ArtistData:
    errors: dict[str, str] = {}
    name = _text(values, "name", errors, "名前", required=True, limit=200)
    display_name = _text(values, "display_name", errors, "表示名", limit=200)
    username = _text(values, "x_username", errors, "Xユーザー名", limit=100)
    if username:
        username = username.lstrip("@")
    x_user_id = _text(values, "x_user_id", errors, "XユーザーID", limit=100)
    official_url = _url(values, "official_url", errors, "公式URL")
    if errors:
        raise InputError(errors)
    return ArtistData(name, display_name, username, x_user_id, official_url, values.get("enabled") == "on")


def parse_event(values: Mapping[str, str]) -> EventData:
    errors: dict[str, str] = {}
    title = _text(values, "title", errors, "イベント名", required=True, limit=300)
    event_date = _date(values, "event_date", errors, "開催日")
    open_at = _time(values, "open_at", errors, "OPEN")
    start_at = _time(values, "start_at", errors, "START")
    end_at = _time(values, "end_at", errors, "END")
    venue_name = _text(values, "venue_name", errors, "会場名", limit=300)
    venue_address = _text(values, "venue_address", errors, "会場住所", limit=500)
    ticket_url = _url(values, "ticket_url", errors, "チケットURL")
    ticket_release_date = _date(values, "ticket_release_date", errors, "チケット発売日", required=False)
    ticket_release_time = _time(values, "ticket_release_time", errors, "チケット発売時刻")
    if ticket_release_time and not ticket_release_date:
        errors["ticket_release_date"] = "発売時刻を指定する場合は発売日も入力してください"
    official_url = _url(values, "official_url", errors, "公式URL")
    status = (values.get("status") or "scheduled").strip()
    if status not in EVENT_STATUSES:
        errors["status"] = "状態を選択してください"
    if open_at and start_at and open_at > start_at:
        errors["open_at"] = "OPENはSTART以前にしてください"
    if errors:
        raise InputError(errors)
    return EventData(title, event_date, open_at, start_at, end_at, venue_name,
                     venue_address, ticket_url, official_url, status,
                     ticket_release_date, ticket_release_time)


def parse_appearance(values: Mapping[str, str]) -> AppearanceData:
    errors: dict[str, str] = {}
    artist_id = _artist_id(values, errors)
    start = _time(values, "appearance_start_at", errors, "出演開始")
    end = _time(values, "appearance_end_at", errors, "出演終了")
    benefit_start = _time(values, "benefit_start_at", errors, "特典会開始")
    benefit_end = _time(values, "benefit_end_at", errors, "特典会終了")
    stage_name = _text(values, "stage_name", errors, "ステージ名", limit=200)
    notes = _text(values, "notes", errors, "メモ")
    if start and end and start > end:
        errors["appearance_start_at"] = "出演開始は終了以前にしてください"
    if benefit_start and benefit_end and benefit_start > benefit_end:
        errors["benefit_start_at"] = "特典会開始は終了以前にしてください"
    if errors:
        raise InputError(errors)
    return AppearanceData(artist_id, start, end, benefit_start, benefit_end, stage_name, notes)


def parse_source(values: Mapping[str, str]) -> SourceData:
    errors: dict[str, str] = {}
    if not source_has_content(values):
        errors["source_text"] = "出典URL、投稿者、本文、投稿日時のいずれかを入力してください"
    source_type = (values.get("source_type") or "manual").strip()
    if source_type not in SOURCE_TYPES:
        errors["source_type"] = "出典の種類を選択してください"
    source_url = _url(values, "source_url", errors, "出典URL")
    source_account = _text(values, "source_account", errors, "投稿者", limit=200)
    source_text = _text(values, "source_text", errors, "投稿本文")
    published_at = _published_at(values, errors)
    if errors:
        raise InputError(errors)
    return SourceData(source_type, source_url, source_account, source_text, published_at)


def source_has_content(values: Mapping[str, str]) -> bool:
    return any((values.get(key) or "").strip() for key in ("source_url", "source_account", "source_text", "published_at"))


class ArtistService:
    def __init__(self, session: Session):
        self.session = session

    def list(self) -> list[Artist]:
        return list(self.session.scalars(select(Artist).order_by(Artist.name, Artist.id)).all())

    def get(self, artist_id: int) -> Artist | None:
        return self.session.get(Artist, artist_id)

    def count(self) -> int:
        return self.session.scalar(select(func.count(Artist.id))) or 0

    def save(self, data: ArtistData, artist: Artist | None = None) -> Artist:
        artist = artist or Artist(name=data.name)
        for key, value in vars(data).items():
            setattr(artist, key, value)
        self.session.add(artist)
        try:
            self.session.commit()
        except Exception:
            self.session.rollback()
            raise
        return artist


class AdminEventService:
    def __init__(self, session: Session):
        self.session = session

    def list(self) -> list[Event]:
        statement = (select(Event).options(selectinload(Event.appearances).selectinload(Appearance.artist))
                     .order_by(Event.event_date.desc(), Event.start_at, Event.id))
        return list(self.session.scalars(statement).all())

    def count(self) -> int:
        return self.session.scalar(select(func.count(Event.id))) or 0

    def get(self, event_id: int) -> Event | None:
        statement = (select(Event).where(Event.id == event_id)
                     .options(selectinload(Event.appearances).selectinload(Appearance.artist),
                              selectinload(Event.sources)))
        return self.session.scalars(statement).one_or_none()

    def _check_artist(self, artist_id: int) -> None:
        if self.session.get(Artist, artist_id) is None:
            raise InputError({"artist_id": "出演者を選択してください"})

    def create(self, event_data: EventData, appearance_data: AppearanceData,
               source_data: SourceData | None = None) -> Event:
        self._check_artist(appearance_data.artist_id)
        event = Event(**vars(event_data))
        event.appearances.append(Appearance(**vars(appearance_data)))
        if source_data:
            event.sources.append(Source(**vars(source_data)))
        self.session.add(event)
        try:
            self.session.commit()
        except Exception:
            self.session.rollback()
            raise
        return event

    def update(self, event: Event, data: EventData) -> Event:
        for key, value in vars(data).items():
            setattr(event, key, value)
        try:
            self.session.commit()
        except Exception:
            self.session.rollback()
            raise
        return event

    def save_appearance(self, event: Event, data: AppearanceData,
                        appearance: Appearance | None = None) -> Appearance:
        self._check_artist(data.artist_id)
        appearance = appearance or Appearance(event=event, artist_id=data.artist_id)
        for key, value in vars(data).items():
            setattr(appearance, key, value)
        self.session.add(appearance)
        try:
            self.session.commit()
        except Exception:
            self.session.rollback()
            raise
        return appearance

    def save_source(self, event: Event, data: SourceData, source: Source | None = None) -> Source:
        source = source or Source(event=event, source_type=data.source_type)
        for key, value in vars(data).items():
            setattr(source, key, value)
        self.session.add(source)
        try:
            self.session.commit()
        except Exception:
            self.session.rollback()
            raise
        return source


def event_is_past(event: Event) -> bool:
    return event.event_date < japan_today()
