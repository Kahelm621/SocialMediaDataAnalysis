#!/usr/bin/env python3
"""Print the public title, description, tags, and SEO checklist for one video.

Costs 1 YouTube Data API unit. Accepts a video id or a watch URL.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import requests  # noqa: E402

from creator_analytics.collectors.youtube import fetch_videos  # noqa: E402
from creator_analytics.config import load_config  # noqa: E402
from creator_analytics.envfile import env_value, load_env_file  # noqa: E402
from creator_analytics.scoring import score_video  # noqa: E402


def video_id(value: str) -> str:
    if "youtube.com" in value or "youtu.be" in value:
        parsed = urlparse(value)
        if parsed.netloc.endswith("youtu.be"):
            return parsed.path.strip("/")
        query = parse_qs(parsed.query)
        if query.get("v"):
            return query["v"][0]
    return value.strip()


def main() -> int:
    parser = argparse.ArgumentParser(description="Analyze one public YouTube video.")
    parser.add_argument("video", help="Video id or URL")
    parser.add_argument("--keyword", action="append", default=[], help="Phrase to score against. Repeatable. Defaults to config/tracked.yaml.")
    args = parser.parse_args()
    load_env_file(ROOT / ".env")
    api_key = env_value(os.environ, "YOUTUBE_API_KEY")
    if not api_key:
        print("Set YOUTUBE_API_KEY in .env first.")
        return 1
    config = load_config(ROOT / "config" / "tracked.yaml")
    keywords = args.keyword or [item["phrase"] for item in config["keywords"]]
    videos = fetch_videos(requests.Session(), api_key, [video_id(args.video)])
    if not videos:
        print("YouTube did not return that video. Check the id, or the video may be private.")
        return 1
    video = videos[0]
    scored = score_video(video, keywords, config["recommendations"]["keyword_front_chars"])
    print(video["title"])
    print(video["url"])
    print(f"Channel: {video['channel_title']}")
    print(f"Views {video['views']}  Likes {video['likes']}  Comments {video['comments']}")
    print(f"Duration seconds: {video['duration_seconds']}")
    print(f"Tags: {', '.join(video['tags']) or 'none returned'}")
    print()
    print((video.get("description") or "")[:500])
    print()
    print(f"SEO score {scored['score']} / 100 ({scored['earned']} of {scored['possible']} points)")
    for check in scored["checks"]:
        mark = "ok" if check["ok"] else "fix"
        print(f"- [{mark}] {check['name']} ({check['earned']}/{check['possible']})")
        if check["fix"]:
            print(f"    {check['fix']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
