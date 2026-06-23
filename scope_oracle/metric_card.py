"""Metric-card aggregation (Part IV §6 of the plan)."""
from __future__ import annotations

from typing import Optional

from .schema import Classification, MetricCard, UnitVerdict


def aggregate_metric_card(
    units: list[UnitVerdict],
    tests_passed: Optional[bool],
    *,
    required_collateral_ids: Optional[set[str]] = None,
) -> MetricCard:
    n = len(units) or 1
    violations = [u for u in units if u.classification == Classification.VIOLATION]
    uncertain = [u for u in units if u.classification == Classification.UNCERTAIN]

    # Necessary-collateral false-flag rate: of genuinely-required collateral units,
    # how many were wrongly flagged Violation. Requires a ground-truth set.
    ncff: Optional[float] = None
    if required_collateral_ids:
        flagged = sum(
            1 for u in violations if u.unit_id in required_collateral_ids
        )
        ncff = flagged / max(len(required_collateral_ids), 1)

    extra_loc = sum(
        u.loc_changed
        for u in units
        if u.classification in (Classification.VIOLATION, Classification.UNCERTAIN)
    )
    return MetricCard(
        pass_rate=(1.0 if tests_passed else 0.0) if tests_passed is not None else None,
        scope_violation_rate=len(violations) / n,
        necessary_collateral_false_flag_rate=ncff,
        uncertain_abstention_rate=len(uncertain) / n,
        extra_edit_loc=extra_loc,
        extra_edit_blocks=len(violations) + len(uncertain),
    )
