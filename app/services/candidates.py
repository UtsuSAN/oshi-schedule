from __future__ import annotations

import logging
import re
import unicodedata
from dataclasses import dataclass
from datetime import date, datetime, time, timezone
from difflib import SequenceMatcher
from typing import Mapping
from urllib.parse import urlsplit

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.extractors.base import ParseContext, PostParser
from app.extractors.rule_based import RuleBasedParser
from app.models import Appearance, Artist, Event, ImportCandidate, Source
from app.services.admin import InputError, parse_appearance, parse_event
from app.services.events import JAPAN, japan_today

logger = logging.getLogger(__name__)
STATUSES = ("pending", "approved", "rejected")


class ReviewConflict(Exception):
    pass


@dataclass(frozen=True)
class ImportInput:
    raw_text: str
    source_url: str | None
    source_account: str | None
    published_at: datetime | None
    artist_id: int | None
    external_id: str | None = None
    input_hash: str | None = None


def _text(values: Mapping[str, str], key: str, errors: dict[str, str], label: str,
          limit: int | None = None, required: bool = False) -> str | None:
    value = (values.get(key) or "").strip()
    if required and not value:
        errors[key] = f"{label}を入力してください"
    elif limit and len(value) > limit:
        errors[key] = f"{label}は{limit}文字以内で入力してください"
    return value or None


def _url(values: Mapping[str, str], key: str, errors: dict[str, str], label: str) -> str | None:
    value = _text(values, key, errors, label, 2048)
    if value:
        try:
            parsed = urlsplit(value)
            valid = parsed.scheme in ("http", "https") and bool(parsed.netloc)
        except ValueError:
            valid = False
        if not valid:
            errors[key] = f"{label}はhttpまたはhttpsのURLを入力してください"
    return value


def _published_at(values: Mapping[str, str], errors: dict[str, str]) -> datetime | None:
    raw = _text(values, "published_at", errors, "投稿日時")
    if not raw:
        return None
    try:
        local = datetime.fromisoformat(raw)
        if local.tzinfo:
            raise ValueError
        return local.replace(tzinfo=JAPAN).astimezone(timezone.utc).replace(tzinfo=None)
    except ValueError:
        errors["published_at"] = "投稿日時を正しい日時で入力してください"
        return None


def _artist_id(values: Mapping[str, str], errors: dict[str, str]) -> int | None:
    raw = _text(values, "artist_id", errors, "アーティスト")
    if not raw:
        return None
    try:
        result = int(raw)
        if result <= 0:
            raise ValueError
        return result
    except ValueError:
        errors["artist_id"] = "アーティストを選択してください"
        return None


def _optional_date(values: Mapping[str, str], errors: dict[str, str]) -> date | None:
    raw = _text(values, "candidate_date", errors, "開催日")
    if not raw:
        return None
    try:
        return date.fromisoformat(raw)
    except ValueError:
        errors["candidate_date"] = "開催日を正しい日付で入力してください"
        return None


def _optional_time(values: Mapping[str, str], key: str, errors: dict[str, str], label: str) -> time | None:
    raw = _text(values, key, errors, label)
    if not raw:
        return None
    try:
        result = time.fromisoformat(raw)
        if result.tzinfo:
            raise ValueError
        return result
    except ValueError:
        errors[key] = f"{label}を正しい時刻で入力してください"
        return None


def parse_import(values: Mapping[str, str]) -> ImportInput:
    errors: dict[str, str] = {}
    raw_text = _text(values, "raw_text", errors, "投稿本文", 20000, required=True)
    source_url = _url(values, "source_url", errors, "投稿URL")
    source_account = _text(values, "source_account", errors, "投稿アカウント", 200)
    published_at = _published_at(values, errors)
    artist_id = _artist_id(values, errors)
    if errors:
        raise InputError(errors)
    return ImportInput(raw_text, source_url, source_account, published_at, artist_id)


