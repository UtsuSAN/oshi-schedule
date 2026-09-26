from datetime import date, time

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db import Base, get_session
from app.main import app
from app.models import Appearance, Artist, Event, ImportCandidate, Source
from app.services.candidates import CandidateService


@pytest.fixture
def candidate_client():
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


def sample_post():
    return """2026/09/27(日)
架空FES
会場：ABC HALL
OPEN 17:00
START 17:30
出演 18:10〜18:30
特典会 18:50〜19:50"""


def candidate_form(candidate: ImportCandidate, **changes):
    fields = (
        "raw_text", "source_url", "source_account", "published_at", "artist_id",
        "candidate_title", "candidate_date", "candidate_open_at", "candidate_start_at",
        "candidate_end_at", "candidate_venue", "candidate_venue_address",
        "candidate_ticket_url", "candidate_official_url", "candidate_appearance_start",
        "candidate_appearance_end", "candidate_benefit_start", "candidate_benefit_end",
        "candidate_stage_name",
    )
    values = {}
    for field in fields:
        value = getattr(candidate, field)
        if field == "published_at" and value:
            from app.services.events import as_japan_datetime
            value = as_japan_datetime(value).strftime("%Y-%m-%dT%H:%M")
        values[field] = value.isoformat(timespec="minutes") if isinstance(value, time) else (
            value.isoformat() if isinstance(value, date) else str(value) if value is not None else "")
    values.update(changes)
    return values


def test_import_creates_pending_candidate_without_event_and_approval_creates_all(candidate_client):
    client, session = candidate_client
    artist = Artist(name="架空ユニット")
    session.add(artist)
    session.commit()
    assert client.get("/admin/import").status_code == 200
    response = client.post("/admin/import", data={
        "raw_text": sample_post(), "source_url": "https://x.com/fictional/status/12345",
        "source_account": "fictional", "published_at": "2026-09-20T12:00",
        "artist_id": str(artist.id),
    })
    assert response.status_code == 200
    assert "候補を作成しました" in response.text
    candidate = session.scalar(select(ImportCandidate))
    assert candidate.review_status == "pending"
    assert candidate.parser_version == "rule-based-v1"
    assert 0 <= candidate.confidence <= 1
    assert candidate.raw_text == sample_post()
    assert candidate.artist_id == artist.id
    assert candidate.published_at.hour == 3
    assert candidate.candidate_appearance_start == time(18, 10)
    assert candidate.candidate_benefit_start == time(18, 50)
    assert session.scalar(select(Event.id)) is None
    assert "架空FES" in client.get("/admin/candidates").text
    detail = client.get(f"/admin/candidates/{candidate.id}")
    assert detail.status_code == 200
    assert "元投稿" in detail.text and "解析結果" in detail.text

    edited = client.post(f"/admin/candidates/{candidate.id}/edit", data=candidate_form(
        candidate, candidate_title="修正した架空FES", candidate_venue="修正ホール"))
    assert "候補を保存しました" in edited.text
    assert candidate.candidate_title == "修正した架空FES"
    assert candidate.parser_version == "rule-based-v1"

    approved = client.post(f"/admin/candidates/{candidate.id}/approve")
    assert "イベントを登録しました" in approved.text
    assert candidate.review_status == "approved"
    assert candidate.created_event_id is not None
    event = session.get(Event, candidate.created_event_id)
    assert event.title == "修正した架空FES"
    assert event.appearances[0].artist_id == artist.id
    assert event.appearances[0].appearance_start_at == time(18, 10)
    assert event.sources[0].source_type == "x"
    assert event.sources[0].source_post_id == "12345"
    assert event.sources[0].source_text == sample_post()
    assert "修正した架空FES" in client.get("/day/2026-09-27").text
    assert sample_post() not in client.get(f"/events/{event.id}").text
    assert client.post(f"/admin/candidates/{candidate.id}/approve").status_code == 409


