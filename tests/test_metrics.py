from datetime import datetime, timezone

from creator_analytics.metrics import engagement_rate, views_per_day


def test_engagement_rate_adds_reactions_and_divides_by_views():
    assert engagement_rate(10, 5, 5, 100) == 0.2


def test_engagement_rate_skips_missing_shares():
    # YouTube does not return shares. 10 likes and 5 comments over 100 views.
    assert engagement_rate(10, 5, None, 100) == 0.15


def test_engagement_rate_refuses_to_divide_without_views_or_reactions():
    assert engagement_rate(1, 1, 1, 0) is None
    assert engagement_rate(1, 1, 1, None) is None
    assert engagement_rate(None, None, None, 100) is None


def test_views_per_day_uses_the_last_two_snapshots():
    start = datetime(2026, 11, 1, tzinfo=timezone.utc)
    later = datetime(2026, 11, 3, tzinfo=timezone.utc)
    assert views_per_day([(later, 180), (start, 100)]) == 40


def test_views_per_day_needs_two_points():
    start = datetime(2026, 11, 1, tzinfo=timezone.utc)
    assert views_per_day([(start, 100)]) is None
    assert views_per_day([(start, None)]) is None
