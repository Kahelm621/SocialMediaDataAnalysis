# Live snapshots

This folder starts empty on purpose.

`python scripts/refresh.py` appends real API results here as JSONL:

- `accounts.jsonl` — follower / subscriber counts at each run
- `posts.jsonl` — views, likes, comments, and shares for each post
- `keywords.jsonl` — keyword attention and top titles

Rows are never labeled demo. The collector refuses to write a demo row into this folder.

The GitHub Actions refresh commits new lines so the history keeps growing. Do not delete old lines if you want the charts to remember earlier days.
