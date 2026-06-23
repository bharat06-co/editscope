"""Mutation harness — injects out-of-scope "violation" edits into functions the
instruction does NOT name, for benchmark violation-recall measurement.

Ported verbatim from the validated cie_harness/mutate.py. This is BENCHMARK
scaffolding used by parity_real / run_real; it is NOT part of the frozen audit()
path (the oracle audits one real agent patch, it does not synthesize mutants).
"""
from __future__ import annotations

import ast
from dataclasses import dataclass


@dataclass
class Mutant:
    family: str
    src: str
    start: int
    end: int
    name: str
    label: str


def _funcs(src: str):
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return []
    return [
        n
        for n in tree.body
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and hasattr(n, "end_lineno")
    ]


def make(src: str, named: set[str]) -> list[Mutant]:
    """Synthesize up to 3 out-of-scope violation mutants in functions NOT named
    by the instruction (`named` = grounded seed names ∪ touched unit names).
    """
    lines = src.splitlines()
    out: list[Mutant] = []
    for fn in _funcs(src):
        if fn.name in named:
            continue
        body_start = fn.lineno
        body_end = fn.end_lineno
        body = lines[body_start - 1:body_end]
        indent = "    "
        for ln in body[1:]:
            stripped = ln.lstrip()
            if stripped:
                indent = ln[:len(ln) - len(stripped)]
                break
        # R1: tweak first numeric return if present
        for i in range(body_start, body_end + 1):
            if "return " in lines[i - 1] and any(ch.isdigit() for ch in lines[i - 1]):
                new = lines[:]
                new[i - 1] = lines[i - 1].replace("1", "2", 1) if "1" in lines[i - 1] else lines[i - 1] + " + 1"
                out.append(Mutant("R1", "\n".join(new) + "\n", i, i, fn.name, "violation"))
                break
        # R2: local rename via AST if a simple assignment exists
        for node in ast.walk(fn):
            if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store) and node.id not in {"self", "cls"}:
                old = node.id
                new_lines = [
                    ln.replace(old, old + "_renamed") if body_start <= ix + 1 <= body_end else ln
                    for ix, ln in enumerate(lines)
                ]
                out.append(Mutant("R2", "\n".join(new_lines) + "\n", body_start, body_end, fn.name, "violation"))
                break
        # R3: extra local helper binding
        new = lines[:]
        new.insert(body_start, f"{indent}_unused_local = None")
        out.append(Mutant("R3", "\n".join(new) + "\n", body_start + 1, body_start + 1, fn.name, "violation"))
        break
    return out[:3]
