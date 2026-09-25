from datetime import date, time

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db import Base, get_session
from app.main import app
from app.models import Appearance, Artist, Event, Source
from app.services.admin import AdminEventService, AppearanceData, EventData, SourceData


@pytest.fixture
def admin_client():
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


def event_form(artist_id: int, **changes):
    values = {
        "title": "架空ライブ", "event_date": "2026-09-24", "open_at": "17:00",
        "start_at": "17:30", "end_at": "20:00", "venue_name": "架空ホール",
        "status": "scheduled", "artist_id": str(artist_id),
        "appearance_start_at": "18:00", "appearance_end_at": "18:20",
        "benefit_start_at": "18:40", "benefit_end_at": "19:20",
    }
    values.update(changes)
    return values


def test_admin_dashboard_and_lists_are_readable(admin_client):
    client, _ = admin_client
    for path in ("/admin", "/admin/artists", "/admin/events", "/admin/artists/new", "/admin/events/new"):
        assert client.get(path).status_code == 200
    assert "0件" in client.get("/admin").text


def test_ticket_release_can_be_saved_with_or_without_time(admin_client):
    client, session = admin_client
    artist = Artist(name="架空ユニット")
    session.add(artist)
    session.commit()
    response = client.post("/admin/events/new", data=event_form(
        artist.id, ticket_release_date="2026-09-26", ticket_release_time="10:00"))
    assert response.status_code == 200
    event = session.scalar(select(Event))
    assert event.ticket_release_date == date(2026, 9, 26)
    assert event.ticket_release_time == time(10)
    assert "チケット発売" in client.get(f"/events/{event.id}").text
    assert client.get(f"/events/{event.id}/calendar/google/ticket-release", follow_redirects=False).status_code == 307

    response = client.post(f"/admin/events/{event.id}/edit", data=event_form(
        artist.id, ticket_release_date="2026-09-27", ticket_release_time=""))
    assert response.status_code == 200
    session.refresh(event)
    assert event.ticket_release_date == date(2026, 9, 27)
    assert event.ticket_release_time is None

    invalid = client.post(f"/admin/events/{event.id}/edit", data=event_form(
        artist.id, ticket_release_date="", ticket_release_time="10:00"))
    assert invalid.status_code == 422


def test_artist_create_edit_validation_and_disable_while_in_use(admin_client):
    client, session = admin_client
    invalid = client.post("/admin/artists/new", data={"name": "", "enabled": "on"})
    assert invalid.status_code == 422
    assert "名前を入力してください" in invalid.text

    created = client.post("/admin/artists/new", data={
        "name": "架空ユニット", "display_name": "架空アイドル", "x_username": "@fictional",
        "x_user_id": "123456789",
        "enabled": "on",
    })
    assert created.status_code == 200
    assert "アーティストを登録しました" in created.text
    artist = session.scalar(select(Artist))
    assert artist.x_username == "fictional"
    assert artist.x_user_id == "123456789"

    event = Event(title="出演イベント", event_date=date(2026, 9, 24),
                  appearances=[Appearance(artist=artist)])
    session.add(event)
    session.commit()
    updated = client.post(f"/admin/artists/{artist.id}/edit", data={
        "name": "架空ユニット改", "display_name": "架空アイドル改",
        "x_username": "fictional_2", "x_user_id": "987654321",
    })
    assert updated.status_code == 200
    assert "アーティストを更新しました" in updated.text
    session.refresh(artist)
    assert artist.name == "架空ユニット改"
    assert artist.x_username == "fictional_2"
    assert artist.x_user_id == "987654321"
    assert artist.enabled is False
    assert session.get(Appearance, event.appearances[0].id).artist_id == artist.id


def test_event_create_with_appearance_and_source_is_public_immediately(admin_client, monkeypatch):
    client, session = admin_client
    monkeypatch.setattr("app.main.japan_today", lambda: date(2026, 9, 24))
    artist = Artist(name="星見ソーダ")
    session.add(artist)
    session.commit()

    response = client.post("/admin/events/new", data=event_form(
        artist.id, source_type="x", source_url="https://example.invalid/post/1",
        source_text="管理用の投稿本文", published_at="2026-09-24T10:30"))
    assert response.status_code == 200
    assert "イベントを登録しました" in response.text
    event = session.scalar(select(Event))
    assert event is not None
    assert event.appearances[0].artist_id == artist.id
    assert event.appearances[0].appearance_start_at == time(18, 0)
    assert event.sources[0].source_type == "x"
    assert event.sources[0].published_at.hour == 1
    assert "架空ライブ" in client.get("/").text
    detail = client.get(f"/events/{event.id}")
    assert "18:00" in detail.text
    assert "管理用の投稿本文" not in detail.text


