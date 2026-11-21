"""Collect official stats and append them to data/snapshots.

Missing keys are skipped. A failure on one account does not stop the others.
Demo rows are never written here.
"""

from __future__ import annotations

from datetime import datetime, timezone

import requests

from creator_analytics.collectors import platform as platform_api
from creator_analytics.collectors import tiktok as tiktok_api
from creator_analytics.collectors import x_api
from creator_analytics.collectors import youtube as youtube_api
from creator_analytics.collectors import youtube_analytics
from creator_analytics.envfile import env_value
from creator_analytics.http_util import APIError, redact
from creator_analytics.quota import QuotaBudget
from creator_analytics.storage import append_jsonl

SECRET_NAMES = (
    "YOUTUBE_API_KEY",
    "X_BEARER_TOKEN",
    "TIKTOK_ACCESS_TOKEN",
    "TIKTOK_RESEARCH_TOKEN",
    "YOUTUBE_OAUTH_CLIENT_ID",
    "YOUTUBE_OAUTH_CLIENT_SECRET",
    "YOUTUBE_ANALYTICS_REFRESH_TOKEN",
)


def _status(source: str, state: str, detail: str, account: str = "") -> dict:
    return {"source": source, "account": account, "state": state, "detail": detail}


def _detail(exc: Exception, env: dict) -> str:
    secrets = [env_value(env, name) for name in SECRET_NAMES]
    return redact(str(exc), secrets)[:500]


