"""Intra-unit smuggling detection (weakness #9) — OPT-IN statement-level units.

The frozen function-level partitioner has a known blind spot (plan §3.4): an
out-of-scope side effect SMUGGLED inside an otherwise seed-authorized function
rides along under the function's seed warrant and is never flagged.

This module decomposes a seed-authorized function into statement-level
sub-units and surfaces *added, side-effecting* statements that are NOT part of
the edit's return/seed closure as their own units, so the policy re-examines
them under the normal sound rule (seed ∪ W2; else routed/flagged).

SYMBOLIC ONLY. No LLM, no execution. Conservative by construction: it only
ever EMITS extra candidate units (it never authorizes), so it cannot break the
soundness invariant. Default audit() granularity stays "unit", so the validated
single-file path is byte-for-byte unchanged; this runs only when the caller
opts into granularity="statement".

Scope / limits (honest): catches separable side-effecting smuggles in
top-level functions — discarded calls (`log(x)`), attribute/subscript/global
mutation of non-return state. Out of scope (treated as no-finding): smuggles
that feed the return value, pure-local dead code, methods inside classes,
and control-flow-entangled creep. Downgrades weakness #9, does not close it.
"""
from __future__ import annotations

import ast


def _reads(node: ast.AST) -> set:
    out: set = set()
    for n in ast.walk(node):
        if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load):
            out.add(n.id)
        elif isinstance(n, ast.Attribute):
            out.add(n.attr)
    return out


def _local_writes(node: ast.AST) -> set:
    """Plain local names bound by this statement (Name Store targets only)."""
    out: set = set()
    for n in ast.walk(node):
        if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Store):
            out.add(n.id)
    return out


def _has_side_effect(stmt: ast.stmt, global_names: set) -> bool:
    """True if the statement mutates state observable outside its own locals."""
    # discarded expression that is a call, e.g. log_to_server(x), lst.append(y)
    if isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Call):
        return True
    # assignment/aug-assign whose target is an attribute or subscript -> mutates
    # an aliased / external object (self.x = ..., obj.attr = ..., d[k] = ...)
    targets = []
    if isinstance(stmt, ast.Assign):
        targets = list(stmt.targets)
    elif isinstance(stmt, (ast.AugAssign, ast.AnnAssign)):
        targets = [stmt.target]
    for t in targets:
        if isinstance(t, (ast.Attribute, ast.Subscript)):
            return True
        if isinstance(t, ast.Name) and t.id in global_names:
            return True  # rebinding a declared global/nonlocal
    return False


def _func_global_names(fn: ast.AST) -> set:
    out: set = set()
    for n in ast.walk(fn):
        if isinstance(n, (ast.Global, ast.Nonlocal)):
            out.update(n.names)
    return out


def _return_relevant(body: list, seed_names: set) -> set:
    """id()s of statements in the return/seed backward slice (fixpoint).

    A statement is relevant if it (transitively) defines a name read by a
    `return`, or reads/writes a seed name. Side-effecting smuggles that feed
    nothing returned are, by design, NOT relevant.
    """
    needed: set = set(seed_names)
    for stmt in body:
        for r in ast.walk(stmt):
            if isinstance(r, ast.Return) and r.value is not None:
                needed |= _reads(r.value)
    relevant: set = set()
    changed = True
    while changed:
        changed = False
        for stmt in body:
            if id(stmt) in relevant:
                continue
            writes = _local_writes(stmt)
            reads = _reads(stmt)
            if (writes & needed) or (reads & seed_names) or (writes & seed_names):
                relevant.add(id(stmt))
                if needed | reads != needed:
                    needed |= reads
                    changed = True
    return relevant


def _body_stmt_strings(body: list) -> list:
    return [ast.dump(s) for s in body]


def find_smuggles(after_src: str, before_src: str, seed_names: set) -> list:
    """Return smuggle records for seed-authorized top-level functions.

    Each record: {name, lineno, end_lineno, loc, reverted_src} where
    `reverted_src` is `after_src` with exactly the smuggled statement removed
    (so the W2 resolver / W1 router can evaluate it via the normal path).
    """
    try:
        after_tree = ast.parse(after_src)
    except SyntaxError:
        return []
    try:
        before_tree = ast.parse(before_src)
    except SyntaxError:
        before_tree = None

    before_funcs = {}
    if before_tree is not None:
        for node in before_tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                before_funcs[node.name] = node

    after_lines = after_src.splitlines()
    records: list = []
    for node in after_tree.body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if node.name not in seed_names:
            continue
        bf = before_funcs.get(node.name)
        before_dumps = _body_stmt_strings(bf.body) if bf is not None else []
        before_pool = list(before_dumps)
        global_names = _func_global_names(node)
        relevant = _return_relevant(node.body, seed_names)
        for stmt in node.body:
            d = ast.dump(stmt)
            # statement present unchanged in the before-body is not "added"
            if d in before_pool:
                before_pool.remove(d)
                continue
            if id(stmt) in relevant:
                continue
            if _reads(stmt) & seed_names:
                continue
            if not _has_side_effect(stmt, global_names):
                continue
            start = getattr(stmt, "lineno", None)
            end = getattr(stmt, "end_lineno", start)
            if start is None:
                continue
            reverted_lines = after_lines[: start - 1] + after_lines[end:]
            reverted_src = "\n".join(reverted_lines)
            if after_src.endswith("\n"):
                reverted_src += "\n"
            records.append({
                "name": node.name,
                "lineno": start,
                "end_lineno": end,
                "loc": end - start + 1,
                "reverted_src": reverted_src,
            })
    return records
