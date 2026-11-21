# Demo data

Every row in the `.jsonl` files here is fake. `is_demo` is true and `source` is `"demo"`.

The dashboard uses these files only when `data/snapshots/` has no real rows. A live collection never copies them into `data/snapshots`. Regenerate with:

```bash
python scripts/make_demo.py
```
