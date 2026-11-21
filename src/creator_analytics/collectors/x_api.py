"""X API v2. Public user metrics, recent posts, and hashtag counts."""

from __future__ import annotations

from creator_analytics.http_util import APIError, request_json, safe_int

API = "https://api.x.com/2"
SAMPLE_NOTE = (
    "X did not allow the full counts endpoint, so this is the size of a small recent sample, "
    "not the real volume of the hashtag."
)
COUNT_NOTE = "Recent post count from the X counts endpoint for this hashtag query."


def _headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def parse_user(payload: dict) -> dict:
    user = payload.get("data") or {}
    metrics = user.get("public_metrics") or {}
    return {
        "account_id": user.get("id"),
        "name": user.get("name") or user.get("username"),
        "handle": user.get("username") or "",
        "followers": safe_int(metrics.get("followers_count")),
        "total_views": None,
    }


def parse_tweet(tweet: dict) -> dict:
    metrics = tweet.get("public_metrics") or {}
    retweets = safe_int(metrics.get("retweet_count")) or 0
    quotes = safe_int(metrics.get("quote_count")) or 0
    tweet_id = tweet.get("id")
    return {
        "post_id": tweet_id,
        "title": tweet.get("text") or "",
        "published_at": tweet.get("created_at"),
        "url": f"https://x.com/i/web/status/{tweet_id}" if tweet_id else "",
        "views": safe_int(metrics.get("impression_count")),
        "likes": safe_int(metrics.get("like_count")),
        "comments": safe_int(metrics.get("reply_count")),
        "shares": retweets + quotes,
    }


def collect_account(session, token: str, account: dict, collected_at: str, limit: int) -> tuple[dict, list[dict]]:
    handle = account.get("handle") or account["name"]
    user_payload = request_json(
        session,
        "GET",
        f"{API}/users/by/username/{handle}",
        params={"user.fields": "public_metrics,username,name"},
        headers=_headers(token),
        secrets=[token],
    )
    user = parse_user(user_payload)
    max_results = max(5, min(int(limit), 100))
    tweets_payload = request_json(
        session,
        "GET",
        f"{API}/users/{user['account_id']}/tweets",
        params={
            "max_results": max_results,
            "tweet.fields": "public_metrics,created_at,text",
            "exclude": "retweets,replies",
        },
        headers=_headers(token),
        secrets=[token],
    )
    account_row = {
        "record_type": "account",
        "collected_at": collected_at,
        "is_demo": False,
        "source": "x_api",
        "platform": "x",
        "account_name": account["name"],
        "account_id": user["account_id"],
        "handle": user["handle"] or handle,
        "niche": account.get("niche") or "",
        "followers": user["followers"],
        "total_views": None,
        "analytics_avg_view_percentage": None,
        "analytics_ctr": None,
    }
    posts = []
    for tweet in tweets_payload.get("data") or []:
        parsed = parse_tweet(tweet)
        posts.append(
            {
                "record_type": "post",
                "collected_at": collected_at,
                "is_demo": False,
                "source": "x_api",
                "platform": "x",
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
                "views_label": "impressions",
            }
        )
    return account_row, posts


def _denied(exc: APIError) -> bool:
    text = str(exc)
    return text.startswith("401") or text.startswith("403") or "Forbidden" in text


def collect_keyword(session, token: str, keyword: dict, collected_at: str) -> dict:
    query = f"#{keyword['hashtag']}" if keyword.get("hashtag") else keyword["phrase"]
    base = {
        "record_type": "keyword",
        "collected_at": collected_at,
        "is_demo": False,
        "source": "x_api",
        "platform": "x",
        "keyword": keyword["phrase"],
        "hashtag": keyword.get("hashtag") or "",
        "example_role": "recent_posts",
    }
    try:
        payload = request_json(
            session,
            "GET",
            f"{API}/tweets/counts/recent",
            params={"query": query, "granularity": "day"},
            headers=_headers(token),
            secrets=[token],
        )
        total = (payload.get("meta") or {}).get("total_tweet_count")
        if total is None:
            total = sum(safe_int(bucket.get("tweet_count")) or 0 for bucket in payload.get("data") or [])
        return {
            **base,
            "attention": total,
            "attention_kind": "recent_post_count",
            "attention_note": COUNT_NOTE,
            "examples": [],
        }
    except APIError as exc:
        if not _denied(exc):
            raise
    search = request_json(
        session,
        "GET",
        f"{API}/tweets/search/recent",
        params={"query": query, "max_results": 10, "tweet.fields": "public_metrics,created_at,text"},
        headers=_headers(token),
        secrets=[token],
    )
    examples = []
    for tweet in search.get("data") or []:
        parsed = parse_tweet(tweet)
        examples.append(
            {
                "title": parsed["title"],
                "author": "",
                "views": parsed["views"],
                "url": parsed["url"],
            }
        )
    return {
        **base,
        "attention": len(examples),
        "attention_kind": "recent_sample",
        "attention_note": SAMPLE_NOTE,
        "examples": examples,
    }
