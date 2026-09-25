from __future__ import annotations

from datetime import date, datetime, time
from typing import Literal
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, field_serializer, field_validator

JAPAN = ZoneInfo("Asia/Tokyo")


class PublicModel(BaseModel):
    """Strict allowlist base: persistence models are never serialized directly."""

    model_config = ConfigDict(extra="forbid")


class PublicArtist(PublicModel):
    id: int
    display_name: str
    official_url: str | None = None
    x_username: str | None = None


class PublicAppearance(PublicModel):
    artist_id: int
    artist_name: str
    appearance_start_at: time | None = None
    appearance_end_at: time | None = None
    benefit_start_at: time | None = None
    benefit_end_at: time | None = None
    stage_name: str | None = None
    notes: str | None = None

    @field_serializer(
        "appearance_start_at",
        "appearance_end_at",
        "benefit_start_at",
        "benefit_end_at",
    )
    def serialize_local_time(self, value: time | None) -> str | None:
        # Event and Appearance SQL Time values are Japan-local wall clock times.
        return value.strftime("%H:%M") if value is not None else None


class PublicSource(PublicModel):
    source_type: str
    source_url: str | None = None


class PublicEvent(PublicModel):
    id: int
    title: str
    event_date: date
    open_at: time | None = None
    start_at: time | None = None
    end_at: time | None = None
    venue_name: str | None = None
    venue_address: str | None = None
    ticket_url: str | None = None
    ticket_release_date: date | None = None
    ticket_release_time: time | None = None
    official_url: str | None = None
    status: Literal["scheduled", "changed", "cancelled"]
    updated_at: datetime
    appearances: list[PublicAppearance]
    sources: list[PublicSource]

    @field_serializer("open_at", "start_at", "end_at", "ticket_release_time")
    def serialize_local_time(self, value: time | None) -> str | None:
        return value.strftime("%H:%M") if value is not None else None

    @field_validator("updated_at")
    @classmethod
    def updated_at_must_be_timezone_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("updated_at must include a timezone")
        return value.astimezone(JAPAN)


class PublicSchedule(PublicModel):
    schema_version: Literal["1.0"] = "1.0"
    generated_at: datetime
    timezone: Literal["Asia/Tokyo"] = "Asia/Tokyo"
    artists: list[PublicArtist]
    events: list[PublicEvent]

    @field_validator("generated_at")
    @classmethod
    def generated_at_must_be_timezone_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("generated_at must include a timezone")
        return value.astimezone(JAPAN)
