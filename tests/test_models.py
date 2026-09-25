from datetime import date, time

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.db import Base
from app.models import Appearance, Artist, Event, ImportCandidate, Source


def test_artist_and_event_crud_and_relationships(tmp_path):
    db_file = tmp_path / "crud.sqlite3"
    engine = create_engine(f"sqlite:///{db_file}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        artist = Artist(name="架空ユニット", x_username="fictional_unit")
        event = Event(
            title="テストライブ",
            event_date=date(2030, 5, 1),
            open_at=time(17, 0),
            start_at=time(17, 30),
            venue_name="架空ホール",
        )
        appearance = Appearance(
            artist=artist,
            appearance_start_at=time(18, 0),
            appearance_end_at=time(18, 20),
            benefit_start_at=time(18, 40),
            benefit_end_at=time(19, 20),
            stage_name="メイン",
        )
        event.appearances.append(appearance)
        source = Source(source_type="manual", source_text="架空の投稿内容", media_urls=["https://example.invalid/flyer.png"])
        event.sources.append(source)
        session.add(event)
        session.commit()
        event_id = event.id
        artist_id = artist.id

        loaded = session.get(Event, event_id)
        assert loaded is not None
        assert loaded.title == "テストライブ"
        assert loaded.appearances[0].artist.name == "架空ユニット"
        assert loaded.appearances[0].appearance_start_at == time(18, 0)
        assert loaded.sources[0].media_urls == ["https://example.invalid/flyer.png"]
        loaded.sources[0].media_urls.append("https://example.invalid/timetable.png")
        session.commit()
        session.expire_all()
        assert session.get(Event, event_id).sources[0].media_urls == [
            "https://example.invalid/flyer.png",
            "https://example.invalid/timetable.png",
        ]

        loaded.title = "更新後ライブ"
        session.commit()
        assert session.scalar(select(Event.title).where(Event.id == event_id)) == "更新後ライブ"

        artist = session.get(Artist, artist_id)
        assert artist is not None
        artist.enabled = False
        session.commit()
        assert session.scalar(select(Artist.enabled).where(Artist.id == artist_id)) is False

        session.delete(loaded)
        session.commit()
        assert session.get(Event, event_id) is None
        assert session.scalars(select(Source)).all() == []
        assert session.scalars(select(Appearance)).all() == []

        session.delete(artist)
        session.commit()
        assert session.get(Artist, artist_id) is None

    engine.dispose()


def test_import_candidate_starts_unreviewed_and_editable(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'candidate.sqlite3'}")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        candidate = ImportCandidate(
            source_url="https://example.invalid/post/1",
            candidate_title="候補ライブ",
            candidate_date=date(2030, 5, 2),
            candidate_type="new",
            confidence=0.72,
        )
        session.add(candidate)
        session.commit()
        assert candidate.review_status == "pending"
        candidate.review_status = "approved"
        session.commit()
        assert session.get(ImportCandidate, candidate.id).review_status == "approved"
    engine.dispose()
