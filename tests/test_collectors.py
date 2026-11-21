import json

from creator_analytics.collectors import tiktok, x_api, youtube, youtube_analytics
from creator_analytics.http_util import APIError


class FakeResponse:
    def __init__(self, payload, status=200):
        self.status_code = status
        self._payload = payload
        self.text = payload if isinstance(payload, str) else json.dumps(payload)
        self.url = "https://example.test/resource"

    def json(self):
        if isinstance(self._payload, str):
            return json.loads(self._payload)
        return self._payload


class FakeSession:
    def __init__(self, handler):
        self.handler = handler
        self.calls = []

    def request(self, method, url, params=None, json=None, data=None, headers=None, timeout=None):
        call = {"method": method, "url": url, "params": params, "json": json, "data": data, "headers": headers}
        self.calls.append(call)
        result = self.handler(call)
        if isinstance(result, Exception):
            raise result
        return result


def test_youtube_maps_public_statistics_and_hides_subscriber_count():
    parsed = youtube.parse_channel_item(
        {
            "id": "UC123",
            "snippet": {"title": "KhaosAyngel"},
            "statistics": {"hiddenSubscriberCount": True, "subscriberCount": "0", "viewCount": "50"},
            "contentDetails": {"relatedPlaylists": {"uploads": "UU123"}},
        }
    )
    assert parsed["followers"] is None
    assert parsed["total_views"] == 50
    video = youtube.parse_video_item(
        {
            "id": "abc",
            "snippet": {"title": "Guess the game", "publishedAt": "2026-11-01T00:00:00Z", "channelTitle": "Quiz"},
            "statistics": {"viewCount": "10", "likeCount": "2", "commentCount": "1"},
        }
    )
    assert video["shares"] is None
    assert video["views"] == 10
    assert video["url"].endswith("abc")


def test_youtube_collect_uses_the_data_api(monkeypatch):
    def handler(call):
        if call["url"].endswith("/channels"):
            assert call["params"]["forHandle"] == "KhaosAyngel"
            assert call["params"]["key"] == "yt-key"
            return FakeResponse(
                {
                    "items": [
                        {
                            "id": "UC1",
                            "snippet": {"title": "KhaosAyngel"},
                            "statistics": {"subscriberCount": "10", "viewCount": "20"},
                            "contentDetails": {"relatedPlaylists": {"uploads": "UU1"}},
                        }
                    ]
                }
            )
        if call["url"].endswith("/playlistItems"):
            return FakeResponse({"items": [{"snippet": {"resourceId": {"videoId": "vid1"}}}]})
        if call["url"].endswith("/videos"):
            return FakeResponse(
                {
                    "items": [
                        {
                            "id": "vid1",
                            "snippet": {"title": "Hello", "publishedAt": "2026-11-01T00:00:00Z"},
                            "statistics": {"viewCount": "5", "likeCount": "1", "commentCount": "0"},
                        }
                    ]
                }
            )
        raise AssertionError(call["url"])

    session = FakeSession(handler)
    account, posts = youtube.collect_account(
        session,
        "yt-key",
        {"name": "KhaosAyngel", "handle": "KhaosAyngel", "niche": "gaming"},
        "2026-11-11T00:00:00+00:00",
        5,
    )
    assert account["is_demo"] is False
    assert account["followers"] == 10
    assert posts[0]["post_id"] == "vid1"
    assert posts[0]["shares"] is None
    assert "yt-key" not in json.dumps(posts)


def test_x_maps_public_metrics_and_falls_back_when_counts_are_forbidden():
    tweet = {
        "id": "99",
        "text": "hello",
        "created_at": "2026-11-01T00:00:00.000Z",
        "public_metrics": {
            "retweet_count": 2,
            "reply_count": 3,
            "like_count": 4,
            "quote_count": 1,
            "impression_count": 50,
        },
    }
    parsed = x_api.parse_tweet(tweet)
    assert parsed["shares"] == 3
    assert parsed["comments"] == 3
    assert parsed["views"] == 50

    def handler(call):
        if call["url"].endswith("/counts/recent"):
            return FakeResponse({"title": "Forbidden", "detail": "nope"}, status=403)
        if call["url"].endswith("/search/recent"):
            return FakeResponse({"data": [tweet]})
        raise AssertionError(call["url"])

    row = x_api.collect_keyword(FakeSession(handler), "bearer-token", {"phrase": "steam", "hashtag": "steam"}, "2026-11-11T00:00:00+00:00")
    assert row["attention_kind"] == "recent_sample"
    assert row["attention"] == 1
    assert row["is_demo"] is False
    assert "bearer-token" not in json.dumps(row)
    assert "sample" in row["attention_note"].lower()


def test_tiktok_parses_display_api_and_rejects_error_codes():
    video = tiktok.parse_video(
        {"id": "55", "title": "clip", "create_time": 1762000000, "view_count": 8, "like_count": 2, "comment_count": 1, "share_count": 1},
        "yourtiktok",
    )
    assert video["views"] == 8
    assert video["url"].endswith("/video/55")
    with __import__("pytest").raises(APIError, match="access_token_invalid"):
        tiktok._raise_if_tiktok_error({"error": {"code": "access_token_invalid", "message": "nope"}})


def test_tiktok_research_query_uses_the_official_endpoint():
    def handler(call):
        assert "/v2/research/video/query/" in call["url"]
        assert call["json"]["query"]["and"][0]["field_values"] == ["steam"]
        return FakeResponse(
            {
                "error": {"code": "ok", "message": ""},
                "data": {"videos": [{"id": "9", "video_description": "steam clip", "view_count": 12, "like_count": 1, "comment_count": 0, "share_count": 0}]},
            }
        )

    from datetime import datetime, timezone

    row = tiktok.collect_keyword(
        FakeSession(handler),
        "research-token",
        {"phrase": "steam", "hashtag": "steam"},
        "2026-11-11T00:00:00+00:00",
        datetime(2026, 11, 11, tzinfo=timezone.utc),
        30,
    )
    assert row["source"] == "tiktok_research_api"
    assert row["attention"] == 12
    assert row["example_role"] == "top_videos"
    assert "scrape" in row["attention_note"].lower() or "does not scrape" in row["attention_note"].lower()


def test_youtube_analytics_posts_a_form_refresh():
    def handler(call):
        if call["url"].endswith("/token"):
            assert call["data"]["grant_type"] == "refresh_token"
            assert call["json"] is None
            return FakeResponse({"access_token": "access-1"})
        assert call["headers"]["Authorization"] == "Bearer access-1"
        if "videoThumbnailImpressionsClickRate" in call["params"]["metrics"]:
            return FakeResponse("bad metric", status=400)
        return FakeResponse(
            {
                "columnHeaders": [{"name": "views"}, {"name": "averageViewPercentage"}],
                "rows": [[100, 42.5]],
            }
        )

    from datetime import datetime, timezone

    session = FakeSession(handler)
    token = youtube_analytics.refresh_access_token(session, "id", "secret", "refresh")
    metrics = youtube_analytics.fetch_channel_analytics(
        session,
        token,
        "UC1",
        datetime(2026, 11, 11, tzinfo=timezone.utc),
        ["secret", "refresh", token],
    )
    assert metrics["analytics_avg_view_percentage"] == 42.5
    assert metrics["analytics_ctr"] is None
