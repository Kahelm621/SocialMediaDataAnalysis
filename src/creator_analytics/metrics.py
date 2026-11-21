"""Metrics a creator can recompute by hand from two snapshots."""

from __future__ import annotations

from datetime import datetime


def engagement_rate(likes, comments, shares, views) -> float | None:
    """(likes + comments + shares) / views.

    A missing share count is left out of the sum. YouTube's public API does
    not return shares, so YouTube rates use likes and comments only.
    None means we refuse to divide: views are missing or zero, or every
    reaction count is missing.
    """
    if views is None or views <= 0:
        return None
    parts = (likes, comments, shares)
    if all(part is None for part in parts):
        return None
    total = sum(int(part) for part in parts if part is not None)
    return total / float(views)


def views_per_day(history: list[tuple[datetime, int | None]]) -> float | None:
    """Views gained between the last two snapshots, divided by the days between them.

    One snapshot is not enough. This is a pace, not lifetime views divided by age.
    """
    points = [(moment, views) for moment, views in history if views is not None]
    points.sort(key=lambda item: item[0])
    if len(points) < 2:
        return None
    (earlier, earlier_views), (later, later_views) = points[-2], points[-1]
    days = (later - earlier).total_seconds() / 86400
    if days <= 0:
        return None
    return (later_views - earlier_views) / days
