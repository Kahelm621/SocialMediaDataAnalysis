"""Optional YouTube Analytics API (OAuth). Private CTR and retention.

Skipped unless client id, client secret, and a refresh token are all set.
Public view and like counts still come from the Data API without this.
"""

from __future__ import annotations

from datetime import timedelta

from creator_analytics.http_util import APIError, request_json

TOKEN_URL = "https://oauth2.googleapis.com/token"
REPORTS_URL = "https://youtubeanalytics.googleapis.com/v2/reports"


def refresh_access_token(session, client_id: str, client_secret: str, refresh_token: str) -> str:
    payload = request_json(
        session,
        "POST",
        TOKEN_URL,
        form_body={
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": client_id,
            "client_secret": client_secret,
        },
        secrets=[client_secret, refresh_token],
    )
    token = payload.get("access_token")
    if not token:
        raise APIError("YouTube Analytics token response did not include an access token.")
    return token


def _report(session, access_token: str, channel_id: str, start: str, end: str, metrics: str, secrets: list[str]) -> dict:
    return request_json(
        session,
        "GET",
        REPORTS_URL,
        params={
            "ids": f"channel=={channel_id}",
            "startDate": start,
            "endDate": end,
            "metrics": metrics,
        },
        headers={"Authorization": f"Bearer {access_token}"},
        secrets=secrets,
    )


def fetch_channel_analytics(session, access_token: str, channel_id: str, now, secrets: list[str]) -> dict:
    end = now.date()
    start = end - timedelta(days=28)
    start_text = start.isoformat()
    end_text = end.isoformat()
    full_metrics = "views,averageViewPercentage,videoThumbnailImpressionsClickRate"
    try:
        payload = _report(session, access_token, channel_id, start_text, end_text, full_metrics, secrets)
    except APIError:
        payload = _report(
            session,
            access_token,
            channel_id,
            start_text,
            end_text,
            "views,averageViewPercentage",
            secrets,
        )
    headers = [item.get("name") for item in payload.get("columnHeaders") or []]
    rows = payload.get("rows") or []
    values = dict(zip(headers, rows[0])) if rows else {}
    ctr = values.get("videoThumbnailImpressionsClickRate")
    retention = values.get("averageViewPercentage")
    return {
        "analytics_avg_view_percentage": None if retention is None else float(retention),
        "analytics_ctr": None if ctr is None else float(ctr),
    }
