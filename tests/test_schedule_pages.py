from datetime import date, datetime, time

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db import Base, get_session
from app.main import app
from app.models import Appearance, Artist, Event, Source


@pytest.fixture
def web_client(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    session = Session(engine, expire_on_commit=False)

    def override_session():
        yield session

    app.dependency_overrides[get_session] = override_session
    monkeypatch.setattr("app.main.japan_today", lambda: date(2026, 9, 24))
    with TestClient(app) as client:
        yield client, session
    app.dependency_overrides.clear()
    session.close()
    engine.dispose()


def test_today_page_shows_today_and_empty_is_normal(web_client):
    client, session = web_client
    session.add_all([
        Event(title="昨日の予定", event_date=date(2026, 9, 23)),
        Event(title="今日の架空ライブ", event_date=date(2026, 9, 24)),
        Event(title="明日の予定", event_date=date(2026, 9, 25)),
    ])
    session.commit()

    response = client.get("/")
    assert response.status_code == 200
    assert "今日の架空ライブ" in response.text
    assert "昨日の予定" not in response.text
    assert "明日の予定" not in response.text

    session.query(Event).delete()
    session.commit()
    empty_response = client.get("/today")
    assert empty_response.status_code == 200
    assert "今日の予定はありません" in empty_response.text


def test_week_and_month_views_render_expected_events_and_calendar_links(web_client):
    client, session = web_client
    session.add_all([
        Event(title="月曜予定", event_date=date(2026, 9, 21)),
        Event(title="日曜予定", event_date=date(2026, 9, 27)),
        Event(title="翌月予定", event_date=date(2026, 10, 1)),
    ])
    session.commit()

    week = client.get("/week")
    assert week.status_code == 200
    assert "月曜予定" in week.text and "日曜予定" in week.text
    assert "翌月予定" not in week.text
    month = client.get("/month?year=2026&month=9")
    assert month.status_code == 200
    assert "2026年9月" in month.text
    assert "/day/2026-09-21" in month.text
    assert "翌月予定" not in month.text


def test_detail_displays_appearances_jst_source_metadata_and_hides_source_text(web_client):
    client, session = web_client
    event = Event(
        title="架空フェス",
        event_date=date(2026, 9, 24),
        open_at=time(17, 0),
        start_at=time(17, 30),
        venue_name="架空ホール",
        updated_at=datetime(2026, 9, 23, 15, 30),
    )
    event.appearances.extend([
        Appearance(artist=Artist(name="星見ソーダ"), appearance_start_at=time(18, 0), benefit_start_at=time(18, 30), stage_name="メイン"),
        Appearance(artist=Artist(name="月虹パレット"), appearance_start_at=time(19, 0)),
    ])
    event.sources.append(Source(
        source_type="manual",
        source_url="https://example.invalid/source",
        source_text="秘密の元テキスト",
        published_at=datetime(2026, 9, 23, 15, 30),
    ))
    session.add(event)
    session.commit()

    response = client.get(f"/events/{event.id}")
    assert response.status_code == 200
    assert "星見ソーダ" in response.text and "月虹パレット" in response.text
    assert "18:00" in response.text and "18:30" in response.text
    assert "17:30" in response.text
    assert "2026/09/24 00:30" in response.text
    assert "https://example.invalid/source" in response.text
    assert "公開 2026/09/24 00:30" in response.text
    assert "秘密の元テキスト" not in response.text
    assert client.get("/events/99999").status_code == 404


def test_artist_filter_applies_to_schedule_views_and_is_kept_in_navigation(web_client):
    client, session = web_client
    chosen = Artist(name="フィルター対象", display_name="対象アーティスト")
    other = Artist(name="別アーティスト")
    session.add_all([chosen, other])
    session.flush()
    session.add_all([
        Event(title="対象イベント", event_date=date(2026, 9, 24), appearances=[Appearance(artist=chosen)]),
        Event(title="別イベント", event_date=date(2026, 9, 24), appearances=[Appearance(artist=other)]),
    ])
    session.commit()

    response = client.get(f"/?artist_id={chosen.id}")
    assert "対象イベント" in response.text
    assert "別イベント" not in response.text
    assert f"/week?artist_id={chosen.id}" in response.text
