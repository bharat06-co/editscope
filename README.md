# EditScope — a sound oracle for scope-faithful code edits

EditScope audits a code edit and decides, per change unit, whether it was
**Authorized**, a **Violation** (out-of-scope creep), or **Closure-uncertain**.
It is *sound* in a trusted-oracle regime: it never wrongly authorizes an
out-of-scope edit, though it may defer to *uncertain*.

The checker is fully **symbolic** — no LLM and no code execution in the oracle
itself. It is the measurement instrument behind the *Scope-Faithful Coding
Agents* study (Track A: measure agent over-editing; Track C: reduce it).

## Headline result (real CanItEdit, n≈95)

| Policy | Collateral false-flag rate | Violation recall | Wrongly authorized |
|---|---|---|---|
| P1 — naive (flag every non-seed) | ~0.54 | 1.00 | 0 |
| **P4 — W2 + W1 router (default)** | **~0.008** | **1.00** | **0** |

P4 cuts the naive false-flag rate ~70× at recall 1.0 with **zero** unsound
authorizations. Reproduced through the frozen `audit()` API (see `parity_real.py`).

## Install

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt   # optional: pyflakes + mypy sharpen the resolver
```

The core has no hard third-party dependency; `pyflakes` and `mypy` are used by
the resolver when present and auto-skipped otherwise.

## Quick start

```python
from scope_oracle import audit

before = {"main.py": "def run():\n    return None\n"}
after  = {"main.py": "def run():\n    return greeting()\n",
          "util.py": "def greeting():\n    return 'hi'\n"}

result = audit("Make run() return a greeting", before, after, policy="P4")
for v in result.verdicts:
    print(v.unit_id, v.classification, v.warrant)
print(result.metric_card)
```

`audit_case(instruction, before, after, tests=None, policy="P4")` is the
single-file convenience wrapper.

## The mechanism

- **Unit** — a minimal compilable cluster of changed code.
- **Seed** — names the instruction grounds in the existing code (authorized intent).
- **W2 (forced closure)** — reverting the unit *provably* breaks compilation,
  name resolution, or imports (incl. **cross-file** call-graph closure).
- **W1 (behavioral)** — demoted to a *risk router*: a non-seed/non-W2 unit
  whose revert flips a test is routed to **Uncertain**, never auto-authorized
  (W1-as-warrant was proven unsound).
- **Soundness invariant:** `Authorized ⇺ seed ∪ resolver-confirmed W2`.

Policies **P1** (naive baseline) and **P4** (default) are frozen; the research
policies P2/P3/P5 live in the upstream harness.

## Resolver

Symbolic only: `py_compile` + `pyflakes` + `mypy --strict` (auto-skipped if
absent) + a **cross-file call-graph / import-graph** closure check. Known limits
(out of scope, treated conservatively as no-closure): dynamic dispatch,
`*`-imports, runtime attribute resolution. See `scope_oracle/FREEZE.md`.

## Tests

```bash
python3 -m scope_oracle.tests.test_audit_freeze   # 7 freeze tests, prints ALL PASS
```

The suite locks the soundness invariant, the canonical P4 decisions, and the
cross-file forced-closure case.

## Layout

```
scope_oracle/
  __init__.py        public surface (audit, audit_case, schema enums)
  audit.py           orchestration + resolver gating
  policy.py          P1 / P4 classification
  schema.py          UnitVerdict / W2Evidence / MetricCard (schema v1.0.0)
  grounding.py       seed extraction
  partitioner.py     unit partitioning + whole-repo recovery
  resolver.py        W2 resolver (compile / names / imports)
  callgraph.py       symbolic cross-file import-graph closure
  mutate.py          mutation injector (parity harness)
  parity_real.py     re-runs the benchmark through the frozen API
  FREEZE.md          frozen-contract notes
  tests/             freeze suite
```

## License

MIT — see `LICENSE`.
