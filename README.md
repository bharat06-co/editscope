# EditScope — Scope-Faithful Coding Agents (canonical repo)

**Owner:** P1 (Oracle / Codebase Lead). This is the *one* canonical repo. Branch hygiene, pinned deps, reproducible configs.

EditScope is a **sound, abstaining, instruction-conditioned scope oracle** for AI coding agents.
Given `(instruction, repo_before, patch)` it labels every change unit **Authorized**, **Violation**, or **Closure-uncertain**.

- **Authorization = seed ∪ W2.** W2 = forced closure verified by a *symbolic* resolver (no LLM inside).
- **W1 is unsound** → demoted to a *risk router* that sends non-seed/non-W2 units to **Closure-uncertain**, never to Authorized.
- **Guarantee:** soundness (never wrongly authorize), not completeness. Abstain instead of guessing.
- **Default policy P4** (W2 + W1 router). **Baseline P1** (naive: every non-seed = Violation).

## Quickstart (reproducibility gate — Phase 0 acceptance)
```bash
git clone <this-repo> && cd editscope
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
pip install -e .                 # editable install (uses pyproject.toml)

# Frozen oracle suite — no dataset or network required:
python -m scope_oracle.tests.test_audit_freeze
python -m scope_oracle.tests.test_grounding_precision
python -m scope_oracle.tests.test_intra_unit_hardening

# CanItEdit parity slice — requires the pinned dataset available locally:
python -m scope_oracle.parity_real --data ./canitedit --limit 102
```
## Track A — scope-faithful editing benchmark (`track_a/`)

Track A runs coding agents over CanItEdit and scores each edit with the frozen
`scope_oracle.audit_case()` API. Run every tool as a module from the repo root:

```bash
# 1. fetch + pin the CanItEdit dataset locally (-> ./canitedit)
python -m track_a.fetch_canitedit

# 2. run an agent and log (instruction, before, after) per problem.
#    --agent dry_run replays gold edits and needs no API key (good smoke test);
#    model agents call Groq (llama-3.1-8b-instant, llama-3.3-70b-versatile, qwen3-32b).
python -m track_a.run_agents --agent dry_run --limit 3

# 3. re-audit the logged runs through the frozen oracle
python -m track_a.rescore --runs results_track_a/runs.jsonl
```

Downstream analysis: `summarize` (pass / scope-violation rates + bootstrap CIs per
granularity), `compare` (P1 vs P4 / cross-agent), and `compute_collateral_fpr`.
Human-agreement utilities: `sample_units` + `render_sheet` + `make_smoke_labels`
build a labeling sheet from sampled units, and `compute_kappa` reports oracle↔human
Cohen's κ. `demo_card` renders a standalone demo metric card. Each tool supports
`--help` for its flags.

**Phase 0 acceptance:** a teammate can clone and run the frozen suite end-to-end from this README alone; zero unverified citation IDs in shared docs.

**Phase 1 acceptance gate:** reproduce collateral FP **0.53 → 0.007 @ recall 1.00**, **0 wrongly-authorized** on CanItEdit (n≈102); soundness invariant holds on the adversarial n=20 (W1-alone is 20/20 unsound and correctly routed to Uncertain).

## Package layout
```
scope_oracle/            # CANONICAL frozen package (the audit() API lives here)
  grounding.py     # seed extraction from instruction
  mutate.py        # revert/mutation harness
  partitioner.py   # minimal compilable change units
  intra_unit.py    # opt-in statement-level smuggle slicer (weakness #9)
  resolver.py      # symbolic closure: py_compile + pyflakes + mypy + callgraph
  callgraph.py     # cross-file forced-closure (import/call graph)
  policy.py        # P1..P5 classification orchestration
  audit.py         # frozen audit() / audit_case() API entrypoint
  metric_card.py   # metric-card aggregation
  schema.py        # frozen dataclasses for JSON output
  parity_real.py   # CanItEdit parity runner (real entrypoint)
  run_real.py      # thin dataset-loader stub (NOT the parity entrypoint)
  tests/           # test_audit_freeze, test_grounding_precision, test_intra_unit_hardening
track_a/                 # Track A agent benchmark harness (runs agents, re-scores via the oracle)
  fetch_canitedit.py     # download + pin the CanItEdit dataset to ./canitedit
  run_agents.py          # run an agent (dry_run/gold or Groq models) and log outputs
  rescore.py             # re-audit logged runs through scope_oracle.audit_case()
  summarize.py           # pass / scope-violation rates + bootstrap CIs per granularity
  compare.py             # policy / cross-agent comparison
  compute_collateral_fpr.py  # collateral false-flag rate
  sample_units.py        # sample change units for human labeling
  render_sheet.py        # build the human-labeling sheet
  make_smoke_labels.py   # generate smoke-test labels
  compute_kappa.py       # oracle <-> human Cohen's kappa
  demo_card.py           # standalone demo metric card

# Experiment scaffolding (NOT part of the frozen API, not pip-installed):
cie_harness/             # adversarial probe (n=20) harness
```

> Note: `scope_oracle.run_real` is an intentional dataset-loader stub. The real
> CanItEdit parity entrypoint is `scope_oracle.parity_real`.

## Hard constraints (non-negotiable)
- No circular eval — human slice + Cohen's κ before claiming numbers.
- API-first, GPU-later (QLoRA 7B).
- Checker stays **symbolic** — no LLM inside the oracle.
- Sandbox network OFF when auditing patches.
- Honest claims only — soundness not completeness; never report an unmeasured number.
