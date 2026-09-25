from datetime import date, datetime, time, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db import Base
from app.models import Appearance, Artist, Event, Source
from app.services.events import EventService, as_japan_datetime, japan_today


def make_session(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'events.sqlite3'}")
    Base.metadata.create_all(engine)
    return engine, Session(engine)


def add_event(session, title, event_day, artist=None):
    event = Event(title=title, event_date=event_day, start_at=time(18, 0))
    if artist is not None:
        event.appearances.append(Appearance(artist=artist, appearance_start_at=time(19, 0)))
    session.add(event)
    session.flush()
    return event


def test_today_range_includes_only_exact_day_and_can_be_empty(tmp_path):
    engine, session = make_session(tmp_path)
    artist = Artist(name="架空アイドル")
    session.add(artist)
    add_event(session, "前日", date(2026, 9, 23), artist)
    add_event(session, "今日", date(2026, 9, 24), artist)
    add_event(session, "翌日", date(2026, 9, 25), artist)
    session.commit()

    service = EventService(session)
    assert [event.title for event in service.get_today_events(date(2026, 9, 24))] == ["今日"]
    assert service.get_today_events(date(2026, 9, 26)) == []
    session.close()
    engine.dispose()


def test_week_uses_monday_to_sunday_across_month_and_year_boundaries(tmp_path):
    engine, session = make_session(tmp_path)
    for title, day in [
        ("週の前日", date(2024, 12, 29)),
        ("月曜", date(2024, 12, 30)),
        ("日曜", date(2025, 1, 5)),
        ("翌週", date(2025, 1, 6)),
    ]:
        add_event(session, title, day)
    session.commit()

    assert [e.title for e in EventService(session).get_week_events(date(2025, 1, 1))] == ["月曜", "日曜"]
    session.close()
    engine.dispose()


def test_week_boundary_crossing_month_excludes_next_month_monday(tmp_path):
    engine, session = make_session(tmp_path)
    add_event(session, "月曜", date(2024, 3, 25))
    add_event(session, "日曜", date(2024, 3, 31))
    add_event(session, "翌月月曜", date(2024, 4, 1))
    session.commit()

    assert [e.title for e in EventService(session).get_week_events(date(2024, 3, 31))] == ["月曜", "日曜"]
    session.close()
    engine.dispose()


def test_month_range_excludes_previous_and_next_month(tmp_path):
    engine, session = make_session(tmp_path)
    add_event(session, "前月", date(2026, 8, 31))
    add_event(session, "月初", date(2026, 9, 1))
    add_event(session, "月末", date(2026, 9, 30))
    add_event(session, "翌月", date(2026, 10, 1))
    session.commit()

    assert [e.title for e in EventService(session).get_month_events(2026, 9)] == ["月初", "月末"]
    session.close()
    engine.dispose()


def test_detail_eager_loads_multiple_appearances_and_sources(tmp_path):
    engine, session = make_session(tmp_path)
    event = Event(title="架空フェス", event_date=date(2026, 9, 24))
    event.appearances.extend([
        Appearance(artist=Artist(name="星見ソーダ"), appearance_start_at=time(18, 0)),
        Appearance(artist=Artist(name="月虹パレット"), appearance_start_at=time(19, 0)),
    ])
    event.sources.append(Source(source_type="manual", source_url="https://example.invalid/info", source_text="非公開の投稿文"))
    session.add(event)
    session.commit()

    loaded = EventService(session).get_event_detail(event.id)
    assert [a.artist.name for a in loaded.appearances] == ["星見ソーダ", "月虹パレット"]
    assert loaded.sources[0].source_url == "https://example.invalid/info"
    assert EventService(session).get_event_detail(99999) is None
    session.close()
    engine.dispose()


def test_japan_date_and_naive_database_timestamp_are_treated_as_utc():
    assert japan_today(datetime(2026, 9, 23, 15, 30, tzinfo=timezone.utc)) == date(2026, 9, 24)
    assert japan_today(datetime(2026, 9, 24, 2, 0, tzinfo=timezone.utc)) == date(2026, 9, 24)
    assert as_japan_datetime(datetime(2026, 9, 23, 15, 30)).isoformat() == "2026-09-24T00:30:00+09:00"
