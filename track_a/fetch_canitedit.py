"""Fetch CanItEdit -> local ./canitedit/canitedit_test.jsonl (Track A)."""
from datasets import load_dataset
from pathlib import Path
import json

REVISION = "3c07f38b1f9385f3214fcea94d4664c79df0d36a"   # was None

ds = load_dataset("nuprl/CanItEdit", revision=REVISION)
split = "test" if "test" in ds else list(ds.keys())[0]
rows = ds[split]

out = Path("canitedit"); out.mkdir(exist_ok=True)
fp = out / "canitedit_test.jsonl"
with open(fp, "w", encoding="utf-8") as f:
    for row in rows:
        f.write(json.dumps(dict(row)) + "\n")
print(f"wrote {len(rows)} rows to {fp}  (split='{split}')")