def test_event_edit_appearance_add_update_and_source_add_update(admin_client, monkeypatch):
    client, session = admin_client
    monkeypatch.setattr("app.main.japan_today", lambda: date(2026, 9, 24))
    first = Artist(name="星見ソーダ")
    second = Artist(name="月虹パレット")
    session.add_all([first, second])
    session.commit()
    client.post("/admin/events/new", data=event_form(first.id))
    event = session.scalar(select(Event))

    edited = client.post(f"/admin/events/{event.id}/edit", data=event_form(
        first.id, title="変更後ライブ", status="changed", event_date="2026-09-25"))
    assert "イベントを更新しました" in edited.text
    assert "変更後ライブ" in client.get("/day/2026-09-25").text
    assert "変更後ライブ" not in client.get("/").text

    added = client.post(f"/admin/events/{event.id}/appearances/new", data={
        "artist_id": str(second.id), "appearance_start_at": "19:00", "appearance_end_at": "19:20",
    })
    assert "出演情報を追加しました" in added.text
    assert len(event.appearances) == 2
    second_appearance = next(a for a in event.appearances if a.artist_id == second.id)
    changed = client.post(f"/admin/events/{event.id}/appearances/{second_appearance.id}/edit", data={
        "artist_id": str(second.id), "appearance_start_at": "19:30", "appearance_end_at": "19:50",
    })
    assert "出演情報を更新しました" in changed.text
    assert "19:30" in client.get(f"/events/{event.id}").text

    source_added = client.post(f"/admin/events/{event.id}/sources/new", data={
        "source_type": "manual", "source_url": "https://example.invalid/source",
        "source_text": "非公開本文",
    })
    assert "出典を追加しました" in source_added.text
    source = event.sources[0]
    source_edited = client.post(f"/admin/events/{event.id}/sources/{source.id}/edit", data={
        "source_type": "official_site", "source_url": "https://example.invalid/updated",
        "source_text": "更新本文",
    })
    assert "出典を更新しました" in source_edited.text
    assert source.source_type == "official_site"
    assert "更新本文" in client.get(f"/admin/events/{event.id}/edit").text
    assert "更新本文" not in client.get(f"/events/{event.id}").text


def test_invalid_event_and_appearance_preserve_input_without_writes(admin_client):
    client, session = admin_client
    artist = Artist(name="架空ユニット")
    session.add(artist)
    session.commit()
    invalid = client.post("/admin/events/new", data=event_form(
        artist.id, title="", open_at="19:00", start_at="18:00",
        appearance_start_at="20:00", appearance_end_at="19:00",
        ticket_url="http://[bad"))
    assert invalid.status_code == 422
    assert "イベント名を入力してください" in invalid.text
    assert "OPENはSTART以前" in invalid.text
    assert "出演開始は終了以前" in invalid.text
    assert "チケットURLはhttpまたはhttps" in invalid.text
    assert 'value="19:00"' in invalid.text
    assert session.scalar(select(Event.id)) is None


def test_transaction_rolls_back_event_when_source_insert_fails(admin_client):
    _, session = admin_client
    artist = Artist(name="架空ユニット")
    session.add(artist)
    session.commit()
    event_data = EventData("失敗するイベント", date(2026, 9, 24), None, None, None,
                           None, None, None, None, "scheduled")
    appearance_data = AppearanceData(artist.id, None, None, None, None, None, None)
    invalid_source = SourceData("invalid", None, None, None, None)
    with pytest.raises(IntegrityError):
        AdminEventService(session).create(event_data, appearance_data, invalid_source)
    assert session.scalar(select(Event.id)) is None
    assert session.scalar(select(Appearance.id)) is None
    assert session.scalar(select(Source.id)) is None


def test_unrelated_appearance_and_source_cannot_be_edited(admin_client):
    client, session = admin_client
    artist = Artist(name="架空ユニット")
    first = Event(title="一件目", event_date=date(2026, 9, 24),
                  appearances=[Appearance(artist=artist)], sources=[Source(source_type="manual")])
    second = Event(title="二件目", event_date=date(2026, 9, 25))
    session.add_all([first, second])
    session.commit()
    assert client.get(f"/admin/events/{second.id}/appearances/{first.appearances[0].id}/edit").status_code == 404
    assert client.get(f"/admin/events/{second.id}/sources/{first.sources[0].id}/edit").status_code == 404


def test_blank_source_is_rejected_without_changing_event(admin_client):
    client, session = admin_client
    event = Event(title="架空イベント", event_date=date(2026, 9, 24))
    session.add(event)
    session.commit()
    response = client.post(f"/admin/events/{event.id}/sources/new", data={"source_type": "manual"})
    assert response.status_code == 422
    assert "出典URL、投稿者、本文、投稿日時のいずれか" in response.text
    assert session.scalar(select(Source.id)) is None
