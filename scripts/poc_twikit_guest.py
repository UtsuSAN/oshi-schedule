from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.collectors.twikit_guest import TwikitGuestCollector, TwikitGuestError
from app.db import SessionLocal
from app.services.imports import ImportService, ImportStatus


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Experimental one-shot Twikit GuestClient PoC")
    parser.add_argument("--account", required=True)
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument("--artist-id", type=int)
    parser.add_argument("--parse", action="store_true", help="Parser dry-run only; never saves candidates")
    parser.add_argument("--debug", action="store_true")
    args = parser.parse_args(argv)
    try:
        posts = TwikitGuestCollector(args.account, limit=args.limit, artist_id=args.artist_id).collect()
    except TwikitGuestError as exc:
        print(str(exc), file=sys.stderr)
        if args.debug and exc.__cause__:
            # Keep debug output from exposing response bodies, cookies, or tokens.
            print(f"debug: {type(exc.__cause__).__name__}", file=sys.stderr)
        return 1
    for post in posts:
        print(f"投稿ID: {post.external_id}\nアカウント: {post.source_account}\n投稿日時: {post.published_at or '不明'}")
        print(f"本文: {post.text}\nURL: {post.source_url}")
        if args.parse:
            with SessionLocal() as session:
                result = ImportService(session).import_post(post, dry_run=True)
            if result.status is ImportStatus.DRY_RUN and result.candidate:
                candidate = result.candidate
                print(f"イベント名: {candidate.candidate_title or '未特定'}\n開催日: {candidate.candidate_date or '未特定'}")
                print(f"Candidate Type: {candidate.candidate_type}\nChange Kind: {candidate.change_kind or 'なし'}")
                print(f"信頼度: {candidate.confidence:.2f}\n警告: {'; '.join(candidate.parse_warnings) if candidate.parse_warnings else 'なし'}")
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
