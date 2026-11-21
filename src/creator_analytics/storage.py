"""JSONL snapshots. Demo rows are refused so they cannot land in data/snapshots."""

from __future__ import annotations

import json
from pathlib import Path


def dedup_key(row: dict) -> tuple:
    record_type = row.get("record_type")
    if record_type == "post":
        ident = (row.get("relationship", "own"), row.get("post_id"))
    elif record_type == "account":
        ident = (row.get("relationship", "own"), row.get("account_name"))
    elif record_type == "trending_video":
        ident = (row.get("region"), row.get("category_id"), row.get("post_id"))
    elif record_type == "keyword_research":
        ident = row.get("keyword")
    else:
        ident = row.get("keyword")
    return (
        record_type,
        row.get("platform"),
        row.get("account_name", ""),
        ident,
        row.get("collected_at"),
    )


def _read_jsonl(path: Path) -> list[dict]:
    rows = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{path} line {line_number} is not valid JSON") from exc
        if not isinstance(row, dict):
            raise ValueError(f"{path} line {line_number} is not a JSON object")
        rows.append(row)
    return rows


def load_rows(directory: Path) -> list[dict]:
    if not directory.exists():
        return []
    rows = []
    for path in sorted(directory.glob("*.jsonl")):
        rows.extend(_read_jsonl(path))
    return rows


def append_jsonl(path: Path, rows: list[dict]) -> int:
    """Append unseen rows. Demo rows are refused so they cannot enter snapshots."""
    for row in rows:
        if row.get("is_demo"):
            raise RuntimeError(
                "Refusing to write demo data into snapshots. Demo rows belong in data/demo only."
            )
    path.parent.mkdir(parents=True, exist_ok=True)
    existing_rows = _read_jsonl(path) if path.exists() else []
    if any(row.get("is_demo") for row in existing_rows):
        raise RuntimeError(
            f"{path} already contains demo data. Sample rows stay in data/demo and are not mixed with real stats."
        )
    existing = {dedup_key(row) for row in existing_rows}
    wrote = 0
    with path.open("a", encoding="utf-8") as handle:
        for row in rows:
            key = dedup_key(row)
            if key in existing:
                continue
            handle.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")
            existing.add(key)
            wrote += 1
    return wrote
