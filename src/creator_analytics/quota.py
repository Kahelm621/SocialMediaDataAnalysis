"""Stay inside the free YouTube Data API quota of 10,000 units per day.

search.list costs 100 units. videos.list, channels.list, playlistItems.list,
and videoCategories.list cost 1 unit each. The scheduled workflow runs every
6 hours, so a daily plan is four runs.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path


def keyword_search_due(now: datetime, every_n_runs: int, runs_per_day: int, force: bool) -> bool:
    if force or every_n_runs <= 1:
        return True
    moment = now.astimezone(timezone.utc) if now.tzinfo else now
    slot_hours = 24 / max(1, int(runs_per_day))
    slot = int(moment.hour // slot_hours)
    return slot % int(every_n_runs) == 0


def quota_plan(config: dict) -> dict:
    """Estimated units per day for the current config. This is a plan, not Google's meter."""
    settings = config["youtube_quota"]
    trending = config["trending"]
    runs = int(settings["runs_per_day"])
    every = max(1, int(settings["keyword_search_every_n_runs"]))
    keyword_runs = runs / every
    regions = trending["regions"]
    categories = [item for item in trending["categories"] if str(item["id"]) not in {"0", ""}]
    keywords = len(config["keywords"])
    own_channels = len(
        [account for account in config["accounts"] if account["platform"] == "youtube" and account["enabled"]]
    )
    competitors = len([channel for channel in config["competitors"] if channel.get("enabled")])
    outlier_channels = int(settings["outlier_channels_per_run"])
    lines = [
        {"item": "videoCategories.list", "units_each": 1, "times_per_day": runs, "units_per_day": runs},
        {
            "item": f"mostPopular overall ({len(regions)} regions)",
            "units_each": 1,
            "times_per_day": runs * len(regions),
            "units_per_day": runs * len(regions),
        },
        {
            "item": f"mostPopular for {len(categories)} categories in {trending['category_region']} only",
            "units_each": 1,
            "times_per_day": runs * len(categories),
            "units_per_day": runs * len(categories),
        },
        {
            "item": f"Your YouTube channels ({own_channels} × channel, playlist, videos)",
            "units_each": 3,
            "times_per_day": runs * own_channels,
            "units_per_day": runs * own_channels * 3,
        },
        {
            "item": f"Enabled competitor channels ({competitors})",
            "units_each": 3,
            "times_per_day": runs * competitors,
            "units_per_day": runs * competitors * 3,
        },
        {
            "item": f"Watchlist search.list ({keywords} keywords, {keyword_runs:g} times/day)",
            "units_each": 100,
            "times_per_day": keyword_runs * keywords,
            "units_per_day": int(keyword_runs * keywords * 100),
        },
        {
            "item": "videos.list and channels.list after each watchlist search",
            "units_each": 2,
            "times_per_day": keyword_runs * keywords,
            "units_per_day": int(keyword_runs * keywords * 2),
        },
        {
            "item": f"Recent uploads for up to {outlier_channels} trending channels",
            "units_each": 2,
            "times_per_day": runs * outlier_channels,
            "units_per_day": runs * outlier_channels * 2,
        },
        {
            "item": "Autocomplete suggestions",
            "units_each": 0,
            "times_per_day": keyword_runs * keywords,
            "units_per_day": 0,
        },
    ]
    estimated = sum(line["units_per_day"] for line in lines)
    budget = int(settings["daily_unit_budget"])
    return {
        "daily_budget": budget,
        "free_quota": 10000,
        "estimated_units_per_day": estimated,
        "over_budget": estimated > budget,
        "lines": lines,
        "note": (
            "search.list costs 100 units. videos.list, channels.list, playlistItems.list, "
            "and videoCategories.list cost 1. The free cap is 10,000 units per day. "
            "This table is the plan for config/tracked.yaml, not a reading from Google. "
            "A live run also writes data/snapshots/quota_log.json and stops before the daily budget."
        ),
    }


class QuotaBudget:
    """Remembers units spent today and refuses a call that would pass the cap."""

    def __init__(self, path: Path, today: str, daily_limit: int):
        self.path = path
        self.today = today
        self.daily_limit = daily_limit
        self.used = 0
        self.spent_this_run = 0
        self.skipped: list[str] = []
        if path.exists():
            try:
                saved = json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                saved = {}
            self.used = int((saved.get("days") or {}).get(today) or 0)

    def allow(self, units: int, reason: str) -> bool:
        if units <= 0:
            return True
        if self.used + units > self.daily_limit:
            self.skipped.append(reason)
            return False
        return True

    def charge(self, units: int) -> None:
        if units <= 0:
            return
        self.used += units
        self.spent_this_run += units
        self.path.parent.mkdir(parents=True, exist_ok=True)
        saved = {"days": {}}
        if self.path.exists():
            try:
                saved = json.loads(self.path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                saved = {"days": {}}
        days = saved.get("days") or {}
        days[self.today] = self.used
        saved["days"] = days
        self.path.write_text(json.dumps(saved, indent=2) + "\n", encoding="utf-8")