def collect(config: dict, env: dict, snapshot_dir, session=None, now=None, force_search: bool = False) -> dict:
    session = session or requests.Session()
    moment = now or datetime.now(timezone.utc).replace(microsecond=0)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    collected_at = moment.isoformat()
    limits = config["limits"]
    statuses = []
    new_rows = 0

    youtube_key = env_value(env, "YOUTUBE_API_KEY")
    client_id = env_value(env, "YOUTUBE_OAUTH_CLIENT_ID")
    client_secret = env_value(env, "YOUTUBE_OAUTH_CLIENT_SECRET")
    refresh_token = env_value(env, "YOUTUBE_ANALYTICS_REFRESH_TOKEN")
    analytics_ready = bool(client_id and client_secret and refresh_token)
    youtube_accounts = [account for account in config["accounts"] if account["platform"] == "youtube"]

    budget = None
    if youtube_key:
        budget = QuotaBudget(
            snapshot_dir / "quota_log.json",
            moment.date().isoformat(),
            int(config["youtube_quota"]["daily_unit_budget"]),
        )

    if not youtube_key:
        statuses.append(
            _status(
                "YouTube Data API",
                "skipped",
                "Set YOUTUBE_API_KEY for public subscribers, video stats, keyword search, and the YouTube-wide explorer.",
            )
        )
    else:
        for account in youtube_accounts:
            if not budget.allow(3, f"channel {account['name']}"):
                statuses.append(
                    _status("YouTube Data API", "skipped", "Daily YouTube unit budget reached.", account["name"])
                )
                continue
            budget.charge(3)
            try:
                account_row, posts = youtube_api.collect_account(
                    session,
                    youtube_key,
                    account,
                    collected_at,
                    limits["videos_per_account"],
                )
                if analytics_ready and account_row.get("account_id"):
                    try:
                        access = youtube_analytics.refresh_access_token(
                            session, client_id, client_secret, refresh_token
                        )
                        extra = youtube_analytics.fetch_channel_analytics(
                            session,
                            access,
                            account_row["account_id"],
                            moment,
                            [client_secret, refresh_token, access],
                        )
                        account_row.update(extra)
                        statuses.append(
                            _status(
                                "YouTube Analytics API",
                                "ok",
                                "Saved thumbnail CTR and average view percentage for the last 28 days.",
                                account["name"],
                            )
                        )
                    except (APIError, Exception) as exc:  # noqa: BLE001 — record and keep public stats
                        statuses.append(
                            _status(
                                "YouTube Analytics API",
                                "error",
                                _detail(exc, env),
                                account["name"],
                            )
                        )
                new_rows += append_jsonl(snapshot_dir / "accounts.jsonl", [account_row])
                new_rows += append_jsonl(snapshot_dir / "posts.jsonl", posts)
                statuses.append(
                    _status(
                        "YouTube Data API",
                        "ok",
                        f"Saved the channel and {len(posts)} recent videos.",
                        account["name"],
                    )
                )
            except (APIError, Exception) as exc:  # noqa: BLE001
                statuses.append(_status("YouTube Data API", "error", _detail(exc, env), account["name"]))

        for competitor in config["competitors"]:
            if not competitor["enabled"] or not (competitor["handle"] or competitor["channel_id"]):
                statuses.append(
                    _status(
                        "YouTube competitor",
                        "skipped",
                        "Set enabled: true and a handle or channel id in config/tracked.yaml.",
                        competitor["name"],
                    )
                )
                continue
            if not budget.allow(3, f"competitor {competitor['name']}"):
                statuses.append(
                    _status("YouTube competitor", "skipped", "Daily YouTube unit budget reached.", competitor["name"])
                )
                continue
            budget.charge(3)
            try:
                account_row, posts = youtube_api.collect_account(
                    session,
                    youtube_key,
                    competitor,
                    collected_at,
                    limits["videos_per_account"],
                )
                new_rows += append_jsonl(snapshot_dir / "accounts.jsonl", [account_row])
                new_rows += append_jsonl(snapshot_dir / "posts.jsonl", posts)
                statuses.append(
                    _status(
                        "YouTube competitor",
                        "ok",
                        f"Saved the channel and {len(posts)} recent videos.",
                        competitor["name"],
                    )
                )
            except (APIError, Exception) as exc:  # noqa: BLE001
                statuses.append(_status("YouTube competitor", "error", _detail(exc, env), competitor["name"]))

        extra_rows, extra_statuses = platform_api.collect_platform(
            session,
            youtube_key,
            config,
            collected_at,
            moment,
            snapshot_dir,
            budget,
            force_search,
        )
        new_rows += extra_rows
        statuses.extend(extra_statuses)

    if youtube_key and not analytics_ready:
        statuses.append(
            _status(
                "YouTube Analytics API",
                "skipped",
                "Optional. Set YOUTUBE_OAUTH_CLIENT_ID, YOUTUBE_OAUTH_CLIENT_SECRET, and "
                "YOUTUBE_ANALYTICS_REFRESH_TOKEN for thumbnail CTR and average view percentage.",
            )
        )
    elif not youtube_key and analytics_ready:
        statuses.append(
            _status(
                "YouTube Analytics API",
                "skipped",
                "Add YOUTUBE_API_KEY as well. Analytics is attached after the public channel lookup.",
            )
        )
    elif not youtube_key:
        statuses.append(
            _status(
                "YouTube Analytics API",
                "skipped",
                "Optional private metrics. Needs the three YouTube OAuth secrets plus YOUTUBE_API_KEY.",
            )
        )

    x_token = env_value(env, "X_BEARER_TOKEN")
    x_accounts = [account for account in config["accounts"] if account["platform"] == "x"]
    if not x_token:
        statuses.append(
            _status(
                "X API",
                "skipped",
                "Set X_BEARER_TOKEN for @AyngelBytes public metrics and recent hashtag counts.",
            )
        )
    else:
        for account in x_accounts:
            try:
                account_row, posts = x_api.collect_account(
                    session,
                    x_token,
                    account,
                    collected_at,
                    limits["tweets_per_account"],
                )
                new_rows += append_jsonl(snapshot_dir / "accounts.jsonl", [account_row])
                new_rows += append_jsonl(snapshot_dir / "posts.jsonl", posts)
                statuses.append(
                    _status("X API", "ok", f"Saved the profile and {len(posts)} recent posts.", account["name"])
                )
            except (APIError, Exception) as exc:  # noqa: BLE001
                statuses.append(_status("X API", "error", _detail(exc, env), account["name"]))
        for keyword in config["keywords"]:
            try:
                row = x_api.collect_keyword(session, x_token, keyword, collected_at)
                new_rows += append_jsonl(snapshot_dir / "keywords.jsonl", [row])
                kind = row["attention_kind"]
                statuses.append(
                    _status(
                        "X hashtags",
                        "ok",
                        f"Saved a {kind.replace('_', ' ')} for #{keyword['hashtag']}.",
                        keyword["phrase"],
                    )
                )
            except (APIError, Exception) as exc:  # noqa: BLE001
                statuses.append(_status("X hashtags", "error", _detail(exc, env), keyword["phrase"]))

    tiktok_token = env_value(env, "TIKTOK_ACCESS_TOKEN")
    research_token = env_value(env, "TIKTOK_RESEARCH_TOKEN")
    for account in config["accounts"]:
        if account["platform"] != "tiktok":
            continue
        if not account["enabled"]:
            statuses.append(
                _status(
                    "TikTok Display API",
                    "skipped",
                    "Disabled in config/tracked.yaml. Set enabled: true and a handle when the account exists, "
                    "then set TIKTOK_ACCESS_TOKEN. Official APIs only; this project does not scrape TikTok.",
                    account["name"],
                )
            )
            continue
        if not tiktok_token:
            statuses.append(
                _status(
                    "TikTok Display API",
                    "skipped",
                    "Set TIKTOK_ACCESS_TOKEN after TikTok approves your app. "
                    "The Display API reads only the account that approved it.",
                    account["name"],
                )
            )
            continue
        try:
            account_row, posts, note = tiktok_api.collect_account(
                session,
                tiktok_token,
                account,
                collected_at,
                limits["tiktok_videos"],
            )
            new_rows += append_jsonl(snapshot_dir / "accounts.jsonl", [account_row])
            new_rows += append_jsonl(snapshot_dir / "posts.jsonl", posts)
            detail = f"Saved the profile and {len(posts)} videos."
            if note:
                detail = f"{detail} {note}"
            statuses.append(_status("TikTok Display API", "ok", detail, account["name"]))
        except (APIError, Exception) as exc:  # noqa: BLE001
            statuses.append(_status("TikTok Display API", "error", _detail(exc, env), account["name"]))

    if not research_token:
        statuses.append(
            _status(
                "TikTok Research API",
                "skipped",
                "Hashtag volume needs TIKTOK_RESEARCH_TOKEN after Research API approval. "
                "The Display API does not provide public hashtag counts. No scraping.",
            )
        )
    else:
        for keyword in config["keywords"]:
            try:
                row = tiktok_api.collect_keyword(
                    session,
                    research_token,
                    keyword,
                    collected_at,
                    moment,
                    limits["trend_lookback_days"],
                )
                new_rows += append_jsonl(snapshot_dir / "keywords.jsonl", [row])
                statuses.append(
                    _status(
                        "TikTok Research API",
                        "ok",
                        f"Saved a hashtag sample for #{keyword['hashtag']}.",
                        keyword["phrase"],
                    )
                )
            except (APIError, Exception) as exc:  # noqa: BLE001
                statuses.append(_status("TikTok Research API", "error", _detail(exc, env), keyword["phrase"]))

    return {"collected_at": collected_at, "statuses": statuses, "new_rows": new_rows}
