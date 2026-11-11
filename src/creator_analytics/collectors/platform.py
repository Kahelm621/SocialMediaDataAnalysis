"""Platform-wide YouTube collection, with a daily unit budget."""

from __future__ import annotations

import json

from creator_analytics.collectors import suggest, youtube
from creator_analytics.http_util import APIError
from creator_analytics.quota import keyword_search_due
from creator_analytics.scoring import score_opportunity
from creator_analytics.storage import append_jsonl

SUGGEST_NOTE = (
    "Autocomplete suggestions from Google's public YouTube suggest endpoint. "
    "They are not search volumes and they do not spend Data API quota."
)
TOTAL_NOTE = "search pageInfo.totalResults is a rough cap from YouTube, not true search volume."


def _status(source: str, state: str, detail: str, account: str = "") -> dict:
    return {"source": source, "account": account, "state": state, "detail": detail}


def collect_platform(
    session,
    api_key: str,
    config: dict,
    collected_at: str,
    now,
    snapshot_dir,
    budget,
    force_search: bool,
) -> tuple[int, list[dict]]:
    settings = config["youtube_quota"]
    trending = config["trending"]
    new_rows = 0
    statuses = []
    new_rows += _trending(session, api_key, trending, settings, collected_at, snapshot_dir, budget, statuses)
    if keyword_search_due(now, settings["keyword_search_every_n_runs"], settings["runs_per_day"], force_search):
        new_rows += _keywords(session, api_key, config, collected_at, now, snapshot_dir, budget, statuses)
    else:
        statuses.append(
            _status(
                "YouTube keyword search",
                "skipped",
                "Not this run's search slot. Keyword search.list costs 100 units, so the watchlist "
                f"runs every {settings['keyword_search_every_n_runs']} scheduled runs. "
                "Use python scripts/refresh.py --search to force it.",
            )
        )
    new_rows += _outlier_channels(session, api_key, config, collected_at, snapshot_dir, budget, statuses)
    if budget.skipped:
        statuses.append(
            _status(
                "YouTube quota budget",
                "skipped",
                f"Stopped before the {budget.daily_limit} unit daily budget. "
                f"Skipped: {', '.join(budget.skipped[:6])}.",
            )
        )
    return new_rows, statuses


def _charge(budget, units: int, reason: str, statuses: list[dict]) -> bool:
    if not budget.allow(units, reason):
        statuses.append(_status("YouTube quota budget", "skipped", f"Skipped {reason} to stay under the daily budget."))
        return False
    budget.charge(units)
    return True


def _trending(session, api_key, trending, settings, collected_at, snapshot_dir, budget, statuses) -> int:
    wrote = 0
    regions = trending["regions"]
    primary = trending["category_region"]
    limit = settings["trending_max_results"]
    calls = [(region, {"id": "0", "name": "All categories"}) for region in regions]
    for category in trending["categories"]:
        if str(category["id"]) in {"0", ""}:
            continue
        calls.append((primary, category))
    for region, category in calls:
        label = f"mostPopular {region} {category['name']}"
        if not _charge(budget, 1, label, statuses):
            continue
        try:
            payload = youtube.fetch_most_popular(session, api_key, region, category["id"], limit)
        except (APIError, Exception) as exc:  # noqa: BLE001
            statuses.append(_status("YouTube trending", "error", str(exc)[:300], f"{region} {category['name']}"))
            continue
        rows = []
        for item in payload.get("items") or []:
            video = youtube.parse_video_item(item)
            rows.append(
                {
                    "record_type": "trending_video",
                    "collected_at": collected_at,
                    "is_demo": False,
                    "source": "youtube_data_api",
                    "platform": "youtube",
                    "region": region,
                    "category_id": str(category["id"]),
                    "category_name": category["name"],
                    "post_id": video["post_id"],
                    "title": video["title"],
                    "channel_title": video["channel_title"],
                    "channel_id": video.get("channel_id") or "",
                    "published_at": video["published_at"],
                    "views": video["views"],
                    "likes": video["likes"],
                    "duration_seconds": video.get("duration_seconds"),
                    "tags": (video.get("tags") or [])[:12],
                    "url": video["url"],
                }
            )
        wrote += append_jsonl(snapshot_dir / "trending.jsonl", rows)
        statuses.append(_status("YouTube trending", "ok", f"Saved {len(rows)} videos.", f"{region} {category['name']}"))
    return wrote


