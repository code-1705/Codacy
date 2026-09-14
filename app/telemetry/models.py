"""
FinGuard Tier 5: Telemetry Models & Contracts
Defines schemas for real-world CI, deployment, and developer feedback events.
"""
from enum import Enum
from typing import Dict, Any, Optional
from pydantic import BaseModel, Field
from datetime import datetime, timezone
import uuid


class TelemetryEventType(str, Enum):
    POST_DEPLOY_REVERT = "POST_DEPLOY_REVERT"
    CI_BUILD_FLAKINESS = "CI_BUILD_FLAKINESS"
    DEV_ACCEPTED_PATCH = "DEV_ACCEPTED_PATCH"
    DEV_REJECTED_FINDING = "DEV_REJECTED_FINDING"


class TelemetryEvent(BaseModel):
    id: str = Field(default_factory=lambda: f"EVT-{uuid.uuid4().hex[:8].upper()}")
    event_type: TelemetryEventType
    repo_name: str = "org/payments"
    commit_sha: str = "0000000000000000000000000000000000000000"
    rule_id: str
    pr_id: Optional[str] = None
    details: Dict[str, Any] = Field(default_factory=dict)
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class RuleWeightUpdateResult(BaseModel):
    event_id: str
    rule_id: str
    previous_weight: float
    updated_weight: float
    delta: float
    event_type: str
    revert_incremented: bool = False
    message: str = ""
