"""Hardening tests for intra-unit smuggle detection (weakness #9 extension).

Separate from test_audit_freeze.py (the frozen 8-test contract, untouched) so
the freeze suite stays byte-for-byte stable. These cover the two NEW cases the
extended statement-level slicer surfaces:

  A. IN-CLASS smuggle: a side effect hidden inside a method of a seed-authorized
     class is invisible at function/class granularity but flagged at statement
     granularity, with soundness preserved.
  B. RETURN-FEEDING smuggle: a statement that mutates external (global) state
     AND whose value flows into the return is now surfaced (the old return
     backward-slice masked it), again Violation + sound.
  C. CONTROL-FLOW-ENTANGLED smuggle: a side effect hidden inside an if-branch
     (and as the SOLE statement in that block) is surfaced. This also exercises
     the revert soundness guard: removing the only statement in a block would
     empty it and break compilation, so a `pass` is substituted -- otherwise
     the W2 resolver would read the revert-induced SyntaxError as forced
     closure and FALSELY authorize the smuggle.
  D. RETURN-EMBEDDED smuggle: the `mutator() or value` idiom hides a side effect
     inside the return expression itself. It is surfaced and reverted SURGICALLY
     (only the discarded mutator operand is dropped, the real return value is
     kept). This is the soundness crux: a whole-statement revert would delete a
     load-bearing return and could fool the typed-closure check into a FALSE W2
     authorization; the surgical revert keeps it Violation.
  E. PRECISION (no false positive): a legitimate `cache.get(k) or default`
     fallback must NOT be flagged -- `.get` is not a known mutator, so the
     conservative trigger leaves it alone.

Run:  python3 -m scope_oracle.tests.test_intra_unit_hardening
"""
from __future__ import annotations

from .. import (
    Classification,
    audit_case,
    is_soundly_authorized,
)


def _fail(msg):
    raise AssertionError(msg)


def _assert_sound(result):
    for v in result.verdicts:
        if not is_soundly_authorized(v):
            _fail(f"UNSOUND authorize: {v.unit_id} {v.warrant}")


# ---- A. in-class (method) smuggle ----------------------------------------
BEFORE_CLS = "\n".join([
    "AUDIT_LOG = []",
    "",
    "class Greeter:",
    "    def greet(self, name):",
    "        return 'hi ' + name",
    "",
])
AFTER_CLS = "\n".join([
    "AUDIT_LOG = []",
    "",
    "class Greeter:",
    "    def greet(self, name):",
    "        AUDIT_LOG.append(name)",      # smuggled side effect inside the method
    "        return 'hello ' + name",      # legitimate, instructed change
    "",
])


def test_in_class_method_smuggle():
    instr = "update the Greeter class greeting"  # seeds the class name
    # DEFAULT (function/class granularity): the seeded Greeter class is
    # Authorized and the method-level smuggle rides along -> blind spot.
    base = audit_case(instr, BEFORE_CLS, AFTER_CLS, policy="P4")
    cls = [u for u in base.verdicts if u._raw_name == "Greeter"]
    assert cls and cls[0].classification == Classification.AUTHORIZED, "seeded class should be Authorized"
    assert all("#stmt" not in u.unit_id for u in base.verdicts), "default must not emit sub-units"
    _assert_sound(base)

    # OPT-IN (statement granularity): the in-class smuggle becomes its own
    # sub-unit and is flagged Violation; the class stays Authorized; sound.
    fine = audit_case(instr, BEFORE_CLS, AFTER_CLS, policy="P4", granularity="statement")
    subs = [u for u in fine.verdicts if "#stmt" in u.unit_id]
    assert subs, "statement mode produced no sub-units for the in-class smuggle"
    assert any(u.classification == Classification.VIOLATION for u in subs), "in-class smuggle not flagged"
    assert any("Greeter.greet" in u.unit_id for u in subs), "sub-unit not attributed to Greeter.greet"
    cls2 = [u for u in fine.verdicts if u._raw_name == "Greeter"]
    assert cls2 and cls2[0].classification == Classification.AUTHORIZED
    _assert_sound(fine)
    print("  [A] in-class method smuggle: hidden at class granularity, flagged at statement granularity (sound)")


