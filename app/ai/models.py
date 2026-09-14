"""
FinGuard Tier 3: AI Schema Models & Contracts
Enforces strict Pydantic schema validation for FinGuardFinding and SSE events.
"""
from enum import Enum
from typing import List, Optional, Dict, Any, Tuple
from pydantic import BaseModel, Field
from datetime import datetime, timezone
import uuid


class SeverityLevel(str, Enum):
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    AUDIT_NOTE = "AUDIT_NOTE"


class FindingCategory(str, Enum):
    IDEMPOTENCY = "IDEMPOTENCY"
    TRANSACTION_ISOLATION = "TRANSACTION_ISOLATION"
    RACE_CONDITION = "RACE_CONDITION"
    LEDGER_INTEGRITY = "LEDGER_INTEGRITY"
    SECURITY_DLP = "SECURITY_DLP"
    AST_SYNTAX = "AST_SYNTAX"


class HistoricalPREvidence(BaseModel):
    pr_id: str
    commit_sha: str
    similarity_score: float
    lesson_learned: str


class SandboxedReproScript(BaseModel):
    runtime: str = "python:3.11-slim"  # "python:3.11-slim" | "node:20-alpine"
    test_framework: str = "pytest"     # "pytest" | "jest"
    script_content: str
    expected_failure: str


class SuggestedPatch(BaseModel):
    diff: str
    explanation: str
    automated_verification_status: str = "PENDING"  # "PASSED" | "FAILED" | "PENDING"


class AuditMetadata(BaseModel):
    dlp_status: str = "CLEAN"  # "CLEAN" | "REDACTED"
    redacted_entities: List[str] = Field(default_factory=list)
    token_cost_usd: float = 0.0
    latency_ms: float = 0.0


class FinGuardFinding(BaseModel):
    """
    Core finding payload adhering strictly to AGENTS.md §4.1 schema.
    """
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    severity: SeverityLevel
    category: FindingCategory
    file_path: str
    line_range: List[int] = Field(default_factory=lambda: [1, 1])
    summary: str
    detailed_analysis: str
    historical_pr_evidence: Optional[HistoricalPREvidence] = None
    sandboxed_repro_script: Optional[SandboxedReproScript] = None
    suggested_patch: Optional[SuggestedPatch] = None
    audit_metadata: AuditMetadata = Field(default_factory=AuditMetadata)


# --- SSE Event Payloads ---

class ReviewStartRequest(BaseModel):
    diff: str
    repo: str = "default/repository"
    commit_sha: str = "0000000000000000000000000000000000000000"
    author_id: str = "developer@fintech.corp"
    execution_mode: str = "cloud"  # "cloud" | "local"


class ReviewStartResponse(BaseModel):
    session_id: str
    status: str = "QUEUED"
    repo: str
    commit_sha: str
    dlp_status: str
    redacted_count: int
    ast_findings_count: int
