"""
FinGuard Tier 3: SSE Streaming Review Coordinator
Implements the two-step review handshake (POST Ingest -> GET SSE Stream) and real-time event pipeline.
"""
import json
import time
import uuid
import hashlib
from typing import AsyncGenerator, Dict, Any, Optional, List
from app.ai.models import (
    FinGuardFinding,
    ReviewStartRequest,
    ReviewStartResponse,
    AuditMetadata
)
from app.ai.prompts import build_grounding_prompt
from app.ai.gemini_service import GeminiStreamService
from app.security.dlp_service import DLPService, DLPInspectionResult
from app.ast_engine.analyzer import ASTAnalyzer
from app.database.manager import DatabaseManager
from app.database.models import ReviewSession


def format_sse_event(event_type: str, data: Any) -> str:
    """Formats an event and payload into RFC-compliant Server-Sent Event text."""
    if isinstance(data, (dict, list)):
        payload_str = json.dumps(data)
    elif isinstance(data, str):
        payload_str = data
    else:
        payload_str = str(data)
    return f"event: {event_type}\ndata: {payload_str}\n\n"


class ReviewSessionContext:
    """In-memory transient context storing pre-flight state between Step 1 and Step 2."""
    def __init__(
        self,
        session_id: str,
        repo: str,
        commit_sha: str,
        author_id: str,
        raw_diff: str,
        dlp_result: DLPInspectionResult,
        quarantine_reason: Optional[str],
        ast_findings: List[Dict[str, Any]],
        historical_precedents: List[Dict[str, Any]],
        elevated_rules: List[str],
        payload_hash: str
    ):
        self.session_id = session_id
        self.repo = repo
        self.commit_sha = commit_sha
        self.author_id = author_id
        self.raw_diff = raw_diff
        self.dlp_result = dlp_result
        self.quarantine_reason = quarantine_reason
        self.ast_findings = ast_findings
        self.historical_precedents = historical_precedents
        self.elevated_rules = elevated_rules
        self.payload_hash = payload_hash
        self.created_at = time.time()


