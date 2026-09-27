from __future__ import annotations

import asyncio
import importlib
from datetime import datetime
from typing import Any

from app.collectors.base import CollectedPost


class TwikitGuestError(Exception):
    """Safe, user-facing failure for the experimental GuestClient PoC."""


def _value(item: Any, name: str, default: Any = None) -> Any:
    value = getattr(item, name, default)
    return value() if callable(value) else value


def _parse_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if not isinstance(value, str):
        return None
    try:
        return datetime.strptime(value, "%a %b %d %H:%M:%S %z %Y")
    except ValueError:
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None


def tweet_to_collected(tweet: Any, username: str, artist_id: int | None = None) -> CollectedPost:
    post_id = str(_value(tweet, "id", ""))
    text = _value(tweet, "text", None) or _value(tweet, "full_text", None)
    if not post_id or not text:
        raise TwikitGuestError("投稿情報を読み取れませんでした")
    account = username.lstrip("@").strip()
    published_at = _parse_datetime(_value(tweet, "created_at_datetime"))
    if published_at is None:
        published_at = _parse_datetime(_value(tweet, "created_at"))
    return CollectedPost(text=str(text), source_url=f"https://x.com/{account}/status/{post_id}",
                         source_account=account, published_at=published_at,
                         artist_id=artist_id, external_id=post_id,
                         metadata={"provider": "twikit_guest"})


class TwikitGuestCollector:
    """One-shot, unauthenticated Twikit GuestClient adapter for the PoC only."""

    def __init__(self, account: str, *, limit: int = 5, timeout_seconds: float = 20,
                 artist_id: int | None = None, client: Any = None) -> None:
        self.account = account.lstrip("@").strip()
        if not self.account or len(self.account) > 15:
            raise TwikitGuestError("Xアカウント名の形式が正しくありません")
        if limit < 1:
            raise TwikitGuestError("取得件数は1以上で指定してください")
        self.limit = min(limit, 10)
        self.timeout_seconds = timeout_seconds
        self.artist_id = artist_id
        self.client = client

    def _client_class(self):
        try:
            module = importlib.import_module("twikit.guest")
            return module.GuestClient
        except (ImportError, AttributeError) as exc:
            raise TwikitGuestError("Twikitがインストールされていません。experimental-xを追加してください") from exc

    async def collect_async(self) -> list[CollectedPost]:
        client = self.client or self._client_class()()
        try:
            await client.activate()
            user = await client.get_user_by_screen_name(self.account)
            tweets = await client.get_user_tweets(user.id, "Tweets", self.limit)
            return [tweet_to_collected(tweet, self.account, self.artist_id)
                    for tweet in list(tweets)[: self.limit]]
        except TwikitGuestError:
            raise
        except Exception as exc:
            raise TwikitGuestError("Twikit Guest取得に失敗しました。X側仕様変更またはGuest API制限の可能性があります。") from exc

    def collect(self) -> list[CollectedPost]:
        try:
            return asyncio.run(asyncio.wait_for(self.collect_async(), timeout=self.timeout_seconds))
        except asyncio.TimeoutError as exc:
            raise TwikitGuestError("Twikit Guest取得がタイムアウトしました") from exc
