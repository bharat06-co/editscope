"""Frozen data contract for audit() output. Schema version 1.0.0.

This is the FREEZE artifact P3/P4 build against. Do not break field names
without bumping SCHEMA_VERSION and updating schemas/audit_output.schema.json.
"""
from __future__ import annotations

import enum
from dataclasses import asdict, dataclass, field
from typing import Optional


class Policy(str, enum.Enum):
    P1 = "P1"  # baseline: every non-seed unit is a Violation (naive)
    P4 = "P4"  # default: Authorization = seed ∪ W2; W1 routes the rest to Uncertain


class Classification(str, enum.Enum):
    AUTHORIZED = "Authorized"
    VIOLATION = "Violation"
    UNCERTAIN = "Closure-uncertain"


class Warrant(str, enum.Enum):
    SEED = "seed"          # part of the instruction seed
    W2 = "W2"              # forced closure, resolver-confirmed
    NONE = "none"          # no sound warrant


@dataclass
class W2Evidence:
    """Why reverting this unit provably breaks the program (resolver-confirmed)."""
    revert_breaks_compile: bool = False
    revert_breaks_name_resolution: bool = False
    revert_breaks_imports: bool = False
    resolver_confirmed_closure: bool = False

    def any_break(self) -> bool:
        return (
            self.revert_breaks_compile
            or self.revert_breaks_name_resolution
            or self.revert_breaks_imports
        )


@dataclass
class RouterSignal:
    """W1 (unsound) used ONLY to route non-seed/non-W2 units to Uncertain."""
    w1_revert_flips_test: Optional[bool] = None  # None => not evaluated / no tests


@dataclass
class UnitVerdict:
    unit_id: str
    files: list[str]
    loc_changed: int
    classification: Classification
    warrant: Warrant = Warrant.NONE
    seed_overlap: float = 0.0
    w2: W2Evidence = field(default_factory=W2Evidence)
    router: RouterSignal = field(default_factory=RouterSignal)
    note: str = ""


@dataclass
class MetricCard:
    # See Part IV §6 of the plan. Rates in [0,1]; None when not computable.
    pass_rate: Optional[float] = None
    scope_violation_rate: float = 0.0
    necessary_collateral_false_flag_rate: Optional[float] = None
    uncertain_abstention_rate: float = 0.0
    extra_edit_loc: int = 0
    extra_edit_blocks: int = 0


@dataclass
class Provenance:
    schema_version: str = "1.0.0"
    resolver: str = "unset"
    git_sha: str = "unknown"
    dataset_revision: str = "unpinned"


@dataclass
class AuditResult:
    policy: Policy
    instruction: str
    verdicts: list[UnitVerdict]
    metric_card: MetricCard
    provenance: Provenance = field(default_factory=Provenance)

    def to_json(self) -> dict:
        d = asdict(self)
        # enums -> their string values
        d["policy"] = self.policy.value
        for v in d["verdicts"]:
            v["classification"] = v["classification"].value if isinstance(
                v["classification"], Classification
            ) else v["classification"]
            v["warrant"] = v["warrant"].value if isinstance(v["warrant"], Warrant) else v["warrant"]
        return d
