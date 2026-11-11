"""YouTube Data API v3. Public stats and search only."""

from __future__ import annotations

from datetime import timedelta, timezone

from creator_analytics.http_util import APIError, request_json, safe_int
from creator_analytics.scoring import parse_iso_duration

API = "https://www.googleapis.com/youtube/v3"
ATTENTION_NOTE = (
    "Combined views of the top YouTube search results in the lookback window. "
    "YouTube does not publish an exact count of videos for a phrase."
)


def parse_channel_item(item: dict) -> dict:
    stats = item.get("statistics") or {}
    hidden = stats.get("hiddenSubscriberCount")
    hidden_flag = hidden is True or str(hidden).lower() == "true"
    return {
        "account_id": item.get("id"),
        "title": (item.get("snippet") or {}).get("title"),
        "followers": None if hidden_flag else safe_int(stats.get("subscriberCount")),
        "total_views": safe_int(stats.get("viewCount")),
        "uploads_playlist": ((item.get("contentDetails") or {}).get("relatedPlaylists") or {}).get("uploads"),
    }


def parse_video_item(item: dict) -> dict:
    snippet = item.get("snippet") or {}
    stats = item.get("statistics") or {}
    video_id = item.get("id")
    thumbnails = snippet.get("thumbnails") or {}
    return {
        "post_id": video_id,
        "title": snippet.get("title") or "",
        "description": (snippet.get("description") or "")[:500],
        "tags": snippet.get("tags") or [],
        "published_at": snippet.get("publishedAt"),
        "url": f"https://www.youtube.com/watch?v={video_id}" if video_id else "",
        "views": safe_int(stats.get("viewCount")),
        "likes": safe_int(stats.get("likeCount")),
        "comments": safe_int(stats.get("commentCount")),
        "shares": None,
        "channel_id": snippet.get("channelId") or "",
        "channel_title": snippet.get("channelTitle") or "",
        "duration_seconds": parse_iso_duration((item.get("contentDetails") or {}).get("duration")),
        "thumbnail": bool(thumbnails.get("high") or thumbnails.get("maxres") or thumbnails.get("medium")),
    }


def _get(session, api_key: str, path: str, params: dict) -> dict:
    return request_json(
        session,
        "GET",
        f"{API}/{path}",
        params={**params, "key": api_key},
        secrets=[api_key],
    )


def fetch_channel(session, api_key: str, account: dict) -> dict:
    params = {"part": "snippet,statistics,contentDetails"}
    if account.get("channel_id"):
        params["id"] = account["channel_id"]
    elif account.get("handle"):
        params["forHandle"] = account["handle"]
    else:
        raise APIError(f"{account['name']} needs a handle or a channel_id in config/tracked.yaml.")
    payload = _get(session, api_key, "channels", params)
    items = payload.get("items") or []
    if not items:
        raise APIError(
            f"No YouTube channel found for {account['name']}. "
            "Check the handle, or paste the channel id (it starts with UC) into config/tracked.yaml."
        )
    return parse_channel_item(items[0])


def fetch_recent_video_ids(session, api_key: str, uploads_playlist: str, limit: int) -> list[str]:
    payload = _get(
        session,
        api_key,
        "playlistItems",
        {
            "part": "snippet",
            "playlistId": uploads_playlist,
            "maxResults": max(1, min(int(limit), 50)),
        },
    )
    ids = []
    for item in payload.get("items") or []:
        video_id = ((item.get("snippet") or {}).get("resourceId") or {}).get("videoId")
        if video_id:
            ids.append(video_id)
    return ids


def fetch_videos(session, api_key: str, video_ids: list[str]) -> list[dict]:
    if not video_ids:
        return []
    payload = _get(
        session,
        api_key,
        "videos",
        {"part": "snippet,statistics,contentDetails", "id": ",".join(video_ids)},
    )
    return [parse_video_item(item) for item in payload.get("items") or []]


