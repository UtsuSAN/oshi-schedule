from datetime import datetime, timezone

import pytest

from app.collectors.twikit_guest import TwikitGuestCollector, TwikitGuestError, tweet_to_collected


class Tweet:
    id = "123456789"
    text = "架空の告知"
    created_at = "2026-09-27T01:02:03Z"


class User:
    id = "42"


class Guest:
    async def activate(self):
        return None

    async def get_user_by_screen_name(self, account):
        assert account == "example_staff"
        return User()

    async def get_user_tweets(self, user_id):
        assert user_id == "42"
        return [Tweet(), Tweet()]


def test_tweet_conversion_and_permalink():
    post = tweet_to_collected(Tweet(), "@example_staff", artist_id=3)
    assert post.source_url == "https://x.com/example_staff/status/123456789"
    assert post.external_id == "123456789"
    assert post.source_account == "example_staff"
    assert post.published_at == datetime(2026, 9, 27, 1, 2, 3, tzinfo=timezone.utc)
    assert post.metadata == {"provider": "twikit_guest"}


def test_guest_collection_limit_and_no_auth():
    posts = TwikitGuestCollector("@example_staff", client=Guest(), limit=1).collect()
    assert len(posts) == 1
    assert posts[0].text == "架空の告知"


@pytest.mark.parametrize("limit", [0, -1])
def test_invalid_limit(limit):
    with pytest.raises(TwikitGuestError):
        TwikitGuestCollector("example_staff", limit=limit)


def test_guest_failure_is_sanitized():
    class Broken:
        async def activate(self):
            raise RuntimeError("secret cookie")

    with pytest.raises(TwikitGuestError, match="Twikit Guest取得に失敗") as exc:
        TwikitGuestCollector("example_staff", client=Broken()).collect()
    assert "cookie" not in str(exc.value)