class ReviewCoordinator:
    """
    Central orchestrator coordinating DLP scrubbing, AST analysis,
    database precedent matching, and Vertex AI Gemini 1.5 Flash SSE streaming.
    """

    def __init__(
        self,
        db_manager: Optional[DatabaseManager] = None,
        gemini_service: Optional[GeminiStreamService] = None,
        offline_mode: bool = False
    ):
        self.db_manager = db_manager or DatabaseManager(backend="sqlite")
        self.gemini_service = gemini_service or GeminiStreamService(offline_mode=offline_mode)
        self.dlp_service = DLPService(backend="local")
        self.ast_analyzer = ASTAnalyzer()
        self._active_sessions: Dict[str, ReviewSessionContext] = {}

    # --- Step 1: Ingestion & Pre-flight Handshake (POST) ---

    def start_review(self, request: ReviewStartRequest) -> ReviewStartResponse:
        """
        Step 1 of the two-step handshake.
        Executes zero-token DLP scrubbing, adversarial inspection, and AST analysis (<200ms).
        Persists ACID audit session and prepares context for streaming.
        """
        session_id = str(uuid.uuid4())
        start_time = time.perf_counter()

        # 1. Tier 1: Cloud / Local DLP Scrubber & Adversarial Quarantine
        dlp_result = self.dlp_service.inspect(request.diff)
        quarantine_reason = dlp_result.quarantine_reason if dlp_result.dlp_status == "QUARANTINED" else None

        # 2. Tier 0: Token-Free AST Analysis on sanitized code
        ast_findings_dicts = []
        if not quarantine_reason:
            raw_ast_findings = self.ast_analyzer.analyze_diff(dlp_result.sanitized_content)
            ast_findings_dicts = raw_ast_findings.deterministic_findings

        # 3. Payload integrity hash
        payload_hash = dlp_result.integrity_hash

        # 4. Tier 2: Retrieve matched historical PR incident precedents & elevated rules
        matched_precedents_dicts = []
        elevated_rules = []
        if not quarantine_reason:
            query_text = f"{request.repo} {dlp_result.sanitized_content[:500]}"
            vec_result = self.db_manager.search_precedents_by_text(query_text, top_k=3, min_similarity=0.75)
            matched_precedents_dicts = [p.to_dict() for p in vec_result.matched_precedents]
            elevated_rules = vec_result.elevated_rules

        # 5. Build in-memory session context
        context = ReviewSessionContext(
            session_id=session_id,
            repo=request.repo,
            commit_sha=request.commit_sha,
            author_id=request.author_id,
            raw_diff=request.diff,
            dlp_result=dlp_result,
            quarantine_reason=quarantine_reason,
            ast_findings=ast_findings_dicts,
            historical_precedents=matched_precedents_dicts,
            elevated_rules=elevated_rules,
            payload_hash=payload_hash
        )
        self._active_sessions[session_id] = context

        # 6. Log immutable ACID session record
        duration_ms = int((time.perf_counter() - start_time) * 1000.0)
        session_record = ReviewSession(
            id=session_id,
            repo_name=request.repo,
            pr_id=request.commit_sha[:8],
            commit_sha=request.commit_sha,
            author_id=request.author_id,
            payload_hash=payload_hash,
            findings_count=len(ast_findings_dicts),
            dlp_status=dlp_result.dlp_status,
            execution_duration_ms=duration_ms
        )
        self.db_manager.log_session(session_record)

        return ReviewStartResponse(
            session_id=session_id,
            status="QUARANTINED" if quarantine_reason else "QUEUED",
            repo=request.repo,
            commit_sha=request.commit_sha,
            dlp_status=dlp_result.dlp_status,
            redacted_count=dlp_result.redacted_findings_count,
            ast_findings_count=len(ast_findings_dicts)
        )


    # --- Step 2: Real-time SSE Streaming Pipeline (GET) ---

    async def stream_review(self, session_id: str) -> AsyncGenerator[str, None]:
        """
        Step 2 of the two-step handshake.
        Streams Gemini 1.5 Flash reasoning chunks, structured FinGuardFinding objects,
        repro specs, and final audit telemetry over Server-Sent Events (SSE).
        """
        context = self._active_sessions.get(session_id)
        if not context:
            yield format_sse_event("error", {"error": "SessionNotFound", "session_id": session_id})
            return

        stream_start = time.perf_counter()

        # 1. Emit init event
        yield format_sse_event("init", {
            "session_id": context.session_id,
            "repo": context.repo,
            "commit_sha": context.commit_sha,
            "author_id": context.author_id,
            "dlp_status": context.dlp_result.dlp_status,
            "redacted_entities": context.dlp_result.redacted_info_types,
            "payload_hash": context.payload_hash
        })

        # 2. Check if quarantined by Tier 1 Adversarial Firewall
        if context.quarantine_reason:
            yield format_sse_event("quarantine", {
                "session_id": context.session_id,
                "reason": context.quarantine_reason,
                "action": "PAYLOAD_REJECTED_BY_SECURITY_GATEKEEPER"
            })
            yield format_sse_event("complete", {
                "session_id": context.session_id,
                "total_findings": 0,
                "status": "QUARANTINED",
                "total_latency_ms": round((time.perf_counter() - stream_start) * 1000.0, 2),
                "audit_hash": context.payload_hash
            })
            return

        # 3. Emit AST summary event (Tier 0 pre-flight findings)
        yield format_sse_event("ast_summary", {
            "session_id": context.session_id,
            "ast_findings_count": len(context.ast_findings),
            "findings": context.ast_findings,
            "elevated_rules": context.elevated_rules,
            "historical_precedents_count": len(context.historical_precedents)
        })

        # 4. Construct grounded prompt for Gemini 1.5 Flash
        grounding_prompt = build_grounding_prompt(
            sanitized_diff=context.dlp_result.sanitized_content,
            ast_findings=context.ast_findings,
            historical_precedents=context.historical_precedents,
            elevated_rules=context.elevated_rules,
            repo_name=context.repo,
            commit_sha=context.commit_sha
        )

        # 5. Stream tokens from Gemini 1.5 Flash
        accumulated_text = ""
        async for chunk in self.gemini_service.stream_audit(
            prompt=grounding_prompt,
            ast_findings=context.ast_findings,
            historical_precedents=context.historical_precedents
        ):
            accumulated_text += chunk
            yield format_sse_event("chunk", {"text": chunk})

        # 6. Parse structured findings from Gemini's full stream
        findings = self.gemini_service.parse_findings(accumulated_text)

        # 7. Emit individual structured findings & repro specs
        for finding in findings:
            # Set audit metadata from context
            finding.audit_metadata.dlp_status = context.dlp_result.dlp_status
            finding.audit_metadata.redacted_entities = context.dlp_result.redacted_info_types
            finding.audit_metadata.latency_ms = round((time.perf_counter() - stream_start) * 1000.0, 2)

            yield format_sse_event("finding", finding.model_dump())

            if finding.sandboxed_repro_script or finding.suggested_patch:
                yield format_sse_event("repro_spec", {
                    "finding_id": finding.id,
                    "repro_script": finding.sandboxed_repro_script.model_dump() if finding.sandboxed_repro_script else None,
                    "suggested_patch": finding.suggested_patch.model_dump() if finding.suggested_patch else None
                })

        # 8. Emit final complete event
        total_latency_ms = round((time.perf_counter() - stream_start) * 1000.0, 2)
        yield format_sse_event("complete", {
            "session_id": context.session_id,
            "total_findings": len(findings),
            "status": "ANALYSIS_COMPLETE",
            "total_latency_ms": total_latency_ms,
            "audit_hash": context.payload_hash
        })
