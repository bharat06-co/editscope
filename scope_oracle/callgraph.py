"""Symbolic cross-file call-graph / import-graph closure check (W2 hardening).

NO LLM, NO execution. Builds an internal import graph and verifies that every
cross-module reference (`from X import n`, or `import X` + `X.n`) resolves to a
top-level definition in the target INTERNAL module. The resolver uses this to
confirm FORCED CLOSURE across files: if reverting a unit leaves another module
referencing a name the edited file no longer defines, the revert provably breaks
name resolution -> W2.

Conservative by design: anything it cannot prove broken is treated as NOT broken
(sound — we never invent a warrant). Out of scope: dynamic dispatch, `*`-imports,
runtime attribute resolution.
"""
from __future__ import annotations

import ast


def _module_name(relpath: str) -> str:
    p = relpath.replace("\\", "/")
    if p.endswith(".py"):
        p = p[:-3]
    parts = [x for x in p.split("/") if x and x != "__init__"]
    return ".".join(parts)


def top_level_defs(src: str) -> set:
    """Names bound at module top level (defs, classes, globals, imported names)."""
    out: set = set()
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return out
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            out.add(node.name)
        elif isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name):
                    out.add(t.id)
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            out.add(node.target.id)
        elif isinstance(node, ast.Import):
            for a in node.names:
                out.add((a.asname or a.name).split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            for a in node.names:
                if a.name != "*":
                    out.add(a.asname or a.name)
    return out


def _resolve_relative(this_module: str, level: int, module) -> str:
    base = this_module.split(".")
    base = base[: len(base) - level] if level <= len(base) else []
    if module:
        base = base + module.split(".")
    return ".".join(base)


def _dependencies(src: str, this_module: str, module_set: set):
    """Yield (target_module, name) cross-module refs to INTERNAL modules only."""
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return
    alias_to_mod: dict = {}
    deps: list = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if node.level:
                target = _resolve_relative(this_module, node.level, node.module)
            else:
                target = node.module or ""
            if target in module_set:
                for a in node.names:
                    if a.name != "*":
                        deps.append((target, a.name))
        elif isinstance(node, ast.Import):
            for a in node.names:
                if a.name in module_set:
                    alias_to_mod[a.asname or a.name] = a.name
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
            mod = alias_to_mod.get(node.value.id)
            if mod:
                deps.append((mod, node.attr))
    for d in deps:
        yield d


def unresolved_refs(repo_map: dict) -> set:
    """(src_module, target_module, name) cross-module refs that do NOT resolve to
    a top-level def in the target internal module."""
    module_map = {}
    for rel, src in repo_map.items():
        module_map[_module_name(rel)] = src
    module_set = set(module_map)
    defs = {m: top_level_defs(s) for m, s in module_map.items()}
    bad: set = set()
    for m, src in module_map.items():
        for target, name in _dependencies(src, m, module_set):
            if target in defs and name not in defs[target]:
                bad.add((m, target, name))
    return bad


def newly_broken_crossfile(audited_map: dict, reverted_map: dict) -> bool:
    """True iff reverting introduced a cross-module reference that no longer
    resolves (resolved in the audited repo, unresolved after the revert)."""
    base = unresolved_refs(audited_map)
    var = unresolved_refs(reverted_map)
    return bool(var - base)
