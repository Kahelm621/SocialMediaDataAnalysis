#!/usr/bin/env python3
"""Regenerate the labeled sample history in data/demo.

This does not touch data/snapshots.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from creator_analytics.demo_data import write_demo  # noqa: E402


def main() -> int:
    destination = ROOT / "data" / "demo"
    write_demo(destination)
    print(f"Wrote labeled demo snapshots to {destination}")
    print("Every row has is_demo true. These are not real stats.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
