from __future__ import annotations

import argparse
import logging
import re
import sys
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pydantic import ValidationError

from app.collectors import CollectedPost, CollectionError, ManualCollector, XApiCollector, XApiError, XUser
from app.config import settings
from app.db import SessionLocal
from app.models import ImportCandidate
from app.services.admin import InputError
from app.services.candidates import CandidateService
from app.services.imports import ImportResult, ImportService, ImportStatus
from sqlalchemy import select

logger = logging.getLogger("update_events")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="手動で投稿を取り込み、確認待ちCandidateを作成します。")
    inputs = parser.add_mutually_exclusive_group()
    inputs.add_argument("--text", help="1件の投稿本文")
    inputs.add_argument("--file", type=Path, help="UTF-8の投稿本文ファイル (1ファイル=1投稿)")
    inputs.add_argument("--json", dest="json_file", type=Path, help="CollectedPost形式のJSON配列")
    parser.add_argument("--source-url", help="--text/--fileで使う投稿URL")
    parser.add_argument("--source-account", help="--text/--fileで使う投稿アカウント")
    parser.add_argument("--artist-id", type=int, help="出演ArtistのID")
    parser.add_argument("--dry-run", action="store_true", help="解析と重複判定だけ行いDBへ保存しない")
    parser.add_argument("--x-account", help="X usernameから投稿を取得 (例: hc_staffACC または @hc_staffACC)")
    parser.add_argument("--x-url", help="X投稿URLを1件取得")
    parser.add_argument("--x-user-id", help="username lookupを省略するX user ID")
    parser.add_argument("--limit", type=int, default=10, help="Xタイムライン取得数 (既定10、最大20)")
    return parser


def _load(args: argparse.Namespace) -> tuple[list[CollectedPost], list[CollectionError], int]:
    if args.text is not None or args.file is not None:
        if args.text is not None:
            text = args.text
        else:
            text = args.file.read_text(encoding="utf-8-sig")
        post = CollectedPost(
            text=text, source_url=args.source_url,
            source_account=args.source_account, artist_id=args.artist_id,
        )
        return ManualCollector(post).collect(), [], 1

    if args.json_file is None:
        raise ValueError("--text、--file、--jsonまたはX取得オプションを指定してください")
    raw_json = args.json_file.read_text(encoding="utf-8-sig")
    batch = ManualCollector.from_json(raw_json)
    return batch.posts, batch.errors, batch.input_count


_X_STATUS_URL = re.compile(r"^/(?:([^/]+)/status(?:es)?|i/status(?:es)?)/(\d+)/?$")


def _parse_x_url(value: str) -> tuple[str | None, str]:
    try:
        parsed = urlsplit(value.strip())
        match = _X_STATUS_URL.fullmatch(parsed.path)
        if parsed.scheme != "https" or parsed.hostname not in {"x.com", "www.x.com", "twitter.com", "www.twitter.com"} or not match:
            raise ValueError
        username, post_id = match.groups()
        if username:
            username = XApiCollector.normalize_username(username)
        return username, XApiCollector.normalize_id(post_id)
    except (ValueError, XApiError):
        raise ValueError("--x-urlにはhttps://x.com/{username}/status/{post_id}形式を指定してください") from None


def _latest_since_id(username: str) -> str | None:
    """Return the latest numeric X post ID already recorded for this account."""
    with SessionLocal() as session:
        values = session.scalars(
            select(ImportCandidate.external_id)
            .where(
                ImportCandidate.source_account == username,
                ImportCandidate.external_id.is_not(None),
                ImportCandidate.source_url.like("https://x.com/%"),
            )
            .order_by(ImportCandidate.id.desc())
            .limit(500)
        )
        numeric_ids = [value for value in values if value and value.isdigit()]
    return max(numeric_ids, key=int) if numeric_ids else None


def _load_x(args: argparse.Namespace) -> tuple[list[CollectedPost], XUser | None]:
    if not settings.x_bearer_token:
        raise XApiError("X_BEARER_TOKENが設定されていません")
    collector = XApiCollector(
        settings.x_bearer_token,
        base_url=settings.x_api_base_url,
        timeout_seconds=settings.x_api_timeout_seconds,
        artist_id=args.artist_id,
    )
    if args.x_url:
        if args.x_account or args.x_user_id:
            raise ValueError("--x-urlと--x-account/--x-user-idは同時に指定できません")
        username, post_id = _parse_x_url(args.x_url)
        user = XUser("", username) if username else None
        return [collector.get_post(post_id, username=username)], user

    if not args.x_account and not args.x_user_id:
        raise ValueError("X取得には--x-account、--x-user-idまたは--x-urlが必要です")
    if args.x_user_id:
        user = collector.resolve_user(user_id=args.x_user_id, username=args.x_account)
    else:
        user = collector.resolve_user(username=args.x_account)
    print(f"Resolved: @{user.username} -> {user.id}")
    since_id = _latest_since_id(user.username)
    return collector.get_timeline(user, limit=args.limit, since_id=since_id), user


