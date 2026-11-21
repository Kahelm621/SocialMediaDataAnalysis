"""Official TikTok APIs only.

Display API reads the account that approved the app (Login Kit access token).
Research API can query hashtags after TikTok approves a research application.
This module does not fetch TikTok web pages or use unofficial scrapers.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from creator_analytics.http_util import APIError, request_json, safe_int

API = "https://open.tiktokapis.com"
RESEARCH_NOTE = (
    "Sum of views on videos returned by the TikTok Research API for this hashtag. "
    "It is a sample from that API, not every public video. "
    "This project does not scrape TikTok."
)


def _raise_if_tiktok_error(payload: dict) -> None:
    error = payload.get("error") or {}
    code = error.get("code")
    if code and code != "ok":
        message = error.get("message") or code
        raise APIError(f"TikTok API: {code}: {message}")


def parse_user(payload: dict) -> dict:
    user = (payload.get("data") or {}).get("user") or {}
    return {
        "account_id": user.get("open_id"),
        "display_name": user.get("display_name") or "",
        "handle": user.get("username") or "",
        "followers": safe_int(user.get("follower_count")),
    }


def parse_video(video: dict, handle: str) -> dict:
    video_id = video.get("id")
    created = safe_int(video.get("create_time"))
    published = None
    if created is not None:
        published = datetime.fromtimestamp(created, timezone.utc).isoformat()
    share_url = video.get("share_url") or ""
    if not share_url and video_id and handle:
        share_url = f"https://www.tiktok.com/@{handle}/video/{video_id}"
    title = video.get("title") or video.get("video_description") or ""
    return {
        "post_id": video_id,
        "title": title,
        "published_at": published,
        "url": share_url,
        "views": safe_int(video.get("view_count")),
        "likes": safe_int(video.get("like_count")),
        "comments": safe_int(video.get("comment_count")),
        "shares": safe_int(video.get("share_count")),
    }


def collect_account(session, token: str, account: dict, collected_at: str, limit: int) -> tuple[dict, list[dict], str]:
    headers = {"Authorization": f"Bearer {token}"}
    user_payload = request_json(
        session,
        "GET",
        f"{API}/v2/user/info/",
        params={"fields": "open_id,display_name,username,follower_count"},
        headers=headers,
        secrets=[token],
    )
    _raise_if_tiktok_error(user_payload)
    user = parse_user(user_payload)
    video_payload = request_json(
        session,
        "POST",
        f"{API}/v2/video/list/",
        params={"fields": "id,title,video_description,create_time,share_url,like_count,comment_count,share_count,view_count"},
        json_body={"max_count": max(1, min(int(limit), 20))},
        headers=headers,
        secrets=[token],
    )
    _raise_if_tiktok_error(video_payload)
    note = ""
    configured = (account.get("handle") or "").lstrip("@")
    actual = user["handle"]
    if configured and actual and configured.casefold() != actual.casefold():
        note = (
            f"The TikTok token belongs to @{actual}, while config/tracked.yaml lists @{configured}. "
            "The Display API can only read the account that approved the app."
        )
    handle = actual or configured
    account_row = {
        "record_type": "account",
        "collected_at": collected_at,
        "is_demo": False,
        "source": "tiktok_display_api",
        "platform": "tiktok",
        "account_name": account["name"],
        "account_id": user["account_id"],
        "handle": handle,
        "niche": account.get("niche") or "",
        "followers": user["followers"],
        "total_views": None,
        "analytics_avg_view_percentage": None,
        "analytics_ctr": None,
    }
    posts = []
    for video in (video_payload.get("data") or {}).get("videos") or []:
        parsed = parse_video(video, handle)
        posts.append(
            {
                "record_type": "post",
                "collected_at": collected_at,
                "is_demo": False,
                "source": "tiktok_display_api",
                "platform": "tiktok",
                "account_name": account["name"],
                "niche": account.get("niche") or "",
                "post_id": parsed["post_id"],
                "title": parsed["title"],
                "url": parsed["url"],
                "published_at": parsed["published_at"],
                "views": parsed["views"],
                "likes": parsed["likes"],
                "comments": parsed["comments"],
                "shares": parsed["shares"],
                "views_label": "views",
            }
        )
    return account_row, posts, note


def collect_keyword(session, token: str, keyword: dict, collected_at: str, now: datetime, lookback_days: int) -> dict:
    start = now - timedelta(days=min(int(lookback_days), 30))
    payload = request_json(
        session,
        "POST",
        f"{API}/v2/research/video/query/",
        params={"fields": "id,video_description,create_time,like_count,share_count,view_count,comment_count"},
        json_body={
            "query": {
                "and": [
                    {
                        "operation": "EQ",
                        "field_name": "hashtag_name",
                        "field_values": [keyword["hashtag"]],
                    }
                ]
            },
            "max_count": 20,
            "start_date": start.strftime("%Y%m%d"),
            "end_date": now.strftime("%Y%m%d"),
        },
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        secrets=[token],
    )
    _raise_if_tiktok_error(payload)
    videos = (payload.get("data") or {}).get("videos") or []
    parsed = [parse_video(video, "") for video in videos]
    parsed.sort(key=lambda video: video["views"] or 0, reverse=True)
    examples = [
        {
            "title": video["title"],
            "author": "",
            "views": video["views"],
            "url": video["url"],
        }
        for video in parsed[:8]
    ]
    return {
        "record_type": "keyword",
        "collected_at": collected_at,
        "is_demo": False,
        "source": "tiktok_research_api",
        "platform": "tiktok",
        "keyword": keyword["phrase"],
        "hashtag": keyword["hashtag"],
        "attention": sum(video["views"] or 0 for video in parsed),
        "attention_kind": "research_sample_views",
        "attention_note": RESEARCH_NOTE,
        "example_role": "top_videos",
        "examples": examples,
    }
