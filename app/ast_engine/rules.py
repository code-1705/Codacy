"""
FinGuard Tier 0: Rule Definitions and Finding Models
Enforces strict deterministic FinTech coding standards without LLM token cost.
"""
from dataclasses import dataclass, field, asdict
from typing import Optional, List, Dict, Any


@dataclass(frozen=True)
class FinTechRule:
    id: str
    name: str
    pattern: str
    severity: str
    category: str
    description: str


@dataclass
class DeterministicFinding:
    rule_id: str
    rule_name: str
    severity: str
    line_start: int
    line_end: int
    col_offset: int
    message: str
    suggested_fix: str
    file_path: str = ""
    category: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# Predefined Rule Registry
AST_FINTECH_RULES: Dict[str, FinTechRule] = {
    "AST-FIN-001": FinTechRule(
        id="AST-FIN-001",
        name="FloatInCurrencyArithmetic",
        pattern="BinaryOp with float literals or float() casting in financial calculation functions",
        severity="CRITICAL",
        category="LEDGER_INTEGRITY",
        description="Floating-point arithmetic introduces IEEE 754 precision drift. Financial ledgers must use decimal.Decimal or integer micro-units (cents)."
    ),
    "AST-FIN-002": FinTechRule(
        id="AST-FIN-002",
        name="MissingIdempotencyGuard",
        pattern="State-mutating payment/transfer routes lacking Idempotency-Key validation parameter",
        severity="HIGH",
        category="IDEMPOTENCY",
        description="Payment or transfer endpoints must demand an Idempotency-Key header or argument to prevent duplicate billing upon client retry."
    ),
    "AST-FIN-003": FinTechRule(
        id="AST-FIN-003",
        name="NetworkCallInsideTransactionBlock",
        pattern="External HTTP or socket network calls executed inside ACID database transaction blocks",
        severity="CRITICAL",
        category="TRANSACTION_ISOLATION",
        description="Holding database transaction locks during external network I/O exhausts database connection pools and causes high lock contention / deadlocks."
    ),
    "AST-FIN-004": FinTechRule(
        id="AST-FIN-004",
        name="UncheckedDebitReturn",
        pattern="Call to debit, deduct, or withdraw function where return value is discarded without conditional checking",
        severity="CRITICAL",
        category="LEDGER_INTEGRITY",
        description="Balance debit or deduct functions must have their return values evaluated or be enclosed in explicit exception-handling blocks."
    ),
}
