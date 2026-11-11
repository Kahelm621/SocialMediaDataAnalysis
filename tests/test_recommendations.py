from creator_analytics.recommendations import build_recommendations

SETTINGS = {
    "title_length_close_chars": 8,
    "rising_pct": 15,
    "falling_pct": -15,
    "keyword_front_chars": 40,
    "min_posts_for_hour": 4,
    "min_posts_in_hour": 2,
    "min_titles": 3,
}


def _post(post_id, title, hour, views, likes):
    published = f"2026-10-20T{hour:02d}:00:00+00:00"
    return {
        "record_type": "post",
        "platform": "youtube",
        "account_name": "KhaosAyngel",
        "post_id": post_id,
        "title": title,
        "published_at": published,
        "collected_at": "2026-11-11T12:00:00+00:00",
        "views": views,
        "likes": likes,
        "comments": 0,
        "shares": None,
    }


def _keyword(phrase, first, second):
    return [
        {
            "record_type": "keyword",
            "platform": "youtube",
            "keyword": phrase,
            "attention_kind": "top_result_views",
            "attention_note": "test",
            "example_role": "top_videos",
            "collected_at": "2026-11-10T12:00:00+00:00",
            "attention": first,
            "examples": [],
        },
        {
            "record_type": "keyword",
            "platform": "youtube",
            "keyword": phrase,
            "attention_kind": "top_result_views",
            "attention_note": "test",
            "example_role": "top_videos",
            "collected_at": "2026-11-11T12:00:00+00:00",
            "attention": second,
            "examples": [
                {"title": "Guess the game in 5 seconds"},
                {"title": "Guess the game: round 12"},
                {"title": "Steam sale 7 picks"},
            ],
        },
    ]


def test_recommendations_cite_the_numbers_they_use():
    posts = [
        _post("a", "I cannot believe how long this blurry clip took before I could guess the game", 3, 1000, 10),
        _post("b", "Four hours later and I still want chat to guess the game with me please", 3, 1000, 12),
        _post("c", "Guess the game before the 30 second timer", 18, 4000, 280),
        _post("d", "Ranking steam demos I actually finished this month please enjoy", 18, 4000, 260),
    ]
    keywords = _keyword("guess the game", 100, 150)
    cards = {card["id"]: card for card in build_recommendations(
        posts,
        keywords,
        phrases=["guess the game", "steam"],
        timezone_name="UTC",
        settings=SETTINGS,
    )}
    assert cards["title_length"]["headline"] == "Try shorter titles"
    assert cards["title_length"]["evidence"]["own_median_chars"] > cards["title_length"]["evidence"]["top_median_chars"]
    assert "characters" in cards["title_length"]["why"]
    assert cards["best_hour"]["evidence"]["best_hour"] == 18
    assert "18:00 UTC" in cards["best_hour"]["why"]
    assert cards["rising_keywords"]["evidence"]["rising"][0]["keyword"] == "guess the game"
    assert cards["rising_keywords"]["evidence"]["rising"][0]["pct_change"] == 50.0
    assert "50" in cards["rising_keywords"]["why"]
