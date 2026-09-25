from datetime import date, datetime, time
from urllib.parse import parse_qs, urlparse

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db import Base, get_session
from app.main import app
from app.models import Appearance, Artist, Event, Source
from app.services.calendar import (
    DEFAULT_APPEARANCE_DURATION,
    DEFAULT_BENEFIT_DURATION,
    DEFAULT_EVENT_DURATION,
    CalendarService,
)


def make_event(**kwargs):
    event = Event(
        id=41,
        title="星空フェス, 秋編; 特別公演",
        event_date=date(2026, 9, 24),
        venue_name="静岡・架空ホール",
        venue_address="静岡県架空市1-2",
        ticket_url="https://tickets.example.invalid/event?id=1&lang=ja",
        official_url="https://official.example.invalid/live",
        updated_at=datetime(2026, 9, 23, 15, 30),
        **kwargs,
    )
    event.sources.append(Source(source_url="https://example.invalid/post/1", source_text="絶対に出力しない秘密の本文"))
    artist = Artist(id=8, name="星見ソーダ", display_name="星見ソーダ")
    appearance = Appearance(
        id=62,
        artist=artist,
        appearance_start_at=time(18, 10),
        appearance_end_at=time(18, 30),
        benefit_start_at=time(18, 50),
        benefit_end_at=time(19, 50),
    )
    event.appearances.append(appearance)
    return event, appearance


def test_google_calendar_urls_encode_japanese_urls_and_local_times():
    event, appearance = make_event(open_at=time(12, 0), start_at=time(12, 30), end_at=time(20, 0))
    service = CalendarService()

    event_url = service.build_event_calendar_url(event)
    params = parse_qs(urlparse(event_url).query)
    assert urlparse(event_url).netloc == "calendar.google.com"
    assert params["dates"] == ["20260924T120000/20260924T200000"]
    assert params["ctz"] == ["Asia/Tokyo"]
    assert "星空フェス, 秋編; 特別公演" in params["text"][0]
    assert "静岡・架空ホール" in params["location"][0]
    assert "https://tickets.example.invalid/event?id=1&lang=ja" in params["details"][0]
    assert "https://example.invalid/post/1" in params["details"][0]
    assert "絶対に出力しない秘密の本文" not in params["details"][0]

    appearance_url = service.build_appearance_calendar_url(event, appearance)
    appearance_params = parse_qs(urlparse(appearance_url).query)
    assert appearance_params["dates"] == ["20260924T181000/20260924T183000"]
    assert "星見ソーダ 出演" in appearance_params["text"][0]
    benefit_url = service.build_benefit_calendar_url(event, appearance)
    benefit_params = parse_qs(urlparse(benefit_url).query)
    assert benefit_params["dates"] == ["20260924T185000/20260924T195000"]
    assert "特典会" in benefit_params["text"][0]


def test_event_all_day_and_missing_end_durations_are_explicit():
    event, appearance = make_event()
    event.open_at = None
    event.start_at = None
    params = parse_qs(urlparse(CalendarService().build_event_calendar_url(event)).query)
    assert params["dates"] == ["20260924/20260925"]
    assert "VALUE=DATE:20260924" in CalendarService().build_event_ics(event)

    event.open_at = time(18, 0)
    event.end_at = None
    event_ics = CalendarService().build_event_ics(event)
    assert "DTEND;TZID=Asia/Tokyo:20260924T200000" in event_ics
    appearance.appearance_end_at = None
    benefit_ics = CalendarService().build_appearance_ics(event, appearance)
    assert "DTEND;TZID=Asia/Tokyo:20260924T184000" in benefit_ics
    appearance.benefit_end_at = None
    benefit_ics = CalendarService().build_benefit_ics(event, appearance)
    assert "DTEND;TZID=Asia/Tokyo:20260924T195000" in benefit_ics
    assert DEFAULT_EVENT_DURATION.total_seconds() == 7200
    assert DEFAULT_APPEARANCE_DURATION.total_seconds() == 1800
    assert DEFAULT_BENEFIT_DURATION.total_seconds() == 3600


def test_overnight_appearance_keeps_japan_wall_time_and_stable_uid():
    event, appearance = make_event()
    appearance.appearance_start_at = time(23, 30)
    appearance.appearance_end_at = time(0, 30)
    service = CalendarService()
    first = service.build_appearance_ics(event, appearance)
    second = service.build_appearance_ics(event, appearance)
    assert "DTSTART;TZID=Asia/Tokyo:20260924T233000" in first
    assert "DTEND;TZID=Asia/Tokyo:20260925T003000" in first
    assert "UID:appearance-62@oshi-schedule" in first
    assert first == second
    assert "DTSTART;TZID=Asia/Tokyo:20260924T181000" not in first


