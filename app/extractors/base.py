from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time
from typing import Protocol


@dataclass(frozen=True)
class ParseContext:
    published_at: datetime | None = None
    reference_date: date | None = None
    artist_name: str | None = None


@dataclass
class ParsedEventCandidate:
    title: str | None = None
    event_date: date | None = None
    open_at: time | None = None
    start_at: time | None = None
    end_at: time | None = None
    venue: str | None = None
    venue_address: str | None = None
    ticket_url: str | None = None
    official_url: str | None = None
    appearance_start: time | None = None
    appearance_end: time | None = None
    benefit_start: time | None = None
    benefit_end: time | None = None
    stage_name: str | None = None
    change_kind: str | None = None
    change_summary: str | None = None
    confidence: float = 0.1
    warnings: list[str] = field(default_factory=list)
    parser_version: str = ""


class PostParser(Protocol):
    version: str

    def parse(self, text: str, context: ParseContext) -> ParsedEventCandidate: ...
