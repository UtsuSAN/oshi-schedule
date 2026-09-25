from __future__ import annotations

from calendar import monthrange
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload, selectinload

from app.models import Appearance, Artist, Event

JAPAN = ZoneInfo("Asia/Tokyo")


def as_japan_datetime(value: datetime | None) -> datetime | None:
    """Format naive database timestamps as UTC, then convert them to JST."""
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(JAPAN)


def japan_today(now: datetime | None = None) -> date:
    """Return the calendar date in Japan, including around UTC date boundaries."""
    instant = now or datetime.now(timezone.utc)
    if instant.tzinfo is None:
        instant = instant.replace(tzinfo=timezone.utc)
    return instant.astimezone(JAPAN).date()


class EventService:
    """Read-side event queries shared by HTML views and future API routes."""

    def __init__(self, session: Session):
        self.session = session

    @staticmethod
    def _options():
        return (
            selectinload(Event.appearances).joinedload(Appearance.artist),
            selectinload(Event.sources),
        )

    def _for_range(self, start: date, end: date, artist_id: int | None = None) -> list[Event]:
        statement = (
            select(Event)
            .where(Event.event_date >= start, Event.event_date <= end)
            .options(*self._options())
            .order_by(Event.event_date, Event.start_at, Event.title, Event.id)
        )
        if artist_id is not None:
            statement = statement.where(
                Event.id.in_(
                    select(Appearance.event_id).where(Appearance.artist_id == artist_id)
                )
            )
        return list(self.session.scalars(statement).unique().all())

    def get_today_events(self, on_date: date | None = None, artist_id: int | None = None) -> list[Event]:
        day = on_date or japan_today()
        return self._for_range(day, day, artist_id)

    def get_week_events(self, on_date: date | None = None, artist_id: int | None = None) -> list[Event]:
        day = on_date or japan_today()
        monday = day - timedelta(days=day.weekday())
        return self._for_range(monday, monday + timedelta(days=6), artist_id)

    def get_month_events(self, year: int, month: int, artist_id: int | None = None) -> list[Event]:
        first = date(year, month, 1)
        last = date(year, month, monthrange(year, month)[1])
        return self._for_range(first, last, artist_id)

    def get_event_detail(self, event_id: int) -> Event | None:
        statement = (
            select(Event)
            .where(Event.id == event_id)
            .options(*self._options())
        )
        return self.session.scalars(statement).unique().one_or_none()

    def get_artists(self) -> list[Artist]:
        return list(self.session.scalars(select(Artist).where(Artist.enabled.is_(True)).order_by(Artist.name, Artist.id)).all())