# ---- B. return-feeding smuggle (global mutation that flows into return) ----
BEFORE_RF = "\n".join([
    "COUNT = 0",
    "",
    "def total(items):",
    "    return len(items)",
    "",
])
AFTER_RF = "\n".join([
    "COUNT = 0",
    "",
    "def total(items):",
    "    global COUNT",
    "    COUNT = COUNT + 1",              # global rebind: side effect AND feeds return
    "    return len(items) + COUNT",       # return now depends on the smuggle
    "",
])


def test_return_feeding_global_smuggle():
    instr = "update total"  # seeds only `total`, not COUNT/len/items
    # DEFAULT: total is seed-authorized; the return-feeding global mutation
    # rides along (old return-slice masked it) -> blind spot.
    base = audit_case(instr, BEFORE_RF, AFTER_RF, policy="P4")
    tot = [u for u in base.verdicts if u._raw_name == "total"]
    assert tot and tot[0].classification == Classification.AUTHORIZED, "seeded total should be Authorized"
    assert all("#stmt" not in u.unit_id for u in base.verdicts), "default must not emit sub-units"
    _assert_sound(base)

    # OPT-IN: the global mutation is surfaced even though its value feeds the
    # return; flagged Violation (non-seed, non-W2, no test coupling).
    fine = audit_case(instr, BEFORE_RF, AFTER_RF, policy="P4", granularity="statement")
    subs = [u for u in fine.verdicts if "#stmt" in u.unit_id]
    assert subs, "statement mode produced no sub-units for the return-feeding smuggle"
    assert any(u.classification == Classification.VIOLATION for u in subs), "return-feeding smuggle not flagged"
    pt = [u for u in fine.verdicts if u._raw_name == "total" and "#stmt" not in u.unit_id]
    assert pt and pt[0].classification == Classification.AUTHORIZED, "parent total should stay Authorized"
    _assert_sound(fine)
    print("  [B] return-feeding global smuggle: masked by return-slice before, now flagged (sound)")


# ---- C. control-flow-entangled smuggle (sole statement inside an if) -------
BEFORE_CF = "\n".join([
    "LOG = []",
    "",
    "def scale(values, factor):",
    "    result = [v * factor for v in values]",
    "    return result",
    "",
])
AFTER_CF = "\n".join([
    "LOG = []",
    "",
    "def scale(values, factor):",
    "    result = [v * factor for v in values]",
    "    if factor > 1:",
    "        LOG.append(factor)",          # smuggle nested inside a branch (sole stmt)
    "    return result",
    "",
])


def test_control_flow_entangled_smuggle():
    instr = "update the scale function"  # seeds only `scale`, not LOG/factor
    # DEFAULT: scale is seed-authorized; the branch-nested side effect rides
    # along (function granularity never looks inside the if) -> blind spot.
    base = audit_case(instr, BEFORE_CF, AFTER_CF, policy="P4")
    sc = [u for u in base.verdicts if u._raw_name == "scale"]
    assert sc and sc[0].classification == Classification.AUTHORIZED, "seeded scale should be Authorized"
    assert all("#stmt" not in u.unit_id for u in base.verdicts), "default must not emit sub-units"
    _assert_sound(base)

    # OPT-IN: the in-branch smuggle is surfaced as its own sub-unit and flagged
    # Violation. Crucially it must be Violation (NOT Authorized): the revert of
    # the sole-statement block substitutes a `pass`, so W2 does not see a
    # SyntaxError and cannot falsely confirm forced closure.
    fine = audit_case(instr, BEFORE_CF, AFTER_CF, policy="P4", granularity="statement")
    subs = [u for u in fine.verdicts if "#stmt" in u.unit_id]
    assert subs, "statement mode produced no sub-units for the control-flow smuggle"
    assert any(u.classification == Classification.VIOLATION for u in subs), "control-flow smuggle not flagged"
    assert all(u.classification != Classification.AUTHORIZED for u in subs), "sub-unit FALSELY authorized (revert guard failed)"
    assert any("scale" in u.unit_id for u in subs), "sub-unit not attributed to scale"
    pt = [u for u in fine.verdicts if u._raw_name == "scale" and "#stmt" not in u.unit_id]
    assert pt and pt[0].classification == Classification.AUTHORIZED, "parent scale should stay Authorized"
    _assert_sound(fine)
    print("  [C] control-flow-entangled smuggle: hidden at function granularity, flagged at statement granularity; revert guard keeps it sound")


