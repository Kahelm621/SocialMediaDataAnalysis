"""Load a local .env file without extra dependencies.

Values already set in the environment are left alone, so GitHub Actions
secrets win over a leftover .env on a developer machine.
"""

from __future__ import annotations

import os
from pathlib import Path


def load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def env_value(env: dict, name: str) -> str:
    return (env.get(name) or "").strip()
