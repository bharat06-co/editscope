"""Frozen audit() API entrypoint  —  EditScope oracle (P1: Codebase Lead).

    audit(instruction, repo_before, patch, policy="P4") -> AuditResult

This is the FROZEN call the rest of the project (Track A / Track C) builds
against. The OUTPUT contract (schema.py) and the soundness rule (policy.py)
are final. The three primitives (grounding / partitioner / resolver) are now
wired to the VALIDATED implementation.

The ONLY way a unit becomes Authorized under P4 is seed ∪ resolver-confirmed
W2. W1 (behavioral) is recorded as a risk signal but never authorizes.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional, Union

from . import grounding, partitioner, resolver
from .metric_card import aggregate_metric_card
from .policy import classify_p1, classify_p4
from .schema import AuditResult, MetricCard, Policy, Provenance, UnitVerdict

RepoBefore = Union[str, dict]  # repo path OR {relpath: source} OR raw before-source


def audit(
    instruction: str,
    repo_before: RepoBefore,
    patch: str,
    policy: Union[str, Policy] = Policy.P4,
    *,
    task_tests: Optional[str] = None,
    tests_cmd: Optional[str] = None,
    provenance: Optional[Provenance] = None,
    granularity: str = "unit",
) -> AuditResult:
    """Label every change unit Authorized / Violation / Closure-uncertain.

    Args:
        instruction: the natural-language editing instruction (the seed source).
        repo_before: pre-edit repo (path, {relpath: src}, or raw before-source).
        patch: a unified diff OR the full after-source produced by the agent.
        policy: "P1" (baseline) or "P4" (default).
        task_tests: optional task test source (module-level asserts) for the
            UNSOUND W1 router only. Never affects authorization.
        tests_cmd: reserved for shell-command test execution in real repos.
        provenance: optional provenance block.
    """
    policy = Policy(policy) if not isinstance(policy, Policy) else policy

    # 1) Seed: what the instruction authorizes.
    seed = grounding.ground_seed(instruction, repo_before, patch)

    # 2) Units: minimal compilable clusters of changed code.
    units: list[UnitVerdict] = partitioner.partition_units(repo_before, patch, seed, granularity=granularity)

    # attach task tests (W1 router input only) to each unit
    if task_tests is not None:
        for u in units:
            u._tests = task_tests  # type: ignore[attr-defined]

    # 3) Per-unit warranting + classification.
    classify = classify_p4 if policy == Policy.P4 else classify_p1
    for unit in units:
        if policy == Policy.P4 and (unit.warrant.value != "seed" and unit.seed_overlap == 0):
            # W2: does reverting this unit provably break the program?
            unit.w2 = resolver.resolve_w2(unit, repo_before, patch)
            # W1 router (unsound, risk-only): does reverting flip a task test?
            unit.router = resolver.w1_router_signal(unit, repo_before, patch, tests_cmd)
        classify(unit)

    metric_card: MetricCard = aggregate_metric_card(units, tests_passed=None)
    return AuditResult(
        policy=policy,
        instruction=instruction,
        verdicts=units,
        metric_card=metric_card,
        provenance=provenance or Provenance(resolver=resolver.RESOLVER_ID),
    )


def audit_case(
    instruction: str,
    before: str,
    after: str,
    tests: Optional[str] = None,
    policy: Union[str, Policy] = Policy.P4,
    granularity: str = "unit",
) -> AuditResult:
    """Validated convenience wrapper for before/after source pairs (CanItEdit).

    Equivalent to audit(instruction, before, after, policy, task_tests=tests)
    where `after` is passed as the whole-file patch.
    """
    return audit(instruction, before, after, policy, task_tests=tests, granularity=granularity)


def save_audit(result: AuditResult, path: str) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(result.to_json(), indent=2), encoding="utf-8")
