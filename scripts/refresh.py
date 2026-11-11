#!/usr/bin/env python3
"""Collect live stats when keys exist, then rebuild the dashboard if data changed.

Demo data is never written into data/snapshots. With no keys, an existing
dashboard is left untouched so a scheduled run does not create an empty commit.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from creator_analytics.config import load_config  # noqa: E402
from creator_analytics.dashboard import build_dashboard  # noqa: E402
from creator_analytics.envfile import load_env_file  # noqa: E402
from creator_analytics.pipeline import collect  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Collect live stats and rebuild the dashboard.")
    parser.add_argument(
        "--search",
        action="store_true",
        help="Force the watchlist keyword search even if this is not the daily slot. Each phrase costs about 102 YouTube units.",
    )
    args = parser.parse_args()
    load_env_file(ROOT / ".env")
    config = load_config(ROOT / "config" / "tracked.yaml")
    print("Creator analytics refresh")
    print("Reading config/tracked.yaml")
    result = collect(config, os.environ, ROOT / "data" / "snapshots", force_search=args.search)
    for item in result["statuses"]:
        account = f" ({item['account']})" if item.get("account") else ""
        print(f"[{item['state']}] {item['source']}{account}: {item['detail']}")
    attempted = [item for item in result["statuses"] if item["state"] != "skipped"]
    dashboard = ROOT / "dashboard" / "index.html"
    if result["new_rows"] or any(item["state"] == "error" for item in result["statuses"]) or not dashboard.exists():
        build_dashboard(ROOT, statuses=result["statuses"] if attempted else None)
        print(f"Rebuilt dashboard/. New snapshot rows: {result['new_rows']}.")
    else:
        print("No API keys set, and the dashboard is already built. Nothing to commit.")
        print("Add keys to .env or GitHub Actions secrets, then run this again.")
    print("Demo rows stay in data/demo. They are not copied into data/snapshots.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
