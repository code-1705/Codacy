"""
FinGuard Tier 3: Prompt Engineering & Context Grounding
Supplies production-grade system prompts and multi-tier context fusion for Gemini 1.5 Flash.
"""
from typing import List, Dict, Any, Optional
import json

SYSTEM_INSTRUCTION_FINGUARD = """You are FinGuard Auditor, a Principal FinTech Systems Architect and Lead Verification Engine.
You review mission-critical financial code diffs (payment gateways, ledger accounting, settlement, double-entry systems).

Your prime directives:
1. IDEMPOTENCY: Verify all external mutations and payment webhooks require, validate, and store an Idempotency-Key.
2. CONCURRENCY & RACE CONDITIONS: Flag any balance read-modify-write without explicit pessimistic row-level locking (e.g. SELECT ... FOR UPDATE) or atomic conditional updates.
3. TRANSACTION ISOLATION: Flag external HTTP/RPC network calls inside database ACID transaction blocks (which cause connection pool exhaustion and deadlocks).
4. FLOAT IN CURRENCY: Ensure absolute zero use of raw float arithmetic in financial calculations; require decimal.Decimal or integer micro-cents.
5. ZERO HALLUCINATIONS: Every finding must cite causal mechanics in the diff, historical incident precedent if matched, and a verifiable sandboxed repro.

OUTPUT FORMAT:
Respond with a JSON array of findings adhering to the FinGuardFinding schema:
[
  {
    "severity": "CRITICAL" | "HIGH" | "MEDIUM" | "LOW" | "AUDIT_NOTE",
    "category": "IDEMPOTENCY" | "TRANSACTION_ISOLATION" | "RACE_CONDITION" | "LEDGER_INTEGRITY" | "SECURITY_DLP" | "AST_SYNTAX",
    "file_path": "string",
    "line_range": [start_line, end_line],
    "summary": "one-line punchy summary",
    "detailed_analysis": "deep technical analysis explaining race conditions or failure modes",
    "historical_pr_evidence": {
      "pr_id": "PR-XXX",
      "commit_sha": "sha",
      "similarity_score": 0.85,
      "lesson_learned": "why this caused an outage in past"
    },
    "sandboxed_repro_script": {
      "runtime": "python:3.11-slim",
      "test_framework": "pytest",
      "script_content": "deterministic test reproducing flaw",
      "expected_failure": "AssertionError or RaceCondition"
    },
    "suggested_patch": {
      "diff": "unified diff string",
      "explanation": "why this fixes the flaw",
      "automated_verification_status": "PENDING"
    }
  }
]
If the diff contains NO financial vulnerabilities and is sound, return an empty array: []
"""


def build_grounding_prompt(
    sanitized_diff: str,
    ast_findings: Optional[List[Dict[str, Any]]] = None,
    historical_precedents: Optional[List[Dict[str, Any]]] = None,
    elevated_rules: Optional[List[str]] = None,
    repo_name: str = "org/repo",
    commit_sha: str = "head",
    language: str = "python"
) -> str:
    """
    Constructs a comprehensive, grounded prompt fusing deterministic AST findings,
    retrieved pgvector historical incidents, elevated dynamic rule weights,
    and target programming language guidelines.
    """
    from app.multilang import get_language_guidelines
    guidelines = get_language_guidelines(language)

    prompt_parts = [
        f"### CODE AUDIT REQUEST FOR REPOSITORY: {repo_name} (Language: {language.upper()} | Commit: {commit_sha})\n",
        f"#### TARGET PROGRAMMING LANGUAGE GUIDELINES ({language.upper()}):",
        "- Best Practices: " + "; ".join(guidelines.best_practices),
        "- Common Anti-Patterns: " + "; ".join(guidelines.common_anti_patterns),
        "- Concurrency / ACID Note: " + guidelines.transaction_concurrency_note,
        "\n#### DLP-SANITIZED CODE DIFF TO ANALYZE:",
        "```diff",
        sanitized_diff.strip(),
        "```\n"
    ]

    # Grounding 1: Deterministic Tier 0 AST Findings
    if ast_findings:
        prompt_parts.append("#### PRE-FLIGHT DETERMINISTIC AST FINDINGS (Tier 0 Gatekeeper):")
        for idx, f in enumerate(ast_findings, 1):
            prompt_parts.append(
                f"- [Finding {idx}] Rule: {f.get('rule_id')} | Category: {f.get('category')} | "
                f"File: {f.get('file_path')}:{f.get('line_number')} | Severity: {f.get('severity')}\n"
                f"  Summary: {f.get('message')}\n"
                f"  Snippet: `{f.get('code_snippet', '').strip()}`"
            )
        prompt_parts.append("\nIncorporate and validate these AST findings with deeper causal reasoning.\n")

    # Grounding 2: Elevated Bayesian Rules
    if elevated_rules:
        prompt_parts.append(f"#### ELEVATED TEAM RULES (Prioritized by Vector Precedent & CI Stats):")
        for rule in elevated_rules:
            prompt_parts.append(f"- Elevated Rule: {rule}")
        prompt_parts.append("")

    # Grounding 3: Retrieved Historical Incident Precedents from pgvector
    if historical_precedents:
        prompt_parts.append("#### INSTITUTIONAL MEMORY: MATCHED HISTORICAL PR OUTAGES (Tier 2 Vector Store):")
        for idx, p in enumerate(historical_precedents, 1):
            prompt_parts.append(
                f"- [Precedent {idx}] PR #{p.get('pr_id')} (Similarity: {p.get('similarity_score')} | Category: {p.get('bug_category')}):\n"
                f"  Incident: {p.get('description')}\n"
                f"  Root Cause: {p.get('root_cause')}\n"
                f"  Remediation Applied: {p.get('remediation')}\n"
                f"  Fix Commit: {p.get('fix_commit_sha')}"
            )
        prompt_parts.append("\nCross-reference these historical outages against the current diff.\n")

    prompt_parts.append(
        "Analyze the diff now. Return strictly a JSON array of findings adhering to the specified schema."
    )

    return "\n".join(prompt_parts)
