"""Load config/tracked.yaml into a predictable shape."""

from __future__ import annotations

from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import yaml


def default_hashtag(phrase: str) -> str:
    return "".join(ch for ch in phrase.casefold() if ch.isalnum())


def load_config(path: Path) -> dict:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"{path} must be a YAML mapping of accounts and keywords.")

    timezone_name = str(raw.get("timezone") or "UTC")
    try:
        ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError as exc:
        raise ValueError(
            f"timezone {timezone_name!r} is not a valid timezone. "
            "Example: America/New_York"
        ) from exc

    limits = {
        "videos_per_account": 15,
        "tweets_per_account": 20,
        "tiktok_videos": 20,
        "keyword_results": 8,
        "trend_lookback_days": 30,
        **(raw.get("limits") or {}),
    }
    recommendations = {
        "title_length_close_chars": 8,
        "rising_pct": 15,
        "falling_pct": -15,
        "keyword_front_chars": 40,
        "min_posts_for_hour": 4,
        "min_posts_in_hour": 2,
        "min_titles": 3,
        **(raw.get("recommendations") or {}),
    }

    accounts_raw = raw.get("accounts") or {}
    accounts = []
    for platform in ("youtube", "x", "tiktok"):
        for entry in accounts_raw.get(platform) or []:
            if not isinstance(entry, dict) or not entry.get("name"):
                raise ValueError(f"Each {platform} account needs a name.")
            accounts.append(
                {
                    "platform": platform,
                    "name": str(entry["name"]),
                    "handle": str(entry.get("handle") or "").lstrip("@"),
                    "channel_id": str(entry.get("channel_id") or ""),
                    "niche": str(entry.get("niche") or ""),
                    "enabled": bool(entry.get("enabled", True)),
                    "keywords": [str(item) for item in (entry.get("keywords") or [])],
                }
            )

    keywords = []
    for entry in raw.get("keywords") or []:
        if isinstance(entry, str):
            phrase = entry.strip()
            hashtag = default_hashtag(phrase)
        elif isinstance(entry, dict) and entry.get("phrase"):
            phrase = str(entry["phrase"]).strip()
            hashtag = str(entry.get("hashtag") or default_hashtag(phrase)).lstrip("#")
        else:
            raise ValueError("Each keyword needs a phrase.")
        keywords.append({"phrase": phrase, "hashtag": hashtag})

    if not keywords:
        raise ValueError("Add at least one keyword under keywords: in config/tracked.yaml.")

    youtube_quota = {
        "daily_unit_budget": 8000,
        "runs_per_day": 4,
        "keyword_search_every_n_runs": 4,
        "outlier_channels_per_run": 8,
        "trending_max_results": 15,
        "strong_view_threshold": 100000,
        "outlier_multiplier": 3,
        **(raw.get("youtube_quota") or {}),
    }
    trending_raw = raw.get("trending") or {}
    categories = []
    for entry in trending_raw.get("categories") or [{"id": "0", "name": "All categories"}]:
        categories.append({"id": str(entry.get("id", "0")), "name": str(entry.get("name") or "All categories")})
    competitors = []
    for entry in (raw.get("competitors") or {}).get("youtube") or []:
        if not isinstance(entry, dict) or not entry.get("name"):
            raise ValueError("Each competitor needs a name.")
        competitors.append(
            {
                "platform": "youtube",
                "name": str(entry["name"]),
                "handle": str(entry.get("handle") or "").lstrip("@"),
                "channel_id": str(entry.get("channel_id") or ""),
                "niche": str(entry.get("niche") or ""),
                "enabled": bool(entry.get("enabled", False)),
                "relationship": "competitor",
                "keywords": [str(item) for item in (entry.get("keywords") or [])],
            }
        )
    trending = {
        "regions": [str(code) for code in (trending_raw.get("regions") or ["US"])],
        "category_region": str(trending_raw.get("category_region") or "US"),
        "categories": categories,
    }

    return {
        "timezone": timezone_name,
        "limits": limits,
        "recommendations": recommendations,
        "accounts": accounts,
        "keywords": keywords,
        "youtube_quota": youtube_quota,
        "trending": trending,
        "competitors": competitors,
    }