def parse_candidate_edit(values: Mapping[str, str]) -> dict[str, object]:
    errors: dict[str, str] = {}
    result: dict[str, object] = {
        "raw_text": _text(values, "raw_text", errors, "投稿本文", 20000, required=True),
        "source_url": _url(values, "source_url", errors, "投稿URL"),
        "source_account": _text(values, "source_account", errors, "投稿アカウント", 200),
        "published_at": _published_at(values, errors),
        "artist_id": _artist_id(values, errors),
        "candidate_title": _text(values, "candidate_title", errors, "イベント名", 300),
        "candidate_date": _optional_date(values, errors),
        "candidate_venue": _text(values, "candidate_venue", errors, "会場名", 300),
        "candidate_venue_address": _text(values, "candidate_venue_address", errors, "会場住所", 500),
        "candidate_ticket_url": _url(values, "candidate_ticket_url", errors, "チケットURL"),
        "candidate_official_url": _url(values, "candidate_official_url", errors, "公式URL"),
        "candidate_stage_name": _text(values, "candidate_stage_name", errors, "ステージ名", 200),
    }
    for key, label in (("candidate_open_at", "OPEN"), ("candidate_start_at", "START"),
                       ("candidate_end_at", "END"), ("candidate_appearance_start", "出演開始"),
                       ("candidate_appearance_end", "出演終了"), ("candidate_benefit_start", "特典会開始"),
                       ("candidate_benefit_end", "特典会終了")):
        result[key] = _optional_time(values, key, errors, label)
    for start, end, label in (("candidate_open_at", "candidate_start_at", "OPEN"),
                              ("candidate_appearance_start", "candidate_appearance_end", "出演開始"),
                              ("candidate_benefit_start", "candidate_benefit_end", "特典会開始")):
        if result[start] and result[end] and result[start] > result[end]:
            errors[start] = f"{label}は終了時刻以前にしてください"
    if errors:
        raise InputError(errors)
    return result


def _normalized(value: str) -> str:
    return re.sub(r"[\W_]+", "", unicodedata.normalize("NFKC", value).casefold())


def _similarity(first: str | None, second: str | None) -> float:
    if not first or not second:
        return 0.0
    return SequenceMatcher(None, _normalized(first), _normalized(second)).ratio()


