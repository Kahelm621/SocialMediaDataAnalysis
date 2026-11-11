"""Turn snapshots (or labeled demo data) into the static dashboard."""

from __future__ import annotations

import csv
import json
from collections import defaultdict
from datetime import datetime
from pathlib import Path

from creator_analytics.config import load_config
from creator_analytics.explorer import build_explorer
from creator_analytics.metrics import engagement_rate, views_per_day
from creator_analytics.recommendations import (
    build_recommendations,
    title_pattern_block,
)
from creator_analytics.storage import load_rows
from creator_analytics.trends import keyword_changes

TEMPLATE = Path(__file__).with_name("dashboard_template.html")
EXPORT_FIELDS = [
    "engagement",
    "category",
    "likes",
    "shares",
    "comments",
    "views",
    "platform",
    "account",
    "title",
    "date",
    "data_source",
]

DEMO_NOTICE = (
    "These are sample numbers so you can click around before API keys exist. "
    "They are not your real stats. Live collection replaces this whole page; "
    "it does not mix sample rows into real ones."
)

DEMO_SOURCES = [
    {
        "source": "YouTube Data API",
        "account": "KhaosAyngel, Strange Biology Club",
        "state": "demo",
        "detail": "Add secret YOUTUBE_API_KEY for public subscribers, video stats, and keyword search.",
    },
    {
        "source": "X API",
        "account": "AyngelBytes",
        "state": "demo",
        "detail": "Add secret X_BEARER_TOKEN for public post metrics and recent hashtag counts.",
    },
    {
        "source": "TikTok Display API",
        "account": "TikTok",
        "state": "demo",
        "detail": "Optional. Add TIKTOK_ACCESS_TOKEN after app approval. It reads only the account that approved the app.",
    },
    {
        "source": "TikTok Research API",
        "account": "",
        "state": "demo",
        "detail": "Optional. Add TIKTOK_RESEARCH_TOKEN for hashtag queries. This project does not scrape TikTok.",
    },
    {
        "source": "YouTube Analytics API",
        "account": "",
        "state": "demo",
        "detail": "Optional. Add the three OAuth secrets for CTR and average view percentage. Demo data does not invent those private numbers.",
    },
]


def parse_time(value: str) -> datetime:
    text = value.replace("Z", "+00:00")
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        from datetime import timezone

        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def choose_rows(root: Path) -> tuple[list[dict], bool]:
    real = load_rows(root / "data" / "snapshots")
    if any(row.get("is_demo") for row in real):
        raise RuntimeError(
            "data/snapshots contains demo rows. Remove them so sample data is not mixed with real stats."
        )
    if real:
        return real, False
    demo = load_rows(root / "data" / "demo")
    if not demo:
        raise RuntimeError("No snapshots in data/snapshots and no demo data in data/demo.")
    if not all(row.get("is_demo") is True for row in demo):
        raise RuntimeError("data/demo has a row that is not marked is_demo. Refusing to build.")
    return demo, True


def _phrases_for(platform: str, name: str, posts: list[dict], config: dict) -> list[str]:
    for account in config["accounts"]:
        if account["platform"] == platform and account["name"] == name and account["keywords"]:
            return list(account["keywords"])
    niche = next((post.get("niche") for post in posts if post.get("niche")), "")
    phrases = []
    for account in config["accounts"]:
        if niche and account.get("niche") == niche:
            for phrase in account["keywords"]:
                if phrase not in phrases:
                    phrases.append(phrase)
    if phrases:
        return phrases
    return [keyword["phrase"] for keyword in config["keywords"]]


