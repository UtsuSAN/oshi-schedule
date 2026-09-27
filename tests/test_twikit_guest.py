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
    def __init__(self):
        self.tweet_request = None

    async def activate(self):
        return None

    async def get_user_by_screen_name(self, account):
        assert account == "example_staff"
        return User()

    async def get_user_tweets(self, user_id, tweet_type, count):
        self.tweet_request = (user_id, tweet_type, count)
        return [Tweet(), Tweet()]


def test_tweet_conversion_and_permalink():
    post = tweet_to_collected(Tweet(), "@example_staff", artist_id=3)
    assert post.source_url == "https://x.com/example_staff/status/123456789"
    assert post.external_id == "123456789"
    assert post.source_account == "example_staff"
    assert post.published_at == datetime(2026, 9, 27, 1, 2, 3, tzinfo=timezone.utc)
    assert post.metadata == {"provider": "twikit_guest"}


def test_guest_collection_limit_and_no_auth():
    guest = Guest()
    posts = TwikitGuestCollector("@example_staff", client=guest, limit=1).collect()
    assert len(posts) == 1
    assert posts[0].text == "架空の告知"
    assert guest.tweet_request == ("42", "Tweets", 1)


def test_guest_requests_five_tweets():
    guest = Guest()
    TwikitGuestCollector("example_staff", client=guest, limit=5).collect()
    assert guest.tweet_request == ("42", "Tweets", 5)


def test_twitter_created_at_format_is_parsed():
    tweet = Tweet()
    tweet.created_at = "Sat Sep 27 03:00:00 +0000 2026"
    post = tweet_to_collected(tweet, "example_staff")
    assert post.published_at is not None
    assert (post.published_at.year, post.published_at.month, post.published_at.day) == (2026, 9, 27)


def test_created_at_datetime_takes_priority():
    tweet = Tweet()
    tweet.created_at = "invalid"
    tweet.created_at_datetime = datetime(2026, 9, 27, 3, 0, tzinfo=timezone.utc)
    assert tweet_to_collected(tweet, "example_staff").published_at == tweet.created_at_datetime


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