def _print_dry_run(results: list[ImportResult]) -> None:
    for index, result in enumerate(results, start=1):
        candidate = result.candidate
        print(f"\n[{index}]")
        if result.status is ImportStatus.SKIPPED:
            print(f"重複: 取り込み済み Candidate #{result.existing_candidate_id}")
            continue
        if result.status is ImportStatus.FAILED:
            print(f"失敗: {result.error}")
            continue
        print(f"イベント名: {candidate.candidate_title or '未特定'}")
        print(f"開催日: {candidate.candidate_date or '未特定'}")
        print(f"会場: {candidate.candidate_venue or '未特定'}")
        print(f"信頼度: {candidate.confidence:.2f}")
        print(f"重複: Event #{candidate.duplicate_event_id}" if candidate.duplicate_event_id else "重複: なし")
        if candidate.parse_warnings:
            print("警告:")
            for warning in candidate.parse_warnings:
                print(f"- {warning}")
        else:
            print("警告: なし")


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    args = _parser().parse_args(argv)
    manual_requested = any(value is not None for value in (args.text, args.file, args.json_file))
    x_requested = any(value is not None for value in (args.x_account, args.x_url, args.x_user_id))
    if manual_requested == x_requested:
        print("--text/--file/--jsonのいずれか、またはX取得オプションを指定してください", file=sys.stderr)
        return 2
    try:
        if x_requested:
            posts, resolved_user = _load_x(args)
            validation_errors, input_count = [], len(posts)
            collector_name = "x_api"
        else:
            posts, validation_errors, input_count = _load(args)
            resolved_user = None
            collector_name = "manual"
    except XApiError as exc:
        print(f"X API取得エラー: {exc}", file=sys.stderr)
        return 2
    except (OSError, UnicodeError, ValueError, ValidationError) as exc:
        if isinstance(exc, ValidationError):
            details = "; ".join(
                f"{'.'.join(str(part) for part in error['loc']) or 'record'}: {error['msg']}"
                for error in exc.errors()
            )
        else:
            details = str(exc)
        print(f"入力を読み込めません: {details}", file=sys.stderr)
        return 2

    logger.info("update started collector=%s input_count=%s dry_run=%s", collector_name, input_count, args.dry_run)
    for error in validation_errors:
        logger.warning("import failed item=%s reason=validation", error.index)
    with SessionLocal() as session:
        results = ImportService(session).import_posts(posts, dry_run=args.dry_run)
        pending_count = CandidateService(session).count_pending()

    if args.dry_run:
        _print_dry_run(results)
    print("\n推し活スケジュール 更新結果" + (" (dry-run: DB保存なし)" if args.dry_run else ""))
    print(f"{'取得Post数' if x_requested else '入力'}             {input_count}件")
    generated = sum(result.status in (ImportStatus.CREATED, ImportStatus.DRY_RUN) for result in results)
    print(f"{'Candidate生成見込み' if args.dry_run else 'Candidate生成'}    {generated}件")
    update_count = sum(bool(result.candidate and result.candidate.candidate_type == "update") for result in results)
    new_count = sum(
        bool(result.candidate and result.status in (ImportStatus.CREATED, ImportStatus.DRY_RUN)
             and result.candidate.candidate_type != "update")
        for result in results
    )
    if x_requested:
        print(f"Update Candidate数 {update_count}件")
        print(f"New Candidate数    {new_count}件")
    print(f"解析警告あり     {sum(bool(result.candidate and result.candidate.parse_warnings) for result in results)}件")
    print(f"重複候補         {sum(bool(result.candidate and result.candidate.duplicate_event_id) for result in results)}件")
    skipped = sum(result.status is ImportStatus.SKIPPED for result in results)
    print(f"{'重複skip数' if x_requested else '二重取り込み'}     {skipped}件")
    failures = len(validation_errors) + sum(result.status is ImportStatus.FAILED for result in results)
    print(f"{'失敗数' if x_requested else '失敗'}             {failures}件")
    print(f"承認待ち         {pending_count}件")
    if x_requested and args.dry_run:
        print("X APIへの通信は実行済みです。dry-runではCandidateをDBへ保存していません。")
    for error in validation_errors:
        print(f"入力{error.index}: {error.message}", file=sys.stderr)
    for result in results:
        if result.status is ImportStatus.FAILED:
            print(f"Candidate処理: {result.error}", file=sys.stderr)
    if not args.dry_run:
        print(f"確認: {settings.app_base_url.rstrip('/')}/admin/candidates")
    return 1 if failures else 0


if __name__ == "__main__":
    if sys.platform == "win32":
        for stream in (sys.stdout, sys.stderr):
            if hasattr(stream, "reconfigure"):
                stream.reconfigure(encoding="utf-8")
    raise SystemExit(main())
