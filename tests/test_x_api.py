from datetime import datetime, timezone

import httpx
import pytest
from pydantic import SecretStr
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.collectors import XApiCollector, XApiError, XUser
from app.db import Base
from app.models import ImportCandidate


TOKEN = "test-only-bearer-secret"


def response_for(request: httpx.Request) -> httpx.Response:
    if request.url.path == "/2/users/by/username/hc_staffACC":
        return httpx.Response(200, json={"data": {"id": "12345", "username": "hc_staffACC"}})
    if request.url.path == "/2/users/12345":
        return httpx.Response(200, json={"data": {"id": "12345", "username": "hc_staffACC"}})
    if request.url.path == "/2/users/12345/tweets":
        return httpx.Response(200, json={"data": [
            {"id": "9002", "text": "架空ライブ告知2", "author_id": "12345", "created_at": "2026-09-25T10:20:30.000Z"},
            {"id": "9001", "text": "架空ライブ告知1", "author_id": "12345", "created_at": "2026-09-24T10:20:30Z"},
            {"id": "9000", "text": "上限外の架空投稿", "author_id": "12345"},
        ]})
    if request.url.path == "/2/tweets/9002":
        return httpx.Response(200, json={"data": {
            "id": "9002", "text": "単一の架空告知", "author_id": "12345", "created_at": "2026-09-25T10:20:30Z",
        }})
    return httpx.Response(404, json={"detail": "fictional missing"})


def make_collector(handler=response_for, **kwargs) -> XApiCollector:
    client = httpx.Client(transport=httpx.MockTransport(handler), base_url="https://api.x.com")
    return XApiCollector(SecretStr(TOKEN), http_client=client, **kwargs)


def test_username_lookup_timeline_and_collected_post_mapping():
    requests = []

    def handler(request):
        requests.append(request)
        assert request.headers["Authorization"] == f"Bearer {TOKEN}"
        return response_for(request)

    collector = make_collector(handler, artist_id=7)
    user = collector.resolve_user(username="@hc_staffACC")
    posts = collector.get_timeline(user, limit=2, since_id="8990")

    assert user == XUser(id="12345", username="hc_staffACC")
    assert len(posts) == 2
    post = posts[0]
    assert post.text == "架空ライブ告知2"
    assert post.source_url == "https://x.com/hc_staffACC/status/9002"
    assert post.source_account == "hc_staffACC"
    assert post.external_id == "9002"
    assert post.artist_id == 7
    assert post.published_at == datetime(2026, 9, 25, 10, 20, 30, tzinfo=timezone.utc)
    assert post.metadata == {"provider": "x_api", "author_id": "12345"}
    assert requests[0].url.path.endswith("/by/username/hc_staffACC")
    assert requests[1].url.params["max_results"] == "5"
    assert requests[1].url.params["since_id"] == "8990"
    assert requests[1].url.params["exclude"] == "replies,retweets"


def test_single_post_id_and_limit_cap():
    collector = make_collector()
    post = collector.get_post("9002", username="@hc_staffACC")
    assert post.external_id == "9002"
    assert post.source_url.endswith("/hc_staffACC/status/9002")
    assert collector.normalize_limit(500) == 20


def test_direct_user_id_skips_username_to_id_endpoint():
    requests = []

    def handler(request):
        requests.append(request.url.path)
        return response_for(request)

    user = make_collector(handler).resolve_user(user_id="12345")
    assert user == XUser(id="12345", username="hc_staffACC")
    assert requests == ["/2/users/12345"]


def test_collector_interface_supports_one_shot_collection():
    posts = make_collector(account="hc_staffACC", limit=1).collect()
    assert len(posts) == 1
    assert posts[0].source_account == "hc_staffACC"


@pytest.mark.parametrize(("status", "message"), [
    (401, "認証情報を確認してください"),
    (403, "X APIのアクセス権・プランを確認してください"),
    (404, "アカウントまたは投稿が見つかりません"),
    (429, "X APIの利用制限に達しました"),
])
def test_http_errors_are_mapped_without_leaking_response_or_token(status, message):
    def handler(_request):
        return httpx.Response(status, text=f"{TOKEN} Authorization: Bearer {TOKEN}")

    collector = make_collector(handler)
    with pytest.raises(XApiError) as error:
        collector.resolve_user(username="fictional_user")
    assert str(error.value) == message
    assert TOKEN not in str(error.value)


