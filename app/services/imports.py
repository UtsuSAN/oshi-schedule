from __future__ import annotations

import hashlib
import json
import logging
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.collectors.base import CollectedPost
from app.models import ImportCandidate
from app.services.admin import InputError
from app.services.candidates import CandidateService, ImportInput
from app.services.events import JAPAN

logger = logging.getLogger(__name__)


class ImportStatus(str, Enum):
    CREATED = "created"
    SKIPPED = "skipped"
    DRY_RUN = "dry_run"
    FAILED = "failed"


@dataclass(frozen=True)
class ImportResult:
    post: CollectedPost
    status: ImportStatus
    candidate: ImportCandidate | None = None
    existing_candidate_id: int | None = None
    error: str | None = None


def normalized_text(text: str) -> str:
    """Normalize Unicode and whitespace while preserving punctuation/content."""
    return " ".join(unicodedata.normalize("NFKC", text).casefold().split())


def post_input_hash(post: CollectedPost) -> str:
    canonical = json.dumps(
        {
            "text": normalized_text(post.text),
            "source_url": post.source_url.strip() if post.source_url else None,
            "artist_id": post.artist_id,
            "source_account": post.source_account,
            "external_id": post.external_id,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class ImportService:
    """Shared collector-to-candidate workflow used by web and command-line inputs."""

    def __init__(self, session: Session, candidates: CandidateService | None = None):
        self.session = session
        self.candidates = candidates or CandidateService(session)

    def _existing(self, post: CollectedPost, input_hash: str) -> ImportCandidate | None:
        if post.source_url:
            existing = self.session.scalar(
                select(ImportCandidate).where(ImportCandidate.source_url == post.source_url)
                .order_by(ImportCandidate.id).limit(1)
            )
            if existing:
                return existing
        if post.external_id:
            existing = self.session.scalar(
                select(ImportCandidate).where(
                    ImportCandidate.external_id == post.external_id,
                    ImportCandidate.source_account == post.source_account,
                ).order_by(ImportCandidate.id).limit(1)
            )
            if existing:
                return existing
        existing = self.session.scalar(
            select(ImportCandidate).where(ImportCandidate.input_hash == input_hash)
            .order_by(ImportCandidate.id).limit(1)
        )
        if existing:
            return existing
        if post.source_url is None:
            legacy = self.session.scalars(
                select(ImportCandidate).where(
                    ImportCandidate.input_hash.is_(None),
                    ImportCandidate.source_url.is_(None),
                    ImportCandidate.artist_id == post.artist_id,
                    ImportCandidate.source_account == post.source_account,
                ).order_by(ImportCandidate.id)
            )
            for candidate in legacy:
                if candidate.raw_text and normalized_text(candidate.raw_text) == normalized_text(post.text):
                    return candidate
        return None

    @staticmethod
    def _published_at(value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            value = value.replace(tzinfo=JAPAN)
        return value.astimezone(timezone.utc).replace(tzinfo=None)

    def import_post(self, post: CollectedPost, *, dry_run: bool = False) -> ImportResult:
        digest = post_input_hash(post)
        existing = self._existing(post, digest)
        if existing:
            logger.info("duplicate skipped candidate_id=%s", existing.id)
            return ImportResult(post, ImportStatus.SKIPPED, existing_candidate_id=existing.id)

        data = ImportInput(
            raw_text=post.text,
            source_url=post.source_url,
            source_account=post.source_account,
            published_at=self._published_at(post.published_at),
            artist_id=post.artist_id,
            external_id=post.external_id,
            input_hash=digest,
        )
        candidate = self.candidates.preview(data)
        if dry_run:
            return ImportResult(post, ImportStatus.DRY_RUN, candidate=candidate)

        try:
            candidate = self.candidates.save_candidate(candidate)
        except IntegrityError:
            # A competing process may have inserted the same hash since the initial lookup.
            self.session.rollback()
            existing = self._existing(post, digest)
            if existing:
                logger.info("duplicate skipped candidate_id=%s", existing.id)
                return ImportResult(post, ImportStatus.SKIPPED, existing_candidate_id=existing.id)
            raise
        if candidate.parse_warnings:
            logger.info("parse warning candidate_id=%s count=%s", candidate.id, len(candidate.parse_warnings))
        return ImportResult(post, ImportStatus.CREATED, candidate=candidate)

    def import_posts(self, posts: list[CollectedPost], *, dry_run: bool = False) -> list[ImportResult]:
        results: list[ImportResult] = []
        logger.info("collector=manual input_count=%s dry_run=%s", len(posts), dry_run)
        for post in posts:
            try:
                result = self.import_post(post, dry_run=dry_run)
                results.append(result)
                if result.status is ImportStatus.CREATED:
                    logger.info("candidate created id=%s", result.candidate.id if result.candidate else None)
            except Exception as exc:
                self.session.rollback()
                logger.warning("import failed error_type=%s", type(exc).__name__)
                if isinstance(exc, InputError):
                    message = "; ".join(exc.errors.values())
                else:
                    message = f"取り込みに失敗しました ({type(exc).__name__})"
                results.append(ImportResult(post, ImportStatus.FAILED, error=message))
        logger.info("update completed input_count=%s", len(posts))
        return results
