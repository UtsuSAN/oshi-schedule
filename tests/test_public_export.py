from __future__ import annotations

import json
from datetime import date, datetime, time
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db import Base
from app.models import Appearance, Artist, Event, ImportCandidate, Source
from app.schemas.public import PublicSchedule
from app.services.public_export import PublicExportService

JAPAN = ZoneInfo("Asia/Tokyo")
FIXED_NOW = datetime(2026, 9, 25, 20, 0, tzinfo=JAPAN)


@pytest.fixture
def export_session(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'public-export.sqlite3'}")
    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as session:
        yield session
    engine.dispose()


def add_event(session: Session, title: str, day: date, *, status: str = "scheduled") -> Event:
    event = Event(title=title, event_date=day, status=status)
    session.add(event)
    session.flush()
    return event


def test_snapshot_uses_public_allowlist_and_nests_multi_artist_appearances(export_session):
    session = export_session
    first = Artist(
        name="内部表示名A", display_name="架空ユニットA", official_url="https://artist.example.invalid/",
        x_username="fictional_a", x_user_id="private-user-id", enabled=False,
    )
    second = Artist(name="架空ユニットB")
    event = Event(
        title="架空フェス", event_date=date(2026, 9, 27), open_at=time(17),
        start_at=time(17, 30), end_at=time(20), venue_name="架空ホール",
        ticket_release_date=date(2026, 9, 26), ticket_release_time=time(10),
        venue_address="静岡県架空市", ticket_url="https://tickets.example.invalid/1",
        official_url="https://event.example.invalid/1", status="changed",
        updated_at=datetime(2026, 9, 25, 11, 0),
    )
    event.appearances.extend([
        Appearance(artist=first, appearance_start_at=time(18, 10), appearance_end_at=time(18, 30),
                   benefit_start_at=time(18, 50), benefit_end_at=time(19, 50),
                   stage_name="メイン", notes="架空の出演メモ"),
        Appearance(artist=second, appearance_start_at=time(19), appearance_end_at=time(19, 20)),
    ])
    event.sources.extend([
        Source(source_type="official_site", source_url="https://source.example.invalid/1",
               source_text="TOP_SECRET_SOURCE_BODY"),
        Source(source_type="x", source_url="https://x.example.invalid/post/1",
               source_post_id="private-post-id", source_account="private-account"),
    ])
    session.add(event)
    session.add(ImportCandidate(
        raw_text="TOP_SECRET_RAW_BODY", input_hash="TOP_SECRET_HASH", external_id="TOP_SECRET_EXTERNAL",
        candidate_title="非公開Candidate", confidence=0.9, parser_version="private-parser",
        parse_warnings=["TOP_SECRET_WARNING"], review_status="pending",
    ))
    session.commit()

    snapshot = PublicExportService(session).build_snapshot(now=FIXED_NOW)
    serialized = PublicExportService.serialize_snapshot(snapshot)
    data = json.loads(serialized)

    assert data["schema_version"] == "1.0"
    assert data["timezone"] == "Asia/Tokyo"
    assert data["generated_at"] == "2026-09-25T20:00:00+09:00"
    assert data["artists"] == [
        {"id": first.id, "display_name": "架空ユニットA", "official_url": "https://artist.example.invalid/", "x_username": "fictional_a"},
        {"id": second.id, "display_name": "架空ユニットB", "official_url": None, "x_username": None},
    ]
    exported = data["events"][0]
    assert exported["status"] == "changed"
    assert exported["updated_at"] == "2026-09-25T20:00:00+09:00"
    assert exported["start_at"] == "17:30"
    assert exported["ticket_release_date"] == "2026-09-26"
    assert exported["ticket_release_time"] == "10:00"
    assert exported["appearances"][0]["appearance_start_at"] == "18:10"
    assert exported["appearances"][0]["benefit_end_at"] == "19:50"
    assert exported["appearances"][0]["artist_name"] == "架空ユニットA"
    assert exported["sources"] == [
        {"source_type": "official_site", "source_url": "https://source.example.invalid/1"},
        {"source_type": "x", "source_url": "https://x.example.invalid/post/1"},
    ]

    assert set(data) == {"schema_version", "generated_at", "timezone", "artists", "events"}
    assert set(data["artists"][0]) == {"id", "display_name", "official_url", "x_username"}
    assert set(exported) == {
        "id", "title", "event_date", "open_at", "start_at", "end_at", "venue_name", "venue_address",
        "ticket_url", "ticket_release_date", "ticket_release_time", "official_url", "status", "updated_at", "appearances", "sources",
    }
    assert set(exported["appearances"][0]) == {
        "artist_id", "artist_name", "appearance_start_at", "appearance_end_at", "benefit_start_at",
        "benefit_end_at", "stage_name", "notes",
    }
    assert all(key not in serialized for key in (
        "source_text", "raw_text", "parse_warnings", "input_hash", "external_id", "review_status",
        "confidence", "parser_version", "private-user-id", "private-post-id", "private-account",
        "TOP_SECRET_",
    ))


