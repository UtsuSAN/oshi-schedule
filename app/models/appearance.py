from __future__ import annotations

from datetime import time

from sqlalchemy import ForeignKey, Integer, String, Text, Time
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class Appearance(Base):
    __tablename__ = "appearances"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id", ondelete="CASCADE"), nullable=False, index=True)
    artist_id: Mapped[int] = mapped_column(ForeignKey("artists.id", ondelete="CASCADE"), nullable=False, index=True)
    appearance_start_at: Mapped[time | None] = mapped_column(Time)
    appearance_end_at: Mapped[time | None] = mapped_column(Time)
    benefit_start_at: Mapped[time | None] = mapped_column(Time)
    benefit_end_at: Mapped[time | None] = mapped_column(Time)
    stage_name: Mapped[str | None] = mapped_column(String(200))
    notes: Mapped[str | None] = mapped_column(Text)

    event: Mapped["Event"] = relationship(back_populates="appearances")
    artist: Mapped["Artist"] = relationship(back_populates="appearances")
