import json
from datetime import date

import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.collectors import CollectedPost, ManualCollector
from app.db import Base
from app.models import Event, ImportCandidate
from app.services.candidates import CandidateService
from app.services.imports import ImportService, ImportStatus


@pytest.fixture
def session_factory():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    yield factory
    engine.dispose()


def post(text="2026/09/27(日)\n架空FES\n会場：ABC HALL\n出演 18:10〜18:30", **fields):
    return CollectedPost(text=text, **fields)


def test_manual_collector_single_multiple_and_optional_fields():
    one = ManualCollector("架空の投稿").collect()
    assert len(one) == 1
    assert one[0].text == "架空の投稿"
    assert one[0].metadata == {}

    multiple = ManualCollector([
        {"text": "投稿1", "artist_id": 1, "external_id": "fictional-1"},
        {"text": "投稿2", "source_url": "https://example.test/post/2"},
    ]).collect()
    assert [item.text for item in multiple] == ["投稿1", "投稿2"]
    assert multiple[0].external_id == "fictional-1"
    assert multiple[1].artist_id is None


def test_manual_collector_rejects_empty_and_validates_json_items_individually():
    with pytest.raises(ValidationError):
        ManualCollector("   ").collect()
    with pytest.raises(ValidationError):
        ManualCollector({"text": "投稿", "source_url": "javascript:alert(1)"}).collect()

    data = json.dumps([
        {"text": "有効な架空投稿", "artist_id": 1},
        {"text": "  "},
        {"text": "2件目の有効な架空投稿", "metadata": {"kind": "fictional"}},
    ])
    batch = ManualCollector.from_json(data)
    assert batch.input_count == 3
    assert len(batch.posts) == 2
    assert len(batch.errors) == 1
    assert batch.errors[0].index == 2


def test_import_service_creates_candidate_with_parser_fields_and_duplicate_classification(session_factory):
    with session_factory() as session:
        event = Event(title="架空FES", event_date=date(2026, 9, 27), venue_name="ABC HALL")
        session.add(event)
        session.commit()

        result = ImportService(session).import_post(post(source_url="https://example.test/fictional/1"))
        assert result.status is ImportStatus.CREATED
        candidate = result.candidate
        assert candidate.parser_version == "rule-based-v1"
        assert candidate.confidence > 0
        assert candidate.candidate_type == "possible_duplicate"
        assert candidate.duplicate_event_id == event.id
        assert candidate.input_hash
        assert candidate.review_status == "pending"
        assert session.scalar(select(func.count(Event.id))) == 1


def test_source_url_and_normalized_hash_prevent_repeated_candidates(session_factory):
    with session_factory() as session:
        service = ImportService(session)
        original = post("架空FES\n2026/09/27", source_url="https://example.test/post/1")
        first = service.import_post(original)
        same_url_different_text = service.import_post(post("修正後の本文", source_url="https://example.test/post/1"))
        assert first.status is ImportStatus.CREATED
        assert same_url_different_text.status is ImportStatus.SKIPPED
        assert same_url_different_text.existing_candidate_id == first.candidate.id

        no_url = post("ＡＢＣ   架空投稿\n2026/09/27")
        second = service.import_post(no_url)
        repeated = service.import_post(post("abc 架空投稿 2026/09/27"))
        assert second.status is ImportStatus.CREATED
        assert repeated.status is ImportStatus.SKIPPED
        assert session.scalar(select(func.count(ImportCandidate.id))) == 2


def test_import_skips_legacy_candidate_without_input_hash(session_factory):
    with session_factory() as session:
        legacy = ImportCandidate(raw_text="ＡＢＣ   架空投稿", review_status="pending")
        session.add(legacy)
        session.commit()

        result = ImportService(session).import_post(post("abc 架空投稿"))
        assert result.status is ImportStatus.SKIPPED
        assert result.existing_candidate_id == legacy.id
        assert session.scalar(select(func.count(ImportCandidate.id))) == 1