def test_ics_includes_metadata_escapes_text_and_folds_utf8_lines():
    event, appearance = make_event(start_at=time(12, 30), end_at=time(20, 0))
    event.title = "推し活" * 40 + ",;\\\n新公演"
    ics = CalendarService().build_event_ics(event)
    unfolded = ics.replace("\r\n ", "")
    assert ics.endswith("\r\n")
    assert "DTSTART;TZID=Asia/Tokyo:20260924T123000" in ics
    assert "DTEND;TZID=Asia/Tokyo:20260924T200000" in ics
    assert "TZID:Asia/Tokyo" in ics and "TZOFFSETTO:+0900" in ics
    assert "LOCATION:静岡・架空ホール\\, 静岡県架空市1-2" in ics
    assert "https://tickets.example.invalid/event?id=1&lang=ja" in unfolded
    assert "https://example.invalid/post/1" in unfolded
    assert "絶対に出力しない秘密の本文" not in unfolded
    assert "\\," in unfolded and "\\;" in unfolded and "\\\\" in unfolded and "\\n" in unfolded
    for physical_line in ics.split("\r\n"):
        assert len(physical_line.encode("utf-8")) <= 75

    appearance_ics = CalendarService().build_appearance_ics(event, appearance)
    benefit_ics = CalendarService().build_benefit_ics(event, appearance)
    assert "UID:appearance-62@oshi-schedule" in appearance_ics
    assert "UID:benefit-62@oshi-schedule" in benefit_ics


def test_appearance_and_benefit_without_start_have_no_calendar_entry():
    event, appearance = make_event()
    appearance.appearance_start_at = None
    appearance.benefit_start_at = None
    service = CalendarService()
    assert service.build_appearance_calendar_url(event, appearance) is None
    assert service.build_appearance_ics(event, appearance) is None
    assert service.build_benefit_calendar_url(event, appearance) is None
    assert service.build_benefit_ics(event, appearance) is None


@pytest.fixture
def calendar_client():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    session = Session(engine, expire_on_commit=False)

    def override_session():
        yield session

    app.dependency_overrides[get_session] = override_session
    with TestClient(app) as client:
        yield client, session
    app.dependency_overrides.clear()
    session.close()
    engine.dispose()


def test_http_calendar_routes_and_detail_cover_event_appearance_and_benefit(calendar_client):
    client, session = calendar_client
    event, appearance = make_event(start_at=time(12, 30), end_at=time(20, 0))
    # Persist using database-generated IDs, keeping the Artist/Appearance relations real.
    event.id = None
    appearance.id = None
    appearance.artist.id = None
    session.add(event)
    session.commit()

    detail = client.get(f"/events/{event.id}")
    assert detail.status_code == 200
    event_response = client.get(f"/events/{event.id}/calendar/event.ics")
    assert event_response.status_code == 200
    assert event_response.headers["content-type"].startswith("text/calendar")
    assert "attachment; filename=\"event-" in event_response.headers["content-disposition"]
    assert f"UID:event-{event.id}@oshi-schedule" in event_response.text

    appearance_response = client.get(f"/events/{event.id}/calendar/appearance/{appearance.id}.ics")
    benefit_response = client.get(f"/events/{event.id}/calendar/benefit/{appearance.id}.ics")
    assert appearance_response.status_code == 200 and "星見ソーダ" in appearance_response.text
    assert benefit_response.status_code == 200 and "特典会" in benefit_response.text
    assert client.get(f"/events/{event.id}/calendar/google/event", follow_redirects=False).status_code == 307

    appearance.appearance_start_at = None
    session.commit()
    assert client.get(f"/events/{event.id}/calendar/appearance/{appearance.id}.ics").status_code == 404
    assert client.get(f"/events/{event.id}/calendar/google/appearance/{appearance.id}").status_code == 404
    assert client.get("/events/999999/calendar/event.ics").status_code == 404


def test_detail_calendar_actions_are_per_artist_and_require_start_times(calendar_client):
    client, session = calendar_client
    event = Event(title="架空の合同ライブ", event_date=date(2026, 9, 24))
    timed = Appearance(artist=Artist(name="星見ソーダ"), appearance_start_at=time(18, 10))
    untimed = Appearance(artist=Artist(name="月虹パレット"))
    event.appearances.extend((timed, untimed))
    session.add(event)
    session.commit()

    detail = client.get(f"/events/{event.id}")
    assert detail.status_code == 200
    assert f"/events/{event.id}/calendar/event.ics" in detail.text
    assert f"/events/{event.id}/calendar/appearance/{timed.id}.ics" in detail.text
    assert f"/events/{event.id}/calendar/appearance/{untimed.id}.ics" not in detail.text
    assert f"/events/{event.id}/calendar/benefit/{untimed.id}.ics" not in detail.text
    assert "星見ソーダ 出演" in detail.text
    assert "月虹パレット 出演" not in detail.text
