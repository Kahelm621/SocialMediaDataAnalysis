import json
from pathlib import Path

import pytest
import requests

from creator_analytics.config import load_config
from creator_analytics.demo_data import generate, write_demo
from creator_analytics.pipeline import collect
from creator_analytics.storage import append_jsonl


ROOT = Path(__file__).resolve().parents[1]


def test_config_tracks_the_accounts_and_keywords():
    config = load_config(ROOT / "config" / "tracked.yaml")
    names = {(account["platform"], account["name"]) for account in config["accounts"]}
    assert ("youtube", "KhaosAyngel") in names
    assert ("youtube", "Strange Biology Club") in names
    assert ("x", "AyngelBytes") in names
    tiktok = next(account for account in config["accounts"] if account["platform"] == "tiktok")
    assert tiktok["enabled"] is False
    phrases = [keyword["phrase"] for keyword in config["keywords"]]
    assert "guess the game" in phrases
    assert "weird biology" in phrases
    assert config["keywords"][0]["hashtag"] == "guessthegame"


def test_demo_rows_are_labeled_and_deterministic(tmp_path):
    first = tmp_path / "one"
    second = tmp_path / "two"
    write_demo(first)
    write_demo(second)
    assert (first / "posts.jsonl").read_text(encoding="utf-8") == (second / "posts.jsonl").read_text(encoding="utf-8")
    for path in first.glob("*.jsonl"):
        for line in path.read_text(encoding="utf-8").splitlines():
            row = json.loads(line)
            assert row["is_demo"] is True
            assert row["source"] == "demo"


def test_storage_refuses_demo_rows(tmp_path):
    row = generate()["posts"][0]
    with pytest.raises(RuntimeError, match="demo"):
        append_jsonl(tmp_path / "posts.jsonl", [row])
    assert not (tmp_path / "posts.jsonl").exists()


def test_storage_dedups_identical_snapshots(tmp_path):
    row = {
        "record_type": "post",
        "platform": "youtube",
        "account_name": "KhaosAyngel",
        "post_id": "abc",
        "collected_at": "2026-11-11T00:00:00+00:00",
        "is_demo": False,
        "views": 10,
    }
    path = tmp_path / "posts.jsonl"
    assert append_jsonl(path, [row]) == 1
    assert append_jsonl(path, [row]) == 0
    assert path.read_text(encoding="utf-8").count("\n") == 1


class ExplodingSession:
    def request(self, *args, **kwargs):
        raise AssertionError("network should not be called when keys are missing")


def test_collect_skips_missing_keys_without_network(tmp_path):
    config = load_config(ROOT / "config" / "tracked.yaml")
    result = collect(config, {}, tmp_path, session=ExplodingSession(), now=__import__("datetime").datetime(2026, 11, 11, tzinfo=__import__("datetime").timezone.utc))
    assert result["new_rows"] == 0
    assert result["statuses"]
    assert all(item["state"] == "skipped" for item in result["statuses"])
    assert not list(tmp_path.glob("*.jsonl"))
    joined = " ".join(item["detail"] for item in result["statuses"])
    assert "YOUTUBE_API_KEY" in joined
    assert "X_BEARER_TOKEN" in joined
    assert "TIKTOK_ACCESS_TOKEN" in joined
    assert "TIKTOK_RESEARCH_TOKEN" in joined
    assert "scrape" in joined.lower()


def test_env_file_does_not_override_existing(monkeypatch, tmp_path):
    from creator_analytics.envfile import load_env_file

    monkeypatch.setenv("YOUTUBE_API_KEY", "already-set")
    env_path = tmp_path / ".env"
    env_path.write_text("YOUTUBE_API_KEY=from-file\nX_BEARER_TOKEN=from-file\n", encoding="utf-8")
    monkeypatch.delenv("X_BEARER_TOKEN", raising=False)
    load_env_file(env_path)
    assert __import__("os").environ["YOUTUBE_API_KEY"] == "already-set"
    assert __import__("os").environ["X_BEARER_TOKEN"] == "from-file"


def test_http_error_redacts_secrets():
    from creator_analytics.http_util import APIError, request_json

    class Session:
        def request(self, *args, **kwargs):
            raise requests.RequestException("failed https://example.test?key=SECRET123")

    with pytest.raises(APIError, match=r"\[redacted\]") as caught:
        request_json(Session(), "GET", "https://example.test", secrets=["SECRET123"])
    assert "SECRET123" not in str(caught.value)
