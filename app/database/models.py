"""
FinGuard Tier 2: Database Models & Contracts
Enforces ACID session logging and semantic vector memory structures.
"""
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any
import uuid


@dataclass
class ReviewSession:
    id: str  # UUIDv4
    repo_name: str
    pr_id: str
    commit_sha: str
    author_id: str
    payload_hash: str  # SHA-256
    findings_count: int
    dlp_status: str  # "CLEAN" | "REDACTED" | "QUARANTINED"
    execution_duration_ms: int
    quality_score: float = 10.0  # Standardized 1.0 to 10.0 scale
    user_id: str = "default_user"  # Persistent user session identifier
    language: str = "python"  # python | javascript | typescript | go | java
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class HistoricalIncident:
    id: str  # UUIDv4
    pr_url: str
    bug_category: str  # e.g., "DOUBLE_SPEND_RACE", "MISSING_IDEMPOTENCY", etc.
    description: str
    root_cause: str
    remediation: str
    fix_commit_sha: str
    embedding: List[float] = field(default_factory=list)  # 768-dim float vector
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ReviewRule:
    rule_id: str
    rule_name: str
    base_weight: float = 1.0
    current_weight: float = 1.0
    ci_flakiness_correlation: float = 0.0
    revert_count: int = 0
    last_updated: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class MatchedPrecedent:
    pr_id: str
    bug_category: str
    similarity_score: float
    description: str
    root_cause: str
    remediation: str
    fix_commit_sha: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class VectorQueryResult:
    matched_precedents: List[MatchedPrecedent]
    elevated_rules: List[str]
    query_duration_ms: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "matched_precedents": [p.to_dict() for p in self.matched_precedents],
            "elevated_rules": self.elevated_rules,
            "query_duration_ms": self.query_duration_ms
        }
