from __future__ import annotations

from datetime import datetime
from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict, Field, field_validator


class CollectedPost(BaseModel):
    """A source-neutral post that can be handed to the shared import service."""

    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=1, max_length=20000)
    source_url: str | None = Field(default=None, max_length=2048)
    source_account: str | None = Field(default=None, max_length=200)
    published_at: datetime | None = None
    artist_id: int | None = Field(default=None, gt=0)
    external_id: str | None = Field(default=None, max_length=100)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("text")
    @classmethod
    def text_must_not_be_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("投稿本文を入力してください")
        return value

    @field_validator("source_url")
    @classmethod
    def source_url_must_be_http(cls, value: str | None) -> str | None:
        if value is None or not value.strip():
            return None
        from urllib.parse import urlsplit

        parsed = urlsplit(value.strip())
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            raise ValueError("source_urlはhttpまたはhttpsのURLを指定してください")
        return value.strip()


class Collector(Protocol):
    def collect(self) -> list[CollectedPost]: ...