def enrich_posts(posts: list[dict]) -> list[dict]:
    groups = defaultdict(list)
    for post in posts:
        groups[(post.get("platform"), post.get("post_id"))].append(post)
    enriched = []
    for history in groups.values():
        ordered = sorted(history, key=lambda row: row.get("collected_at") or "")
        for index, row in enumerate(ordered):
            window = [
                (parse_time(item["collected_at"]), item.get("views"))
                for item in ordered[: index + 1]
                if item.get("collected_at")
            ]
            pace = views_per_day(window)
            enriched.append(
                {
                    "collected_at": row.get("collected_at"),
                    "platform": row.get("platform"),
                    "account_name": row.get("account_name"),
                    "niche": row.get("niche") or "",
                    "post_id": row.get("post_id"),
                    "title": row.get("title") or "",
                    "url": row.get("url") or "",
                    "published_at": row.get("published_at"),
                    "views": row.get("views"),
                    "likes": row.get("likes"),
                    "comments": row.get("comments"),
                    "shares": row.get("shares"),
                    "views_label": row.get("views_label") or "views",
                    "engagement_rate": engagement_rate(
                        row.get("likes"), row.get("comments"), row.get("shares"), row.get("views")
                    ),
                    "views_per_day": None if pace is None else round(pace, 2),
                }
            )
    return enriched


def _account_catalog(posts: list[dict], accounts: list[dict], config: dict) -> list[dict]:
    handles = {}
    for row in accounts:
        handles[(row.get("platform"), row.get("account_name"))] = row.get("handle") or ""
    catalog = []
    seen = set()
    for post in posts:
        key = (post.get("platform"), post.get("account_name"))
        if key in seen or not key[0] or not key[1]:
            continue
        seen.add(key)
        subset = [item for item in posts if (item.get("platform"), item.get("account_name")) == key]
        catalog.append(
            {
                "platform": key[0],
                "account_name": key[1],
                "niche": post.get("niche") or "",
                "handle": handles.get(key, ""),
                "keywords": _phrases_for(key[0], key[1], subset, config),
            }
        )
    catalog.sort(key=lambda item: (item["platform"], item["account_name"]))
    return catalog


def _keyword_series(rows: list[dict]) -> list[dict]:
    series = []
    for row in rows:
        series.append(
            {
                "collected_at": row.get("collected_at"),
                "platform": row.get("platform"),
                "keyword": row.get("keyword"),
                "hashtag": row.get("hashtag") or "",
                "attention": row.get("attention"),
                "attention_kind": row.get("attention_kind"),
                "attention_note": row.get("attention_note") or "",
            }
        )
    return series


def _latest_examples(rows: list[dict]) -> list[dict]:
    groups = defaultdict(list)
    for row in rows:
        groups[(row.get("platform"), row.get("keyword"))].append(row)
    latest = []
    for items in groups.values():
        newest = sorted(items, key=lambda row: row.get("collected_at") or "")[-1]
        latest.append(
            {
                "platform": newest.get("platform"),
                "keyword": newest.get("keyword"),
                "collected_at": newest.get("collected_at"),
                "example_role": newest.get("example_role"),
                "attention_note": newest.get("attention_note") or "",
                "examples": newest.get("examples") or [],
            }
        )
    return latest


def _account_series(rows: list[dict]) -> list[dict]:
    series = []
    for row in rows:
        series.append(
            {
                "collected_at": row.get("collected_at"),
                "platform": row.get("platform"),
                "account_name": row.get("account_name"),
                "handle": row.get("handle") or "",
                "followers": row.get("followers"),
                "total_views": row.get("total_views"),
                "analytics_avg_view_percentage": row.get("analytics_avg_view_percentage"),
                "analytics_ctr": row.get("analytics_ctr"),
            }
        )
    return series


