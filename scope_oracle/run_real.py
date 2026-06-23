"""Dataset runner. Drives audit() over CanItEdit / agent-generated patches and
emits the metric card. Orchestration written; per-row wiring depends on the
migrated primitives + pinned dataset revision.

Usage:
    python -m scope_oracle.run_real --dataset canitedit --policy P4
"""
from __future__ import annotations

import argparse
import json
import sys

from .schema import Policy

# CanItEdit: HF nuprl/CanItEdit test split, 105 problems; ids 25/52/78 skipped => 102.
CANITEDIT_SKIP_IDS = {25, 52, 78}
CANITEDIT_HF = "nuprl/CanItEdit"


def _load_dataset(name: str):
    if name != "canitedit":
        raise SystemExit(f"unknown dataset: {name!r}")
    raise NotImplementedError(
        "MIGRATE run_real._load_dataset: load nuprl/CanItEdit test split at a "
        "pinned revision; drop ids 25/52/78; yield (instruction, repo_before, patch)."
    )


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="run_real")
    ap.add_argument("--dataset", default="canitedit")
    ap.add_argument("--policy", default="P4", choices=[p.value for p in Policy])
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--out", default="runs/metric_card.json")
    args = ap.parse_args(argv)

    # from .audit import audit  # enable once primitives are migrated
    rows = _load_dataset(args.dataset)  # raises until migrated
    _ = (rows, args)
    print(json.dumps({"status": "primitives-not-migrated"}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
