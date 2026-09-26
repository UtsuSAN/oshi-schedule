from __future__ import annotations

from datetime import date, datetime, time

from sqlalchemy import CheckConstraint, Date, DateTime, Float, ForeignKey, Integer, JSON, String, Text, Time, func
from sqlalchemy.ext.mutable import MutableList
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models.artist import utc_now


class ImportCandidate(Base):
    __tablename__ = "import_candidates"
    __table_args__ = (
        CheckConstraint("candidate_type IN ('new', 'update', 'possible_duplicate', 'unknown')", name="candidate_type_valid"),
        CheckConstraint("change_kind IS NULL OR change_kind IN ('appearance_cancelled', 'event_cancelled', 'postponed', 'time_changed', 'venue_changed', 'ticket_changed', 'generic_update')", name="change_kind_valid"),
        CheckConstraint("review_status IN ('pending', 'approved', 'rejected')", name="review_status_valid"),
        CheckConstraint("confidence IS NULL OR (confidence >= 0 AND confidence <= 1)", name="confidence_range"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    input_hash: Mapped[str | None] = mapped_column(String(64), unique=True, index=True)
    external_id: Mapped[str | None] = mapped_column(String(100))
    source_url: Mapped[str | None] = mapped_column(String(2048))
    raw_text: Mapped[str | None] = mapped_column(Text)
    source_account: Mapped[str | None] = mapped_column(String(200))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    artist_id: Mapped[int | None] = mapped_column(ForeignKey("artists.id", ondelete="SET NULL"), index=True)
    candidate_title: Mapped[str | None] = mapped_column(String(300))
    candidate_date: Mapped[date | None] = mapped_column(Date)
    candidate_open_at: Mapped[time | None] = mapped_column(Time)
    candidate_start_at: Mapped[time | None] = mapped_column(Time)
    candidate_end_at: Mapped[time | None] = mapped_column(Time)
    candidate_venue: Mapped[str | None] = mapped_column(String(300))
    candidate_venue_address: Mapped[str | None] = mapped_column(String(500))
    candidate_ticket_url: Mapped[str | None] = mapped_column(String(2048))
    candidate_official_url: Mapped[str | None] = mapped_column(String(2048))
    candidate_appearance_start: Mapped[time | None] = mapped_column(Time)
    candidate_appearance_end: Mapped[time | None] = mapped_column(Time)
    candidate_benefit_start: Mapped[time | None] = mapped_column(Time)
    candidate_benefit_end: Mapped[time | None] = mapped_column(Time)
    candidate_stage_name: Mapped[str | None] = mapped_column(String(200))
    confidence: Mapped[float | None] = mapped_column(Float)
    candidate_type: Mapped[str] = mapped_column(String(30), nullable=False, default="unknown", server_default="unknown")
    change_kind: Mapped[str | None] = mapped_column(String(40))
    change_summary: Mapped[str | None] = mapped_column(String(500))
    target_event_id: Mapped[int | None] = mapped_column(ForeignKey("events.id", ondelete="SET NULL"), index=True)
    review_status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending", server_default="pending")
    parser_version: Mapped[str] = mapped_column(String(50), nullable=False, default="rule-based-v1", server_default="legacy")
    parse_warnings: Mapped[list[str]] = mapped_column(MutableList.as_mutable(JSON), nullable=False, default=list, server_default="[]")
    duplicate_event_id: Mapped[int | None] = mapped_column(ForeignKey("events.id", ondelete="SET NULL"))
    created_event_id: Mapped[int | None] = mapped_column(ForeignKey("events.id", ondelete="SET NULL"))
    review_note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now, server_default=func.current_timestamp())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now, server_default=func.current_timestamp())