def test_snapshot_range_is_configurable_and_only_public_statuses_are_included(export_session):
    add_event(export_session, "境界開始", date(2026, 8, 26))
    add_event(export_session, "境界終了", date(2027, 9, 25), status="cancelled")
    add_event(export_session, "過去範囲外", date(2026, 8, 25))
    add_event(export_session, "未来範囲外", date(2027, 9, 26))
    add_event(export_session, "内部unknown", date(2026, 9, 25), status="unknown")
    export_session.commit()

    events = PublicExportService(export_session).build_snapshot(now=FIXED_NOW).events
    assert [event.title for event in events] == ["境界開始", "境界終了"]
    assert events[1].status == "cancelled"

    narrowed = PublicExportService(export_session).build_snapshot(
        now=FIXED_NOW, past_days=0, future_days=0,
    )
    assert narrowed.events == []
    with pytest.raises(ValueError):
        PublicExportService(export_session).build_snapshot(now=FIXED_NOW, past_days=-1)


def test_snapshot_includes_ticket_release_in_range_when_event_is_later(export_session):
    event = add_event(export_session, "翌々年の架空公演", date(2028, 1, 1))
    event.ticket_release_date = date(2026, 9, 26)
    event.ticket_release_time = time(10)
    export_session.commit()

    snapshot = PublicExportService(export_session).build_snapshot(now=FIXED_NOW)
    assert [item.title for item in snapshot.events] == ["翌々年の架空公演"]
    assert snapshot.events[0].ticket_release_date == date(2026, 9, 26)


def test_empty_snapshot_and_example_fixture_validate(export_session):
    empty = PublicExportService(export_session).build_snapshot(now=FIXED_NOW)
    assert empty.events == []
    assert empty.artists == []
    assert PublicSchedule.model_validate_json(PublicExportService.serialize_snapshot(empty))

    example_path = Path(__file__).parents[1] / "examples" / "public_schedule.example.json"
    example = PublicSchedule.model_validate_json(example_path.read_text(encoding="utf-8"))
    assert any(len(event.appearances) == 2 for event in example.events)
    assert any(event.status == "cancelled" for event in example.events)


def test_write_is_atomic_utf8_and_keeps_existing_snapshot_on_validation_failure(export_session, tmp_path, monkeypatch):
    event = add_event(export_session, "日本語の架空予定", date(2026, 9, 25))
    export_session.commit()
    destination = tmp_path / "exports" / "public_schedule.json"
    service = PublicExportService(export_session)
    snapshot = service.write_snapshot(destination, now=FIXED_NOW)
    original = destination.read_bytes()
    assert "日本語の架空予定" in original.decode("utf-8")
    assert snapshot.events[0].id == event.id
    assert not list(destination.parent.glob("*.tmp"))

    def reject_payload(cls, *_args, **_kwargs):
        raise ValidationError.from_exception_data("PublicSchedule", [])

    monkeypatch.setattr(PublicSchedule, "model_validate_json", classmethod(reject_payload))
    with pytest.raises(ValidationError):
        service.write_snapshot(destination, now=FIXED_NOW)
    assert destination.read_bytes() == original
    assert not list(destination.parent.glob("*.tmp"))


def test_snapshot_requires_timezone_aware_generation_instant(export_session):
    with pytest.raises(ValueError, match="timezone-aware"):
        PublicExportService(export_session).build_snapshot(now=datetime(2026, 9, 25, 20))


def test_snapshot_drops_local_paths_and_urls_with_embedded_credentials(export_session):
    artist = Artist(name="架空アーティスト", official_url="file:///C:/Users/private/artist.html")
    event = Event(
        title="架空イベント", event_date=date(2026, 9, 25),
        ticket_url="C:\\Users\\private\\tickets.txt",
    )
    event.appearances.append(Appearance(artist=artist))
    event.sources.append(Source(
        source_type="official_site", source_url="https://account:secret@example.invalid/event",
    ))
    event.sources.append(Source(
        source_type="official_site", source_url="http://127.0.0.1:8000/private",
    ))
    event.sources.append(Source(
        source_type="official_site", source_url="https://example.invalid/event?access_token=private",
    ))
    export_session.add(event)
    export_session.commit()

    data = json.loads(PublicExportService.serialize_snapshot(
        PublicExportService(export_session).build_snapshot(now=FIXED_NOW),
    ))
    assert data["artists"][0]["official_url"] is None
    assert data["events"][0]["ticket_url"] is None
    assert all(source["source_url"] is None for source in data["events"][0]["sources"])
    serialized = json.dumps(data, ensure_ascii=False)
    assert "C:\\Users" not in serialized
    assert "account:secret" not in serialized
    assert "127.0.0.1" not in serialized
    assert "access_token" not in serialized
