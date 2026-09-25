from __future__ import annotations

from datetime import date, datetime, time

from sqlalchemy import CheckConstraint, Date, DateTime, Integer, String, Time, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.artist import utc_now


class Event(Base):
    __tablename__ = "events"
    __table_args__ = (CheckConstraint("status IN ('scheduled', 'changed', 'cancelled', 'unknown')", name="status_valid"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(300), nullable=False, index=True)
    event_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    open_at: Mapped[time | None] = mapped_column(Time)
    start_at: Mapped[time | None] = mapped_column(Time)
    end_at: Mapped[time | None] = mapped_column(Time)
    venue_name: Mapped[str | None] = mapped_column(String(300))
    venue_address: Mapped[str | None] = mapped_column(String(500))
    ticket_url: Mapped[str | None] = mapped_column(String(2048))
    ticket_release_date: Mapped[date | None] = mapped_column(Date)
    ticket_release_time: Mapped[time | None] = mapped_column(Time)
    official_url: Mapped[str | None] = mapped_column(String(2048))
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="scheduled", server_default="scheduled")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now, server_default=func.current_timestamp())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now, server_default=func.current_timestamp())

    appearances: Mapped[list["Appearance"]] = relationship(back_populates="event", cascade="all, delete-orphan")
    sources: Mapped[list["Source"]] = relationship(back_populates="event", cascade="all, delete-orphan")
