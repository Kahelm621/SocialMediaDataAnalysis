from creator_analytics.trends import (
    FALLING,
    RISING,
    STEADY,
    keyword_changes,
    keyword_in_front,
    title_stats,
)


def test_keyword_in_front_matches_phrase_and_spaceless_form():
    assert keyword_in_front("Guess the game: round 12", ["guess the game"], 40)
    assert keyword_in_front("GuessTheGame before the timer", ["guess the game"], 40)
    assert not keyword_in_front("I cannot believe how long this blurry clip took before I could guess the game", ["guess the game"], 40)


def test_short_keyword_does_not_match_inside_another_word():
    assert not keyword_in_front("streamers united tonight", ["steam"], 40)
    assert keyword_in_front("Ranking steam demos I finished", ["steam"], 40)


def test_title_stats_reports_length_numbers_and_placement():
    stats = title_stats(
        ["Guess the game in 5 seconds", "A very long title with no digit or early keyword at all"],
        ["guess the game"],
        40,
    )
    assert stats["count"] == 2
    assert stats["pct_with_number"] == 0.5
    assert stats["pct_keyword_in_front"] == 0.5
    assert stats["median_chars"] > 0


def test_keyword_changes_uses_about_a_week_when_history_is_long():
    from datetime import datetime, timedelta, timezone

    start = datetime(2026, 10, 28, 12, tzinfo=timezone.utc)
    rows = []
    for index in range(15):
        rows.append(
            {
                "platform": "youtube",
                "keyword": "balatro",
                "attention_kind": "top_result_views",
                "attention": 40000 + index * 1714,
                "collected_at": (start + timedelta(days=index)).isoformat(),
            }
        )
    change = keyword_changes(rows, rising_pct=15, falling_pct=-15)[0]
    # The previous day only moves a couple of percent. A week of gain crosses 15%.
    assert change["label"] == RISING
    assert change["previous_collected_at"].startswith("2026-11-04")


def test_keyword_changes_labels_rising_falling_and_steady():
    rows = [
        {"platform": "youtube", "keyword": "balatro", "attention_kind": "top_result_views", "attention": 100, "collected_at": "2026-11-10T00:00:00+00:00"},
        {"platform": "youtube", "keyword": "balatro", "attention_kind": "top_result_views", "attention": 160, "collected_at": "2026-11-11T00:00:00+00:00"},
        {"platform": "youtube", "keyword": "steam", "attention_kind": "top_result_views", "attention": 200, "collected_at": "2026-11-10T00:00:00+00:00"},
        {"platform": "youtube", "keyword": "steam", "attention_kind": "top_result_views", "attention": 150, "collected_at": "2026-11-11T00:00:00+00:00"},
        {"platform": "youtube", "keyword": "quiz", "attention_kind": "top_result_views", "attention": 100, "collected_at": "2026-11-10T00:00:00+00:00"},
        {"platform": "youtube", "keyword": "quiz", "attention_kind": "top_result_views", "attention": 105, "collected_at": "2026-11-11T00:00:00+00:00"},
    ]
    labeled = {row["keyword"]: row for row in keyword_changes(rows, rising_pct=15, falling_pct=-15)}
    assert labeled["balatro"]["label"] == RISING
    assert labeled["balatro"]["pct_change"] == 60
    assert labeled["steam"]["label"] == FALLING
    assert labeled["quiz"]["label"] == STEADY