def test_missing_post_is_422_but_unparseable_post_is_saved(candidate_client):
    client, session = candidate_client
    invalid = client.post("/admin/import", data={"raw_text": ""})
    assert invalid.status_code == 422
    assert "投稿本文を入力してください" in invalid.text
    response = client.post("/admin/import", data={"raw_text": "今週末こちらです！\nよろしくお願いします！"})
    assert response.status_code == 200
    candidate = session.scalar(select(ImportCandidate))
    assert candidate.candidate_date is None
    assert candidate.candidate_title is None
    assert candidate.confidence == 0.1
    assert candidate.review_status == "pending"
    assert "開催日を特定できませんでした" in response.text
    cannot_approve = client.post(f"/admin/candidates/{candidate.id}/approve")
    assert cannot_approve.status_code == 422
    assert candidate.review_status == "pending"
    assert session.scalar(select(Event.id)) is None


def test_reject_keeps_candidate_and_note(candidate_client):
    client, session = candidate_client
    client.post("/admin/import", data={"raw_text": sample_post()})
    candidate = session.scalar(select(ImportCandidate))
    rejected = client.post(f"/admin/candidates/{candidate.id}/reject", data={"review_note": "架空テストのため"})
    assert rejected.status_code == 200
    assert "候補を却下しました" in rejected.text
    assert candidate.review_status == "rejected"
    assert candidate.review_note == "架空テストのため"
    assert client.post(f"/admin/candidates/{candidate.id}/edit", data={}).status_code == 409
    assert session.scalar(select(Event.id)) is None


def test_duplicate_requires_explicit_confirmation(candidate_client):
    client, session = candidate_client
    artist = Artist(name="架空ユニット")
    original = Event(title="架空FES", event_date=date(2026, 9, 27), venue_name="ABC HALL",
                     appearances=[Appearance(artist=artist)])
    session.add(original)
    session.commit()
    response = client.post("/admin/import", data={"raw_text": sample_post(), "artist_id": str(artist.id)})
    candidate = session.scalar(select(ImportCandidate))
    assert candidate.candidate_type == "possible_duplicate"
    assert candidate.duplicate_event_id == original.id
    assert "既存イベントの可能性があります" in response.text
    assert f"/admin/events/{original.id}/edit" in response.text
    blocked = client.post(f"/admin/candidates/{candidate.id}/approve")
    assert blocked.status_code == 422
    assert session.scalar(select(__import__("sqlalchemy").func.count(Event.id))) == 1
    allowed = client.post(f"/admin/candidates/{candidate.id}/approve", data={"confirm_duplicate": "on"})
    assert allowed.status_code == 200
    assert candidate.review_status == "approved"
    assert candidate.created_event_id != original.id


def test_source_url_exact_match_is_duplicate_even_without_date(candidate_client):
    client, session = candidate_client
    existing = Event(title="既存", event_date=date(2026, 9, 20),
                     sources=[Source(source_type="x", source_url="https://x.com/fictional/status/123")])
    session.add(existing)
    session.commit()
    client.post("/admin/import", data={"raw_text": "情報不足です", "source_url": "https://x.com/fictional/status/123"})
    candidate = session.scalar(select(ImportCandidate))
    assert candidate.candidate_type == "possible_duplicate"
    assert candidate.duplicate_event_id == existing.id


def test_web_import_uses_idempotent_shared_import_service(candidate_client):
    client, session = candidate_client
    form = {"raw_text": "共有Serviceの架空投稿", "source_url": "https://example.test/shared-import/42"}
    first = client.post("/admin/import", data=form, follow_redirects=False)
    candidate = session.scalar(select(ImportCandidate))
    second = client.post("/admin/import", data=form, follow_redirects=False)
    assert first.status_code == 303
    assert second.status_code == 303
    assert second.headers["location"] == f"/admin/candidates/{candidate.id}?saved=skipped"
    assert "この投稿は取り込み済みです" in client.get(second.headers["location"]).text
    assert session.scalar(select(__import__("sqlalchemy").func.count(ImportCandidate.id))) == 1


