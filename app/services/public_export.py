from __future__ import annotations

import os
import tempfile
from ipaddress import ip_address
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import parse_qsl, urlsplit
from zoneinfo import ZoneInfo

from sqlalchemy import or_, select
from sqlalchemy.orm import Session, joinedload, selectinload

from app.models import Appearance, Artist, Event
from app.schemas.public import PublicAppearance, PublicArtist, PublicEvent, PublicSchedule, PublicSource
from app.services.events import as_japan_datetime, japan_today

JAPAN = ZoneInfo("Asia/Tokyo")
PUBLIC_STATUSES = ("scheduled", "changed", "cancelled")


def _public_web_url(value: str | None) -> str | None:
    """Keep only absolute web URLs; never serialize local paths or URL credentials."""
    if not value:
        return None
    candidate = value.strip()
    try:
        parsed = urlsplit(candidate)
        if (
            parsed.scheme.lower() not in {"http", "https"}
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
        ):
            return None
        hostname = parsed.hostname.lower()
        if hostname == "localhost" or hostname.endswith(".localhost"):
            return None
        try:
            if not ip_address(hostname).is_global:
                return None
        except ValueError:
            pass
        private_query_keys = {"api_key", "apikey", "token", "access_token", "auth", "authorization", "secret", "password", "signature", "sig"}
        if any(key.lower() in private_query_keys for key, _ in parse_qsl(parsed.query, keep_blank_values=True)):
            return None
    except ValueError:
        return None
    return candidate


class PublicExportService:
    """Build a validated, explicitly allowlisted read-only schedule snapshot."""

    def __init__(self, session: Session):
        self.session = session

    def build_snapshot(
        self,
        *,
        now: datetime | None = None,
        past_days: int = 30,
        future_days: int = 365,
    ) -> PublicSchedule:
        if past_days < 0 or future_days < 0:
            raise ValueError("past_days and future_days must be non-negative")

        instant = now or datetime.now(timezone.utc)
        if instant.tzinfo is None or instant.utcoffset() is None:
            raise ValueError("now must be timezone-aware")
        instant = instant.astimezone(JAPAN)
        today = japan_today(instant)
        start_date = today - timedelta(days=past_days)
        end_date = today + timedelta(days=future_days)

        events = list(self.session.scalars(
            select(Event)
            .where(
                or_(
                    Event.event_date.between(start_date, end_date),
                    Event.ticket_release_date.between(start_date, end_date),
                ),
                Event.status.in_(PUBLIC_STATUSES),
            )
            .options(
                selectinload(Event.appearances).joinedload(Appearance.artist),
                selectinload(Event.sources),
            )
            .order_by(Event.event_date, Event.start_at, Event.title, Event.id)
        ).unique().all())

        artist_by_id: dict[int, Artist] = {}
        public_events: list[PublicEvent] = []
        for event in events:
            public_appearances = []
            for appearance in event.appearances:
                artist = appearance.artist
                if artist is None:
                    continue
                artist_by_id[artist.id] = artist
                public_appearances.append(PublicAppearance(
                    artist_id=artist.id,
                    artist_name=artist.display_name or artist.name,
                    appearance_start_at=appearance.appearance_start_at,
                    appearance_end_at=appearance.appearance_end_at,
                    benefit_start_at=appearance.benefit_start_at,
                    benefit_end_at=appearance.benefit_end_at,
                    stage_name=appearance.stage_name,
                    notes=appearance.notes,
                ))

            public_events.append(PublicEvent(
                id=event.id,
                title=event.title,
                event_date=event.event_date,
                open_at=event.open_at,
                start_at=event.start_at,
                end_at=event.end_at,
                venue_name=event.venue_name,
                venue_address=event.venue_address,
                ticket_url=_public_web_url(event.ticket_url),
                ticket_release_date=event.ticket_release_date,
                ticket_release_time=event.ticket_release_time,
                official_url=_public_web_url(event.official_url),
                status=event.status,
                updated_at=as_japan_datetime(event.updated_at),
                appearances=public_appearances,
                sources=[
                    PublicSource(source_type=source.source_type, source_url=_public_web_url(source.source_url))
                    for source in event.sources
                ],
            ))

        public_artists = [
            PublicArtist(
                id=artist.id,
                display_name=artist.display_name or artist.name,
                official_url=_public_web_url(artist.official_url),
                x_username=artist.x_username,
            )
            for artist in sorted(artist_by_id.values(), key=lambda item: (item.display_name or item.name, item.id))
        ]
        return PublicSchedule(
            generated_at=instant,
            artists=public_artists,
            events=public_events,
        )

    @staticmethod
    def serialize_snapshot(snapshot: PublicSchedule) -> str:
        """Serialize and validate the exact JSON payload before any file is touched."""
        payload = snapshot.model_dump_json(indent=2)
        PublicSchedule.model_validate_json(payload)
        return payload + "\n"

    def write_snapshot(
        self,
        path: str | Path,
        *,
        now: datetime | None = None,
        past_days: int = 30,
        future_days: int = 365,
    ) -> PublicSchedule:
        snapshot = self.build_snapshot(now=now, past_days=past_days, future_days=future_days)
        payload = self.serialize_snapshot(snapshot)
        destination = Path(path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        temp_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-8", newline="\n", dir=destination.parent,
                prefix=f".{destination.name}.", suffix=".tmp", delete=False,
            ) as handle:
                temp_path = Path(handle.name)
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_path, destination)
            temp_path = None
        finally:
            if temp_path is not None:
                temp_path.unlink(missing_ok=True)
        return snapshot
