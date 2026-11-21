#!/usr/bin/env python3
"""Look up one phrase on YouTube and print the estimate.

Spends about 102 Data API units (search.list 100, videos.list 1, channels.list 1)
plus one free autocomplete call. Nothing is written unless you pass --save.
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import requests  # noqa: E402

from creator_analytics.collectors import suggest  # noqa: E402
from creator_analytics.collectors.youtube import collect_keyword_with_videos, fetch_subscriber_counts  # noqa: E402
from creator_analytics.config import load_config  # noqa: E402
from creator_analytics.envfile import env_value, load_env_file  # noqa: E402
from creator_analytics.scoring import score_opportunity  # noqa: E402
from creator_analytics.storage import append_jsonl  # noqa: E402


def _median(values: list[float]) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    mid = len(ordered) // 2
    if len(ordered) % 2:
        return float(ordered[mid])
    return (ordered[mid - 1] + ordered[mid]) / 2


def main() -> int:
    parser = argparse.ArgumentParser(description="Estimate opportunity for one YouTube phrase.")
    parser.add_argument("phrase", help="Phrase to look up, for example: guess the game")
    parser.add_argument("--save", action="store_true", help="Append the result to data/snapshots (real data, not demo).")
    args = parser.parse_args()
    load_env_file(ROOT / ".env")
    api_key = env_value(os.environ, "YOUTUBE_API_KEY")
    if not api_key:
        print("Set YOUTUBE_API_KEY in .env first. This lookup needs the YouTube Data API.")
        return 1
    config = load_config(ROOT / "config" / "tracked.yaml")
    keyword = {"phrase": args.phrase, "hashtag": "".join(ch for ch in args.phrase.casefold() if ch.isalnum())}
    now = datetime.now(timezone.utc).replace(microsecond=0)
    collected_at = now.isoformat()
    session = requests.Session()
    print(f"Searching YouTube for {args.phrase!r}. This spends about 102 quota units.")
    row, videos, _total = collect_keyword_with_videos(
        session,
        api_key,
        keyword,
        collected_at,
        now,
        config["limits"]["trend_lookback_days"],
        config["limits"]["keyword_results"],
    )
    try:
        suggestions = suggest.fetch_suggestions(session, args.phrase)
    except Exception as exc:  # noqa: BLE001
        suggestions = []
        print(f"Autocomplete was unavailable ({exc}). The score still uses the search results.")
    channel_ids = []
    for video in videos:
        if video.get("channel_id") and video["channel_id"] not in channel_ids:
            channel_ids.append(video["channel_id"])
    subscribers = fetch_subscriber_counts(session, api_key, channel_ids) if channel_ids else {}
    threshold = config["youtube_quota"]["strong_view_threshold"]
    view_values = [video["views"] for video in videos if video.get("views") is not None]
    sub_values = [subscribers[video["channel_id"]] for video in videos if subscribers.get(video.get("channel_id")) is not None]
    scored = score_opportunity(
        suggestion_count=len(suggestions),
        median_views=_median(view_values),
        median_subscribers=_median(sub_values),
        strong_results=sum(1 for video in videos if (video.get("views") or 0) >= threshold),
        top_result_count=len(videos),
        strong_view_threshold=threshold,
    )
    print()
    print(f"Top results: {len(videos)}")
    print(f"Median views: {scored and _median(view_values)}")
    print(f"Median subscribers: {_median(sub_values)}")
    print(f"Demand {scored['demand_score']}  Competition {scored['competition_score']}  Opportunity {scored['opportunity_score']}")
    print(scored["formula"])
    print("Suggestions (not volumes):", ", ".join(suggestions[:8]) or "none")
    print("Combined views of these results:", row["attention"])
    for video in videos[:8]:
        print(f"- {video['title']} · {video['channel_title']} · {video['views']} views")
    if args.save:
        research = {
            "record_type": "keyword_research",
            "collected_at": collected_at,
            "is_demo": False,
            "source": "youtube_data_api",
            "platform": "youtube",
            "keyword": args.phrase,
            "suggestion_count": len(suggestions),
            "suggestions": suggestions[:12],
            "suggestion_note": "Autocomplete suggestions, not search volume.",
            "median_views": None if _median(view_values) is None else round(_median(view_values)),
            "median_subscribers": None if _median(sub_values) is None else round(_median(sub_values)),
            "strong_results": sum(1 for video in videos if (video.get("views") or 0) >= threshold),
            "top_result_count": len(videos),
            "examples": [
                {"title": video["title"], "author": video["channel_title"], "views": video["views"], "url": video["url"]}
                for video in videos[:8]
            ],
            **scored,
        }
        append_jsonl(ROOT / "data" / "snapshots" / "keywords.jsonl", [row])
        append_jsonl(ROOT / "data" / "snapshots" / "research.jsonl", [research])
        print("Saved under data/snapshots. Rebuild with python scripts/build_dashboard.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
