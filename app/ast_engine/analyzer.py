"""
FinGuard Tier 0: AST Analyzer & Short-Circuit Engine
Executes token-free deterministic inspection in <15ms before Vertex AI invocation.
"""
import ast
import time
import re
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Any, Optional
from app.ast_engine.visitor import FinTechASTVisitor
from app.ast_engine.rules import DeterministicFinding


@dataclass
class ASTAnalysisResult:
    ast_status: str  # "PROCEED_TO_LLM" | "SHORT_CIRCUIT_CRITICAL" | "CLEAN"
    syntax_valid: bool
    execution_time_ms: float
    deterministic_findings: List[Dict[str, Any]]
    llm_token_savings: int
    file_path: str = ""
    error_message: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class ASTAnalyzer:
    """Zero-token static AST inspection engine for financial codebases."""

    CRITICAL_SHORT_CIRCUIT_THRESHOLD = 3

    def __init__(self, critical_threshold: int = CRITICAL_SHORT_CIRCUIT_THRESHOLD):
        self.critical_threshold = critical_threshold

    def analyze_source(self, source_code: str, file_path: str = "<source>") -> ASTAnalysisResult:
        """
        Analyze a Python source code string.
        Executes in <15ms and enforces zero LLM token cost for deterministic errors.
        """
        start_time = time.perf_counter()
        
        # Estimate token count if sent to Gemini: ~1 token per 3.5 chars + prompt overhead
        raw_char_count = len(source_code)
        estimated_token_cost = max(250, int(raw_char_count / 3.5))

        # Check raw syntax validity
        try:
            tree = ast.parse(source_code, filename=file_path)
        except SyntaxError as e:
            elapsed_ms = (time.perf_counter() - start_time) * 1000.0
            error_finding = {
                "rule_id": "AST-SYNTAX-ERR",
                "rule_name": "SyntaxError",
                "severity": "CRITICAL",
                "line_start": e.lineno or 1,
                "line_end": e.lineno or 1,
                "col_offset": e.offset or 0,
                "message": f"SyntaxError: {e.msg} at line {e.lineno}",
                "suggested_fix": "Fix Python syntax error before running semantic LLM review.",
                "file_path": file_path
            }
            return ASTAnalysisResult(
                ast_status="SHORT_CIRCUIT_CRITICAL",
                syntax_valid=False,
                execution_time_ms=round(elapsed_ms, 2),
                deterministic_findings=[error_finding],
                llm_token_savings=estimated_token_cost,
                file_path=file_path,
                error_message=f"SyntaxError: {e.msg} at line {e.lineno}"
            )

        # Run FinTech AST Visitor
        visitor = FinTechASTVisitor(file_path=file_path, source_code=source_code)
        visitor.visit(tree)

        elapsed_ms = (time.perf_counter() - start_time) * 1000.0
        findings_dicts = [f.to_dict() for f in visitor.findings]

        critical_count = sum(1 for f in visitor.findings if f.severity == "CRITICAL")

        # Determine short-circuit state
        if critical_count >= self.critical_threshold:
            status = "SHORT_CIRCUIT_CRITICAL"
            token_savings = estimated_token_cost
        elif len(visitor.findings) == 0:
            status = "CLEAN"
            token_savings = 0
        else:
            status = "PROCEED_TO_LLM"
            token_savings = 0

        return ASTAnalysisResult(
            ast_status=status,
            syntax_valid=True,
            execution_time_ms=round(elapsed_ms, 2),
            deterministic_findings=findings_dicts,
            llm_token_savings=token_savings,
            file_path=file_path,
            error_message=None
        )

    def analyze_file(self, file_path: str) -> ASTAnalysisResult:
        """Analyze a Python file from disk."""
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                code = f.read()
            return self.analyze_source(code, file_path=file_path)
        except UnicodeDecodeError:
            with open(file_path, "r", encoding="latin-1") as f:
                code = f.read()
            return self.analyze_source(code, file_path=file_path)
        except Exception as e:
            return ASTAnalysisResult(
                ast_status="SHORT_CIRCUIT_CRITICAL",
                syntax_valid=False,
                execution_time_ms=0.0,
                deterministic_findings=[],
                llm_token_savings=0,
                file_path=file_path,
                error_message=str(e)
            )

    def analyze_diff(self, diff_text: str, default_filename: str = "patch.py") -> ASTAnalysisResult:
        """
        Extract added and context lines from a unified git diff and inspect the AST tree.
        Includes surrounding context lines (e.g. function defs) and dedents if needed.
        """
        import textwrap

        diff_text = textwrap.dedent(diff_text).strip()
        hunk_lines: List[str] = []
        target_filename = default_filename

        for line in diff_text.splitlines():
            if line.startswith("+++ b/"):
                target_filename = line[6:].strip()
            elif line.startswith("+++") or line.startswith("---") or line.startswith("@@"):
                continue
            elif line.startswith("+"):
                hunk_lines.append(line[1:])
            elif line.startswith(" "):
                hunk_lines.append(line[1:])
            # '-' deleted lines are skipped

        reconstructed_code = "\n".join(hunk_lines)
        if not reconstructed_code.strip():
            return ASTAnalysisResult(
                ast_status="CLEAN",
                syntax_valid=True,
                execution_time_ms=0.1,
                deterministic_findings=[],
                llm_token_savings=0,
                file_path=target_filename
            )

        # Try analyzing reconstructed code with context
        result = self.analyze_source(reconstructed_code, file_path=target_filename)
        if result.syntax_valid:
            return result

        # Fallback: try dedenting just in case of unmatched indentation
        dedented = textwrap.dedent(reconstructed_code)
        result_dedented = self.analyze_source(dedented, file_path=target_filename)
        if result_dedented.syntax_valid:
            return result_dedented

        # Fallback 2: wrap in dummy block if it is a block-level statement
        wrapped = "def _diff_scope():\n" + textwrap.indent(dedented, "    ")
        result_wrapped = self.analyze_source(wrapped, file_path=target_filename)
        if result_wrapped.syntax_valid:
            return result_wrapped

        # Return original error result
        return result