def build_payload(rows: list[dict], config: dict, is_demo: bool, statuses: list[dict] | None) -> dict:
    posts = [
        row
        for row in rows
        if row.get("record_type") == "post" and row.get("relationship", "own") == "own"
    ]
    accounts = [
        row
        for row in rows
        if row.get("record_type") == "account" and row.get("relationship", "own") == "own"
    ]
    keywords = [row for row in rows if row.get("record_type") == "keyword"]
    enriched = enrich_posts(posts)
    catalog = _account_catalog(posts, accounts, config)
    settings = config["recommendations"]
    phrases = [keyword["phrase"] for keyword in config["keywords"]]
    recommendations = {
        "all": build_recommendations(
            posts,
            keywords,
            phrases=phrases,
            timezone_name=config["timezone"],
            settings=settings,
        )
    }
    patterns = {"all": title_pattern_block(posts, keywords, phrases, settings["keyword_front_chars"])}
    for account in catalog:
        key = f"{account['platform']}::{account['account_name']}"
        subset = [
            row
            for row in posts
            if row.get("platform") == account["platform"] and row.get("account_name") == account["account_name"]
        ]
        recommendations[key] = build_recommendations(
            subset,
            keywords,
            phrases=account["keywords"],
            timezone_name=config["timezone"],
            settings=settings,
        )
        patterns[key] = title_pattern_block(subset, keywords, account["keywords"], settings["keyword_front_chars"])

    stamps = [row.get("collected_at") for row in rows if row.get("collected_at")]
    if statuses is None:
        sources = DEMO_SOURCES if is_demo else [
            {
                "source": "Snapshots",
                "account": "",
                "state": "ok",
                "detail": "Built from data/snapshots. Run python scripts/refresh.py to collect again.",
            }
        ]
    else:
        sources = statuses

    return {
        "is_demo": is_demo,
        "demo_notice": DEMO_NOTICE if is_demo else "",
        "generated_from": max(stamps) if stamps else "",
        "timezone": config["timezone"],
        "accounts": catalog,
        "keywords": phrases,
        "sources": sources,
        "accounts_over_time": _account_series(accounts),
        "posts_over_time": enriched,
        "keywords_over_time": _keyword_series(keywords),
        "keyword_changes": keyword_changes(
            keywords, rising_pct=settings["rising_pct"], falling_pct=settings["falling_pct"]
        ),
        "latest_examples": _latest_examples(keywords),
        "title_patterns": patterns,
        "recommendations": recommendations,
        "thresholds": {
            "rising_pct": settings["rising_pct"],
            "falling_pct": settings["falling_pct"],
            "keyword_front_chars": settings["keyword_front_chars"],
        },
        "explorer": build_explorer(
            rows,
            config,
            keyword_changes(keywords, rising_pct=settings["rising_pct"], falling_pct=settings["falling_pct"]),
        ),
    }


def write_export(path: Path, enriched_posts: list[dict], is_demo: bool) -> None:
    latest = {}
    for row in enriched_posts:
        key = (row["platform"], row["post_id"])
        if key not in latest or (row["collected_at"] or "") > (latest[key]["collected_at"] or ""):
            latest[key] = row
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=EXPORT_FIELDS)
        writer.writeheader()
        for row in sorted(latest.values(), key=lambda item: (item["platform"], item["account_name"], item["title"])):
            parts = [row["likes"], row["comments"], row["shares"]]
            engagement = "" if all(part is None for part in parts) else sum(part or 0 for part in parts)
            writer.writerow(
                {
                    "engagement": engagement,
                    "category": row["niche"] or row["platform"],
                    "likes": "" if row["likes"] is None else row["likes"],
                    "shares": "" if row["shares"] is None else row["shares"],
                    "comments": "" if row["comments"] is None else row["comments"],
                    "views": "" if row["views"] is None else row["views"],
                    "platform": row["platform"],
                    "account": row["account_name"],
                    "title": row["title"],
                    "date": row["published_at"] or "",
                    "data_source": "demo" if is_demo else "live",
                }
            )


def render_html(payload: dict) -> str:
    template = TEMPLATE.read_text(encoding="utf-8")
    encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).replace("<", "\\u003c")
    if "/*__DATA__*/" not in template:
        raise RuntimeError("Dashboard template is missing the data placeholder.")
    return template.replace("/*__DATA__*/", encoded)


def build_dashboard(root: Path, out_dir: Path | None = None, statuses: list[dict] | None = None) -> Path:
    config = load_config(root / "config" / "tracked.yaml")
    rows, is_demo = choose_rows(root)
    payload = build_payload(rows, config, is_demo, statuses)
    destination = out_dir or (root / "dashboard")
    destination.mkdir(parents=True, exist_ok=True)
    (destination / ".nojekyll").write_text("", encoding="utf-8")
    (destination / "data.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (destination / "index.html").write_text(render_html(payload), encoding="utf-8")
    explore_js = Path(__file__).with_name("explore.js")
    if explore_js.exists():
        (destination / "explore.js").write_text(explore_js.read_text(encoding="utf-8"), encoding="utf-8")
    export_path = root / "data" / "exports" / "engagement.csv"
    write_export(export_path, payload["posts_over_time"], is_demo)
    return destination
