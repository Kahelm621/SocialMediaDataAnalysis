"""Labeled sample history so the dashboard renders before any API key exists.

Every row has is_demo true and source "demo". Nothing here is a real stat.
The story is deliberate so the suggestion cards have something to explain:

- KhaosAyngel titles run long, and the keyword often sits at the end.
- Her 18:00 UTC posts earn a higher engagement rate than her 03:00 UTC posts.
- "balatro" and "guess the game" rise across the two weeks. "steam" falls.
- Strange Biology Club titles are already about as long as the sample top videos.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from creator_analytics.explorer import demo_bundle

DEMO_END = datetime(2026, 11, 11, 12, 0, tzinfo=timezone.utc)
DAYS = 15

YOUTUBE_TOP = {
    "guess the game": [
        {"title": "Guess the game in 5 seconds", "author": "QuizGoblin", "views": 900000},
        {"title": "Guess the game: round 12", "author": "ClipQuiz", "views": 640000},
        {"title": "Guess the game #4", "author": "HUDHunter", "views": 410000},
    ],
    "gaming quiz": [
        {"title": "Gaming quiz: 10 frames", "author": "FrameFlash", "views": 280000},
        {"title": "Guess the game by HUD", "author": "HUDHunter", "views": 190000},
    ],
    "steam": [
        {"title": "Steam next fest gems", "author": "DemoDen", "views": 500000},
        {"title": "Steam sale 7 picks", "author": "SaleScout", "views": 320000},
    ],
    "balatro": [
        {"title": "Balatro in 9 minutes", "author": "RunReset", "views": 450000},
        {"title": "Balatro build that clears ante 8", "author": "ChipPath", "views": 260000},
    ],
    "weird biology": [
        {"title": "Weird biology: immortal jellyfish", "author": "BioCurios", "views": 220000},
        {"title": "The animal that never sleeps", "author": "DeepOddities", "views": 180000},
        {"title": "Weird biology in 40 seconds", "author": "LabNotes", "views": 140000},
        {"title": "A parasite that eats a tongue", "author": "OddOrgans", "views": 110000},
    ],
}

# Attention moves in a straight line from the first number to the last.
# Over about a week, balatro and "guess the game" rise past the threshold,
# steam falls past it, and the other two stay nearly flat.
YOUTUBE_ATTENTION = {
    "guess the game": (120000, 168000),
    "gaming quiz": (90000, 96000),
    "steam": (200000, 140000),
    "balatro": (40000, 64000),
    "weird biology": (60000, 63000),
}

X_ATTENTION = {
    "guess the game": (700, 1040),
    "gaming quiz": (400, 420),
    "steam": (1800, 1200),
    "balatro": (300, 480),
    "weird biology": (220, 230),
}

TIKTOK_ATTENTION = {
    "guess the game": (400, 700),
    "gaming quiz": (260, 270),
    "steam": (800, 500),
    "balatro": (180, 300),
    "weird biology": (140, 146),
}

NOTE_YOUTUBE = (
    "DEMO. Combined views of sample top videos, not a live YouTube search. "
    "YouTube does not publish an exact count of videos for a phrase."
)
NOTE_X = "DEMO. Sample recent-post counts, not a live X query."
NOTE_TIKTOK = (
    "DEMO. Sample hashtag view totals. A real run needs TikTok Research API approval. "
    "This project does not scrape TikTok."
)


def collected_times() -> list[datetime]:
    start = DEMO_END - timedelta(days=DAYS - 1)
    return [start + timedelta(days=offset) for offset in range(DAYS)]


def _iso(moment: datetime) -> str:
    return moment.isoformat()


def _attention_series(baseline: int, last: int) -> list[int]:
    if DAYS == 1:
        return [last]
    return [int(round(baseline + (last - baseline) * index / (DAYS - 1))) for index in range(DAYS)]


def _account_row(when: str, platform: str, name: str, handle: str, niche: str, followers: int, total_views: int) -> dict:
    return {
        "record_type": "account",
        "collected_at": when,
        "is_demo": True,
        "source": "demo",
        "platform": platform,
        "account_name": name,
        "account_id": f"demo-{platform}-{name.lower().replace(' ', '-')}",
        "handle": handle,
        "relationship": "own",
        "niche": niche,
        "followers": followers,
        "total_views": total_views,
        "analytics_avg_view_percentage": None,
        "analytics_ctr": None,
    }


STRONG_SEO = {
    "demo-yt-khaos-5",
    "demo-yt-khaos-6",
    "demo-yt-khaos-7",
    "demo-yt-khaos-8",
    "demo-yt-bio-1",
    "demo-yt-bio-3",
}


def _post_row(spec: dict, when: str, views: int) -> dict:
    likes = int(round(views * spec["like_rate"]))
    comments = int(round(views * spec["comment_rate"]))
    shares = None if spec["share_rate"] is None else int(round(views * spec["share_rate"]))
    strong = spec["post_id"] in STRONG_SEO and spec["platform"] == "youtube"
    description = ""
    tags: list[str] = []
    if strong:
        description = (
            f"{spec['title']}\n\n"
            "0:00 Intro\n0:45 The clue\n2:00 The answer\n\n"
            "#guessthegame #weirdbiology"
        )
        tags = ["guess the game", "gaming quiz", "weird biology", "steam"]
    return {
        "record_type": "post",
        "collected_at": when,
        "is_demo": True,
        "source": "demo",
        "platform": spec["platform"],
        "relationship": spec.get("relationship", "own"),
        "account_name": spec["account_name"],
        "niche": spec["niche"],
        "post_id": spec["post_id"],
        "title": spec["title"],
        "description": description,
        "tags": tags,
        "duration_seconds": 480 if spec["platform"] == "youtube" else None,
        "thumbnail": True,
        "url": spec["url"],
        "published_at": spec["published_at"],
        "views": views,
        "likes": likes,
        "comments": comments,
        "shares": shares,
        "views_label": spec["views_label"],
    }


def _posts() -> list[dict]:
    return [
        {
            "platform": "youtube",
            "account_name": "KhaosAyngel",
            "niche": "gaming",
            "post_id": "demo-yt-khaos-1",
            "title": "I cannot believe how long this blurry clip took before I could guess the game",
            "url": "https://www.youtube.com/watch?v=demoKhaos01",
            "published_at": "2026-10-18T03:00:00+00:00",
            "views_start": 800,
            "views_daily": 25,
            "like_rate": 0.012,
            "comment_rate": 0.003,
            "share_rate": None,
            "views_label": "views",
        },
        {
            "platform": "youtube",
            "account_name": "KhaosAyngel",
            "niche": "gaming",
            "post_id": "demo-yt-khaos-2",
            "title": "Four hours later and I still want chat to guess the game with me please",
            "url": "https://www.youtube.com/watch?v=demoKhaos02",
            "published_at": "2026-10-19T03:00:00+00:00",
            "views_start": 1200,
            "views_daily": 30,
            "like_rate": 0.012,
            "comment_rate": 0.003,
            "share_rate": None,
            "views_label": "views",
        },
        {
            "platform": "youtube",
            "account_name": "KhaosAyngel",
            "niche": "gaming",
            "post_id": "demo-yt-khaos-3",
            "title": "This boss theme is stuck in my head so please guess the game from it",
            "url": "https://www.youtube.com/watch?v=demoKhaos03",
            "published_at": "2026-10-20T03:00:00+00:00",
            "views_start": 900,
            "views_daily": 35,
            "like_rate": 0.012,
            "comment_rate": 0.003,
            "share_rate": None,
            "views_label": "views",
        },
        {
            "platform": "youtube",
            "account_name": "KhaosAyngel",
            "niche": "gaming",
            "post_id": "demo-yt-khaos-4",
            "title": "No commentary just audio clues until you finally guess the game",
            "url": "https://www.youtube.com/watch?v=demoKhaos04",
            "published_at": "2026-10-21T03:00:00+00:00",
            "views_start": 1500,
            "views_daily": 40,
            "like_rate": 0.012,
            "comment_rate": 0.003,
            "share_rate": None,
            "views_label": "views",
        },
        {
            "platform": "youtube",
            "account_name": "KhaosAyngel",
            "niche": "gaming",
            "post_id": "demo-yt-khaos-5",
            "title": "Only the map is showing so can you guess the game",
            "url": "https://www.youtube.com/watch?v=demoKhaos05",
            "published_at": "2026-10-22T18:00:00+00:00",
            "views_start": 4000,
            "views_daily": 160,
            "like_rate": 0.055,
            "comment_rate": 0.012,
            "share_rate": None,
            "views_label": "views",
        },
        {
            "platform": "youtube",
            "account_name": "KhaosAyngel",
            "niche": "gaming",
            "post_id": "demo-yt-khaos-6",
            "title": "Ranking steam demos I actually finished this month",
            "url": "https://www.youtube.com/watch?v=demoKhaos06",
            "published_at": "2026-10-24T18:00:00+00:00",
            "views_start": 6200,
            "views_daily": 220,
            "like_rate": 0.055,
            "comment_rate": 0.012,
            "share_rate": None,
            "views_label": "views",
        },
        {
            "platform": "youtube",
            "account_name": "KhaosAyngel",
            "niche": "gaming",
            "post_id": "demo-yt-khaos-7",
            "title": "A gaming quiz for people who skip every cutscene",
            "url": "https://www.youtube.com/watch?v=demoKhaos07",
            "published_at": "2026-10-26T18:00:00+00:00",
            "views_start": 5100,
            "views_daily": 260,
            "like_rate": 0.055,
            "comment_rate": 0.012,
            "share_rate": None,
            "views_label": "views",
        },
        {
            "platform": "youtube",
            "account_name": "KhaosAyngel",
            "niche": "gaming",
            "post_id": "demo-yt-khaos-8",
            "title": "Guess the game before the 30 second timer",
            "url": "https://www.youtube.com/watch?v=demoKhaos08",
            "published_at": "2026-10-28T18:00:00+00:00",
            "views_start": 8400,
            "views_daily": 310,
            "like_rate": 0.055,
            "comment_rate": 0.012,
            "share_rate": None,
            "views_label": "views",
        },
        {
            "platform": "youtube",
            "account_name": "Strange Biology Club",
            "niche": "weird biology",
            "post_id": "demo-yt-bio-1",
            "title": "Weird biology: frog that freezes",
            "url": "https://www.youtube.com/watch?v=demoBio01",
            "published_at": "2026-10-19T15:00:00+00:00",
            "views_start": 2400,
            "views_daily": 90,
            "like_rate": 0.03,
            "comment_rate": 0.008,
            "share_rate": None,
            "views_label": "views",
        },
        {
            "platform": "youtube",
            "account_name": "Strange Biology Club",
            "niche": "weird biology",
            "post_id": "demo-yt-bio-2",
            "title": "The moth that drinks tears",
            "url": "https://www.youtube.com/watch?v=demoBio02",
            "published_at": "2026-10-21T15:00:00+00:00",
            "views_start": 1800,
            "views_daily": 70,
            "like_rate": 0.03,
            "comment_rate": 0.008,
            "share_rate": None,
            "views_label": "views",
        },
        {
            "platform": "youtube",
            "account_name": "Strange Biology Club",
            "niche": "weird biology",
            "post_id": "demo-yt-bio-3",
            "title": "Weird biology: tongue parasite",
            "url": "https://www.youtube.com/watch?v=demoBio03",
            "published_at": "2026-10-23T15:00:00+00:00",
            "views_start": 3100,
            "views_daily": 110,
            "like_rate": 0.03,
            "comment_rate": 0.008,
            "share_rate": None,
            "views_label": "views",
        },
        {
            "platform": "youtube",
            "account_name": "Strange Biology Club",
            "niche": "weird biology",
            "post_id": "demo-yt-bio-4",
            "title": "This shrimp punches really hard",
            "url": "https://www.youtube.com/watch?v=demoBio04",
            "published_at": "2026-10-25T15:00:00+00:00",
            "views_start": 2700,
            "views_daily": 80,
            "like_rate": 0.03,
            "comment_rate": 0.008,
            "share_rate": None,
            "views_label": "views",
        },
        {
            "platform": "youtube",
            "account_name": "Strange Biology Club",
            "niche": "weird biology",
            "post_id": "demo-yt-bio-5",
            "title": "A fish that lives in the dark",
            "url": "https://www.youtube.com/watch?v=demoBio05",
            "published_at": "2026-10-27T15:00:00+00:00",
            "views_start": 2200,
            "views_daily": 75,
            "like_rate": 0.03,
            "comment_rate": 0.008,
            "share_rate": None,
            "views_label": "views",
        },
        {
            "platform": "x",
            "account_name": "AyngelBytes",
            "niche": "gaming",
            "post_id": "demo-x-1",
            "title": "late night steam demo and I am losing",
            "url": "https://x.com/AyngelBytes/status/demo1",
            "published_at": "2026-10-18T01:00:00+00:00",
            "views_start": 600,
            "views_daily": 20,
            "like_rate": 0.01,
            "comment_rate": 0.002,
            "share_rate": 0.001,
            "views_label": "impressions",
        },
        {
            "platform": "x",
            "account_name": "AyngelBytes",
            "niche": "gaming",
            "post_id": "demo-x-2",
            "title": "someone guess the game from this one pixel",
            "url": "https://x.com/AyngelBytes/status/demo2",
            "published_at": "2026-10-20T01:00:00+00:00",
            "views_start": 540,
            "views_daily": 18,
            "like_rate": 0.01,
            "comment_rate": 0.002,
            "share_rate": 0.001,
            "views_label": "impressions",
        },
        {
            "platform": "x",
            "account_name": "AyngelBytes",
            "niche": "gaming",
            "post_id": "demo-x-3",
            "title": "balatro run ended at ante 4 again",
            "url": "https://x.com/AyngelBytes/status/demo3",
            "published_at": "2026-10-22T01:00:00+00:00",
            "views_start": 700,
            "views_daily": 22,
            "like_rate": 0.01,
            "comment_rate": 0.002,
            "share_rate": 0.001,
            "views_label": "impressions",
        },
        {
            "platform": "x",
            "account_name": "AyngelBytes",
            "niche": "gaming",
            "post_id": "demo-x-4",
            "title": "guess the game: chat got it in four replies",
            "url": "https://x.com/AyngelBytes/status/demo4",
            "published_at": "2026-10-23T17:00:00+00:00",
            "views_start": 2400,
            "views_daily": 90,
            "like_rate": 0.04,
            "comment_rate": 0.01,
            "share_rate": 0.008,
            "views_label": "impressions",
        },
        {
            "platform": "x",
            "account_name": "AyngelBytes",
            "niche": "gaming",
            "post_id": "demo-x-5",
            "title": "gaming quiz tonight, soundtrack only",
            "url": "https://x.com/AyngelBytes/status/demo5",
            "published_at": "2026-10-25T17:00:00+00:00",
            "views_start": 2800,
            "views_daily": 100,
            "like_rate": 0.04,
            "comment_rate": 0.01,
            "share_rate": 0.008,
            "views_label": "impressions",
        },
        {
            "platform": "x",
            "account_name": "AyngelBytes",
            "niche": "gaming",
            "post_id": "demo-x-6",
            "title": "steam next fest list is up",
            "url": "https://x.com/AyngelBytes/status/demo6",
            "published_at": "2026-10-27T17:00:00+00:00",
            "views_start": 3100,
            "views_daily": 120,
            "like_rate": 0.04,
            "comment_rate": 0.01,
            "share_rate": 0.008,
            "views_label": "impressions",
        },
        {
            "platform": "tiktok",
            "account_name": "TikTok (sample)",
            "niche": "gaming",
            "post_id": "demo-tt-1",
            "title": "Watch me fail this guess the game until the very last clue finally drops in",
            "url": "https://www.tiktok.com/@yourtiktok/video/demo1",
            "published_at": "2026-10-19T05:00:00+00:00",
            "views_start": 1500,
            "views_daily": 40,
            "like_rate": 0.015,
            "comment_rate": 0.003,
            "share_rate": 0.002,
            "views_label": "views",
        },
        {
            "platform": "tiktok",
            "account_name": "TikTok (sample)",
            "niche": "gaming",
            "post_id": "demo-tt-2",
            "title": "Too many steam demos in one sitting and not nearly enough sleep tonight",
            "url": "https://www.tiktok.com/@yourtiktok/video/demo2",
            "published_at": "2026-10-21T05:00:00+00:00",
            "views_start": 1300,
            "views_daily": 35,
            "like_rate": 0.015,
            "comment_rate": 0.003,
            "share_rate": 0.002,
            "views_label": "views",
        },
        {
            "platform": "tiktok",
            "account_name": "TikTok (sample)",
            "niche": "gaming",
            "post_id": "demo-tt-3",
            "title": "Gaming quiz but I only know the soundtrack",
            "url": "https://www.tiktok.com/@yourtiktok/video/demo3",
            "published_at": "2026-10-24T16:00:00+00:00",
            "views_start": 8000,
            "views_daily": 400,
            "like_rate": 0.035,
            "comment_rate": 0.008,
            "share_rate": 0.006,
            "views_label": "views",
        },
        {
            "platform": "tiktok",
            "account_name": "TikTok (sample)",
            "niche": "gaming",
            "post_id": "demo-tt-4",
            "title": "Can you guess the game from this one messy HUD",
            "url": "https://www.tiktok.com/@yourtiktok/video/demo4",
            "published_at": "2026-10-26T16:00:00+00:00",
            "views_start": 9200,
            "views_daily": 450,
            "like_rate": 0.035,
            "comment_rate": 0.008,
            "share_rate": 0.006,
            "views_label": "views",
        },
    ]


def _keyword_rows(times: list[str]) -> list[dict]:
    rows = []
    hashtags = {
        "guess the game": "guessthegame",
        "gaming quiz": "gamingquiz",
        "steam": "steam",
        "balatro": "balatro",
        "weird biology": "weirdbiology",
    }
    plans = (
        ("youtube", "top_result_views", "top_videos", NOTE_YOUTUBE, YOUTUBE_ATTENTION, True),
        ("x", "recent_post_count", "recent_posts", NOTE_X, X_ATTENTION, False),
        ("tiktok", "research_sample_views", "top_videos", NOTE_TIKTOK, TIKTOK_ATTENTION, False),
    )
    for platform, kind, role, note, table, include_examples in plans:
        for phrase, (baseline, last) in table.items():
            series = _attention_series(baseline, last)
            for index, when in enumerate(times):
                examples = []
                if include_examples and index == len(times) - 1:
                    examples = [
                        {
                            "title": item["title"],
                            "author": item["author"],
                            "views": item["views"],
                            "url": "",
                        }
                        for item in YOUTUBE_TOP[phrase]
                    ]
                rows.append(
                    {
                        "record_type": "keyword",
                        "collected_at": when,
                        "is_demo": True,
                        "source": "demo",
                        "platform": platform,
                        "keyword": phrase,
                        "hashtag": hashtags[phrase],
                        "attention": series[index],
                        "attention_kind": kind,
                        "attention_note": note,
                        "example_role": role,
                        "examples": examples,
                    }
                )
    return rows


def generate() -> dict[str, list[dict]]:
    times = [_iso(moment) for moment in collected_times()]
    accounts = []
    growth = {
        ("youtube", "KhaosAyngel"): (4180, 18, 210000, 1400),
        ("youtube", "Strange Biology Club"): (1820, 22, 96000, 900),
        ("x", "AyngelBytes"): (860, 9, 42000, 300),
        ("tiktok", "TikTok (sample)"): (300, 16, 28000, 700),
    }
    handles = {
        "KhaosAyngel": "KhaosAyngel",
        "Strange Biology Club": "StrangeBiologyClub",
        "AyngelBytes": "AyngelBytes",
        "TikTok (sample)": "yourtiktok",
    }
    niches = {
        "KhaosAyngel": "gaming",
        "Strange Biology Club": "weird biology",
        "AyngelBytes": "gaming",
        "TikTok (sample)": "gaming",
    }
    for index, when in enumerate(times):
        for (platform, name), (followers, follower_step, views, view_step) in growth.items():
            accounts.append(
                _account_row(
                    when,
                    platform,
                    name,
                    handles[name],
                    niches[name],
                    followers + follower_step * index,
                    views + view_step * index,
                )
            )
    posts = []
    for spec in _posts():
        for index, when in enumerate(times):
            views = spec["views_start"] + spec["views_daily"] * index
            posts.append(_post_row(spec, when, views))
    extra = demo_bundle(times)
    accounts.extend(extra["accounts"])
    posts.extend(extra["posts"])
    return {
        "accounts": accounts,
        "posts": posts,
        "keywords": _keyword_rows(times),
        "trending": extra["trending"],
        "research": extra["research"],
    }


def write_demo(directory: Path) -> None:
    """Write sample JSONL into `directory`. Caller must pass the demo folder."""
    payload = generate()
    for rows in payload.values():
        if not rows or not all(row.get("is_demo") is True and row.get("source") == "demo" for row in rows):
            raise RuntimeError("Demo generator produced a row that is not labeled demo.")
    directory.mkdir(parents=True, exist_ok=True)
    for name, rows in payload.items():
        path = directory / f"{name}.jsonl"
        text = "".join(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n" for row in rows)
        path.write_text(text, encoding="utf-8")