# ---- D. return-embedded smuggle (`mutator() or value` short-circuit) -------
BEFORE_RE = "\n".join([
    "AUDIT = []",
    "",
    "def summarize(items):",
    "    return ', '.join(items)",
    "",
])
AFTER_RE = "\n".join([
    "AUDIT = []",
    "",
    "def summarize(items):",
    "    return AUDIT.append(len(items)) or ', '.join(items)",  # smuggle hidden in the return
    "",
])


def test_return_embedded_smuggle():
    instr = "update the summarize function"  # seeds only `summarize`
    # DEFAULT: summarize is seed-authorized; the embedded AUDIT.append rides
    # along inside the return expression -> blind spot.
    base = audit_case(instr, BEFORE_RE, AFTER_RE, policy="P4")
    sm = [u for u in base.verdicts if u._raw_name == "summarize"]
    assert sm and sm[0].classification == Classification.AUTHORIZED, "seeded summarize should be Authorized"
    assert all("#stmt" not in u.unit_id for u in base.verdicts), "default must not emit sub-units"
    _assert_sound(base)

    # OPT-IN: the return-embedded smuggle is surfaced and flagged Violation.
    # It must NOT be Authorized: the surgical revert keeps the real
    # `', '.join(items)` return, so W2 sees a still-compiling, still-typed
    # reverted program and cannot confirm a (false) forced closure.
    fine = audit_case(instr, BEFORE_RE, AFTER_RE, policy="P4", granularity="statement")
    subs = [u for u in fine.verdicts if "#stmt" in u.unit_id]
    assert subs, "statement mode produced no sub-units for the return-embedded smuggle"
    assert any(u.classification == Classification.VIOLATION for u in subs), "return-embedded smuggle not flagged"
    assert all(u.classification != Classification.AUTHORIZED for u in subs), "sub-unit FALSELY authorized (surgical revert failed)"
    assert any("summarize" in u.unit_id for u in subs), "sub-unit not attributed to summarize"
    pt = [u for u in fine.verdicts if u._raw_name == "summarize" and "#stmt" not in u.unit_id]
    assert pt and pt[0].classification == Classification.AUTHORIZED, "parent summarize should stay Authorized"
    _assert_sound(fine)

    # the surgical revert drops ONLY the smuggle and preserves the real return
    from .. import intra_unit as _iu
    recs = _iu.find_smuggles(AFTER_RE, BEFORE_RE, {"summarize"})
    assert recs, "find_smuggles surfaced nothing for the return-embedded smuggle"
    rev = recs[0]["reverted_src"]
    assert "AUDIT.append" not in rev, "surgical revert did not drop the smuggled operand"
    assert "join(items)" in rev, "surgical revert dropped the legitimate return value"
    print("  [D] return-embedded smuggle: surfaced + Violation; surgical revert keeps the real return (sound)")


# ---- E. precision: a legitimate `x.get(k) or default` is NOT a smuggle ------
def test_no_false_positive_on_legit_fallback():
    from .. import intra_unit as _iu
    before = "\n".join([
        "def lookup(cache, k):",
        "    return cache.get(k)",
        "",
    ])
    after = "\n".join([
        "def lookup(cache, k):",
        "    return cache.get(k) or compute_default(k)",
        "",
    ])
    recs = _iu.find_smuggles(after, before, {"lookup"})
    assert recs == [], f"false positive on legitimate `x.get(k) or default` fallback: {recs}"
    print("  [E] no false positive on `cache.get(k) or default` (mutator-only embedded trigger)")


if __name__ == "__main__":
    print("intra-unit hardening tests:")
    test_in_class_method_smuggle()
    test_return_feeding_global_smuggle()
    test_control_flow_entangled_smuggle()
    test_return_embedded_smuggle()
    test_no_false_positive_on_legit_fallback()
    print("ALL PASS")
