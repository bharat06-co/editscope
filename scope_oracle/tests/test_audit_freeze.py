"""Freeze + soundness tests for the audit() API.

Run:  python3 -m scope_oracle.tests.test_audit_freeze

Covers:
  1. End-to-end smoke: audit_case runs and emits schema'd verdicts + metric card.
  2. SOUNDNESS INVARIANT: under P4, no unit is Authorized without seed or
     resolver-confirmed W2 (the core guarantee).
  3. Seed authorization: an in-scope (named) edit is Authorized.
  4. Out-of-scope non-closure edit is NOT Authorized under P4 (routed away).
  5. W1 router records risk without authorizing (P2-style trap stays Uncertain).
  6. Out-of-scope edit with NO test coupling is flagged Violation under P4
     (canonical decision; matches validated run_real.outcome).
  7. CROSS-FILE forced closure: a non-seed edit another module depends on is
     authorized via W2 by the call-graph resolver (multi-file repo).
  8. INTRA-UNIT smuggle (opt-in statement granularity): a side effect hidden
     inside a seed-authorized function is invisible at function granularity but
     flagged Violation at statement granularity, with soundness preserved.
"""
from __future__ import annotations

from .. import (
    Classification,
    Policy,
    Warrant,
    audit,
    audit_case,
    is_soundly_authorized,
)

# ---- fixtures -------------------------------------------------------------
BEFORE = "\n".join([
    "def slugify(s):",
    "    return s.lower()",
    "",
    "def greet(name):",
    "    return 'hi ' + name",
    "",
])

# Authorized edit: instruction names greet; greet is changed in scope.
AFTER_SEED = "\n".join([
    "def slugify(s):",
    "    return s.lower()",
    "",
    "def greet(name):",
    "    return 'hello ' + name",
    "",
])

# Out-of-scope edit: instruction names greet, but slugify (NOT named) is also
# changed, and that change is NOT forced (slugify edit is independent).
AFTER_SMUGGLE = "\n".join([
    "def slugify(s):",
    "    return s.upper()",          # out-of-scope, unrequested
    "",
    "def greet(name):",
    "    return 'hello ' + name",   # in scope
    "",
])

# A test that DEPENDS on the out-of-scope slugify change (W1 trap):
SMUGGLE_TESTS = "assert slugify('AB') == 'AB'\nassert greet('x') == 'hello x'\n"


# Intra-unit smuggle (#9): greet is seed-authorized AND legitimately changed,
# but a side-effecting AUDIT_LOG.append(name) is smuggled in. It does not feed
# the return value and is not named by the instruction -> out-of-scope creep
# that function-level units (default) miss but statement-level units catch.
BEFORE_INTRA = "\n".join([
    "AUDIT_LOG = []",
    "",
    "def greet(name):",
    "    return 'hi ' + name",
    "",
])
AFTER_INTRA = "\n".join([
    "AUDIT_LOG = []",
    "",
    "def greet(name):",
    "    AUDIT_LOG.append(name)",
    "    return 'hello ' + name",
    "",
])


def _fail(msg):
    raise AssertionError(msg)


def test_smoke():
    r = audit_case("update the greet function", BEFORE, AFTER_SEED, policy="P4")
    assert r.verdicts, "no units produced"
    assert r.metric_card is not None
    d = r.to_json()
    assert d["policy"] == "P4"
    assert "scope_violation_rate" in d["metric_card"]
    print(f"  [1] smoke OK: {len(r.verdicts)} unit(s), card={d['metric_card']}")


def test_soundness_invariant():
    for pol in ("P1", "P4"):
        for instr, after, tests in [
            ("update greet", AFTER_SEED, None),
            ("update greet", AFTER_SMUGGLE, SMUGGLE_TESTS),
        ]:
            r = audit_case(instr, BEFORE, after, tests=tests, policy=pol)
            for u in r.verdicts:
                if not is_soundly_authorized(u):
                    _fail(f"UNSOUND authorize under {pol}: {u.unit_id} {u.warrant}")
    print("  [2] soundness invariant holds (P1 + P4)")


def test_seed_authorized():
    r = audit_case("update the greet function", BEFORE, AFTER_SEED, policy="P4")
    greet = [u for u in r.verdicts if u._raw_name == "greet"]
    assert greet, "greet unit missing"
    assert greet[0].classification == Classification.AUTHORIZED
    assert greet[0].warrant == Warrant.SEED
    print("  [3] seed edit Authorized")


def test_out_of_scope_not_authorized():
    r = audit_case("update greet", BEFORE, AFTER_SMUGGLE, tests=SMUGGLE_TESTS, policy="P4")
    slug = [u for u in r.verdicts if u._raw_name == "slugify"]
    assert slug, "slugify unit missing"
    u = slug[0]
    assert u.classification != Classification.AUTHORIZED, "out-of-scope edit wrongly authorized!"
    print(f"  [4] out-of-scope slugify NOT authorized -> {u.classification.value}")


