"""Unit partitioning + before/after recovery.

Ports the VALIDATED cie_harness partitioner (AST-span change units, unit revert)
and adds partition_units(...) which produces the frozen UnitVerdict objects the
audit() orchestration consumes.

Each UnitVerdict carries non-serialized context (_audited_src / _reverted_src /
_raw_name / _tests) used by the resolver. asdict()/to_json only serialize the
declared schema fields, so the freeze contract is untouched.
"""
from __future__ import annotations

import ast
import difflib
import os
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Union

from .schema import Classification, UnitVerdict, Warrant

RepoBefore = Union[str, dict]


# --------------------------------------------------------------------------
# VALIDATED core (ported verbatim from cie_harness/partitioner.py)
# --------------------------------------------------------------------------
@dataclass
class Unit:
    unit_id: str
    family: str
    start: int
    end: int
    before_text: str
    after_text: str
    name: str


def _spans(src: str) -> dict[str, tuple[int, int, str]]:
    lines = src.splitlines()
    out = {"<module>": (1, len(lines), src)}
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return out
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and hasattr(node, "end_lineno"):
            text = "\n".join(lines[node.lineno - 1:node.end_lineno])
            out[node.name] = (node.lineno, node.end_lineno, text)
    return out


def changed_units(before: str, after: str) -> list[Unit]:
    b = _spans(before)
    a = _spans(after)
    units: list[Unit] = []
    for name in sorted(set(b) | set(a)):
        bt = b.get(name, (1, 0, ""))[2]
        at = a.get(name, (1, 0, ""))[2]
        if bt != at and name != "<module>":
            s, e, _ = a.get(name, b.get(name, (1, 0, "")))
            units.append(Unit(f"gold_{len(units)}", "gold", s, e, bt, at, name))
    if not units and before != after:
        s, e, _ = a.get("<module>", (1, len(after.splitlines()), after))
        units.append(Unit("gold_0", "gold", s, e, before, after, "<module>"))
    return units


def touched_names(units: list[Unit]) -> set[str]:
    return {u.name for u in units}


def restore_unit(edited: str, unit: Unit) -> str:
    lines = edited.splitlines()
    if unit.name == "<module>":
        return unit.before_text
    return "\n".join(lines[:unit.start - 1] + unit.before_text.splitlines() + lines[unit.end:]) + ("\n" if edited.endswith("\n") else "")


def diff_size(a: str, b: str) -> int:
    return sum(1 for x in difflib.ndiff(a.splitlines(), b.splitlines()) if x[:1] in {"+", "-"})


# --------------------------------------------------------------------------
# before/after recovery from the audit() inputs
# --------------------------------------------------------------------------
def _looks_like_diff(patch: str) -> bool:
    if not isinstance(patch, str):
        return False
    head = patch.lstrip()[:600]
    return head.startswith("diff ") or head.startswith("--- ") or "\n@@ " in ("\n" + patch) or patch.lstrip().startswith("@@ ")


def _primary_source(repo_before: RepoBefore) -> tuple[str, str]:
    """Return (relpath, before_source) for the single primary file.

    Supports: in-memory {relpath: src}, a path to a .py file, or a raw source
    string. Multi-file repos return the first file; cross-file call-graph
    closure is the next resolver hardening step (weakness #7).
    """
    if isinstance(repo_before, dict):
        if not repo_before:
            return ("candidate.py", "")
        relpath = sorted(repo_before)[0]
        return (relpath, repo_before[relpath])
    if isinstance(repo_before, str):
        p = Path(repo_before)
        if len(repo_before) < 4096 and p.exists() and p.is_file():
            return (p.name, p.read_text(encoding="utf-8"))
        return ("candidate.py", repo_before)
    raise TypeError(f"unsupported repo_before type: {type(repo_before)!r}")


