from datetime import date, datetime, time, timezone

from app.extractors.base import ParseContext
from app.extractors.rule_based import RuleBasedParser


def parse(text: str, **context):
    return RuleBasedParser().parse(text, ParseContext(reference_date=date(2026, 9, 1), **context))


def test_slash_date_open_start_appearance_benefit_and_venue():
    result = parse("""9/27(日)
○○FES
OPEN 17:00
START 17:30
出演 18:10〜18:30
特典会 18:50〜19:50
会場：ABC HALL""")
    assert result.event_date == date(2026, 9, 27)
    assert result.title == "○○FES"
    assert result.open_at == time(17, 0)
    assert result.start_at == time(17, 30)
    assert (result.appearance_start, result.appearance_end) == (time(18, 10), time(18, 30))
    assert (result.benefit_start, result.benefit_end) == (time(18, 50), time(19, 50))
    assert result.venue == "ABC HALL"
    assert result.confidence > 0.7
    assert result.parser_version == "rule-based-v1"


def test_japanese_date_and_open_start_without_spaces():
    result = parse("9月27日\nABCライブ\n開場17:00 開演17:30")
    assert result.event_date == date(2026, 9, 27)
    assert result.title == "ABCライブ"
    assert result.open_at == time(17, 0)
    assert result.start_at == time(17, 30)


def test_range_before_live_label_and_merchandise():
    result = parse("9/27 ○○FES\n18:10-18:30 LIVE\n19:00-20:00 物販")
    assert result.title == "○○FES"
    assert result.appearance_start == time(18, 10)
    assert result.benefit_start == time(19, 0)


def test_insufficient_post_still_has_low_confidence_and_warnings():
    result = parse("今週末こちらです！\nよろしくお願いします！")
    assert result.event_date is None
    assert result.title is None
    assert result.confidence == 0.1
    assert "開催日を特定できませんでした" in result.warnings


def test_multiple_urls_are_classified_only_when_labelled():
    result = parse("2026-09-27\n架空FES\nチケット\nhttps://example.invalid/ticket\n公式 https://example.invalid/info\nhttps://example.invalid/other")
    assert result.ticket_url == "https://example.invalid/ticket"
    assert result.official_url == "https://example.invalid/info"
    assert any("用途不明" in warning for warning in result.warnings)


def test_year_rollover_uses_post_date_and_warns():
    result = parse("1/5\n新年架空ライブ", published_at=datetime(2026, 12, 20, tzinfo=timezone.utc))
    assert result.event_date == date(2027, 1, 5)
    assert any("年跨ぎ" in warning for warning in result.warnings)


def test_weekday_mismatch_warns_without_changing_date():
    result = parse("9/27(月)\n架空FES")
    assert result.event_date == date(2026, 9, 27)
    assert "曜日と日付が一致しません" in result.warnings


def test_at_username_is_not_a_venue_and_ambiguous_ranges_are_unassigned():
    result = parse("9/27\n架空FES\n@fictional_user\n18:00-18:20\n19:00-19:20")
    assert result.venue is None
    assert result.appearance_start is None
    assert any("複数の時間帯" in warning for warning in result.warnings)


def test_change_notice_quoted_title_and_cancelled_appearance_regression():
    result = parse("""【出演キャンセルのお知らせ】
10月2日（金）
「しずおか大好きまつり 前夜祭」への出演について、対象アーティストは出演キャンセルとなりました。""")
    assert result.event_date == date(2026, 10, 2)
    assert result.title == "しずおか大好きまつり 前夜祭"
    assert result.change_kind == "appearance_cancelled"
    assert "出演キャンセル" in result.change_summary
    assert result.title != "出演キャンセルのお知らせ"


def test_change_notice_categories():
    examples = {
        "出演辞退": "appearance_cancelled",
        "開催中止": "event_cancelled",
        "公演延期": "postponed",
        "タイムテーブル変更": "time_changed",
        "会場変更": "venue_changed",
        "チケット発売変更": "ticket_changed",
        "変更のお知らせ": "generic_update",
    }
    for phrase, expected in examples.items():
        assert parse(f"{phrase}についてお知らせします").change_kind == expected
