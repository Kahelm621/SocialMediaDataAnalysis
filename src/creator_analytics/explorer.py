"""Turn raw snapshot rows into the YouTube-wide explorer.

Demo trending and keyword-research rows are built here too, with the same
scoring functions the live collector uses.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, timezone
from statistics import median

from creator_analytics.quota import quota_plan
from creator_analytics.scoring import (
    find_outliers,
    is_short,
    lifetime_views_per_hour,
    rising_terms,
    score_opportunity,
    score_video,
    snapshot_views_per_hour,
    term_counts,
    title_features,
)

PACE_NOTE = (
    "Lifetime pace is views divided by hours since the video was published. "
    "Snapshot pace is the view change between the last two saves, divided by the hours between them. "
    "Neither one is a live views-per-hour counter."
)
SHORTS_NOTE = "A Short here means a duration of 60 seconds or less. Videos with no duration are left out of the share."


def _latest_map(rows: list[dict], key_fn) -> list[dict]:
    chosen = {}
    for row in rows:
        key = key_fn(row)
        if key not in chosen or (row.get("collected_at") or "") > (chosen[key].get("collected_at") or ""):
            chosen[key] = row
    return list(chosen.values())


def _earlier_stamp(stamps: list[str]) -> str | None:
    if len(stamps) < 2:
        return None
    latest = datetime.fromisoformat(stamps[-1])
    target = latest - timedelta(days=7)
    chosen = stamps[-2]
    for stamp in stamps[:-1]:
        if datetime.fromisoformat(stamp) <= target:
            chosen = stamp
    return chosen


def _streak(stamps: list[str]) -> int:
    if not stamps:
        return 0
    moments = [datetime.fromisoformat(stamp) for stamp in stamps]
    run = 1
    for earlier, later in zip(reversed(moments[:-1]), reversed(moments[1:])):
        if (later - earlier) <= timedelta(hours=36):
            run += 1
        else:
            break
    return run


def _slim_trending(row: dict, days_on_chart: int, streak: int, snapshot_pace) -> dict:
    duration = row.get("duration_seconds")
    return {
        "collected_at": row.get("collected_at"),
        "region": row.get("region"),
        "category_id": row.get("category_id") or "0",
        "category_name": row.get("category_name") or "All categories",
        "post_id": row.get("post_id"),
        "title": row.get("title") or "",
        "channel_title": row.get("channel_title") or "",
        "channel_id": row.get("channel_id") or "",
        "published_at": row.get("published_at"),
        "views": row.get("views"),
        "likes": row.get("likes"),
        "duration_seconds": duration,
        "is_short": is_short(duration),
        "tags": (row.get("tags") or [])[:8],
        "lifetime_views_per_hour": _round(
            lifetime_views_per_hour(row.get("views"), row.get("published_at"), row.get("collected_at"))
        ),
        "snapshot_views_per_hour": _round(snapshot_pace),
        "days_on_chart": days_on_chart,
        "streak": streak,
        "url": row.get("url") or "",
    }


def _round(value):
    if value is None:
        return None
    return round(float(value), 2)


def _trending_summary(rows: list[dict]) -> dict:
    grouped: dict[tuple, list[dict]] = defaultdict(list)
    for row in rows:
        grouped[(row.get("region"), row.get("category_id") or "0", row.get("post_id"))].append(row)
    latest_rows = []
    for history in grouped.values():
        ordered = sorted(history, key=lambda item: item.get("collected_at") or "")
        stamps = [item["collected_at"] for item in ordered if item.get("collected_at")]
        pace = snapshot_views_per_hour([(item.get("collected_at"), item.get("views")) for item in ordered])
        latest_rows.append(_slim_trending(ordered[-1], len(set(stamps)), _streak(stamps), pace))

    pattern_rows = []
    shorts_rows = []
    buckets: dict[tuple, list[dict]] = defaultdict(list)
    for row in rows:
        buckets[(row.get("collected_at"), row.get("region"), row.get("category_id") or "0")].append(row)
    for (stamp, region, category_id), videos in sorted(buckets.items()):
        features = title_features([video.get("title") or "" for video in videos])
        pattern_rows.append(
            {
                "collected_at": stamp,
                "region": region,
                "category_id": category_id,
                "median_chars": features["median_chars"],
                "pct_number": features["pct_number"],
                "pct_caps": features["pct_caps"],
                "pct_emoji": features["pct_emoji"],
                "pct_question": features["pct_question"],
                "count": features["count"],
            }
        )
        known = [video for video in videos if is_short(video.get("duration_seconds")) is not None]
        shorts = [video for video in known if is_short(video.get("duration_seconds"))]
        shorts_rows.append(
            {
                "collected_at": stamp,
                "region": region,
                "category_id": category_id,
                "short_count": len(shorts),
                "long_count": len(known) - len(shorts),
                "short_share": None if not known else len(shorts) / len(known),
            }
        )

    by_chart: dict[tuple, list[dict]] = defaultdict(list)
    for row in rows:
        by_chart[(row.get("region"), row.get("category_id") or "0")].append(row)
    topics = []
    top_channels = []
    for (region, category_id), videos in by_chart.items():
        stamps = sorted({video.get("collected_at") for video in videos if video.get("collected_at")})
        latest_stamp = stamps[-1] if stamps else None
        earlier = _earlier_stamp(stamps) if stamps else None
        current_videos = [video for video in videos if video.get("collected_at") == latest_stamp]
        previous_videos = [video for video in videos if video.get("collected_at") == earlier]
        for item in rising_terms(term_counts(current_videos), term_counts(previous_videos)):
            topics.append({"region": region, "category_id": category_id, **item})
        channel_counts: dict[str, int] = {}
        for video in current_videos:
            name = video.get("channel_title") or "Unknown"
            channel_counts[name] = channel_counts.get(name, 0) + 1
        ranked = sorted(channel_counts.items(), key=lambda item: item[1], reverse=True)[:8]
        for name, appearances in ranked:
            top_channels.append(
                {
                    "region": region,
                    "category_id": category_id,
                    "channel_title": name,
                    "appearances": appearances,
                }
            )
    return {
        "videos": latest_rows,
        "title_patterns_over_time": pattern_rows,
        "shorts_over_time": shorts_rows,
        "topics": topics,
        "top_channels": top_channels,
        "pace_note": PACE_NOTE,
        "shorts_note": SHORTS_NOTE,
    }


def _research_summary(rows: list[dict]) -> list[dict]:
    grouped: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        grouped[row.get("keyword") or ""].append(row)
    slim = []
    for items in grouped.values():
        ordered = sorted(items, key=lambda item: item.get("collected_at") or "")
        latest_stamp = ordered[-1].get("collected_at")
        for item in ordered:
            latest = item.get("collected_at") == latest_stamp
            slim.append(
                {
                    "collected_at": item.get("collected_at"),
                    "keyword": item.get("keyword"),
                    "opportunity_score": item.get("opportunity_score"),
                    "demand_score": item.get("demand_score"),
                    "competition_score": item.get("competition_score"),
                    "median_views": item.get("median_views"),
                    "median_subscribers": item.get("median_subscribers"),
                    "suggestion_count": item.get("suggestion_count"),
                    "strong_results": item.get("strong_results"),
                    "top_result_count": item.get("top_result_count"),
                    "search_total_results": item.get("search_total_results"),
                    "formula": item.get("formula") or "",
                    "suggestion_note": item.get("suggestion_note") or "",
                    "suggestions": item.get("suggestions") or [] if latest else [],
                    "examples": item.get("examples") or [] if latest else [],
                }
            )
    return slim


def _seo_and_audit(posts: list[dict], accounts: list[dict], keywords_by_account: dict, front_chars: int) -> tuple[list, list]:
    latest_posts = _latest_map(
        [post for post in posts if post.get("relationship", "own") == "own" and post.get("platform") == "youtube"],
        lambda post: (post.get("account_name"), post.get("post_id")),
    )
    seo_rows = []
    for post in latest_posts:
        keywords = keywords_by_account.get(post.get("account_name"), [])
        scored = score_video(post, keywords, front_chars)
        seo_rows.append(
            {
                "account_name": post.get("account_name"),
                "post_id": post.get("post_id"),
                "title": post.get("title") or "",
                "url": post.get("url") or "",
                "score": scored["score"],
                "checks": scored["checks"],
            }
        )
    seo_rows.sort(key=lambda row: (row["account_name"] or "", row["score"]))
    latest_accounts = _latest_map(
        [row for row in accounts if row.get("relationship", "own") == "own" and row.get("platform") == "youtube"],
        lambda row: row.get("account_name"),
    )
    audits = []
    for account in latest_accounts:
        name = account.get("account_name")
        mine = [row for row in latest_posts if row.get("account_name") == name and row.get("published_at")]
        published = sorted(row["published_at"] for row in mine)
        gap = None
        if len(published) >= 2:
            moments = [datetime.fromisoformat(stamp) for stamp in published]
            gaps = [(later - earlier).total_seconds() / 86400 for earlier, later in zip(moments, moments[1:])]
            gap = round(median(gaps), 1)
        scores = [row["score"] for row in seo_rows if row["account_name"] == name]
        average = None if not scores else round(sum(scores) / len(scores), 1)
        weakest = None
        missed: dict[str, int] = {}
        for row in seo_rows:
            if row["account_name"] != name:
                continue
            for check in row["checks"]:
                if not check["ok"]:
                    missed[check["name"]] = missed.get(check["name"], 0) + 1
        if missed:
            weakest = max(missed.items(), key=lambda item: item[1])
        top = max(mine, key=lambda row: row.get("views") or 0) if mine else None
        audits.append(
            {
                "account_name": name,
                "followers": account.get("followers"),
                "total_views": account.get("total_views"),
                "videos_in_snapshot": len(mine),
                "average_seo": average,
                "weakest_check": None if weakest is None else {"name": weakest[0], "videos": weakest[1]},
                "median_days_between_uploads": gap,
                "top_title": None if top is None else top.get("title"),
                "top_views": None if top is None else top.get("views"),
            }
        )
    return seo_rows, audits


def _competitor_summary(posts: list[dict], accounts: list[dict]) -> list[dict]:
    latest_accounts = _latest_map(
        [row for row in accounts if row.get("relationship") == "competitor"],
        lambda row: row.get("account_name"),
    )
    latest_posts = _latest_map(
        [row for row in posts if row.get("relationship") == "competitor"],
        lambda row: (row.get("account_name"), row.get("post_id")),
    )
    summaries = []
    for account in latest_accounts:
        name = account.get("account_name")
        videos = [row for row in latest_posts if row.get("account_name") == name]
        published = sorted(row["published_at"] for row in videos if row.get("published_at"))
        gap = None
        if len(published) >= 2:
            moments = [datetime.fromisoformat(stamp) for stamp in published]
            gaps = [(later - earlier).total_seconds() / 86400 for earlier, later in zip(moments, moments[1:])]
            gap = round(median(gaps), 1)
        top = max(videos, key=lambda row: row.get("views") or 0) if videos else None
        history = sorted(
            (row for row in accounts if row.get("relationship") == "competitor" and row.get("account_name") == name),
            key=lambda row: row.get("collected_at") or "",
        )
        summaries.append(
            {
                "account_name": name,
                "niche": account.get("niche") or "",
                "followers": account.get("followers"),
                "total_views": account.get("total_views"),
                "median_days_between_uploads": gap,
                "top_title": None if top is None else top.get("title"),
                "top_views": None if top is None else top.get("views"),
                "followers_over_time": [
                    {"collected_at": row.get("collected_at"), "followers": row.get("followers")} for row in history
                ],
            }
        )
    return summaries


def _ideas(changes: list[dict], outliers: list[dict], topics: list[dict]) -> list[dict]:
    ideas = []
    rising = [row for row in changes if row.get("platform") == "youtube" and row.get("label") == "rising"]
    for row in rising[:3]:
        pct = row.get("pct_change")
        ideas.append(
            {
                "headline": f"Make the next video about '{row['keyword']}'",
                "why": (
                    f"On YouTube, '{row['keyword']}' moved {None if pct is None else round(pct, 1)}% "
                    f"({row.get('previous')} to {row.get('current')}) versus the earlier snapshot. "
                    "That number is combined views of the top search results, not search volume."
                ),
                "try_this": f"Put '{row['keyword']}' in the first 40 characters of the title, then again in the first lines of the description.",
            }
        )
    for row in outliers[:2]:
        ideas.append(
            {
                "headline": f"Study '{row['title']}'",
                "why": row["note"],
                "try_this": "Look at that title's length, whether it asks a question, and where the keyword sits. Borrow the pattern, not the footage.",
            }
        )
    fresh_topics = [row for row in topics if row.get("label") in {"rising", "new"}]
    for row in fresh_topics[:2]:
        ideas.append(
            {
                "headline": f"Trending wording: '{row['term']}'",
                "why": (
                    f"In {row.get('region')} / category {row.get('category_id')}, "
                    f"'{row['term']}' shows up in {row['current']} trending titles or tags now "
                    f"and {row['previous']} in the earlier snapshot."
                ),
                "try_this": "Use the wording only if the video is actually about it. This count is titles on the most-popular chart, not a search-volume rank.",
            }
        )
    if not ideas:
        ideas.append(
            {
                "headline": "No breakout idea in this snapshot",
                "why": "Nothing on the watchlist rose, and no sampled video cleared the outlier bar.",
                "try_this": "Add a game name or niche phrase to the keyword list, or enable a competitor channel, then collect again.",
            }
        )
    return ideas


def build_explorer(rows: list[dict], config: dict, keyword_changes: list[dict]) -> dict:
    posts = [row for row in rows if row.get("record_type") == "post"]
    accounts = [row for row in rows if row.get("record_type") == "account"]
    trending = [row for row in rows if row.get("record_type") == "trending_video"]
    research = [row for row in rows if row.get("record_type") == "keyword_research"]
    keywords_by_account = {}
    for account in config["accounts"]:
        if account["platform"] == "youtube":
            keywords_by_account[account["name"]] = account["keywords"] or [
                item["phrase"] for item in config["keywords"]
            ]
    front = config["recommendations"]["keyword_front_chars"]
    seo_rows, audits = _seo_and_audit(posts, accounts, keywords_by_account, front)
    multiplier = config["youtube_quota"]["outlier_multiplier"]
    outliers = find_outliers(
        posts,
        relationships={"competitor", "channel_sample", "own"},
        multiplier=multiplier,
    )
    summary = _trending_summary(trending)
    plan = quota_plan(config)
    return {
        "quota": plan,
        "regions": config["trending"]["regions"],
        "categories": config["trending"]["categories"],
        "trending": summary["videos"],
        "title_patterns_over_time": summary["title_patterns_over_time"],
        "shorts_over_time": summary["shorts_over_time"],
        "topics": summary["topics"],
        "top_channels": summary["top_channels"],
        "pace_note": summary["pace_note"],
        "shorts_note": summary["shorts_note"],
        "research": _research_summary(research),
        "outliers": outliers,
        "ideas": _ideas(keyword_changes, outliers, summary["topics"]),
        "video_seo": seo_rows,
        "audit": audits,
        "competitors": _competitor_summary(posts, accounts),
    }


def demo_bundle(times: list[str]) -> dict[str, list[dict]]:
    """Labeled sample rows for the explorer. Scores use score_opportunity, not hand-written totals."""
    trending = _demo_trending(times)
    research = _demo_research(times)
    accounts, posts = _demo_competitors(times)
    return {"trending": trending, "research": research, "accounts": accounts, "posts": posts}


def _demo_trending(times: list[str]) -> list[dict]:
    catalog = [
        ("US", "0", "All categories", "t-us-all-1", "Guess the game in 5 seconds?", "QuizGoblin", 48, 800000, 20000, "all", ["guess the game", "shorts"]),
        ("US", "0", "All categories", "t-us-all-2", "Why this jellyfish never dies", "BioCurios", 480, 420000, 8000, "all", ["jellyfish", "weird biology"]),
        ("US", "0", "All categories", "t-us-all-3", "THIS BOSS IS UNFAIR", "HUDHunter", 720, 510000, 4000, "early", []),
        ("US", "0", "All categories", "t-us-all-4", "Wait what? 🔥", "ClipQuiz", 55, 260000, 30000, "late", ["shorts"]),
        ("US", "20", "Gaming", "t-us-game-1", "Guess the game in 5 seconds?", "QuizGoblin", 48, 900000, 25000, "all", ["guess the game", "gaming quiz"]),
        ("US", "20", "Gaming", "t-us-game-2", "I survived day 100", "RunReset", 1100, 300000, 6000, "all", ["guess the game", "balatro", "day 100"]),
        ("US", "20", "Gaming", "t-us-game-3", "Balatro roulette build is broken", "ChipPath", 860, 180000, 22000, "late", ["balatro"]),
        ("US", "20", "Gaming", "t-us-game-4", "New update guide", "DemoDen", 640, 150000, 2000, "early", ["update"]),
        ("US", "28", "Science & Technology", "t-us-sci-1", "Why this jellyfish never dies", "BioCurios", 480, 220000, 5000, "all", ["jellyfish", "weird biology"]),
        ("US", "28", "Science & Technology", "t-us-sci-2", "The shrimp that punches at 50 mph", "OddOrgans", 360, 140000, 3000, "all", ["shrimp"]),
        ("US", "28", "Science & Technology", "t-us-sci-3", "A 4 minute tour of a cell", "LabNotes", 240, 90000, 2500, "all", ["weird biology", "cell"]),
        ("US", "28", "Science & Technology", "t-us-sci-4", "Science wait what?", "DeepOddities", 50, 70000, 12000, "late", ["shorts"]),
        ("GB", "0", "All categories", "t-gb-1", "Guess the game: round 12", "QuizGoblin", 600, 240000, 6000, "all", ["guess the game"]),
        ("GB", "0", "All categories", "t-gb-2", "Steam sale 7 picks", "SaleScout", 900, 180000, 3000, "all", ["steam"]),
        ("GB", "0", "All categories", "t-gb-3", "Weird biology in 40 seconds", "LabNotes", 40, 60000, 4000, "late", ["weird biology"]),
    ]
    end = datetime.fromisoformat(times[-1])
    rows = []
    for index, stamp in enumerate(times):
        for region, category_id, category_name, post_id, title, channel, duration, start, daily, span, tags in catalog:
            if span == "early" and index > 7:
                continue
            if span == "late" and index < len(times) - 4:
                continue
            published = (end - timedelta(days=20)).isoformat()
            rows.append(
                {
                    "record_type": "trending_video",
                    "collected_at": stamp,
                    "is_demo": True,
                    "source": "demo",
                    "platform": "youtube",
                    "region": region,
                    "category_id": category_id,
                    "category_name": category_name,
                    "post_id": post_id,
                    "title": title,
                    "channel_title": channel,
                    "channel_id": f"demo-{channel.lower()}",
                    "published_at": published,
                    "views": start + daily * index,
                    "likes": int((start + daily * index) * 0.04),
                    "duration_seconds": duration,
                    "tags": tags,
                    "url": f"https://www.youtube.com/watch?v={post_id}",
                }
            )
    return rows


def _demo_research(times: list[str]) -> list[dict]:
    plans = {
        "guess the game": (80000, 150000, 250000, ["guess the game", "guess the game in 5 seconds", "guess the game 2026"]),
        "gaming quiz": (70000, 76000, 180000, ["gaming quiz", "gaming quiz questions"]),
        "steam": (180000, 90000, 400000, ["steam", "steam sale", "steam next fest"]),
        "weird biology": (40000, 48000, 35000, ["weird biology", "weird biology facts"]),
        "balatro": (30000, 90000, 80000, ["balatro", "balatro build", "balatro seed"]),
    }
    rows = []
    last = times[-1]
    steps = max(1, len(times) - 1)
    for phrase, (start_views, end_views, subscribers, suggestions) in plans.items():
        for index, stamp in enumerate(times):
            median_views = start_views + (end_views - start_views) * index / steps
            strong = max(1, min(8, round(8 * min(median_views, 200000) / 200000)))
            scored = score_opportunity(
                suggestion_count=len(suggestions),
                median_views=median_views,
                median_subscribers=subscribers,
                strong_results=strong,
                top_result_count=8,
                strong_view_threshold=100000,
            )
            rows.append(
                {
                    "record_type": "keyword_research",
                    "collected_at": stamp,
                    "is_demo": True,
                    "source": "demo",
                    "platform": "youtube",
                    "keyword": phrase,
                    "suggestion_count": len(suggestions),
                    "suggestions": suggestions if stamp == last else [],
                    "suggestion_note": (
                        "DEMO sample autocomplete strings, not a live suggest call and not search volume."
                    ),
                    "search_total_results": None,
                    "median_views": round(median_views),
                    "median_subscribers": subscribers,
                    "strong_results": strong,
                    "top_result_count": 8,
                    "examples": []
                    if stamp != last
                    else [
                        {
                            "title": suggestions[0],
                            "author": "Sample channel",
                            "views": round(median_views),
                            "subscribers": subscribers,
                        }
                    ],
                    **scored,
                }
            )
    return rows


def _demo_competitors(times: list[str]) -> tuple[list[dict], list[dict]]:
    channels = [
        ("QuizGoblin", "gaming", 520000, 1800),
        ("BioCurios", "weird biology", 140000, 900),
    ]
    videos = [
        ("QuizGoblin", "comp-quiz-1", "Guess the game in one frame", 12000, 400, "2026-10-20T20:00:00+00:00"),
        ("QuizGoblin", "comp-quiz-2", "Five HUD clues", 9000, 250, "2026-10-22T20:00:00+00:00"),
        ("QuizGoblin", "comp-quiz-3", "Chat guesses the boss", 11000, 300, "2026-10-25T21:00:00+00:00"),
        ("QuizGoblin", "comp-quiz-4", "Only 1% saw the logo", 140000, 6000, "2026-10-28T20:00:00+00:00"),
        ("BioCurios", "comp-bio-1", "Weird biology: immortal jellyfish", 8000, 200, "2026-10-19T15:00:00+00:00"),
        ("BioCurios", "comp-bio-2", "A moth that drinks tears", 7000, 180, "2026-10-22T15:00:00+00:00"),
        ("BioCurios", "comp-bio-3", "The frozen frog", 7500, 160, "2026-10-24T16:00:00+00:00"),
        ("BioCurios", "comp-bio-4", "This shrimp punches through glass", 60000, 2500, "2026-10-27T15:00:00+00:00"),
    ]
    accounts = []
    posts = []
    for index, stamp in enumerate(times):
        for name, niche, followers, step in channels:
            accounts.append(
                {
                    "record_type": "account",
                    "collected_at": stamp,
                    "is_demo": True,
                    "source": "demo",
                    "platform": "youtube",
                    "relationship": "competitor",
                    "account_name": name,
                    "account_id": f"demo-{name.lower()}",
                    "handle": name,
                    "niche": niche,
                    "followers": followers + step * index,
                    "total_views": None,
                    "analytics_avg_view_percentage": None,
                    "analytics_ctr": None,
                }
            )
        for name, post_id, title, start, daily, published in videos:
            views = start + daily * index
            posts.append(
                {
                    "record_type": "post",
                    "collected_at": stamp,
                    "is_demo": True,
                    "source": "demo",
                    "platform": "youtube",
                    "relationship": "competitor",
                    "account_name": name,
                    "niche": "gaming" if name == "QuizGoblin" else "weird biology",
                    "post_id": post_id,
                    "title": title,
                    "url": f"https://www.youtube.com/watch?v={post_id}",
                    "published_at": published,
                    "views": views,
                    "likes": int(views * 0.05),
                    "comments": int(views * 0.005),
                    "shares": None,
                    "views_label": "views",
                    "description": "",
                    "tags": [],
                    "duration_seconds": 600,
                    "thumbnail": True,
                }
            )
    return accounts, posts
