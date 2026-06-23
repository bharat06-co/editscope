"""Behavior-preservation parity harness for the FROZEN audit() API.

Re-runs the CanItEdit benchmark (gold real-edit units + injected violation
mutants) but produces EVERY verdict through the frozen `audit_case()` entrypoint
instead of the legacy `run_real.outcome()` decision function.

Writes results/metrics_oracle.json in the SAME schema as the validated
results/metrics_real.json, so the two can be diffed directly. Only the FROZEN
policies are emitted: P1 (naive baseline) and P4 (default oracle). P2/P3/P5 are
research baselines that live in the run_real harness, outside the frozen API.

Run (from the folder whose child package is scope_oracle, e.g.
C:\\Users\\bhara\\Desktop\\scope_auditor_real):
    py -m scope_oracle.parity_real --data .\\canitedit --limit 102

Then diff results/metrics_oracle.json against your results/metrics_real.json.
Headline parity target (n=95): P1 collateral_fpr ~0.538; P4 collateral_fpr
~0.008, violation_recall ~1.0, wrongly_allowed 0 (soundness).
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import random
import statistics
import sys
from pathlib import Path

from . import audit_case
from .grounding import extract
from .mutate import make as make_mutants
from .partitioner import changed_units, touched_names
from .resolver import _run_tests_src
from .schema import Classification

# Frozen policies only (the audit() API commits to P1 baseline + P4 default).
POLICIES = ["P1", "P4"]

_VIOLATION = Classification.VIOLATION.value
_AUTHORIZED = Classification.AUTHORIZED.value
_UNCERTAIN = Classification.UNCERTAIN.value


def _load_jsonl(path: Path):
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            yield json.loads(line)


def load_cases(root: Path):
    """CanItEdit loader (recognizes instruction_descriptive / instruction_lazy)."""
    files = list(root.rglob("*.jsonl")) + list(root.rglob("*.json"))
    for f in files:
        try:
            rows = list(_load_jsonl(f)) if f.suffix == ".jsonl" else json.loads(f.read_text(encoding="utf-8"))
            if isinstance(rows, dict):
                rows = rows.get("data") or rows.get("examples") or []
            for i, row in enumerate(rows):
                b = row.get("before")
                a = row.get("after")
                d = (
                    row.get("instruction_descriptive")
                    or row.get("instruction_lazy")
                    or row.get("descriptive")
                    or row.get("instruction")
                )
                tests = row.get("tests", "")
                if b and a and d:
                    yield {
                        "problem_id": row.get("id", f"{f.name}:{i}"),
                        "before": b,
                        "after": a,
                        "prompt": d,
                        "tests": tests,
                    }
        except Exception:
            continue


def ci(vals):
    if not vals:
        return [None, None]
    rng = random.Random(20260617)
    boots = [statistics.mean(rng.choice(vals) for _ in vals) for _ in range(1000)]
    boots.sort()
    return [boots[24], boots[974]]


def _classify_map(prompt, before, after, tests, policy):
    """Run frozen audit_case once; return {raw_name: classification_value}."""
    r = audit_case(prompt, before, after, tests=tests or None, policy=policy)
    out = {}
    for u in r.verdicts:
        out[getattr(u, "_raw_name", u.unit_id)] = u.classification.value
    return out, r.verdicts


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="parity_real")
    ap.add_argument("--data", default=os.environ.get("CANITEDIT_DIR", "./canitedit"))
    ap.add_argument("--limit", type=int, default=102)
    ap.add_argument("--out", default="results/metrics_oracle.json")
    args = ap.parse_args(argv)
    root = Path(args.data)

    rows = []
    skips = []
    attempted = 0
    gold_ok = 0
    loaded_any = False
    if not root.exists():
        skips.append({"problem_id": "dataset", "reason": "dataset path not found"})

    for case in load_cases(root):
        loaded_any = True
        if gold_ok >= args.limit:
            break
        attempted += 1
        pid = str(case["problem_id"])
        if not _run_tests_src(case["after"], case.get("tests", "")):
            skips.append({"problem_id": pid, "reason": "gold tests did not pass here"})
            continue
        gold_ok += 1

        g = extract(case["prompt"], case["before"])
        real_units = changed_units(case["before"], case["after"])
        named = touched_names(real_units) | g.names
        label_of = {u.name: ("seed" if u.name in g.names else "collateral") for u in real_units}

        # ---- REAL units: route the whole before->after through frozen audit_case.
        for pol in POLICIES:
            try:
                cmap, _ = _classify_map(case["prompt"], case["before"], case["after"], case.get("tests", ""), pol)
            except Exception as exc:  # noqa: BLE001
                skips.append({"problem_id": pid, "reason": f"audit_case(real) failed: {exc}"})
                continue
            for name, cls in cmap.items():
                rows.append({
                    "problem_id": pid, "policy": pol, "unit_id": f"gold::{name}",
                    "family": "gold", "true_label": label_of.get(name, "collateral"), "outcome": cls,
                })

        # ---- MUTANTS: inject violations into non-seed functions; route gold->mutant.
        for m in make_mutants(case["after"], named):
            for pol in POLICIES:
                try:
                    cmap, verdicts = _classify_map(case["prompt"], case["after"], m.src, case.get("tests", ""), pol)
                except Exception as exc:  # noqa: BLE001
                    skips.append({"problem_id": pid, "reason": f"audit_case(mutant {m.family}) failed: {exc}"})
                    continue
                cls = cmap.get(m.name)
                if cls is None and verdicts:
                    cls = verdicts[0].classification.value
                if cls is None:
                    continue
                rows.append({
                    "problem_id": pid, "policy": pol, "unit_id": f"mut_{m.family}::{m.name}",
                    "family": m.family, "true_label": "violation", "outcome": cls,
                })

    if root.exists() and not loaded_any:
        skips.append({"problem_id": "dataset", "reason": "no benchmark records found in local checkout"})

    Path("results").mkdir(exist_ok=True)
    with open("results/per_unit_oracle.csv", "w", newline="", encoding="utf-8") as f:
        fields = ["problem_id", "policy", "unit_id", "family", "true_label", "outcome"]
        wr = csv.DictWriter(f, fieldnames=fields)
        wr.writeheader()
        wr.writerows(rows)

    metrics = {
        "data_revision": "unpinned",
        "source": "frozen audit_case() (scope_oracle.parity_real)",
        "coverage": {"attempted": attempted, "passed_gold": gold_ok, "skipped": skips},
    }
    byp = {}
    for pol in POLICIES:
        rr = [r for r in rows if r["policy"] == pol]
        coll = [r["outcome"] == _VIOLATION for r in rr if r["true_label"] in {"collateral", "seed"}]
        vio = [r["outcome"] == _VIOLATION for r in rr if r["true_label"] == "violation"]
        wrong_allow = sum(1 for r in rr if r["true_label"] == "violation" and r["outcome"] == _AUTHORIZED)
        third = [r["outcome"] == _UNCERTAIN for r in rr]
        byp[pol] = {
            "collateral_fpr": statistics.mean(coll) if coll else None,
            "collateral_fpr_ci": ci(coll),
            "violation_recall": statistics.mean(vio) if vio else None,
            "violation_recall_ci": ci(vio),
            "wrongly_allowed_count": wrong_allow,
            "third_outcome_rate": statistics.mean(third) if third else None,
        }
    metrics["policies"] = byp
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(metrics, indent=2), encoding="utf-8")

    # ---- console summary + validated parity targets -----------------------
    TARGET = {
        "P1": {"collateral_fpr": 0.538},
        "P4": {"collateral_fpr": 0.0077, "violation_recall": 1.0, "wrongly_allowed_count": 0},
    }
    print(f"coverage: attempted={attempted} passed_gold={gold_ok} skipped={len(skips)}")
    for pol in POLICIES:
        p = byp[pol]
        t = TARGET[pol]
        print(f"\n[{pol}]  (verdicts via frozen audit_case)")
        print(f"  collateral_fpr   = {p['collateral_fpr']}   (validated ~ {t.get('collateral_fpr')})")
        print(f"  violation_recall = {p['violation_recall']}   (validated ~ {t.get('violation_recall', '-')})")
        print(f"  wrongly_allowed  = {p['wrongly_allowed_count']}   (MUST be 0 for soundness)")
        print(f"  uncertain_rate   = {p['third_outcome_rate']}")
    soundness_ok = all(byp[pol]["wrongly_allowed_count"] == 0 for pol in POLICIES)
    print(f"\nsoundness (wrongly_allowed==0 everywhere): {'PASS' if soundness_ok else 'FAIL'}")
    print(f"wrote {args.out} and results/per_unit_oracle.csv")
    return 0 if soundness_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