def collect_account(session, api_key: str, account: dict, collected_at: str, limit: int) -> tuple[dict, list[dict]]:
    channel = fetch_channel(session, api_key, account)
    account_row = {
        "record_type": "account",
        "collected_at": collected_at,
        "is_demo": False,
        "source": "youtube_data_api",
        "platform": "youtube",
        "account_name": account["name"],
        "account_id": channel["account_id"],
        "handle": account.get("handle") or "",
        "relationship": account.get("relationship") or "own",
        "niche": account.get("niche") or "",
        "followers": channel["followers"],
        "channel_title": channel.get("title") or "",
        "total_views": channel["total_views"],
        "analytics_avg_view_percentage": None,
        "analytics_ctr": None,
    }
    posts = []
    if channel["uploads_playlist"]:
        ids = fetch_recent_video_ids(session, api_key, channel["uploads_playlist"], limit)
        for video in fetch_videos(session, api_key, ids):
            posts.append(
                {
                    "record_type": "post",
                    "collected_at": collected_at,
                    "is_demo": False,
                    "source": "youtube_data_api",
                    "platform": "youtube",
                    "relationship": account.get("relationship") or "own",
                    "account_name": account["name"],
                    "niche": account.get("niche") or "",
                    "post_id": video["post_id"],
                    "title": video["title"],
                    "description": video.get("description") or "",
                    "tags": video.get("tags") or [],
                    "duration_seconds": video.get("duration_seconds"),
                    "thumbnail": video.get("thumbnail"),
                    "url": video["url"],
                    "published_at": video["published_at"],
                    "views": video["views"],
                    "likes": video["likes"],
                    "comments": video["comments"],
                    "shares": None,
                    "views_label": "views",
                }
            )
    return account_row, posts


def collect_keyword(session, api_key: str, keyword: dict, collected_at: str, now, lookback_days: int, limit: int) -> dict:
    row, _videos, _total = collect_keyword_with_videos(
        session, api_key, keyword, collected_at, now, lookback_days, limit
    )
    return row


def collect_keyword_with_videos(session, api_key: str, keyword: dict, collected_at: str, now, lookback_days: int, limit: int):
    """One search.list (100 units) plus one videos.list (1 unit)."""
    moment = now.astimezone(timezone.utc) if now.tzinfo else now
    published_after = (moment - timedelta(days=int(lookback_days))).strftime("%Y-%m-%dT%H:%M:%SZ")
    search = _get(
        session,
        api_key,
        "search",
        {
            "part": "snippet",
            "q": keyword["phrase"],
            "type": "video",
            "order": "viewCount",
            "maxResults": max(1, min(int(limit), 15)),
            "publishedAfter": published_after,
        },
    )
    ids = []
    for item in search.get("items") or []:
        video_id = (item.get("id") or {}).get("videoId")
        if video_id:
            ids.append(video_id)
    videos = fetch_videos(session, api_key, ids)
    videos.sort(key=lambda video: video["views"] or 0, reverse=True)
    examples = [
        {
            "title": video["title"],
            "author": video["channel_title"],
            "channel_id": video.get("channel_id") or "",
            "views": video["views"],
            "url": video["url"],
        }
        for video in videos
    ]
    row = {
        "record_type": "keyword",
        "collected_at": collected_at,
        "is_demo": False,
        "source": "youtube_data_api",
        "platform": "youtube",
        "keyword": keyword["phrase"],
        "hashtag": keyword["hashtag"],
        "attention": sum(video["views"] or 0 for video in videos),
        "attention_kind": "top_result_views",
        "attention_note": ATTENTION_NOTE,
        "search_total_results": (search.get("pageInfo") or {}).get("totalResults"),
        "example_role": "top_videos",
        "examples": examples,
    }
    return row, videos, (search.get("pageInfo") or {}).get("totalResults")


def fetch_most_popular(session, api_key: str, region: str, category_id: str, max_results: int) -> dict:
    params = {
        "part": "snippet,statistics,contentDetails",
        "chart": "mostPopular",
        "regionCode": region,
        "maxResults": max(1, min(int(max_results), 50)),
    }
    if str(category_id) not in {"0", ""}:
        params["videoCategoryId"] = str(category_id)
    return _get(session, api_key, "videos", params)


def fetch_subscriber_counts(session, api_key: str, channel_ids: list[str]) -> dict[str, int | None]:
    if not channel_ids:
        return {}
    payload = _get(
        session,
        api_key,
        "channels",
        {"part": "statistics", "id": ",".join(channel_ids[:50])},
    )
    counts = {}
    for item in payload.get("items") or []:
        parsed = parse_channel_item(item)
        counts[item.get("id")] = parsed["followers"]
    return counts