def test_approval_rolls_back_event_appearance_and_source_if_flush_fails(candidate_client, monkeypatch):
    client, session = candidate_client
    artist = Artist(name="架空ユニット")
    session.add(artist)
    session.commit()
    client.post("/admin/import", data={"raw_text": sample_post(), "artist_id": str(artist.id)})
    candidate = session.scalar(select(ImportCandidate))
    original_flush = session.flush

    def fail_after_flush(*args, **kwargs):
        original_flush(*args, **kwargs)
        raise RuntimeError("simulated failure after insert")

    with monkeypatch.context() as patcher:
        patcher.setattr(session, "flush", fail_after_flush)
        with pytest.raises(RuntimeError):
            CandidateService(session).approve(candidate)
    session.expire_all()
    assert session.get(ImportCandidate, candidate.id).review_status == "pending"
    assert session.scalar(select(Event.id)) is None
    assert session.scalar(select(Appearance.id)) is None
    assert session.scalar(select(Source.id)) is None


def test_raw_html_is_escaped_on_candidate_detail(candidate_client):
    client, session = candidate_client
    client.post("/admin/import", data={"raw_text": "<script>alert('fictional')</script>"})
    candidate = session.scalar(select(ImportCandidate))
    response = client.get(f"/admin/candidates/{candidate.id}")
    assert response.status_code == 200
    assert "<script>alert" not in response.text
    assert "&lt;script&gt;" in response.text


def test_change_candidate_matches_conservatively_and_never_creates_event(candidate_client):
    client, session = candidate_client
    artist = Artist(name="架空アーティスト")
    target = Event(title="しずおか大好きまつり 前夜祭", event_date=date(2026, 10, 2),
                   appearances=[Appearance(artist=artist)])
    session.add(target)
    session.commit()

    response = client.post("/admin/import", data={
        "raw_text": "【出演キャンセルのお知らせ】\n10月2日（金）\n"
                    "「しずおか大好きまつり 前夜祭」への出演について、対象アーティストは出演キャンセルとなりました。",
        "artist_id": str(artist.id),
    })
    candidate = session.scalar(select(ImportCandidate))
    assert candidate.candidate_type == "update"
    assert candidate.change_kind == "appearance_cancelled"
    assert candidate.target_event_id == target.id
    assert "変更候補" in response.text
    assert "対象Eventを開く" in response.text
    assert "Event内容は自動変更しません" in response.text

    assert client.post(f"/admin/candidates/{candidate.id}/approve").status_code == 409
    session.refresh(target)
    assert target.title == "しずおか大好きまつり 前夜祭"
    assert session.scalar(select(__import__("sqlalchemy").func.count(Event.id))) == 1

    applied = client.post(f"/admin/candidates/{candidate.id}/applied")
    assert applied.status_code == 200
    assert "反映済み" in applied.text
    assert candidate.review_status == "approved"
    assert session.scalar(select(__import__("sqlalchemy").func.count(Event.id))) == 1


def test_change_candidate_without_strong_event_match_stays_unlinked(candidate_client):
    client, session = candidate_client
    artist = Artist(name="架空アーティスト")
    target = Event(title="まったく異なる企画", event_date=date(2026, 10, 2),
                   appearances=[Appearance(artist=artist)])
    session.add(target)
    session.commit()
    client.post("/admin/import", data={
        "raw_text": "【出演キャンセル】\n10月2日\n「しずおか大好きまつり 前夜祭」への出演をキャンセルします。",
        "artist_id": str(artist.id),
    })
    candidate = session.scalar(select(ImportCandidate))
    assert candidate.candidate_type == "update"
    assert candidate.target_event_id is None
    assert "対象イベントを特定できませんでした" in candidate.parse_warnings
    detail = client.get(f"/admin/candidates/{candidate.id}").text
    assert "対象イベント候補:" in detail
    assert "特定できませんでした" in detail
