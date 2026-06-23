"""Symbolic closure resolver (W2) + unsound W1 router signal.

Self-contained and SYMBOLIC ONLY (py_compile + pyflakes + mypy --strict).
No LLM is ever consulted inside the oracle. Soundness lives here:

  W2 (forced closure) is asserted ONLY when reverting a unit provably breaks
  compilation / name-resolution / typing.  W1 (behavioral) is UNSOUND and can
  never authorize — it is reported as a risk-routing signal only.

Resolver context (_audited_src / _reverted_src / _tests) is attached to each
UnitVerdict by the partitioner; these functions read it.
"""
from __future__ import annotations

import os
import py_compile
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Union

from . import callgraph
from .schema import RouterSignal, W2Evidence

RepoBefore = Union[str, dict]


def _mypy_available() -> bool:
    try:
        r = subprocess.run([sys.executable, "-m", "mypy", "--version"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=20)
        return r.returncode == 0
    except Exception:
        return False


_MYPY_ON = _mypy_available()
RESOLVER_ID = f"symbolic:pycompile+pyflakes+mypy(strict={'on' if _MYPY_ON else 'off'});callgraph=symbolic-import-name"


def _write(src: str, stem: str) -> Path:
    d = Path(tempfile.mkdtemp(prefix="cie_audit_"))
    p = d / f"{stem}.py"
    p.write_text("import sys\nsys.dont_write_bytecode = True\n" + src, encoding="utf-8")
    return p


def check(src: str, stem: str = "case") -> dict:
    """Static health of a source: compile / pyflakes / mypy. (Ported, validated.)"""
    p = _write(src, stem)
    env = os.environ.copy()
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    out = {"compile_ok": True, "pyflakes_ok": True, "mypy_ok": None, "messages": []}
    try:
        py_compile.compile(str(p), doraise=True)
    except py_compile.PyCompileError as exc:
        out["compile_ok"] = False
        out["messages"].append(str(exc))
    pf = subprocess.run([sys.executable, "-m", "pyflakes", str(p)], text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=env, timeout=20)
    out["pyflakes_ok"] = pf.returncode == 0
    if pf.stdout:
        out["messages"].append(pf.stdout)
    if _MYPY_ON:
        my = subprocess.run([sys.executable, "-m", "mypy", "--strict", str(p)], text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=env, timeout=40)
        if "No module named mypy" not in my.stdout:
            out["mypy_ok"] = my.returncode == 0
            if my.stdout:
                out["messages"].append(my.stdout)
    return out


def newly_broken(base: dict, variant: dict) -> bool:
    return (
        (base.get("compile_ok") and not variant.get("compile_ok"))
        or (base.get("pyflakes_ok") and not variant.get("pyflakes_ok"))
        or (base.get("mypy_ok") is True and variant.get("mypy_ok") is False)
    )


def resolve_w2(unit, repo_before: RepoBefore = None, patch: str = None) -> W2Evidence:  # noqa: ANN001
    """Forced-closure check: does reverting THIS unit provably break the program?

    audited  = the full edited program (W2 base health).
    reverted = the program with this unit restored to its before-text.
    W2 fires iff reverting newly breaks compile / name-resolution / typing.
    """
    audited = getattr(unit, "_audited_src", None)
    reverted = getattr(unit, "_reverted_src", None)
    if audited is None or reverted is None:
        return W2Evidence()
    base = check(audited, "w2_base")
    var = check(reverted, "w2_var")
    comp = bool(base.get("compile_ok") and not var.get("compile_ok"))
    name = bool(base.get("pyflakes_ok") and not var.get("pyflakes_ok"))
    typ = bool(base.get("mypy_ok") is True and var.get("mypy_ok") is False)
    # Cross-file forced closure (call-graph / import-graph): does reverting THIS
    # unit leave another module referencing a name this file no longer defines?
    # Single-file repos have no cross-module edges, so this stays False there and
    # the single-file W2 result is byte-for-byte unchanged.
    repo_aud = getattr(unit, "_repo_audited", None)
    repo_rev = getattr(unit, "_repo_reverted", None)
    imports = False
    if isinstance(repo_aud, dict) and isinstance(repo_rev, dict) and len(repo_aud) > 1:
        imports = callgraph.newly_broken_crossfile(repo_aud, repo_rev)
    return W2Evidence(
        revert_breaks_compile=comp,
        revert_breaks_name_resolution=name or typ,
        revert_breaks_imports=imports,
        resolver_confirmed_closure=(comp or name or typ or imports),
    )


def _run_tests_src(src: str, tests: str) -> bool:
    """Plain-module test runner (matches the validated run_fixed runner).

    CanItEdit tests are module-level `assert` blocks, not pytest functions, so
    we exec `from candidate import *` + the test body and treat a clean exit
    (returncode 0) as pass.
    """
    if not tests:
        return True
    d = Path(tempfile.mkdtemp(prefix="cie_test_"))
    (d / "candidate.py").write_text(src, encoding="utf-8")
    runner = "from candidate import *\n" + tests + "\n"
    (d / "_run.py").write_text(runner, encoding="utf-8")
    env = os.environ.copy()
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    try:
        p = subprocess.run([sys.executable, "_run.py"], cwd=str(d), env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=60)
        return p.returncode == 0
    except Exception:
        return False


def w1_router_signal(unit, repo_before: RepoBefore = None, patch: str = None, tests_cmd: str = None) -> RouterSignal:  # noqa: ANN001
    """UNSOUND behavioral signal. Risk-routing ONLY — can never authorize.

    w1 = (audited passes tests) AND (reverting this unit fails a test).
    Task tests are attached to the unit as `_tests`; if absent, returns None.
    """
    audited = getattr(unit, "_audited_src", None)
    reverted = getattr(unit, "_reverted_src", None)
    tests = getattr(unit, "_tests", None)
    if audited is None or reverted is None or not tests:
        return RouterSignal(w1_revert_flips_test=None)
    audited_pass = _run_tests_src(audited, tests)
    reverted_pass = _run_tests_src(reverted, tests)
    return RouterSignal(w1_revert_flips_test=bool(audited_pass and not reverted_pass))
