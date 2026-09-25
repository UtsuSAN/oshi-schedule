from __future__ import annotations

from datetime import date, time, timedelta

from sqlalchemy import select

from app.db import SessionLocal
from app.models import Appearance, Artist, Event, Source
from app.services.events import japan_today


def seed() -> int:
    """Insert five fictional, date-relative demo events once."""
    with SessionLocal() as session:
        if session.scalar(select(Event.id).limit(1)) is not None:
            print("既存イベントがあるためseedをスキップしました。")
            return 0

        today = japan_today()
        artists = [
            Artist(name="星見ソーダ", display_name="星見ソーダ", x_username="hoshimi_soda"),
            Artist(name="月虹パレット", display_name="月虹パレット", x_username="gekkou_palette"),
        ]
        session.add_all(artists)
        session.flush()

        next_month = (today.replace(day=28) + timedelta(days=4)).replace(day=1)
        days_until_week_end = 6 - today.weekday()
        this_week_date = today + timedelta(days=min(3, days_until_week_end))
        fixtures = [
            ("きらめきミニライブ", today, "scheduled", time(17, 0), time(17, 30), "青空ホール", artists[0]),
            ("星見ソーダ リリースイベント", today + timedelta(days=1), "scheduled", time(13, 00), time(13, 30), "ひだまり広場", artists[0]),
            ("Weekend Pop Garden", this_week_date, "scheduled", time(16, 0), time(16, 30), "リバーサイドステージ", artists[1]),
            ("秋色アイドルフェス", next_month + timedelta(days=6), "scheduled", time(11, 0), time(11, 30), "森の音楽堂", artists[0]),
            ("月虹パレット特別公演（時間変更）", today + timedelta(days=2), "changed", time(18, 0), time(18, 30), "星空シアター", artists[1]),
        ]
        for title, event_date, status, opens, starts, venue, artist in fixtures:
            event = Event(
                title=title,
                event_date=event_date,
                open_at=opens,
                start_at=starts,
                end_at=time(starts.hour + 1, starts.minute),
                venue_name=venue,
                status=status,
            )
            if title == "秋色アイドルフェス":
                event.ticket_release_date = today + timedelta(days=1)
                event.ticket_release_time = time(10, 0)
            event.appearances.append(
                Appearance(
                    artist=artist,
                    appearance_start_at=time(starts.hour + 1, 0),
                    appearance_end_at=time(starts.hour + 1, 20),
                    benefit_start_at=time(starts.hour + 1, 40),
                    benefit_end_at=time(starts.hour + 2, 30),
                    stage_name="メインステージ",
                )
            )
            event.sources.append(Source(source_type="manual", source_text="架空のデモデータです。"))
            session.add(event)
        session.commit()
        print(f"架空のイベントを{len(fixtures)}件登録しました。")
        return len(fixtures)


if __name__ == "__main__":
    seed()
