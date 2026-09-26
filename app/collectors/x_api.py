from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from urllib.parse import quote

import httpx
from pydantic import SecretStr

from app.collectors.base import CollectedPost


class XApiError(Exception):
    """An X API failure with a deliberately sanitized, user-facing message."""


@dataclass(frozen=True)
class XUser:
    id: str
    username: str


class XApiCollector:
    """Fetch X posts through the official X API v2 endpoints only."""

    MAX_LIMIT = 20
    USERNAME_RE = re.compile(r"^[A-Za-z0-9_]{1,15}$")
    ID_RE = re.compile(r"^[0-9]+$")

    def __init__(
        self,
        bearer_token: SecretStr | str | None,
        *,
        base_url: str = "https://api.x.com",
        timeout_seconds: float = 10,
        artist_id: int | None = None,
        account: str | None = None,
        user_id: str | None = None,
        post_id: str | None = None,
        limit: int = 10,
        since_id: str | None = None,
        http_client: httpx.Client | None = None,
    ) -> None:
        if isinstance(bearer_token, SecretStr):
            bearer_token = bearer_token.get_secret_value()
        self._token = bearer_token.strip() if isinstance(bearer_token, str) else ""
        self._base_url = base_url.rstrip("/")
        self._timeout_seconds = timeout_seconds
        self._artist_id = artist_id
        self._account = account
        self._user_id = user_id
        self._post_id = post_id
        self._limit = self.normalize_limit(limit)
        self._since_id = since_id
        self._http_client = http_client

    def collect(self) -> list[CollectedPost]:
        """Implement the shared Collector interface for configured one-shot collection."""
        if self._post_id:
            return [self.get_post(self._post_id, username=self._account)]
        user = self.resolve_user(username=self._account, user_id=self._user_id)
        return self.get_timeline(user, limit=self._limit, since_id=self._since_id)

    @classmethod
    def normalize_username(cls, username: str) -> str:
        normalized = username.strip().removeprefix("@").strip()
        if not cls.USERNAME_RE.fullmatch(normalized):
            raise XApiError("Xアカウント名の形式が正しくありません")
        return normalized

    @classmethod
    def normalize_id(cls, user_id: str) -> str:
        normalized = user_id.strip()
        if not cls.ID_RE.fullmatch(normalized):
            raise XApiError("XのIDは数字で指定してください")
        return normalized

    @staticmethod
    def normalize_limit(limit: int) -> int:
        if limit < 1:
            raise XApiError("取得件数は1以上で指定してください")
        return min(limit, XApiCollector.MAX_LIMIT)

    def _request_json(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        if not self._token:
            raise XApiError("X_BEARER_TOKENが設定されていません")
        own_client = self._http_client is None
        client = self._http_client or httpx.Client(
            base_url=self._base_url,
            headers={"Authorization": f"Bearer {self._token}"},
            timeout=self._timeout_seconds,
            follow_redirects=False,
        )
        try:
            try:
                response = client.get(path, params=params, headers={"Authorization": f"Bearer {self._token}"})
            except httpx.TimeoutException:
                raise XApiError("X APIへの接続がタイムアウトしました") from None
            except httpx.RequestError:
                raise XApiError("X APIへ接続できませんでした") from None
            if response.status_code == 401:
                raise XApiError("認証情報を確認してください")
            if response.status_code == 403:
                raise XApiError("X APIのアクセス権・プランを確認してください")
            if response.status_code == 404:
                raise XApiError("アカウントまたは投稿が見つかりません")
            if response.status_code == 429:
                raise XApiError("X APIの利用制限に達しました")
            if response.status_code >= 400:
                raise XApiError(f"X APIでエラーが発生しました (HTTP {response.status_code})")
            try:
                payload = response.json()
            except (ValueError, TypeError):
                raise XApiError("X APIから有効な応答を取得できませんでした") from None
            if not isinstance(payload, dict):
                raise XApiError("X APIから有効な応答を取得できませんでした")
            return payload
        finally:
            if own_client:
                client.close()

    def resolve_user(self, *, username: str | None = None, user_id: str | None = None) -> XUser:
        """Resolve a handle, or verify a directly supplied user ID."""
        if user_id:
            normalized_id = self.normalize_id(user_id)
            if username:
                return XUser(normalized_id, self.normalize_username(username))
            payload = self._request_json(f"/2/users/{quote(normalized_id, safe='')}", {"user.fields": "username"})
        elif username:
            normalized_username = self.normalize_username(username)
            payload = self._request_json(
                f"/2/users/by/username/{quote(normalized_username, safe='')}", {"user.fields": "username"}
            )
        else:
            raise XApiError("--x-accountまたは--x-user-idを指定してください")

        data = payload.get("data")
        if not isinstance(data, dict) or not data.get("id") or not data.get("username"):
            raise XApiError("アカウントまたは投稿が見つかりません")
        try:
            return XUser(self.normalize_id(str(data["id"])), self.normalize_username(str(data["username"])))
        except XApiError:
            raise XApiError("X APIから有効なアカウント情報を取得できませんでした") from None

    @staticmethod
    def _published_at(value: Any) -> datetime | None:
        if not isinstance(value, str):
            return None
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None

    def _to_collected_post(self, item: dict[str, Any], *, username: str | None = None) -> CollectedPost:
        post_id = item.get("id")
        author_id = item.get("author_id")
        text = item.get("text")
        if not post_id or not author_id or not isinstance(text, str) or not text.strip():
            raise XApiError("X APIから有効な投稿情報を取得できませんでした")
        account = self.normalize_username(username) if username else None
        permalink = f"https://x.com/{account}/status/{post_id}" if account else f"https://x.com/i/status/{post_id}"
        source_account = account or f"user_id:{author_id}"
        return CollectedPost(
            text=text,
            source_url=permalink,
            source_account=source_account,
            published_at=self._published_at(item.get("created_at")),
            artist_id=self._artist_id,
            external_id=str(post_id),
            metadata={"provider": "x_api", "author_id": str(author_id)},
        )

    def get_timeline(
        self,
        user: XUser,
        *,
        limit: int = 10,
        since_id: str | None = None,
    ) -> list[CollectedPost]:
        requested = self.normalize_limit(limit)
        params: dict[str, Any] = {
            "max_results": max(5, requested),
            "tweet.fields": "id,text,created_at,author_id",
            "exclude": "replies,retweets",
        }
        if since_id and self.ID_RE.fullmatch(str(since_id)):
            params["since_id"] = str(since_id)
        payload = self._request_json(f"/2/users/{quote(user.id, safe='')}/tweets", params)
        data = payload.get("data", [])
        if not isinstance(data, list):
            raise XApiError("X APIから有効な投稿一覧を取得できませんでした")
        return [self._to_collected_post(item, username=user.username) for item in data[:requested] if isinstance(item, dict)]

    def get_post(self, post_id: str, *, username: str | None = None) -> CollectedPost:
        normalized_id = self.normalize_id(post_id)
        payload = self._request_json(
            f"/2/tweets/{quote(normalized_id, safe='')}", {"tweet.fields": "id,text,created_at,author_id"}
        )
        data = payload.get("data")
        if not isinstance(data, dict):
            raise XApiError("アカウントまたは投稿が見つかりません")
        return self._to_collected_post(data, username=username)