def test_external_id_is_an_additional_idempotency_key(session_factory):
    with session_factory() as session:
        service = ImportService(session)
        first = service.import_post(post("外部ID付きの架空投稿", external_id="fictional-42",
                                         source_account="fictional_account"))
        repeated = service.import_post(post("再掲された本文", external_id="fictional-42",
                                            source_account="fictional_account"))
        assert first.status is ImportStatus.CREATED
        assert repeated.status is ImportStatus.SKIPPED
        assert repeated.existing_candidate_id == first.candidate.id


def test_import_batch_isolates_invalid_artist_and_persists_later_post(session_factory):
    with session_factory() as session:
        results = ImportService(session).import_posts([
            post("最初の架空投稿", artist_id=999),
            post("次の架空投稿"),
        ])
        assert [result.status for result in results] == [ImportStatus.FAILED, ImportStatus.CREATED]
        assert "アーティスト" in results[0].error
        assert session.scalar(select(func.count(ImportCandidate.id))) == 1


def test_dry_run_parses_and_detects_duplicate_without_writing(session_factory):
    with session_factory() as session:
        session.add(Event(title="架空FES", event_date=date(2026, 9, 27), venue_name="ABC HALL"))
        session.commit()
        result = ImportService(session).import_post(post(), dry_run=True)
        assert result.status is ImportStatus.DRY_RUN
        assert result.candidate.candidate_title == "架空FES"
        assert result.candidate.duplicate_event_id is not None
        assert session.scalar(select(func.count(ImportCandidate.id))) == 0


def test_parser_failure_still_creates_reviewable_candidate(session_factory, monkeypatch):
    with session_factory() as session:
        candidates = CandidateService(session)

        def fail_parser(*_args, **_kwargs):
            raise RuntimeError("simulated fictional parser issue")

        monkeypatch.setattr(candidates.parser, "parse", fail_parser)
        result = ImportService(session, candidates).import_post(post("架空の読めない投稿"))
        assert result.status is ImportStatus.CREATED
        assert result.candidate.parser_version == "rule-based-v1"
        assert result.candidate.parse_warnings
        assert result.candidate.review_status == "pending"


def test_update_events_cli_supports_text_file_json_and_dry_run(session_factory, tmp_path, monkeypatch, capsys):
    from scripts import update_events

    monkeypatch.setattr(update_events, "SessionLocal", session_factory)
    text_args = ["--text", "架空CLI投稿"]
    assert update_events.main(text_args) == 0
    assert "Candidate生成    1件" in capsys.readouterr().out

    text_file = tmp_path / "fictional-post.txt"
    text_file.write_text("架空ファイル投稿", encoding="utf-8-sig")
    assert update_events.main(["--file", str(text_file)]) == 0

    json_file = tmp_path / "posts.json"
    json_file.write_text(json.dumps([
        {"text": "架空JSON投稿1"}, {"text": "架空JSON投稿2"}, {"text": " "},
    ]), encoding="utf-8-sig")
    assert update_events.main(["--json", str(json_file)]) == 1
    output = capsys.readouterr()
    assert "入力             3件" in output.out
    assert "失敗             1件" in output.out

    before = None
    with session_factory() as session:
        before = session.scalar(select(func.count(ImportCandidate.id)))
    assert update_events.main(["--text", "dry-runだけの架空投稿", "--dry-run"]) == 0
    with session_factory() as session:
        assert session.scalar(select(func.count(ImportCandidate.id))) == before
    assert "DB保存なし" in capsys.readouterr().out


def test_cli_candidate_link_uses_configured_base_url(session_factory, monkeypatch, capsys):
    from scripts import update_events

    monkeypatch.setattr(update_events, "SessionLocal", session_factory)
    monkeypatch.setattr(update_events.settings, "app_base_url", "http://127.0.0.1:9123/")
    assert update_events.main(["--text", "架空の設定確認投稿"]) == 0
    assert "確認: http://127.0.0.1:9123/admin/candidates" in capsys.readouterr().out
