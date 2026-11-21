import json
from pathlib import Path

import pytest

from creator_analytics.config import load_config
from creator_analytics.dashboard import build_dashboard, build_payload, choose_rows
from creator_analytics.demo_data import generate, write_demo

ROOT = Path(__file__).resolve().parents[1]


def _rows():
    payload = generate()
    rows = []
    for group in payload.values():
        rows.extend(group)
    return rows


def test_demo_story_drives_explainable_suggestions():
    config = load_config(ROOT / "config" / "tracked.yaml")
    payload = build_payload(_rows(), config, True, None)
    assert payload["is_demo"] is True
    assert "sample" in payload["demo_notice"].lower()
    assert all(row["analytics_ctr"] is None for row in payload["accounts_over_time"])
    assert all(row["analytics_avg_view_percentage"] is None for row in payload["accounts_over_time"])

    khaos = {card["id"]: card for card in payload["recommendations"]["youtube::KhaosAyngel"]}
    assert khaos["title_length"]["headline"] == "Try shorter titles"
    assert khaos["title_length"]["evidence"]["own_median_chars"] > khaos["title_length"]["evidence"]["top_median_chars"]
    assert khaos["keyword_placement"]["headline"] == "Put the keyword at the front"
    assert khaos["best_hour"]["evidence"]["best_hour"] == 18
    rising = [item["keyword"] for item in khaos["rising_keywords"]["evidence"]["rising"]]
    falling = [item["keyword"] for item in khaos["rising_keywords"]["evidence"]["falling"]]
    assert rising[0] == "balatro"
    assert "guess the game" in rising
    assert "steam" in falling

    biology = {card["id"]: card for card in payload["recommendations"]["youtube::Strange Biology Club"]}
    assert biology["title_length"]["headline"] == "Title length is close to top videos"
    assert biology["best_hour"]["headline"] == "Not enough posting times to compare yet"

    series = [row for row in payload["posts_over_time"] if row["post_id"] == "demo-yt-khaos-8"]
    assert series[0]["views_per_day"] is None
    assert series[-1]["views_per_day"] == 310
    assert series[-1]["engagement_rate"] == pytest.approx(0.067, abs=0.003)
    explorer = payload["explorer"]
    assert explorer["quota"]["estimated_units_per_day"] < 8000
    assert explorer["trending"]
    assert all(video["lifetime_views_per_hour"] is not None for video in explorer["trending"])
    assert any(row["keyword"] == "balatro" for row in explorer["research"])
    assert any(row["score"] < 80 for row in explorer["video_seo"])
    assert any(row["score"] >= 80 for row in explorer["video_seo"])
    assert any(row["multiple"] >= 3 for row in explorer["outliers"])


def test_dashboard_build_uses_demo_and_labels_it(tmp_path):
    root = tmp_path / "repo"
    (root / "config").mkdir(parents=True)
    (root / "config" / "tracked.yaml").write_text((ROOT / "config" / "tracked.yaml").read_text(encoding="utf-8"), encoding="utf-8")
    write_demo(root / "data" / "demo")
    (root / "data" / "snapshots").mkdir(parents=True)
    out = build_dashboard(root, out_dir=root / "dashboard")
    html = (out / "index.html").read_text(encoding="utf-8")
    data = json.loads((out / "data.json").read_text(encoding="utf-8"))
    assert data["is_demo"] is True
    assert "DEMO DATA" in html
    assert 'id="platform"' in html
    assert 'id="account"' in html
    assert 'id="keyword"' in html
    assert 'id="from"' in html
    assert "What to do better" in html
    export = (root / "data" / "exports" / "engagement.csv").read_text(encoding="utf-8")
    import csv
    exported = list(csv.DictReader(export.splitlines()))
    assert exported
    assert {row["data_source"] for row in exported} == {"demo"}
    assert "engagement" in exported[0] and "category" in exported[0]


def test_real_snapshots_are_not_mixed_with_demo(tmp_path):
    root = tmp_path / "repo"
    (root / "config").mkdir(parents=True)
    (root / "config" / "tracked.yaml").write_text((ROOT / "config" / "tracked.yaml").read_text(encoding="utf-8"), encoding="utf-8")
    write_demo(root / "data" / "demo")
    real_post = {
        "record_type": "post",
        "collected_at": "2026-11-11T00:00:00+00:00",
        "is_demo": False,
        "source": "youtube_data_api",
        "platform": "youtube",
        "account_name": "KhaosAyngel",
        "niche": "gaming",
        "post_id": "real-1",
        "title": "A real title",
        "url": "https://www.youtube.com/watch?v=real",
        "published_at": "2026-11-01T18:00:00+00:00",
        "views": 10,
        "likes": 1,
        "comments": 0,
        "shares": None,
        "views_label": "views",
    }
    snapshot = root / "data" / "snapshots"
    snapshot.mkdir(parents=True)
    (snapshot / "posts.jsonl").write_text(json.dumps(real_post) + "\n", encoding="utf-8")
    rows, is_demo = choose_rows(root)
    assert is_demo is False
    assert {row["post_id"] for row in rows} == {"real-1"}
    out = build_dashboard(root, out_dir=root / "site")
    data = json.loads((out / "data.json").read_text(encoding="utf-8"))
    assert data["is_demo"] is False
    assert all(row["post_id"] == "real-1" for row in data["posts_over_time"])
    html = (out / "index.html").read_text(encoding="utf-8")
    assert "LIVE DATA" in html
    assert "demo-yt-khaos-1" not in html


def test_snapshots_containing_demo_rows_are_rejected(tmp_path):
    root = tmp_path / "repo"
    (root / "config").mkdir(parents=True)
    (root / "data" / "snapshots").mkdir(parents=True)
    demo_row = generate()["posts"][0]
    (root / "data" / "snapshots" / "posts.jsonl").write_text(json.dumps(demo_row) + "\n", encoding="utf-8")
    with pytest.raises(RuntimeError, match="demo"):
        choose_rows(root)


def test_notebook_points_at_the_export():
    notebook = (ROOT / "notebooks" / "analysis.ipynb").read_text(encoding="utf-8")
    assert "engagement.csv" in notebook
    assert "data_source" in notebook
