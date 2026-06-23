"""EditScope oracle — frozen audit() API (P1: Oracle / Codebase Lead).

Public surface (schema v1.0.0):
    audit(instruction, repo_before, patch, policy="P4") -> AuditResult
    audit_case(instruction, before, after, tests=None, policy="P4") -> AuditResult

Authorization invariant (sound): a unit is Authorized under P4 ONLY if it is
in the instruction seed OR satisfies resolver-confirmed W2 (forced closure).
W1 (behavioral) is a risk router and can never authorize.
"""
from .audit import audit, audit_case, save_audit
from .policy import is_soundly_authorized
from .schema import (
    AuditResult,
    Classification,
    MetricCard,
    Policy,
    Provenance,
    UnitVerdict,
    Warrant,
    W2Evidence,
    RouterSignal,
)

SCHEMA_VERSION = "1.0.0"

__all__ = [
    "audit",
    "audit_case",
    "save_audit",
    "is_soundly_authorized",
    "AuditResult",
    "Classification",
    "MetricCard",
    "Policy",
    "Provenance",
    "UnitVerdict",
    "Warrant",
    "W2Evidence",
    "RouterSignal",
    "SCHEMA_VERSION",
]
