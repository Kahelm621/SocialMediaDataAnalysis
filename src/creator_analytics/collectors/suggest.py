"""YouTube autocomplete suggestions.

This is Google's public suggest endpoint (client=firefox, ds=yt). It does not
use YouTube Data API quota. The strings are search suggestions, not volumes.
"""

from __future__ import annotations

from creator_analytics.http_util import APIError, redact

SUGGEST_URL = "https://suggestqueries.google.com/complete/search"


def parse_suggest(payload) -> list[str]:
    if isinstance(payload, list) and len(payload) >= 2 and isinstance(payload[1], list):
        return [str(item) for item in payload[1] if str(item).strip()]
    return []


def fetch_suggestions(session, query: str) -> list[str]:
    try:
        response = session.request(
            "GET",
            SUGGEST_URL,
            params={"client": "firefox", "ds": "yt", "q": query},
            headers={"User-Agent": "SocialMediaDataAnalysis/1.0"},
            timeout=20,
        )
    except Exception as exc:  # noqa: BLE001 — suggestions are optional
        raise APIError(redact(str(exc), [])) from None
    if response.status_code >= 400:
        raise APIError(f"{response.status_code} from YouTube suggest")
    try:
        payload = response.json()
    except ValueError as exc:
        raise APIError("YouTube suggest did not return JSON") from exc
    return parse_suggest(payload)
