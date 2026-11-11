"""Scores and pattern math.

Every number here is computed from fields we actually stored. YouTube does not
provide real search volume or a live views-per-hour counter, so those names
are not used for these estimates.
"""

from __future__ import annotations

import math
import re
from datetime import datetime, timezone

from creator_analytics.trends import keyword_in_front

EMOJI = re.compile(
    "["
    "\U0001F300-\U0001FAFF"
    "\u2600-\u27BF"
    "]"
)
STOPWORDS = {
    "the", "and", "for", "you", "your", "with", "this", "that", "from", "have",
    "just", "what", "when", "how", "why", "are", "was", "were", "its", "it's",
    "but", "not", "all", "can", "out", "new", "off", "into", "about", "than",
    "then", "them", "they", "she", "his", "her", "who", "will", "got", "get",
    "video", "videos", "watch", "official",
}


def parse_iso_duration(value: str | None) -> int | None:
    """YouTube contentDetails.duration, for example PT1H2M3S or PT45S."""
    if not value:
        return None
    match = re.fullmatch(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", value)
    if not match:
        return None
    hours, minutes, seconds = (int(part or 0) for part in match.groups())
    return hours * 3600 + minutes * 60 + seconds


def is_short(duration_seconds: int | None) -> bool | None:
    """Shorts are treated as 60 seconds or less. None if we were not given a duration."""
    if duration_seconds is None:
        return None
    return duration_seconds <= 60


def _moment(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def lifetime_views_per_hour(views, published_at, collected_at) -> float | None:
    """Views divided by hours since publish.

    This is a lifetime pace. It is not the views gained in the last hour.
    """
    if views is None or not published_at or not collected_at:
        return None
    hours = (_moment(collected_at) - _moment(published_at)).total_seconds() / 3600
    if hours <= 0:
        return None
    return views / hours


def snapshot_views_per_hour(history: list[tuple[str, int | None]]) -> float | None:
    """View change between the last two snapshots, divided by the hours between them."""
    points = [(stamp, views) for stamp, views in history if views is not None and stamp]
    points.sort(key=lambda item: item[0])
    if len(points) < 2:
        return None
    (earlier, earlier_views), (later, later_views) = points[-2], points[-1]
    hours = (_moment(later) - _moment(earlier)).total_seconds() / 3600
    if hours <= 0:
        return None
    return (later_views - earlier_views) / hours


def _log_score(value, cap: float) -> float:
    if value is None or value <= 0 or cap <= 0:
        return 0.0
    return max(0.0, min(100.0, 100.0 * math.log10(1 + value) / math.log10(1 + cap)))


def score_opportunity(
    *,
    suggestion_count: int | None,
    median_views: float | None,
    median_subscribers: float | None,
    strong_results: int,
    top_result_count: int,
    strong_view_threshold: int,
) -> dict:
    """Transparent 0-100 opportunity estimate.

    Demand leans on the median views of the top search results (people are
    watching this phrase) plus a smaller nudge from how many autocomplete
    suggestions came back. Competition leans on how big those channels are
    and what share of the results already have a lot of views.
    """
    views_score = _log_score(median_views, 1_000_000)
    if suggestion_count is None:
        demand = views_score
    else:
        demand = views_score * 0.75 + _log_score(suggestion_count, 13) * 0.25
    strong_share = 0.0 if not top_result_count else strong_results / top_result_count
    competition = 0.5 * _log_score(median_subscribers, 1_000_000) + 0.5 * (strong_share * 100)
    opportunity = demand * (100 - competition) / 100
    return {
        "demand_score": round(demand, 1),
        "competition_score": round(competition, 1),
        "opportunity_score": round(opportunity, 1),
        "strong_share": round(strong_share, 3),
        "strong_view_threshold": strong_view_threshold,
        "formula": (
            "Estimate. YouTube does not publish search volume. "
            "Demand is a 0-100 log score of the median views among the top results "
            "(100 means around 1,000,000 views), with 25% of the blend coming from "
            "how many autocomplete suggestions returned when that list exists. "
            "Competition is half the log score of those channels' median subscribers "
            "and half the share of results at or above "
            f"{strong_view_threshold:,} views. "
            "Opportunity = demand × (100 − competition) / 100."
        ),
    }


def _check(name: str, ok: bool, possible: int, fix: str) -> dict:
    return {
        "name": name,
        "earned": possible if ok else 0,
        "possible": possible,
        "ok": bool(ok),
        "fix": "" if ok else fix,
    }


def score_video(video: dict, keywords: list[str], front_chars: int = 40) -> dict:
    """Point score for a public video. Each miss includes a fix written from that check."""
    title = video.get("title") or ""
    description = video.get("description") or ""
    tags = [str(tag) for tag in (video.get("tags") or []) if str(tag).strip()]
    length = len(title)
    hashtags = re.findall(r"#\w+", description)
    title_words = {word.casefold() for word in re.findall(r"[A-Za-z0-9']{3,}", title)}
    tag_words = {word.casefold() for tag in tags for word in re.findall(r"[A-Za-z0-9']{3,}", tag)}
    chapters = re.search(r"(?m)(?:^|\s)\d{1,2}:\d{2}\b", description) is not None
    checks = [
        _check(
            "Title length",
            40 <= length <= 70,
            15,
            f"This title is {length} characters. A useful range here is 40 to 70: long enough to be specific, short enough for a feed.",
        ),
        _check(
            "Keyword in the first 40 characters",
            bool(keywords) and keyword_in_front(title, keywords, front_chars),
            20,
            "Move one of your tracked phrases into the first 40 characters of the title.",
        ),
        _check(
            "Description opening",
            len(description.strip()) >= 80,
            15,
            "Write at least a short paragraph. The first lines are the part people and search see.",
        ),
        _check(
            "Keyword in the description opening",
            bool(keywords) and keyword_in_front(description, keywords, 160),
            15,
            "Repeat the phrase in the first lines of the description.",
        ),
        _check(
            "Tag count",
            3 <= len(tags) <= 15,
            10,
            "Use 3 to 15 tags. The public API only returns tags the channel chose to set.",
        ),
        _check(
            "Tags overlap the title",
            bool(title_words & tag_words),
            10,
            "Reuse the important words from the title as tags.",
        ),
        _check(
            "Chapters",
            chapters,
            10,
            "Add timestamp lines such as '0:00 Intro' if the video has sections. YouTube can turn those into chapters.",
        ),
        _check(
            "Hashtags",
            1 <= len(hashtags) <= 15,
            5,
            "Add between 1 and 15 hashtags in the description. The first three can show above the title. More than 15 and YouTube ignores all of them.",
        ),
    ]
    earned = sum(item["earned"] for item in checks)
    possible = sum(item["possible"] for item in checks)
    return {
        "score": round(100 * earned / possible) if possible else 0,
        "earned": earned,
        "possible": possible,
        "checks": checks,
    }


def title_features(titles: list[str]) -> dict:
    cleaned = [title.strip() for title in titles if title and title.strip()]
    count = len(cleaned)
    if not count:
        return {
            "count": 0,
            "median_chars": None,
            "pct_number": None,
            "pct_caps": None,
            "pct_emoji": None,
            "pct_question": None,
        }
    lengths = sorted(len(title) for title in cleaned)
    mid = count // 2
    median_chars = lengths[mid] if count % 2 else (lengths[mid - 1] + lengths[mid]) / 2

    def share(predicate) -> float:
        return sum(1 for title in cleaned if predicate(title)) / count

    def mostly_caps(title: str) -> bool:
        letters = [char for char in title if char.isalpha()]
        if len(letters) < 4:
            return False
        return sum(char.isupper() for char in letters) / len(letters) >= 0.6

    return {
        "count": count,
        "median_chars": median_chars,
        "pct_number": share(lambda title: re.search(r"\d", title) is not None),
        "pct_caps": share(mostly_caps),
        "pct_emoji": share(lambda title: EMOJI.search(title) is not None),
        "pct_question": share(lambda title: "?" in title),
    }


def term_counts(videos: list[dict]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for video in videos:
        tags = " ".join(video.get("tags") or [])
        tokens = re.findall(r"[a-z0-9']{3,}", f"{video.get('title') or ''} {tags}".casefold())
        words = [token for token in tokens if token not in STOPWORDS]
        seen = set(words)
        seen.update(f"{left} {right}" for left, right in zip(words, words[1:]))
        for term in seen:
            counts[term] = counts.get(term, 0) + 1
    return counts


def rising_terms(current: dict[str, int], previous: dict[str, int], limit: int = 8) -> list[dict]:
    rows = []
    for term, count in current.items():
        if count < 2:
            continue
        before = previous.get(term, 0)
        if before == 0:
            label = "new"
            pct = None
        else:
            pct = (count - before) / before * 100
            if pct < 15 or count - before < 1:
                continue
            label = "rising"
        rows.append({"term": term, "current": count, "previous": before, "pct_change": pct, "label": label})
    rows.sort(key=lambda row: (row["label"] != "rising", -(row["pct_change"] or 0), -row["current"]))
    return rows[:limit]


def find_outliers(posts: list[dict], *, relationships: set[str], multiplier: float = 3, min_videos: int = 4) -> list[dict]:
    """Videos at or above `multiplier` times their channel's median views.

    The median is taken from the videos in this snapshot for that channel,
    not from every video that channel has ever posted.
    """
    latest: dict[tuple, dict] = {}
    for post in posts:
        if post.get("relationship", "own") not in relationships:
            continue
        if post.get("views") is None:
            continue
        key = (post.get("account_name"), post.get("post_id"))
        if key not in latest or (post.get("collected_at") or "") > (latest[key].get("collected_at") or ""):
            latest[key] = post
    grouped: dict[str, list[dict]] = {}
    for post in latest.values():
        grouped.setdefault(post.get("account_name") or "", []).append(post)
    found = []
    for name, videos in grouped.items():
        views = sorted(video["views"] for video in videos)
        if len(views) < min_videos:
            continue
        mid = len(views) // 2
        median_views = views[mid] if len(views) % 2 else (views[mid - 1] + views[mid]) / 2
        if median_views <= 0:
            continue
        for video in videos:
            multiple = video["views"] / median_views
            if multiple < multiplier:
                continue
            found.append(
                {
                    "account_name": name,
                    "relationship": video.get("relationship"),
                    "title": video.get("title") or "",
                    "url": video.get("url") or "",
                    "views": video["views"],
                    "median_views": round(median_views, 1),
                    "multiple": round(multiple, 2),
                    "video_count": len(views),
                    "note": (
                        f"This video has {multiple:.1f}x the median views of the {len(views)} "
                        f"{name} videos in the latest snapshot. It is not a scan of the whole channel history."
                    ),
                }
            )
    found.sort(key=lambda item: item["multiple"], reverse=True)
    return found
