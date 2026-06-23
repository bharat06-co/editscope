"""Classification orchestration for P1 (baseline) and P4 (default).

The SOUNDNESS-CRITICAL rule lives here and is fully written:

  P4:  Authorized  <=  (in seed)  OR  (W2 forced-closure, resolver-confirmed)
       Uncertain    <=  non-seed, non-W2, but the W1 router fired (a task test
                        depends on the edit): record risk and abstain. W1 can
                        never authorize.
       Violation    <=  non-seed, non-W2, and W1 did NOT fire: an unjustified
                        out-of-scope edit. This is the canonical P4 decision
                        (matches the validated run_real.outcome("P4")).

The ONLY way a unit becomes Authorized under P4 is seed ∪ resolver-confirmed W2.
This is the invariant tests/test_soundness_invariant.py asserts.
"""
from __future__ import annotations

from .schema import Classification, UnitVerdict, Warrant


def classify_p1(unit: UnitVerdict) -> UnitVerdict:
    """Naive baseline: seed => Authorized, everything else => Violation."""
    if unit.warrant == Warrant.SEED or unit.seed_overlap > 0:
        unit.warrant = Warrant.SEED
        unit.classification = Classification.AUTHORIZED
    else:
        unit.classification = Classification.VIOLATION
    return unit


def classify_p4(unit: UnitVerdict) -> UnitVerdict:
    """Default policy: Authorization = seed ∪ W2.

    For non-seed/non-W2 units: if the W1 router fired (a task test depends on
    the edit) abstain to Closure-uncertain; otherwise flag Violation. W1
    (unit.router.w1_revert_flips_test) is recorded for analysis but is NEVER
    allowed to upgrade a unit to Authorized — it was proven unsound (Run B).
    """
    if unit.warrant == Warrant.SEED or unit.seed_overlap > 0:
        unit.warrant = Warrant.SEED
        unit.classification = Classification.AUTHORIZED
        return unit

    if unit.w2.resolver_confirmed_closure and unit.w2.any_break():
        unit.warrant = Warrant.W2
        unit.classification = Classification.AUTHORIZED
        return unit

    # Non-seed, non-W2: we may NOT authorize.
    unit.warrant = Warrant.NONE
    if unit.router.w1_revert_flips_test:
        # A task test depends on this edit: behavioral coupling is UNSOUND
        # evidence, so we abstain rather than authorize.
        unit.classification = Classification.UNCERTAIN
        unit.note = "W1 router: revert flips a test (risk signal only; not authorized)"
    else:
        # No seed, no forced closure, no test coupling: unjustified out-of-scope edit.
        unit.classification = Classification.VIOLATION
    return unit


def is_soundly_authorized(unit: UnitVerdict) -> bool:
    """Invariant helper: an Authorized verdict must carry seed or resolver-confirmed W2."""
    if unit.classification != Classification.AUTHORIZED:
        return True
    if unit.warrant == Warrant.SEED:
        return True
    return unit.warrant == Warrant.W2 and unit.w2.resolver_confirmed_closure
