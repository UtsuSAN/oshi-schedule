from __future__ import annotations

from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.ext.mutable import MutableList
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class Source(Base):
    __tablename__ = "sources"
    __table_args__ = (CheckConstraint("source_type IN ('x', 'manual', 'official_site', 'other')", name="source_type_valid"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id", ondelete="CASCADE"), nullable=False, index=True)
    source_type: Mapped[str] = mapped_column(String(20), nullable=False, default="manual", server_default="manual")
    source_url: Mapped[str | None] = mapped_column(String(2048))
    source_account: Mapped[str | None] = mapped_column(String(200))
    source_post_id: Mapped[str | None] = mapped_column(String(100), index=True)
    source_text: Mapped[str | None] = mapped_column(Text)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    fetched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    media_urls: Mapped[list[str]] = mapped_column(MutableList.as_mutable(JSON), nullable=False, default=list)

    event: Mapped["Event"] = relationship(back_populates="sources")
