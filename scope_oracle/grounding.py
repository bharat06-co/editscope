"""Seed grounding (what the instruction authorizes).

Ports the VALIDATED cie_harness grounding (token ∩ AST-name extraction) and
exposes ground_seed(...) in the shape the audit() orchestration expects.
"""
from __future__ import annotations

import ast
import re
from dataclasses import dataclass
from typing import Union

from .partitioner import _all_sources, _primary_source

RepoBefore = Union[str, dict]


@dataclass
class Grounding:
    names: set[str]
    confidence: float
    missed: bool


_WORD = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


def code_names(src: str) -> set[str]:
    names: set[str] = set()
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return names
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)
        elif isinstance(node, ast.Name):
            names.add(node.id)
        elif isinstance(node, ast.Attribute):
            names.add(node.attr)
    return names


def extract(prompt: str, src: str) -> Grounding:
    known = code_names(src)
    raw = set(_WORD.findall(prompt or ""))
    quoted = set(re.findall(r"[`'\"]([A-Za-z_][A-Za-z0-9_]*)[`'\"]", prompt or ""))
    names = (raw | quoted) & known
    conf = 0.0
    if names:
        conf = min(1.0, 0.45 + 0.1 * len(names) + (0.25 if quoted & known else 0.0))
    return Grounding(names=names, confidence=conf, missed=not bool(names))


def ground_seed(instruction: str, repo_before: RepoBefore, patch: str) -> Grounding:
    """Grounds the instruction against the PRE-edit source (the before).

    Grounding deliberately uses the before-source: the seed is what the
    instruction names in the code that already exists.
    """
    sources = _all_sources(repo_before)
    known: set = set()
    for src in sources.values():
        known |= code_names(src)
    raw = set(_WORD.findall(instruction or ""))
    quoted = set(re.findall(r"[`'\"]([A-Za-z_][A-Za-z0-9_]*)[`'\"]", instruction or ""))
    names = (raw | quoted) & known
    conf = 0.0
    if names:
        conf = min(1.0, 0.45 + 0.1 * len(names) + (0.25 if quoted & known else 0.0))
    return Grounding(names=names, confidence=conf, missed=not bool(names))
