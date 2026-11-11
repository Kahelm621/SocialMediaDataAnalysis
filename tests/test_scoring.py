from datetime import datetime, timezone

from creator_analytics.quota import QuotaBudget, keyword_search_due, quota_plan
from creator_analytics.scoring import (
    find_outliers,
    lifetime_views_per_hour,
    parse_iso_duration,
    rising_terms,
    score_opportunity,
    score_video,
    snapshot_views_per_hour,
    title_features,
)
from creator_analytics.collectors.suggest import parse_suggest
from creator_analytics.config import load_config
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_duration_and_lifetime_pace():
    assert parse_iso_duration("PT45S") == 45
    assert parse_iso_duration("PT1H2M3S") == 3723
    pace = lifetime_views_per_hour(7200, "2026-11-11T00:00:00+00:00", "2026-11-11T02:00:00+00:00")
    assert pace == 3600
    assert snapshot_views_per_hour(
        [("2026-11-11T00:00:00+00:00", 100), ("2026-11-11T02:00:00+00:00", 300)]
    ) == 100


def test_opportunity_score_is_the_documented_blend():
    scored = score_opportunity(
        suggestion_count=None,
        median_views=1_000_000,
        median_subscribers=1_000_000,
        strong_results=4,
        top_result_count=8,
        strong_view_threshold=100000,
    )
    assert scored["demand_score"] == 100
    assert scored["competition_score"] == 75
    assert scored["opportunity_score"] == 25
    assert "search volume" in scored["formula"]


def test_seo_score_names_the_missing_pieces():
    weak = score_video({"title": "Hi", "description": "", "tags": [], "thumbnail": True}, ["guess the game"])
    assert weak["score"] < 40
    fixes = " ".join(check["fix"] for check in weak["checks"] if not check["ok"])
    assert "40 to 70" in fixes
    assert "tags" in fixes.lower()
    strong = score_video(
        {
            "title": "Guess the game before the 30 second timer ends",
            "description": "Guess the game from the HUD alone, before the timer runs out.\n\n0:00 Intro\n1:00 Answer\n#guessthegame",
            "tags": ["guess the game", "hud", "quiz"],
            "thumbnail": True,
        },
        ["guess the game"],
    )
    assert strong["score"] == 100


def test_title_features_and_rising_terms():
    features = title_features(["Guess the game?", "THIS IS LOUD", "Wait 🔥"])
    assert features["pct_question"] == 1 / 3
    assert features["pct_caps"] == 1 / 3
    assert features["pct_emoji"] == 1 / 3
    rising = rising_terms({"balatro": 4, "quiet": 2}, {"balatro": 1, "quiet": 2})
    assert rising[0]["term"] == "balatro"
    assert rising[0]["label"] == "rising"


def test_outlier_uses_the_channel_median():
    posts = []
    for index, views in enumerate((8000, 9000, 11000, 90000)):
        posts.append(
            {
                "relationship": "competitor",
                "account_name": "QuizGoblin",
                "post_id": f"v{index}",
                "title": f"video {index}",
                "views": views,
                "collected_at": "2026-11-11T00:00:00+00:00",
            }
        )
    found = find_outliers(posts, relationships={"competitor"}, multiplier=3, min_videos=4)
    assert len(found) == 1
    assert found[0]["title"] == "video 3"
    assert "median" in found[0]["note"]


def test_default_quota_plan_fits_under_the_free_cap():
    plan = quota_plan(load_config(ROOT / "config" / "tracked.yaml"))
    assert plan["estimated_units_per_day"] < 8000
    assert plan["estimated_units_per_day"] < plan["free_quota"]
    assert plan["over_budget"] is False
    assert any("100" == str(line["units_each"]) or line["units_each"] == 100 for line in plan["lines"])


def test_budget_refuses_a_call_that_would_pass_the_cap(tmp_path):
    budget = QuotaBudget(tmp_path / "quota_log.json", "2026-11-11", 150)
    assert budget.allow(100, "search")
    budget.charge(100)
    assert budget.allow(40, "another")
    assert budget.allow(60, "too big") is False
    assert "too big" in budget.skipped[0]


def test_keyword_search_slot_and_suggest_parser():
    midnight = datetime(2026, 11, 11, 0, 30, tzinfo=timezone.utc)
    later = datetime(2026, 11, 11, 12, 0, tzinfo=timezone.utc)
    assert keyword_search_due(midnight, 4, 4, False) is True
    assert keyword_search_due(later, 4, 4, False) is False
    assert keyword_search_due(later, 4, 4, True) is True
    assert parse_suggest(["guess the game", ["guess the game", "guess the game 5 seconds"], []]) == [
        "guess the game",
        "guess the game 5 seconds",
    ]
