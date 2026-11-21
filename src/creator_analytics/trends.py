"""Keyword movement and title-pattern comparisons."""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from statistics import median

RISING = "rising"
FALLING = "falling"
STEADY = "steady"
NEW = "new"
NOT_ENOUGH = "not_enough_history"


def keyword_in_front(title: str, keywords: list[str], window: int) -> bool:
    """True when a tracked phrase sits inside the first `window` characters.

    Multi-word phrases also match with the spaces removed, so "guess the game"
    counts inside "GuessTheGame:". Short single words are not compacted, so
    "steam" does not match inside "streamers".
    """
    head = title.casefold()[:window]
    compact_head = head.replace(" ", "")
    for phrase in keywords:
        folded = phrase.strip().casefold()
        if not folded:
            continue
        if folded in head:
            return True
        if " " in folded and folded.replace(" ", "") in compact_head:
            return True
    return False


def has_number(title: str) -> bool:
    return re.search(r"\d", title) is not None


def title_stats(titles: list[str], keywords: list[str], window: int) -> dict:
    cleaned = [title.strip() for title in titles if title and title.strip()]
    if not cleaned:
        return {
            "count": 0,
            "median_chars": None,
            "median_words": None,
            "pct_with_number": None,
            "pct_keyword_in_front": None,
        }
    count = len(cleaned)
    return {
        "count": count,
        "median_chars": median(len(title) for title in cleaned),
        "median_words": median(len(title.split()) for title in cleaned),
        "pct_with_number": sum(has_number(title) for title in cleaned) / count,
        "pct_keyword_in_front": sum(keyword_in_front(title, keywords, window) for title in cleaned) / count,
    }


def _moment(value: str) -> datetime:
    text = value.replace("Z", "+00:00")
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _earlier_row(ordered: list[dict]) -> dict | None:
    """The snapshot about seven days before the latest one.

    A 6-hour collector makes the immediately previous point a weak comparison:
    most phrases will not move 15% in six hours. When the history is shorter
    than a week, the previous snapshot is used instead.
    """
    if len(ordered) < 2:
        return None
    latest = _moment(ordered[-1]["collected_at"])
    target = latest - timedelta(days=7)
    chosen = ordered[-2]
    for row in ordered[:-1]:
        if _moment(row["collected_at"]) <= target:
            chosen = row
    return chosen


def keyword_changes(rows: list[dict], rising_pct: float = 15, falling_pct: float = -15) -> list[dict]:
    """Compare the latest attention number with an earlier snapshot.

    `attention` is whatever that platform can honestly measure: combined views
    of top YouTube results, an X recent-post count, or a TikTok research sample.
    Rows with a different attention_kind are not compared to each other.
    """
    groups: dict[tuple, list[dict]] = {}
    for row in rows:
        key = (row.get("platform"), row.get("keyword"), row.get("attention_kind"))
        groups.setdefault(key, []).append(row)

    changes = []
    for (platform, keyword, kind), items in groups.items():
        ordered = sorted(items, key=lambda row: row.get("collected_at") or "")
        current = ordered[-1]
        previous = _earlier_row(ordered)
        current_value = current.get("attention")
        previous_value = None if previous is None else previous.get("attention")
        pct = None
        if previous is None or current_value is None or previous_value is None:
            label = NOT_ENOUGH
        elif previous_value == 0:
            label = NEW if current_value > 0 else STEADY
        else:
            pct = (current_value - previous_value) / abs(previous_value) * 100
            if pct >= rising_pct:
                label = RISING
            elif pct <= falling_pct:
                label = FALLING
            else:
                label = STEADY
        changes.append(
            {
                "platform": platform,
                "keyword": keyword,
                "attention_kind": kind,
                "attention_note": current.get("attention_note") or "",
                "current": current_value,
                "previous": previous_value,
                "pct_change": pct,
                "label": label,
                "collected_at": current.get("collected_at"),
                "previous_collected_at": None if previous is None else previous.get("collected_at"),
            }
        )
    changes.sort(key=lambda row: (row["pct_change"] is None, -(row["pct_change"] or 0)))
    return changes
