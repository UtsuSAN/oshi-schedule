from __future__ import annotations

import argparse
from pathlib import Path

from app.db import SessionLocal
from app.services.public_export import PublicExportService


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Export an allowlisted, read-only schedule snapshot for a public Sites UI."
    )
    parser.add_argument(
        "--output", type=Path, default=Path("exports/public_schedule.json"),
        help="output JSON path (default: exports/public_schedule.json)",
    )
    parser.add_argument(
        "--past-days", type=int, default=30,
        help="include events this many days before the Japan calendar date (default: 30)",
    )
    parser.add_argument(
        "--future-days", type=int, default=365,
        help="include events this many days after the Japan calendar date (default: 365)",
    )
    args = parser.parse_args()
    if args.past_days < 0 or args.future_days < 0:
        parser.error("--past-days and --future-days must be non-negative")

    with SessionLocal() as session:
        snapshot = PublicExportService(session).write_snapshot(
            args.output,
            past_days=args.past_days,
            future_days=args.future_days,
        )
    print(f"公開スナップショットを生成しました: {args.output}")
    print(f"Event {len(snapshot.events)}件 / Artist {len(snapshot.artists)}件")
    print(f"生成日時: {snapshot.generated_at.isoformat()} (Asia/Tokyo)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
