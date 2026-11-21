#!/usr/bin/env python3
"""Rebuild the static dashboard from snapshots, or from demo data if none exist."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from creator_analytics.dashboard import build_dashboard  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the static creator dashboard.")
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Output folder. Defaults to dashboard/ in the repo.",
    )
    args = parser.parse_args()
    destination = build_dashboard(ROOT, out_dir=args.out)
    print(f"Wrote {destination / 'index.html'}")
    print("Open that file in a browser. Charts load from the internet (Plotly).")
    print("The notebook export is data/exports/engagement.csv.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
