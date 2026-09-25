from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Artist(Base):
    __tablename__ = "artists"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    display_name: Mapped[str | None] = mapped_column(String(200))
    x_username: Mapped[str | None] = mapped_column(String(100))
    x_user_id: Mapped[str | None] = mapped_column(String(100))
    official_url: Mapped[str | None] = mapped_column(String(2048))
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="1")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now, server_default=func.current_timestamp())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now, server_default=func.current_timestamp())

    appearances: Mapped[list["Appearance"]] = relationship(back_populates="artist", cascade="all, delete-orphan")
