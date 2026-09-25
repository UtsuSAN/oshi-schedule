from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from pydantic import ValidationError

from app.collectors.base import CollectedPost


@dataclass(frozen=True)
class CollectionError:
    index: int
    message: str


@dataclass(frozen=True)
class CollectionBatch:
    posts: list[CollectedPost]
    errors: list[CollectionError]
    input_count: int


class ManualCollector:
    """Collect user-supplied text or JSON records without contacting external services."""

    def __init__(self, posts: CollectedPost | dict[str, Any] | str | Iterable[CollectedPost | dict[str, Any]]):
        if isinstance(posts, (CollectedPost, dict, str)):
            self._posts = [posts]
        else:
            self._posts = list(posts)

    def collect(self) -> list[CollectedPost]:
        return [item if isinstance(item, CollectedPost) else self._from_value(item) for item in self._posts]

    @staticmethod
    def _from_value(value: CollectedPost | dict[str, Any] | str) -> CollectedPost:
        if isinstance(value, str):
            value = {"text": value}
        return CollectedPost.model_validate(value)

    @classmethod
    def from_json(cls, raw_json: str) -> CollectionBatch:
        """Validate a JSON array item by item so one bad record does not discard peers."""
        try:
            values = json.loads(raw_json)
        except json.JSONDecodeError as exc:
            raise ValueError(f"JSONを読み込めません (line {exc.lineno}, column {exc.colno}): {exc.msg}") from exc
        if not isinstance(values, list):
            raise ValueError("JSONの最上位は投稿オブジェクトの配列にしてください")

        posts: list[CollectedPost] = []
        errors: list[CollectionError] = []
        for index, value in enumerate(values, start=1):
            try:
                posts.append(cls._from_value(value))
            except (ValidationError, TypeError, ValueError) as exc:
                if isinstance(exc, ValidationError):
                    message = "; ".join(
                        f"{'.'.join(str(part) for part in error['loc']) or 'record'}: {error['msg']}"
                        for error in exc.errors()
                    )
                else:
                    message = str(exc)
                errors.append(CollectionError(index=index, message=message))
        return CollectionBatch(posts=posts, errors=errors, input_count=len(values))

    @classmethod
    def from_file(cls, path: str | Path) -> "ManualCollector":
        text = Path(path).read_text(encoding="utf-8-sig")
        return cls(text)