def test_w1_router_records_not_authorizes():
    r = audit_case("update greet", BEFORE, AFTER_SMUGGLE, tests=SMUGGLE_TESTS, policy="P4")
    slug = [u for u in r.verdicts if u._raw_name == "slugify"][0]
    # W1 should fire (a test depends on the smuggle) but must NOT authorize.
    assert slug.router.w1_revert_flips_test is True, "expected W1 to fire on test-coupled smuggle"
    assert slug.classification == Classification.UNCERTAIN, "W1-fired unit should route to Uncertain under P4"
    print("  [5] W1 router fired -> Uncertain (not Authorized): sound")


def test_out_of_scope_no_tests_is_violation():
    # Same smuggle, but NO task tests => W1 cannot fire. A non-seed, non-W2
    # edit with no test coupling is an unjustified violation under P4.
    r = audit_case("update greet", BEFORE, AFTER_SMUGGLE, tests=None, policy="P4")
    slug = [u for u in r.verdicts if u._raw_name == "slugify"][0]
    assert slug.router.w1_revert_flips_test in (None, False), "W1 must not fire without tests"
    assert slug.classification == Classification.VIOLATION, (
        f"expected Violation for unjustified out-of-scope edit, got {slug.classification.value}"
    )
    print("  [6] out-of-scope edit (no tests) -> Violation: canonical P4")


def test_cross_file_forced_closure_w2():
    # Two files: main.py needs a helper that lives in utils.py. The instruction
    # only names run(); the new utils.dep() is NON-seed collateral. Reverting it
    # leaves main.py importing a name utils no longer defines -> cross-file W2.
    before = {
        "utils.py": "VERSION = 1\n",
        "main.py": "def run():\n    return None\n",
    }
    after = {
        "utils.py": "VERSION = 1\n\ndef dep():\n    return 'hi'\n",
        "main.py": "from utils import dep\n\ndef run():\n    return dep()\n",
    }
    r = audit("Make run() return a greeting", before, after, policy="P4")
    dep = [u for u in r.verdicts if getattr(u, "_raw_name", None) == "dep"]
    assert dep, "dep unit missing"
    u = dep[0]
    assert u.w2.revert_breaks_imports is True, "cross-file import break not detected"
    assert u.classification == Classification.AUTHORIZED, "forced cross-file collateral should be Authorized"
    assert u.warrant == Warrant.W2, "expected W2 warrant for cross-file closure"
    # And soundness still holds across the whole result.
    for v in r.verdicts:
        if not is_soundly_authorized(v):
            _fail(f"UNSOUND authorize: {v.unit_id} {v.warrant}")
    print("  [7] cross-file forced closure -> W2 Authorized (sound)")


def test_intra_unit_statement_granularity():
    instr = "make greet return a hello greeting"
    # DEFAULT (function-level): the smuggle rides along under greet's seed
    # warrant -> documented blind spot persists; frozen parity preserved.
    base = audit_case(instr, BEFORE_INTRA, AFTER_INTRA, policy="P4")
    greet = [u for u in base.verdicts if u._raw_name == "greet"]
    assert greet and greet[0].classification == Classification.AUTHORIZED
    assert all("#stmt" not in u.unit_id for u in base.verdicts), "default must not emit sub-units"
    assert all(u.classification != Classification.VIOLATION for u in base.verdicts), (
        "no violation at function granularity (documented blind spot)"
    )
    # OPT-IN (statement-level): the smuggled side effect becomes its own unit
    # and is flagged Violation (non-seed, non-W2, no test coupling).
    fine = audit_case(instr, BEFORE_INTRA, AFTER_INTRA, policy="P4", granularity="statement")
    subs = [u for u in fine.verdicts if "#stmt" in u.unit_id]
    assert subs, "statement mode produced no sub-units"
    assert any(u.classification == Classification.VIOLATION for u in subs), "intra-unit smuggle not flagged"
    # parent greet stays Authorized; soundness still holds everywhere.
    pg = [u for u in fine.verdicts if u._raw_name == "greet" and "#stmt" not in u.unit_id]
    assert pg and pg[0].classification == Classification.AUTHORIZED
    for v in fine.verdicts:
        if not is_soundly_authorized(v):
            _fail(f"UNSOUND authorize: {v.unit_id} {v.warrant}")
    print("  [8] intra-unit smuggle: hidden at function granularity, flagged at statement granularity (sound)")


if __name__ == "__main__":
    print("audit() freeze tests:")
    test_smoke()
    test_soundness_invariant()
    test_seed_authorized()
    test_out_of_scope_not_authorized()
    test_w1_router_records_not_authorizes()
    test_out_of_scope_no_tests_is_violation()
    test_cross_file_forced_closure_w2()
    test_intra_unit_statement_granularity()
    print("ALL PASS")