def _apply_unified(before: str, patch: str, relpath: str) -> str:
    """Apply a unified diff to a single file using the system patch tool."""
    d = Path(tempfile.mkdtemp(prefix="cie_patch_"))
    target = d / relpath
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(before, encoding="utf-8")
    pf = d / "change.patch"
    pf.write_text(patch if patch.endswith("\n") else patch + "\n", encoding="utf-8")
    for strip in ("1", "0", "2"):
        r = subprocess.run(["patch", f"-p{strip}", "--no-backup-if-mismatch", "-d", str(d), "-i", str(pf)], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        if r.returncode == 0:
            # find the patched file (relpath may differ after strip)
            if target.exists():
                return target.read_text(encoding="utf-8")
            cands = [p for p in d.rglob("*.py")]
            if cands:
                return cands[0].read_text(encoding="utf-8")
    raise ValueError("could not apply unified diff; pass the full after-source as `patch` instead")


def before_after(repo_before: RepoBefore, patch: str) -> tuple[str, str, str]:
    """Return (relpath, before_source, after_source).

    `patch` may be a unified diff (applied to before) OR the full after-source
    (the validated whole-file path used by audit_case / CanItEdit).
    """
    relpath, before = _primary_source(repo_before)
    if _looks_like_diff(patch):
        after = _apply_unified(before, patch, relpath)
    else:
        after = patch
    return relpath, before, after


# --------------------------------------------------------------------------
# multi-file repo recovery (cross-file call-graph closure support)
# --------------------------------------------------------------------------
def _all_sources(repo_before: RepoBefore) -> dict:
    """Whole-repo before map {relpath: source}."""
    if isinstance(repo_before, dict):
        return {k: v for k, v in repo_before.items()} or {"candidate.py": ""}
    relpath, before = _primary_source(repo_before)
    return {relpath: before}


def _apply_unified_repo(before_map: dict, patch: str) -> dict:
    """Apply a (possibly multi-file) unified diff over the whole repo."""
    d = Path(tempfile.mkdtemp(prefix="cie_patchrepo_"))
    for rel, src in before_map.items():
        t = d / rel
        t.parent.mkdir(parents=True, exist_ok=True)
        t.write_text(src, encoding="utf-8")
    pf = d / "change.patch"
    pf.write_text(patch if patch.endswith("\n") else patch + "\n", encoding="utf-8")
    for strip in ("1", "0", "2"):
        r = subprocess.run(["patch", f"-p{strip}", "--no-backup-if-mismatch", "-d", str(d), "-i", str(pf)], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        if r.returncode == 0:
            break
    after_map = dict(before_map)
    for p in d.rglob("*.py"):
        rel = str(p.relative_to(d)).replace(os.sep, "/")
        after_map[rel] = p.read_text(encoding="utf-8")
    return after_map


def before_after_repo(repo_before: RepoBefore, patch) -> tuple:  # noqa: ANN001
    """Return (before_map, after_map) over the whole repo.

    `patch` may be: a {relpath: after_source} dict (multi-file), a unified diff
    (applied across the repo), or the full after-source string for the single
    primary file (the validated CanItEdit path).
    """
    before_map = _all_sources(repo_before)
    if isinstance(patch, dict):
        after_map = dict(before_map)
        after_map.update(patch)
        return before_map, after_map
    if _looks_like_diff(patch):
        return before_map, _apply_unified_repo(before_map, patch)
    relpath, _ = _primary_source(repo_before)
    after_map = dict(before_map)
    after_map[relpath] = patch
    return before_map, after_map


# --------------------------------------------------------------------------
# frozen-contract producer
# --------------------------------------------------------------------------
def partition_units(repo_before: RepoBefore, patch, seed) -> list[UnitVerdict]:  # noqa: ANN001
    before_map, after_map = before_after_repo(repo_before, patch)
    seed_names = getattr(seed, "names", set()) or set()
    files = sorted(set(before_map) | set(after_map))
    multi = len(files) > 1
    verdicts: list[UnitVerdict] = []
    for relpath in files:
        before = before_map.get(relpath, "")
        after = after_map.get(relpath, "")
        if before == after:
            continue
        for u in changed_units(before, after):
            is_seed = u.name in seed_names
            reverted_file = restore_unit(after, u)
            repo_reverted = dict(after_map)
            repo_reverted[relpath] = reverted_file
            v = UnitVerdict(
                unit_id=f"{relpath}:{u.unit_id}" if multi else u.unit_id,
                files=[relpath],
                loc_changed=diff_size(u.before_text, u.after_text),
                classification=Classification.UNCERTAIN,  # placeholder until classify()
                warrant=Warrant.SEED if is_seed else Warrant.NONE,
                seed_overlap=1.0 if is_seed else 0.0,
            )
            # non-serialized resolver context (single-file + whole-repo)
            v._audited_src = after                # type: ignore[attr-defined]
            v._reverted_src = reverted_file       # type: ignore[attr-defined]
            v._raw_name = u.name                  # type: ignore[attr-defined]
            v._file = relpath                     # type: ignore[attr-defined]
            v._repo_audited = dict(after_map)     # type: ignore[attr-defined]
            v._repo_reverted = repo_reverted      # type: ignore[attr-defined]
            verdicts.append(v)
    return verdicts
