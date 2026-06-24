"""Intra-unit smuggling detection (weakness #9) — OPT-IN statement-level units.

The frozen function-level partitioner has a known blind spot (plan §3.4): an
out-of-scope side effect SMUGGLED inside an otherwise seed-authorized function
(or method) rides along under that unit's seed warrant and is never flagged.

This module decomposes a seed-authorized function/method into statement-level
sub-units and surfaces *added, side-effecting* statements as their own units,
so the policy re-examines each one under the normal sound rule (seed ∪ W2;
else routed/flagged).

SYMBOLIC ONLY. No LLM, no execution. Conservative by construction: it only
ever EMITS extra candidate units (warrant NONE) — it never authorizes — so it
cannot break the soundness invariant. Default audit() granularity stays
"unit", so the validated single-file path is byte-for-byte unchanged; this runs
only when the caller opts into granularity="statement".

Coverage (what is surfaced as a candidate smuggle):
  * separable side-effecting statements in seed-authorized TOP-LEVEL functions
    (discarded calls like `log(x)` / `lst.append(y)`; attribute / subscript
    mutation like `obj.attr = ...`, `d[k] = ...`; rebinding a declared global);
  * the same, inside METHODS of a class — when either the method name or its
    enclosing class name is in the seed (in-class smuggles);
  * RETURN-FEEDING smuggles: a statement that performs one of the external
    side effects above is now surfaced even when its value also flows into the
    function's return (previously such statements were masked by the return
    backward-slice);
  * CONTROL-FLOW-ENTANGLED creep: the traversal descends into the bodies of
    if / for / while / with / try blocks (incl. else/finally/except handlers),
    but NOT into nested def/class scopes (those are separate units), so a side
    effect hidden inside a branch or loop is surfaced as its own candidate.
    Reverting such a nested statement keeps its block non-empty (a `pass` is
    substituted when removal would empty the block) so the W2 resolver cannot
    be fooled into a false forced-closure authorization by a revert-induced
    SyntaxError;
  * RETURN-EMBEDDED short-circuit smuggles: the canonical idiom that hides a
    side effect inside a return / value expression via short-circuit
    evaluation — `mutator() or value` — where a known in-place mutator's (None)
    result is discarded and `value` is what actually flows out. The discarded
    mutator operand is surfaced and reverted SURGICALLY: only that operand is
    dropped (`return mutator() or value` -> `return value`), so the legitimate,
    possibly load-bearing return is preserved. A whole-statement revert would
    remove the real return and could fool the typed-closure check into a FALSE
    W2 authorization; the surgical revert avoids that.

Out of scope (treated as no-finding, honest limits):
  * embedded effects that are NOT a known mutator, or where the effect is the
    LAST operand of the short-circuit (`value or effect()`): conservatively
    left unflagged to avoid false-positives on legitimate fallbacks such as
    `cache.get(k) or default` (precision over recall here);
  * pure-local dead code that never escapes the frame (no external write,
    no return contribution).

Precision note: seed grounding is NAME-level, not semantic, so statement mode
can over-surface a side effect the instruction legitimately asked for (it has
no way to know `append` was authorized). It therefore trades precision for
recall and only ever raises *candidates* for review — it never authorizes.
Downgrades weakness #9, does not close it.
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


# In-place mutator methods whose return value is None, so `m(...) or value`
# discards the call result and returns `value` — the canonical short-circuit
# smuggle idiom. Restricting to these keeps precision high (it avoids flagging
# a legitimate `cache.get(k) or default`, where `.get` is not a mutator).
_MUTATOR_METHODS = frozenset({
    "append", "extend", "insert", "add", "update", "discard", "remove",
    "clear", "sort", "reverse", "setdefault", "write", "writelines",
})


def _value_exprs(stmt: ast.stmt):
    """The value expression of a statement to scan for an embedded side effect,
    or None when there is nothing embeddable to inspect. A bare discarded call
    (`Expr` whose value is directly a `Call`) is the SEPARABLE case handled by
    `_has_side_effect`, so it is excluded here."""
    if isinstance(stmt, ast.Return):
        return stmt.value
    if isinstance(stmt, (ast.Assign, ast.AugAssign, ast.AnnAssign)):
        return stmt.value
    if isinstance(stmt, ast.Expr):
        return None if isinstance(stmt.value, ast.Call) else stmt.value
    return None


def _embedded_drops(stmt: ast.stmt, seed_names: set) -> list:
    """Return the short-circuit operand(s) to drop for a return-embedded smuggle.

    Targets the `mutator() or value` idiom: in a BoolOp (`and`/`or`), the LAST
    operand is the value the chain actually yields; an earlier operand that is
    an in-place-mutator attribute call (its None result discarded) and does not
    reference a seed name is a smuggled side effect. Returns [] otherwise.
    """
    root = _value_exprs(stmt)
    if root is None:
        return []
    drops: list = []
    for n in ast.walk(root):
        if isinstance(n, ast.BoolOp):
            for v in n.values[:-1]:  # last operand is the real value; keep it
                if (isinstance(v, ast.Call)
                        and isinstance(v.func, ast.Attribute)
                        and v.func.attr in _MUTATOR_METHODS
                        and not (_reads(v) & seed_names)):
                    drops.append(v)
    return drops


def _func_global_names(fn: ast.AST) -> set:
    out: set = set()
    for n in ast.walk(fn):
        if isinstance(n, (ast.Global, ast.Nonlocal)):
            out.update(n.names)
    return out


def _body_stmt_strings(body: list) -> list:
    return [ast.dump(s) for s in body]


# Compound statements whose bodies belong to the SAME unit (control-flow creep
# lives inside these). We descend into them, but never into nested def/class
# scopes, which are separate units.
_SKIP_DESCEND = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)


def _iter_statements(body: list):
    """Yield every statement in `body`, recursing into control-flow compound
    statements (if / for / while / with / try, incl. else/finally/handlers) but
    NOT into nested function or class scopes (those are separate units)."""
    for stmt in body:
        yield stmt
        if isinstance(stmt, _SKIP_DESCEND):
            continue
        for field in ("body", "orelse", "finalbody"):
            sub = getattr(stmt, field, None)
            if isinstance(sub, list):
                yield from _iter_statements(sub)
        for handler in getattr(stmt, "handlers", []) or []:
            yield from _iter_statements(handler.body)


def _all_stmt_dumps(body: list) -> list:
    return [ast.dump(s) for s in _iter_statements(body)]


def _iter_target_funcs(tree: ast.Module, seed_names: set):
    """Yield (func_node, qualname) for functions whose smuggles should surface.

    Targets are seed-authorized callables:
      * a TOP-LEVEL function whose name is in the seed;
      * a METHOD whose own name is in the seed, OR whose enclosing class name
        is in the seed (so a smuggle inside a seed-authorized class is caught).
    """
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name in seed_names:
                yield node, node.name
        elif isinstance(node, ast.ClassDef):
            class_seeded = node.name in seed_names
            for sub in node.body:
                if isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    if class_seeded or sub.name in seed_names:
                        yield sub, f"{node.name}.{sub.name}"


def _before_bodies(before_tree) -> dict:
    """Map qualname -> statement body for every before-side function/method."""
    out: dict = {}
    if before_tree is None:
        return out
    for node in before_tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            out[node.name] = node.body
        elif isinstance(node, ast.ClassDef):
            for sub in node.body:
                if isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    out[f"{node.name}.{sub.name}"] = sub.body
    return out


def _revert_lines(after_src: str, after_lines: list, start: int, end: int) -> str:
    """Return `after_src` with lines [start, end] (1-based, inclusive) removed.

    If removing them empties an enclosing block — which would make the reverted
    source fail to compile and could fool the W2 resolver into a FALSE
    forced-closure authorization (revert_breaks_compile) — a `pass` is
    substituted at the removed statement's indentation instead, keeping the
    block non-empty and the comparison fair.
    """
    tail_nl = "\n" if after_src.endswith("\n") else ""
    cut = after_lines[: start - 1] + after_lines[end:]
    reverted = "\n".join(cut) + tail_nl
    try:
        ast.parse(reverted)
        return reverted
    except SyntaxError:
        first = after_lines[start - 1]
        indent = first[: len(first) - len(first.lstrip())]
        patched = after_lines[: start - 1] + [indent + "pass"] + after_lines[end:]
        return "\n".join(patched) + tail_nl


def _surgical_revert(after_src: str, after_lines: list, stmt: ast.stmt, drop_calls: list):
    """Build reverted source by dropping ONLY the smuggled (value-discarded)
    short-circuit operand(s), keeping the statement's real value
    (`return effect() or value` -> `return value`).

    Only the offending statement's lines change, so the W2 health comparison
    stays fair AND the legitimate return is preserved — a whole-statement revert
    could remove a load-bearing return and fool the typed-closure check into a
    FALSE forced-closure (W2) authorization. Returns None if it cannot build a
    clean reverted source (the caller then falls back to line removal).
    """
    drop_src = {ast.unparse(c) for c in drop_calls}

    class _Pruner(ast.NodeTransformer):
        def visit_BoolOp(self, node):  # noqa: N802
            self.generic_visit(node)
            kept = [v for v in node.values if ast.unparse(v) not in drop_src]
            if not kept:
                return node
            if len(kept) == 1:
                return kept[0]
            node.values = kept
            return node

    try:
        fresh = ast.parse(ast.unparse(stmt)).body[0]
        pruned = _Pruner().visit(fresh)
        ast.fix_missing_locations(pruned)
        rendered = ast.unparse(pruned)
    except Exception:
        return None
    start = getattr(stmt, "lineno", None)
    end = getattr(stmt, "end_lineno", start)
    if start is None:
        return None
    first = after_lines[start - 1]
    indent = first[: len(first) - len(first.lstrip())]
    new_block = [indent + ln for ln in rendered.splitlines()]
    tail_nl = "\n" if after_src.endswith("\n") else ""
    patched = after_lines[: start - 1] + new_block + after_lines[end:]
    reverted = "\n".join(patched) + tail_nl
    try:
        ast.parse(reverted)
        return reverted
    except SyntaxError:
        return None


def find_smuggles(after_src: str, before_src: str, seed_names: set) -> list:
    """Return smuggle records for seed-authorized functions and methods.

    Each record: {name, lineno, end_lineno, loc, reverted_src} where `name` is
    the qualified owner (`func` or `Class.method`) and `reverted_src` is
    `after_src` with exactly the smuggled statement removed (so the W2 resolver
    / W1 router can evaluate it via the normal sound path).
    """
    try:
        after_tree = ast.parse(after_src)
    except SyntaxError:
        return []
    try:
        before_tree = ast.parse(before_src)
    except SyntaxError:
        before_tree = None

    before_bodies = _before_bodies(before_tree)
    after_lines = after_src.splitlines()
    records: list = []
    seen: set = set()
    for fn, qualname in _iter_target_funcs(after_tree, seed_names):
        # recursive statement multiset of the before-body (control-flow aware),
        # so a nested statement counts as "added" only if it is genuinely new.
        before_pool = list(_all_stmt_dumps(before_bodies.get(qualname, [])))
        global_names = _func_global_names(fn)
        # descend into control-flow blocks, but not into nested def/class scopes
        for stmt in _iter_statements(fn.body):
            d = ast.dump(stmt)
            # statement present unchanged in the before-body is not "added"
            if d in before_pool:
                before_pool.remove(d)
                continue
            reads_seed = bool(_reads(stmt) & seed_names)
            # (1) SEPARABLE external side effect (discarded call, attribute /
            # subscript write, global rebind) — including return-feeding and
            # control-flow-nested statements. Skipped if it reads a seed name
            # (authorized seed work).
            separable = (not reads_seed) and _has_side_effect(stmt, global_names)
            # (2) RETURN-EMBEDDED short-circuit smuggle (`mutator() or value`):
            # surfaced even if the statement also reads a seed name, because the
            # seed check is applied to the discarded operand itself.
            drops = _embedded_drops(stmt, seed_names)
            if not (separable or drops):
                continue
            start = getattr(stmt, "lineno", None)
            end = getattr(stmt, "end_lineno", start)
            if start is None or (start, end) in seen:
                continue
            seen.add((start, end))
            if separable:
                reverted_src = _revert_lines(after_src, after_lines, start, end)
            else:
                # surgical: drop only the smuggled operand, keep the real value,
                # so reverting cannot remove a load-bearing return (false W2).
                reverted_src = _surgical_revert(after_src, after_lines, stmt, drops)
                if reverted_src is None:
                    reverted_src = _revert_lines(after_src, after_lines, start, end)
            records.append({
                "name": qualname,
                "lineno": start,
                "end_lineno": end,
                "loc": end - start + 1,
                "reverted_src": reverted_src,
            })
    return records