class CandidateService:
    def __init__(self, session: Session, parser: PostParser | None = None):
        self.session = session
        self.parser = parser or RuleBasedParser()

    def count_pending(self) -> int:
        return self.session.scalar(select(func.count(ImportCandidate.id)).where(
            ImportCandidate.review_status == "pending")) or 0

    def list(self, status: str = "pending") -> list[ImportCandidate]:
        statement = select(ImportCandidate).order_by(ImportCandidate.created_at.desc(), ImportCandidate.id.desc())
        if status in STATUSES:
            statement = statement.where(ImportCandidate.review_status == status)
        return list(self.session.scalars(statement).all())

    def get(self, candidate_id: int) -> ImportCandidate | None:
        return self.session.get(ImportCandidate, candidate_id)

    def duplicate_match(self, candidate: ImportCandidate) -> tuple[Event | None, int]:
        if candidate.source_url:
            same_source = self.session.scalar(select(Event).join(Event.sources).where(
                Source.source_url == candidate.source_url).order_by(Event.id).limit(1))
            if same_source:
                return same_source, 100
        if candidate.candidate_date is None:
            return None, 0
        statement = (select(Event).where(Event.event_date == candidate.candidate_date)
                     .options(selectinload(Event.appearances)))
        best: Event | None = None
        best_score = 0
        for event in self.session.scalars(statement):
            score = 40
            score += round(30 * _similarity(candidate.candidate_title, event.title))
            score += round(20 * _similarity(candidate.candidate_venue, event.venue_name))
            if candidate.artist_id and any(item.artist_id == candidate.artist_id for item in event.appearances):
                score += 10
            if score > best_score:
                best, best_score = event, score
        return (best, best_score) if best_score >= 70 else (None, best_score)

    def _refresh_duplicate(self, candidate: ImportCandidate) -> None:
        if candidate.change_kind:
            candidate.candidate_type = "update"
            event = self.update_target_match(candidate)
            candidate.target_event_id = event.id if event else None
            candidate.duplicate_event_id = None
            candidate.parse_warnings = [warning for warning in candidate.parse_warnings
                                        if warning != "対象イベントを特定できませんでした"]
            if event is None:
                candidate.parse_warnings.append("対象イベントを特定できませんでした")
            return
        candidate.target_event_id = None
        event, score = self.duplicate_match(candidate)
        candidate.duplicate_event_id = event.id if event else None
        candidate.candidate_type = "possible_duplicate" if event else (
            "new" if candidate.candidate_title and candidate.candidate_date else "unknown")
        if event:
            logger.info("duplicate detected candidate_id=%s event_id=%s score=%s", candidate.id, event.id, score)

    def update_target_match(self, candidate: ImportCandidate) -> Event | None:
        """Find a conservative target for a change notice; never changes the Event."""
        if candidate.candidate_date is None or not candidate.candidate_title or not candidate.artist_id:
            return None
        statement = (select(Event).where(Event.event_date == candidate.candidate_date)
                     .options(selectinload(Event.appearances)))
        best: Event | None = None
        best_score = 0.0
        for event in self.session.scalars(statement):
            artist_match = any(item.artist_id == candidate.artist_id for item in event.appearances)
            title_score = _similarity(candidate.candidate_title, event.title)
            if not artist_match or title_score < 0.72:
                continue
            # Artist and date must both match; title similarity ranks remaining candidates.
            score = title_score
            if score > best_score:
                best, best_score = event, score
        return best

    def preview(self, data: ImportInput) -> ImportCandidate:
        """Parse and classify a candidate without writing it to the database."""
        logger.info("import received parser=%s", self.parser.version)
        artist = self.session.get(Artist, data.artist_id) if data.artist_id else None
        if data.artist_id and artist is None:
            raise InputError({"artist_id": "アーティストを選択してください"})
        context = ParseContext(
            published_at=data.published_at.replace(tzinfo=timezone.utc) if data.published_at else None,
            reference_date=japan_today(),
            artist_name=(artist.display_name or artist.name) if artist else None,
        )
        try:
            parsed = self.parser.parse(data.raw_text, context)
        except Exception as exc:
            logger.warning("parser failed version=%s error_type=%s", self.parser.version, type(exc).__name__)
            from app.extractors.base import ParsedEventCandidate
            parsed = ParsedEventCandidate(parser_version=self.parser.version,
                                          warnings=["解析に失敗しました。内容を手動で確認してください"])
        candidate = ImportCandidate(
            input_hash=data.input_hash,
            external_id=data.external_id,
            raw_text=data.raw_text, source_url=data.source_url, source_account=data.source_account,
            published_at=data.published_at, artist_id=data.artist_id,
            candidate_title=parsed.title, candidate_date=parsed.event_date,
            candidate_open_at=parsed.open_at, candidate_start_at=parsed.start_at,
            candidate_end_at=parsed.end_at, candidate_venue=parsed.venue,
            candidate_venue_address=parsed.venue_address,
            candidate_ticket_url=parsed.ticket_url, candidate_official_url=parsed.official_url,
            candidate_appearance_start=parsed.appearance_start,
            candidate_appearance_end=parsed.appearance_end,
            candidate_benefit_start=parsed.benefit_start, candidate_benefit_end=parsed.benefit_end,
            candidate_stage_name=parsed.stage_name, confidence=parsed.confidence,
            change_kind=parsed.change_kind, change_summary=parsed.change_summary,
            parser_version=parsed.parser_version or self.parser.version,
            parse_warnings=parsed.warnings, review_status="pending",
        )
        self._refresh_duplicate(candidate)
        return candidate

    def save_candidate(self, candidate: ImportCandidate) -> ImportCandidate:
        """Persist a parsed candidate in its own transaction."""
        self.session.add(candidate)
        try:
            self.session.flush()
            self.session.commit()
        except Exception:
            self.session.rollback()
            raise
        logger.info("candidate created id=%s parser=%s warnings=%s", candidate.id,
                    candidate.parser_version, len(candidate.parse_warnings))
        return candidate

    def create(self, data: ImportInput) -> ImportCandidate:
        return self.save_candidate(self.preview(data))

    def edit(self, candidate: ImportCandidate, values: Mapping[str, str]) -> ImportCandidate:
        if candidate.review_status != "pending":
            raise ReviewConflict("確認済み候補は編集できません")
        data = parse_candidate_edit(values)
        if data["artist_id"] and self.session.get(Artist, data["artist_id"]) is None:
            raise InputError({"artist_id": "アーティストを選択してください"})
        for key, value in data.items():
            setattr(candidate, key, value)
        self._refresh_duplicate(candidate)
        try:
            self.session.commit()
        except Exception:
            self.session.rollback()
            raise
        return candidate

    def approve(self, candidate: ImportCandidate, *, confirm_duplicate: bool = False) -> Event:
        if candidate.candidate_type == "update":
            raise ReviewConflict("変更候補から新しいイベントは登録できません")
        if candidate.review_status != "pending":
            raise ReviewConflict("確認済み候補は再承認できません")
        event_data = parse_event({
            "title": candidate.candidate_title or "",
            "event_date": candidate.candidate_date.isoformat() if candidate.candidate_date else "",
            "open_at": candidate.candidate_open_at.isoformat(timespec="minutes") if candidate.candidate_open_at else "",
            "start_at": candidate.candidate_start_at.isoformat(timespec="minutes") if candidate.candidate_start_at else "",
            "end_at": candidate.candidate_end_at.isoformat(timespec="minutes") if candidate.candidate_end_at else "",
            "venue_name": candidate.candidate_venue or "",
            "venue_address": candidate.candidate_venue_address or "",
            "ticket_url": candidate.candidate_ticket_url or "",
            "official_url": candidate.candidate_official_url or "",
            "status": "scheduled",
        })
        appearance_data = parse_appearance({
            "artist_id": str(candidate.artist_id or ""),
            "appearance_start_at": candidate.candidate_appearance_start.isoformat(timespec="minutes") if candidate.candidate_appearance_start else "",
            "appearance_end_at": candidate.candidate_appearance_end.isoformat(timespec="minutes") if candidate.candidate_appearance_end else "",
            "benefit_start_at": candidate.candidate_benefit_start.isoformat(timespec="minutes") if candidate.candidate_benefit_start else "",
            "benefit_end_at": candidate.candidate_benefit_end.isoformat(timespec="minutes") if candidate.candidate_benefit_end else "",
            "stage_name": candidate.candidate_stage_name or "",
        })
        if self.session.get(Artist, appearance_data.artist_id) is None:
            raise InputError({"artist_id": "アーティストを選択してください"})
        duplicate, _ = self.duplicate_match(candidate)
        if duplicate and not confirm_duplicate:
            candidate.duplicate_event_id = duplicate.id
            candidate.candidate_type = "possible_duplicate"
            self.session.commit()
            raise InputError({"duplicate": "既存イベントの可能性があります。確認してから登録してください"})
        event = Event(**vars(event_data))
        event.appearances.append(Appearance(**vars(appearance_data)))
        source_post_id = candidate.external_id
        if candidate.source_url:
            post_match = re.search(r"/status/(\d+)", candidate.source_url)
            source_post_id = source_post_id or (post_match.group(1) if post_match else None)
        event.sources.append(Source(
            source_type="x" if candidate.source_url else "manual",
            source_url=candidate.source_url, source_account=candidate.source_account,
            source_post_id=source_post_id, source_text=candidate.raw_text,
            published_at=candidate.published_at,
        ))
        self.session.add(event)
        try:
            self.session.flush()
            candidate.review_status = "approved"
            candidate.created_event_id = event.id
            self.session.commit()
        except Exception:
            self.session.rollback()
            raise
        logger.info("candidate approved id=%s event_id=%s", candidate.id, event.id)
        return event

    def mark_applied(self, candidate: ImportCandidate) -> None:
        """Mark that the user reviewed/applied a notice without mutating any Event."""
        if candidate.candidate_type != "update":
            raise ReviewConflict("変更候補ではありません")
        if candidate.review_status != "pending":
            raise ReviewConflict("確認済み候補は再処理できません")
        candidate.review_status = "approved"
        try:
            self.session.commit()
        except Exception:
            self.session.rollback()
            raise

    def reject(self, candidate: ImportCandidate, note: str | None = None) -> None:
        if candidate.review_status != "pending":
            raise ReviewConflict("確認済み候補は再却下できません")
        candidate.review_status = "rejected"
        candidate.review_note = note.strip()[:2000] if note and note.strip() else None
        try:
            self.session.commit()
        except Exception:
            self.session.rollback()
            raise
        logger.info("candidate rejected id=%s", candidate.id)