def test_timeout_is_mapped_without_exposing_http_exception():
    def handler(_request):
        raise httpx.ReadTimeout(f"timed out with {TOKEN}")

    collector = make_collector(handler)
    with pytest.raises(XApiError, match="X APIへの接続がタイムアウトしました") as error:
        collector.resolve_user(username="fictional_user")
    assert TOKEN not in str(error.value)


def test_missing_token_is_lazy_and_sanitized():
    collector = XApiCollector(None)
    assert "token" not in repr(collector).lower()
    with pytest.raises(XApiError, match="X_BEARER_TOKENが設定されていません"):
        collector.resolve_user(username="fictional_user")


@pytest.fixture
def session_factory():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    yield factory
    engine.dispose()


def test_cli_x_account_limit_dry_run_and_direct_user_id(session_factory, monkeypatch, capsys):
    from scripts import update_events

    monkeypatch.setattr(update_events, "SessionLocal", session_factory)
    monkeypatch.setattr(update_events.settings, "x_bearer_token", SecretStr(TOKEN))

    class MockCollector(XApiCollector):
        def __init__(self, token, **kwargs):
            super().__init__(token, http_client=httpx.Client(
                transport=httpx.MockTransport(response_for), base_url="https://api.x.com"
            ), **kwargs)

    monkeypatch.setattr(update_events, "XApiCollector", MockCollector)
    assert update_events.main(["--x-account", "hc_staffACC", "--limit", "2", "--dry-run"]) == 0
    output = capsys.readouterr().out
    assert "Resolved: @hc_staffACC -> 12345" in output
    assert "取得Post数             2件" in output
    assert "Candidate生成見込み" in output
    assert "X APIへの通信は実行済み" in output
    with session_factory() as session:
        assert session.scalar(select(func.count(ImportCandidate.id))) == 0

    assert update_events.main([
        "--x-user-id", "12345", "--x-account", "hc_staffACC", "--limit", "1", "--dry-run",
    ]) == 0
    capsys.readouterr()


def test_cli_x_url_single_post_and_safe_missing_token(session_factory, monkeypatch, capsys):
    from scripts import update_events

    monkeypatch.setattr(update_events, "SessionLocal", session_factory)
    monkeypatch.setattr(update_events.settings, "x_bearer_token", SecretStr(TOKEN))

    class MockCollector(XApiCollector):
        def __init__(self, token, **kwargs):
            super().__init__(token, http_client=httpx.Client(
                transport=httpx.MockTransport(response_for), base_url="https://api.x.com"
            ), **kwargs)

    monkeypatch.setattr(update_events, "XApiCollector", MockCollector)
    assert update_events.main(["--x-url", "https://x.com/hc_staffACC/status/9002", "--dry-run"]) == 0
    output = capsys.readouterr().out
    assert "取得Post数             1件" in output

    monkeypatch.setattr(update_events.settings, "x_bearer_token", None)
    assert update_events.main(["--x-account", "hc_staffACC"]) == 2
    error = capsys.readouterr().err
    assert "X_BEARER_TOKENが設定されていません" in error
    assert TOKEN not in error


def test_since_id_uses_latest_recorded_x_candidate(session_factory, monkeypatch):
    from scripts import update_events

    monkeypatch.setattr(update_events, "SessionLocal", session_factory)
    with session_factory() as session:
        session.add_all([
            ImportCandidate(external_id="123", source_account="fictional_account",
                            source_url="https://x.com/fictional_account/status/123", raw_text="old", review_status="pending"),
            ImportCandidate(external_id="145", source_account="fictional_account",
                            source_url="https://x.com/fictional_account/status/145", raw_text="new", review_status="pending"),
            ImportCandidate(external_id="999", source_account="other_account",
                            source_url="https://x.com/other_account/status/999", raw_text="other", review_status="pending"),
            ImportCandidate(external_id="777", source_account="fictional_account",
                            source_url="https://example.test/not-x", raw_text="manual", review_status="pending"),
        ])
        session.commit()
    assert update_events._latest_since_id("fictional_account") == "145"
