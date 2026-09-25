from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pydantic import ValidationError

from app.collectors import CollectedPost, CollectionError, ManualCollector
from app.config import settings
from app.db import SessionLocal
from app.services.admin import InputError
from app.services.candidates import CandidateService
from app.services.imports import ImportResult, ImportService, ImportStatus

logger = logging.getLogger("update_events")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="手動で投稿を取り込み、確認待ちCandidateを作成します。")
    inputs = parser.add_mutually_exclusive_group(required=True)
    inputs.add_argument("--text", help="1件の投稿本文")
    inputs.add_argument("--file", type=Path, help="UTF-8の投稿本文ファイル (1ファイル=1投稿)")
    inputs.add_argument("--json", dest="json_file", type=Path, help="CollectedPost形式のJSON配列")
    parser.add_argument("--source-url", help="--text/--fileで使う投稿URL")
    parser.add_argument("--source-account", help="--text/--fileで使う投稿アカウント")
    parser.add_argument("--artist-id", type=int, help="出演ArtistのID")
    parser.add_argument("--dry-run", action="store_true", help="解析と重複判定だけ行いDBへ保存しない")
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

    raw_json = args.json_file.read_text(encoding="utf-8-sig")
    batch = ManualCollector.from_json(raw_json)
    return batch.posts, batch.errors, batch.input_count


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
    try:
        posts, validation_errors, input_count = _load(args)
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

    logger.info("update started collector=manual input_count=%s dry_run=%s", input_count, args.dry_run)
    for error in validation_errors:
        logger.warning("import failed item=%s reason=validation", error.index)
    with SessionLocal() as session:
        results = ImportService(session).import_posts(posts, dry_run=args.dry_run)
        pending_count = CandidateService(session).count_pending()

    if args.dry_run:
        _print_dry_run(results)
    print("\n推し活スケジュール 更新結果" + (" (dry-run: DB保存なし)" if args.dry_run else ""))
    print(f"入力             {input_count}件")
    generated = sum(result.status in (ImportStatus.CREATED, ImportStatus.DRY_RUN) for result in results)
    print(f"{'Candidate生成見込み' if args.dry_run else 'Candidate生成'}    {generated}件")
    print(f"解析警告あり     {sum(bool(result.candidate and result.candidate.parse_warnings) for result in results)}件")
    print(f"重複候補         {sum(bool(result.candidate and result.candidate.duplicate_event_id) for result in results)}件")
    skipped = sum(result.status is ImportStatus.SKIPPED for result in results)
    print(f"二重取り込み     {skipped}件")
    failures = len(validation_errors) + sum(result.status is ImportStatus.FAILED for result in results)
    print(f"失敗             {failures}件")
    print(f"承認待ち         {pending_count}件")
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