def _keywords(session, api_key, config, collected_at, now, snapshot_dir, budget, statuses) -> int:
    wrote = 0
    threshold = config["youtube_quota"]["strong_view_threshold"]
    for keyword in config["keywords"]:
        if not _charge(budget, 101, f"search {keyword['phrase']}", statuses):
            continue
        try:
            keyword_row, videos, search_total = youtube.collect_keyword_with_videos(
                session,
                api_key,
                keyword,
                collected_at,
                now,
                config["limits"]["trend_lookback_days"],
                config["limits"]["keyword_results"],
            )
        except (APIError, Exception) as exc:  # noqa: BLE001
            statuses.append(_status("YouTube keyword search", "error", str(exc)[:300], keyword["phrase"]))
            continue
        wrote += append_jsonl(snapshot_dir / "keywords.jsonl", [keyword_row])
        suggestions = []
        try:
            suggestions = suggest.fetch_suggestions(session, keyword["phrase"])
        except (APIError, Exception):  # noqa: BLE001 — suggestions are optional
            suggestions = []
        channel_ids = []
        for video in videos:
            channel_id = video.get("channel_id")
            if channel_id and channel_id not in channel_ids:
                channel_ids.append(channel_id)
        subscribers = {}
        if channel_ids and _charge(budget, 1, f"channels for {keyword['phrase']}", statuses):
            try:
                subscribers = youtube.fetch_subscriber_counts(session, api_key, channel_ids)
            except (APIError, Exception) as exc:  # noqa: BLE001
                statuses.append(_status("YouTube keyword search", "error", str(exc)[:300], keyword["phrase"]))
        view_values = sorted(video["views"] for video in videos if video.get("views") is not None)
        sub_values = sorted(
            subscribers[video["channel_id"]]
            for video in videos
            if video.get("channel_id") in subscribers and subscribers[video["channel_id"]] is not None
        )
        median_views = _median(view_values)
        median_subscribers = _median(sub_values)
        strong = sum(1 for video in videos if (video.get("views") or 0) >= threshold)
        scored = score_opportunity(
            suggestion_count=len(suggestions),
            median_views=median_views,
            median_subscribers=median_subscribers,
            strong_results=strong,
            top_result_count=len(videos),
            strong_view_threshold=threshold,
        )
        research = {
            "record_type": "keyword_research",
            "collected_at": collected_at,
            "is_demo": False,
            "source": "youtube_data_api",
            "platform": "youtube",
            "keyword": keyword["phrase"],
            "suggestion_count": len(suggestions),
            "suggestions": suggestions[:12],
            "suggestion_note": SUGGEST_NOTE,
            "search_total_results": search_total,
            "search_total_note": TOTAL_NOTE,
            "median_views": None if median_views is None else round(median_views),
            "median_subscribers": None if median_subscribers is None else round(median_subscribers),
            "strong_results": strong,
            "top_result_count": len(videos),
            "examples": [
                {
                    "title": video["title"],
                    "author": video["channel_title"],
                    "views": video["views"],
                    "subscribers": subscribers.get(video.get("channel_id")),
                    "url": video["url"],
                }
                for video in videos[:8]
            ],
            **scored,
        }
        wrote += append_jsonl(snapshot_dir / "research.jsonl", [research])
        statuses.append(
            _status(
                "YouTube keyword search",
                "ok",
                f"Saved {len(videos)} top videos. Opportunity score {scored['opportunity_score']}.",
                keyword["phrase"],
            )
        )
    return wrote


def _outlier_channels(session, api_key, config, collected_at, snapshot_dir, budget, statuses) -> int:
    """Fetch recent uploads for a few channels that appeared in today's trending file.

    This is a sample, not a scan of YouTube. Channels already saved as your
    own or as configured competitors are skipped.
    """
    path = snapshot_dir / "trending.jsonl"
    if not path.exists():
        return 0
    seen = []
    known = {
        account.get("channel_id")
        for account in config["accounts"] + config["competitors"]
        if account.get("channel_id")
    }
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        if row.get("collected_at") != collected_at or not row.get("channel_id"):
            continue
        if row["channel_id"] in known or row["channel_id"] in seen:
            continue
        seen.append(row["channel_id"])
    limit = int(config["youtube_quota"]["outlier_channels_per_run"])
    wrote = 0
    sampled = 0
    for channel_id in seen:
        if sampled >= limit:
            break
        if not _charge(budget, 3, f"uploads {channel_id}", statuses):
            break
        try:
            account_row, posts = youtube.collect_account(
                session,
                api_key,
                {
                    "name": channel_id,
                    "handle": "",
                    "channel_id": channel_id,
                    "niche": "",
                    "relationship": "channel_sample",
                },
                collected_at,
                8,
            )
        except (APIError, Exception) as exc:  # noqa: BLE001
            statuses.append(_status("YouTube outlier sample", "error", str(exc)[:300], channel_id))
            continue
        display = account_row.get("channel_title") or channel_id
        account_row["account_name"] = display
        account_row["relationship"] = "channel_sample"
        for post in posts:
            post["relationship"] = "channel_sample"
            post["account_name"] = display
        wrote += append_jsonl(snapshot_dir / "accounts.jsonl", [account_row])
        wrote += append_jsonl(snapshot_dir / "posts.jsonl", posts)
        sampled += 1
    if sampled:
        statuses.append(
            _status(
                "YouTube outlier sample",
                "ok",
                f"Saved recent uploads for {sampled} channels that were on today's trending chart. This is a sample, not all of YouTube.",
            )
        )
    return wrote


def _median(values: list) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    mid = len(ordered) // 2
    if len(ordered) % 2:
        return float(ordered[mid])
    return (ordered[mid - 1] + ordered[mid]) / 2
