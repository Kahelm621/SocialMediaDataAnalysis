"""Suggestion cards. Every card cites the numbers it used."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from statistics import median
from zoneinfo import ZoneInfo

from creator_analytics.metrics import engagement_rate
from creator_analytics.trends import keyword_changes, title_stats

TITLE_PLATFORMS = {"youtube", "tiktok"}


def _card(card_id: str, headline: str, why: str, try_this: str, evidence: dict) -> dict:
    return {
        "id": card_id,
        "headline": headline,
        "why": why,
        "try_this": try_this,
        "evidence": evidence,
    }


def _round(value, digits=2):
    if value is None:
        return None
    return round(float(value), digits)


def _pct(value) -> str:
    if value is None:
        return "n/a"
    return f"{value * 100:.0f}%"


def _hour_label(hour: int, timezone_name: str) -> str:
    return f"{hour:02d}:00 {timezone_name}"


def _parse_time(value: str) -> datetime:
    text = value.replace("Z", "+00:00")
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=ZoneInfo("UTC"))
    return parsed


def latest_posts(posts: list[dict]) -> list[dict]:
    """One row per post: the newest snapshot, plus engagement rate."""
    grouped: dict[tuple, list[dict]] = defaultdict(list)
    for post in posts:
        grouped[(post.get("platform"), post.get("post_id"))].append(post)
    latest = []
    for history in grouped.values():
        ordered = sorted(history, key=lambda row: row.get("collected_at") or "")
        row = dict(ordered[-1])
        row["engagement_rate"] = engagement_rate(
            row.get("likes"), row.get("comments"), row.get("shares"), row.get("views")
        )
        latest.append(row)
    return latest


def _titles(posts: list[dict]) -> list[str]:
    return [
        post["title"]
        for post in posts
        if post.get("platform") in TITLE_PLATFORMS and post.get("title")
    ]


def _top_titles(keyword_rows: list[dict], phrases: list[str]) -> list[str]:
    """Titles from the newest top-video list for each phrase."""
    wanted = set(phrases)
    grouped: dict[tuple, list[dict]] = defaultdict(list)
    for row in keyword_rows:
        if row.get("example_role") != "top_videos":
            continue
        if row.get("keyword") not in wanted:
            continue
        grouped[(row.get("platform"), row.get("keyword"))].append(row)
    titles = []
    seen = set()
    for items in grouped.values():
        newest = sorted(items, key=lambda row: row.get("collected_at") or "")[-1]
        for example in newest.get("examples") or []:
            title = (example.get("title") or "").strip()
            key = title.casefold()
            if title and key not in seen:
                seen.add(key)
                titles.append(title)
    return titles


def _length_card(own: dict, top: dict, settings: dict) -> dict:
    close = settings["title_length_close_chars"]
    evidence = {
        "own_median_chars": _round(own["median_chars"], 1),
        "top_median_chars": _round(top["median_chars"], 1),
        "own_count": own["count"],
        "top_count": top["count"],
        "close_chars": close,
    }
    if own["count"] < settings["min_titles"] or top["count"] < settings["min_titles"]:
        return _card(
            "title_length",
            "Not enough titles to compare length yet",
            "Length is compared only when both your titles and the current top videos have "
            f"at least {settings['min_titles']} titles. You have {own['count']}. "
            f"The top-video list has {top['count']}.",
            "Keep collecting. After a few videos and a keyword search, this card will compare median length.",
            evidence,
        )
    own_median = own["median_chars"]
    top_median = top["median_chars"]
    difference = own_median - top_median
    evidence["difference"] = _round(difference, 1)
    if abs(difference) <= close:
        return _card(
            "title_length",
            "Title length is close to top videos",
            f"Your median title is {own_median:.0f} characters. Top videos for your keywords "
            f"sit at {top_median:.0f}. The gap is {abs(difference):.0f} characters, inside the "
            f"{close}-character 'close enough' rule.",
            "Length is not the first thing to change. Look at keyword placement and the rising phrases instead.",
            evidence,
        )
    if difference > 0:
        return _card(
            "title_length",
            "Try shorter titles",
            f"Your median title is {own_median:.0f} characters. Top videos for your keywords "
            f"have a median of {top_median:.0f}. That is {difference:.0f} characters longer on your side. "
            "People decide from a short line in a feed. This is a pattern in the saved titles, not a guarantee.",
            f"Cut the next title toward {top_median:.0f} characters. Lead with the topic and drop the warm-up clause.",
            evidence,
        )
    return _card(
        "title_length",
        "Try longer titles",
        f"Your median title is {own_median:.0f} characters. Top videos for your keywords "
        f"have a median of {top_median:.0f}. Yours are {abs(difference):.0f} characters shorter. "
        "A little more specific detail is the pattern in this comparison.",
        f"Add one concrete detail so the next title lands nearer {top_median:.0f} characters.",
        evidence,
    )


def _placement_card(own: dict, top: dict, settings: dict) -> dict:
    window = settings["keyword_front_chars"]
    evidence = {
        "own_pct_keyword_in_front": _round(own["pct_keyword_in_front"], 3),
        "top_pct_keyword_in_front": _round(top["pct_keyword_in_front"], 3),
        "window_chars": window,
        "own_count": own["count"],
        "top_count": top["count"],
    }
    if own["count"] < settings["min_titles"] or top["count"] < settings["min_titles"]:
        return _card(
            "keyword_placement",
            "Not enough titles to compare keywords yet",
            "Placement means: does a tracked phrase show up in the first "
            f"{window} characters? Both sides need at least {settings['min_titles']} titles.",
            "Add keywords in config/tracked.yaml, then collect again.",
            evidence,
        )
    gap = top["pct_keyword_in_front"] - own["pct_keyword_in_front"]
    evidence["gap"] = _round(gap, 3)
    if gap >= 0.2:
        return _card(
            "keyword_placement",
            "Put the keyword at the front",
            f"{_pct(own['pct_keyword_in_front'])} of your titles put a tracked keyword in the first {window} characters. "
            f"{_pct(top['pct_keyword_in_front'])} of top videos do. The gap is {gap * 100:.0f} percentage points.",
            "Start the next title with the phrase itself, for example \"Guess the game:\" or \"Weird biology:\".",
            evidence,
        )
    if gap <= -0.2:
        return _card(
            "keyword_placement",
            "Keyword placement is already strong",
            f"{_pct(own['pct_keyword_in_front'])} of your titles put a tracked keyword in the first {window} characters, "
            f"ahead of top videos at {_pct(top['pct_keyword_in_front'])}.",
            "Keep leading with the phrase. Spend the next edit on length or a rising keyword instead.",
            evidence,
        )
    return _card(
        "keyword_placement",
        "Keyword placement is close to top videos",
        f"{_pct(own['pct_keyword_in_front'])} of your titles put a tracked keyword in the first {window} characters. "
        f"Top videos are at {_pct(top['pct_keyword_in_front'])}.",
        "Keep the phrase early when it fits. This gap is too small to treat as a problem.",
        evidence,
    )


def _numbers_card(own: dict, top: dict, settings: dict) -> dict:
    evidence = {
        "own_pct_with_number": _round(own["pct_with_number"], 3),
        "top_pct_with_number": _round(top["pct_with_number"], 3),
        "own_count": own["count"],
        "top_count": top["count"],
    }
    if own["count"] < settings["min_titles"] or top["count"] < settings["min_titles"]:
        return _card(
            "numbers_in_titles",
            "Not enough titles to compare numbers yet",
            "This card counts titles that contain a digit, such as \"5 seconds\" or \"40 seconds\". "
            f"Both sides need at least {settings['min_titles']} titles.",
            "Collect a few more titles, then check this again.",
            evidence,
        )
    gap = top["pct_with_number"] - own["pct_with_number"]
    evidence["gap"] = _round(gap, 3)
    if gap >= 0.2:
        return _card(
            "numbers_in_titles",
            "Try a real number in the title",
            f"{_pct(own['pct_with_number'])} of your titles include a digit. "
            f"{_pct(top['pct_with_number'])} of top videos do. The gap is {gap * 100:.0f} percentage points. "
            "A specific number gives the eye something to catch. Only use a number that is true.",
            "If the video has a count, a round, or a time limit, put that digit in the title.",
            evidence,
        )
    if gap <= -0.2:
        return _card(
            "numbers_in_titles",
            "You already use numbers more than top videos",
            f"{_pct(own['pct_with_number'])} of your titles include a digit, compared with "
            f"{_pct(top['pct_with_number'])} of top videos.",
            "Keep the number when it is real. You do not need to add more of them just to match.",
            evidence,
        )
    return _card(
        "numbers_in_titles",
        "Numbers in titles are close to top videos",
        f"{_pct(own['pct_with_number'])} of your titles include a digit. Top videos are at {_pct(top['pct_with_number'])}.",
        "Use a number when the video actually has one. There is no large gap to close.",
        evidence,
    )


def _hour_card(posts: list[dict], timezone_name: str, settings: dict) -> dict:
    buckets: dict[int, list[float]] = defaultdict(list)
    zone = ZoneInfo(timezone_name)
    for post in posts:
        rate = post.get("engagement_rate")
        published = post.get("published_at")
        if rate is None or not published:
            continue
        hour = _parse_time(published).astimezone(zone).hour
        buckets[hour].append(rate)
    usable = {hour: rates for hour, rates in buckets.items() if len(rates) >= settings["min_posts_in_hour"]}
    scored = sum(len(rates) for rates in buckets.values())
    evidence = {
        "timezone": timezone_name,
        "posts_with_engagement": scored,
        "min_posts": settings["min_posts_for_hour"],
        "min_posts_in_hour": settings["min_posts_in_hour"],
        "hours": {
            str(hour): {"posts": len(rates), "median_engagement_rate": _round(median(rates), 4)}
            for hour, rates in sorted(usable.items())
        },
    }
    if scored < settings["min_posts_for_hour"] or len(usable) < 2:
        return _card(
            "best_hour",
            "Not enough posting times to compare yet",
            f"{scored} posts have an engagement rate. A comparison needs at least "
            f"{settings['min_posts_for_hour']} posts, and at least two different hours with "
            f"{settings['min_posts_in_hour']} posts each. Hours are in {timezone_name}.",
            "Set timezone in config/tracked.yaml to your clock, then keep posting. "
            "This card will name an hour once the history is wide enough.",
            evidence,
        )
    ranked = sorted(usable.items(), key=lambda item: median(item[1]), reverse=True)
    best_hour, best_rates = ranked[0]
    worst_hour, worst_rates = ranked[-1]
    best_median = median(best_rates)
    worst_median = median(worst_rates)
    evidence.update(
        {
            "best_hour": best_hour,
            "best_posts": len(best_rates),
            "best_median_engagement_rate": _round(best_median, 4),
            "weakest_hour": worst_hour,
            "weakest_posts": len(worst_rates),
            "weakest_median_engagement_rate": _round(worst_median, 4),
        }
    )
    return _card(
        "best_hour",
        f"Post around {_hour_label(best_hour, timezone_name)}",
        f"Posts at {_hour_label(best_hour, timezone_name)} have a median engagement rate of "
        f"{best_median * 100:.1f}% across {len(best_rates)} posts. "
        f"The weaker saved hour is {_hour_label(worst_hour, timezone_name)} at "
        f"{worst_median * 100:.1f}% across {len(worst_rates)} posts. "
        "Engagement rate is (likes + comments + shares) / views.",
        f"Schedule the next post near {_hour_label(best_hour, timezone_name)}. "
        "Change timezone in config/tracked.yaml if that clock is not yours.",
        evidence,
    )


def _rising_card(changes: list[dict], phrases: list[str]) -> dict:
    wanted = set(phrases)
    chosen = [
        change
        for change in changes
        if change.get("keyword") in wanted and change.get("platform") == "youtube"
    ]
    rising = [change for change in chosen if change["label"] == "rising"]
    falling = [change for change in chosen if change["label"] == "falling"]
    rising.sort(key=lambda change: change["pct_change"] or 0, reverse=True)
    falling.sort(key=lambda change: change["pct_change"] or 0)

    def brief(change: dict) -> dict:
        pct = change["pct_change"]
        earlier = change.get("previous_collected_at") or ""
        return {
            "keyword": change["keyword"],
            "pct_change": None if pct is None else round(pct, 1),
            "current": change["current"],
            "previous": change["previous"],
            "previous_collected_at": earlier[:10],
            "attention_kind": change["attention_kind"],
        }

    evidence = {"rising": [brief(item) for item in rising[:3]], "falling": [brief(item) for item in falling[:3]]}
    if not rising and not falling:
        return _card(
            "rising_keywords",
            "No keyword on your list is clearly rising",
            "Rising means the YouTube attention number moved at least the configured percent "
            "versus the snapshot from about a week earlier. Nothing on this account's keyword list crossed that line. "
            "YouTube attention is the combined views of the top search results, not an exact census of the phrase.",
            "Leave the list as it is, or add a game name you are about to cover in config/tracked.yaml.",
            evidence,
        )
    bits = []
    for item in evidence["rising"][:2]:
        bits.append(
            f"'{item['keyword']}' is up {item['pct_change']}% "
            f"({item['previous']} on {item['previous_collected_at']} to {item['current']})"
        )
    for item in evidence["falling"][:1]:
        bits.append(
            f"'{item['keyword']}' is down {abs(item['pct_change'])}% "
            f"({item['previous']} on {item['previous_collected_at']} to {item['current']})"
        )
    why = (
        "Compared with the snapshot from about a week earlier (or the previous one, if the history is shorter), "
        + "; ".join(bits)
        + ". The number is combined views of the top YouTube results for that phrase."
    )
    if rising:
        lead = evidence["rising"][0]["keyword"]
        avoid = f" You can skip forcing '{evidence['falling'][0]['keyword']}' unless the video is actually about it." if falling else ""
        try_this = f"Use '{lead}' in the next title, near the front.{avoid}"
        headline = "Use rising keywords in the next title"
    else:
        name = evidence["falling"][0]["keyword"]
        try_this = f"You do not have a rising phrase in this list. Avoid leaning on '{name}' unless the video is about it."
        headline = "No keyword on your list is clearly rising"
    return _card("rising_keywords", headline, why, try_this, evidence)


def build_recommendations(
    posts: list[dict],
    keyword_rows: list[dict],
    *,
    phrases: list[str],
    timezone_name: str,
    settings: dict,
) -> list[dict]:
    latest = latest_posts(posts)
    window = settings["keyword_front_chars"]
    own = title_stats(_titles(latest), phrases, window)
    top = title_stats(_top_titles(keyword_rows, phrases), phrases, window)
    changes = keyword_changes(
        keyword_rows,
        rising_pct=settings["rising_pct"],
        falling_pct=settings["falling_pct"],
    )
    return [
        _length_card(own, top, settings),
        _placement_card(own, top, settings),
        _numbers_card(own, top, settings),
        _hour_card(latest, timezone_name, settings),
        _rising_card(changes, phrases),
    ]


def title_pattern_block(posts: list[dict], keyword_rows: list[dict], phrases: list[str], window: int) -> dict:
    latest = latest_posts(posts)
    own = title_stats(_titles(latest), phrases, window)
    top = title_stats(_top_titles(keyword_rows, phrases), phrases, window)
    return {"yours": own, "top_videos": top, "keywords": phrases, "window_chars": window}
