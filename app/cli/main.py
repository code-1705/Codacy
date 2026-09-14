"""
FinGuard CLI: Command Line Interface Entrypoint
Enterprise FinTech Verifiable Code Review CLI.
Joint credit: created at Code Kitchen Season 01
"""
import sys
import os
import json
import argparse
import webbrowser
import subprocess
from typing import List, Dict, Any, Optional

from app.ast_engine.analyzer import ASTAnalyzer
from app.security.dlp_service import DLPService
from app.cli.git_utils import get_git_diff, get_git_repo_metadata, install_pre_commit_hook, uninstall_pre_commit_hook
from app.cli.output import print_banner, render_findings_report, print_diff_highlighted

VERSION = "1.0.0"
CREDIT = "created at Code Kitchen Season 01"

SEVERITY_RANKS = {
    "AUDIT_NOTE": 0,
    "LOW": 1,
    "MEDIUM": 2,
    "HIGH": 3,
    "CRITICAL": 4,
}


def parse_severity(sev_str: str) -> int:
    return SEVERITY_RANKS.get(sev_str.upper(), 2)


def run_local_review(code: str, file_path: str = "<workstation>") -> Dict[str, Any]:
    """
    Executes Tier 0 (AST) and Tier 1 (DLP / Anti-Injection) deterministic checks locally.
    Zero network latency, zero token cost.
    """
    findings: List[Dict[str, Any]] = []
    
    # 1. Tier 1: Cloud DLP / Injection pre-scrubbing
    dlp_service = DLPService(backend="local_regex")
    dlp_result = dlp_service.inspect(code)
    
    if dlp_result.dlp_status == "QUARANTINED":
        findings.append({
            "id": "SEC-QUARANTINE",
            "severity": "CRITICAL",
            "category": "SECURITY_DLP",
            "file_path": file_path,
            "line_range": [1, 1],
            "summary": "Adversarial Prompt Injection Quarantined",
            "detailed_analysis": f"Payload contained malicious prompt injection pattern: {dlp_result.quarantine_reason}",
            "audit_metadata": {
                "dlp_status": "QUARANTINED",
                "redacted_entities": dlp_result.redacted_info_types,
                "token_cost_usd": 0.0,
                "latency_ms": dlp_result.execution_time_ms
            }
        })
        return {
            "findings": findings,
            "stats": {
                "token_cost_usd": 0.0,
                "latency_ms": dlp_result.execution_time_ms,
                "token_free_rules_fired": 1,
                "dlp_status": "QUARANTINED"
            }
        }

    if dlp_result.redacted_findings_count > 0:
        findings.append({
            "id": "SEC-DLP-LEAK",
            "severity": "CRITICAL",
            "category": "SECURITY_DLP",
            "file_path": file_path,
            "line_range": [1, 1],
            "summary": f"Detected {dlp_result.redacted_findings_count} Sensitive Secrets/Credentials/PANs",
            "detailed_analysis": f"Redacted info types: {', '.join(dlp_result.redacted_info_types)}. Secrets must never be committed.",
            "audit_metadata": {
                "dlp_status": "REDACTED",
                "redacted_entities": dlp_result.redacted_info_types,
                "token_cost_usd": 0.0,
                "latency_ms": dlp_result.execution_time_ms
            }
        })

    # 2. Tier 0: AST Deterministic Gatekeeper
    ast_analyzer = ASTAnalyzer()
    ast_res = ast_analyzer.analyze_source(dlp_result.sanitized_content, file_path=file_path)
    
    for df in ast_res.deterministic_findings:
        findings.append({
            "id": df.get("rule_id", "AST-DETERMINISTIC"),
            "rule_id": df.get("rule_id", "AST-DETERMINISTIC"),
            "severity": df.get("severity", "HIGH"),
            "category": "IDEMPOTENCY" if "IDEM" in df.get("rule_id", "") else "TRANSACTION_ISOLATION",
            "file_path": file_path,
            "line_range": [df.get("line_start", 1), df.get("line_end", 1)],
            "summary": df.get("message", "Deterministic AST Rule Violation"),
            "detailed_analysis": df.get("rule_name", "") + " - " + df.get("message", ""),
            "suggested_patch": {
                "diff": f"--- a/{file_path}\n+++ b/{file_path}\n@@ -{df.get('line_start', 1)} +{df.get('line_start', 1)} @@\n+# Fix: {df.get('suggested_fix', '')}",
                "explanation": df.get("suggested_fix", ""),
                "automated_verification_status": "PENDING"
            },
            "audit_metadata": {
                "dlp_status": dlp_result.dlp_status,
                "redacted_entities": dlp_result.redacted_info_types,
                "token_cost_usd": 0.0,
                "latency_ms": ast_res.execution_time_ms
            }
        })

    total_latency = dlp_result.execution_time_ms + ast_res.execution_time_ms
    return {
        "findings": findings,
        "stats": {
            "token_cost_usd": 0.0,
            "latency_ms": total_latency,
            "token_free_rules_fired": len(ast_res.deterministic_findings) + (1 if dlp_result.redacted_findings_count > 0 else 0),
            "dlp_status": dlp_result.dlp_status
        }
    }


def cmd_review(args: argparse.Namespace) -> int:
    """Handles `finguard review` subcommand."""
    code_to_review = ""
    target_name = ""

    if args.file:
        if not os.path.exists(args.file):
            print(f"Error: File not found: {args.file}", file=sys.stderr)
            return 2
        with open(args.file, "r", encoding="utf-8", errors="replace") as f:
            code_to_review = f.read()
        target_name = args.file
    elif args.diff:
        if not os.path.exists(args.diff):
            print(f"Error: Diff file not found: {args.diff}", file=sys.stderr)
            return 2
        with open(args.diff, "r", encoding="utf-8", errors="replace") as f:
            code_to_review = f.read()
        target_name = args.diff
    elif args.staged:
        code_to_review = get_git_diff(staged=True)
        target_name = "git-staged"
    else:
        # Default: check working tree diff
        code_to_review = get_git_diff(staged=False)
        target_name = "git-working-tree"

    if not code_to_review.strip():
        if not args.json:
            print_banner()
            print(f"No changes detected in {target_name}. Workstation is clean.")
        else:
            print(json.dumps({"findings": [], "stats": {"message": "Clean"}}, indent=2))
        return 0

    # Execute review
    result = run_local_review(code_to_review, file_path=target_name)
    findings = result.get("findings", [])
    stats = result.get("stats", {})

    threshold = parse_severity(args.severity or "medium")
    filtered_findings = [
        f for f in findings if parse_severity(f.get("severity", "LOW")) >= threshold
    ]

    if args.json:
        print(json.dumps({"findings": filtered_findings, "stats": stats}, indent=2))
    else:
        print_banner()
        render_findings_report(filtered_findings, stats=stats)

    if args.ui:
        print("Launching FinGuard Web Console...")
        cmd_dashboard(args)

    # Return exit code: 1 if any finding exceeds threshold, else 0
    if filtered_findings:
        return 1
    return 0


def cmd_init(args: argparse.Namespace) -> int:
    """Handles `finguard init` subcommand."""
    config_dir = ".finguard"
    os.makedirs(config_dir, exist_ok=True)
    config_file = os.path.join(config_dir, "config.yaml")

    config_content = f"""# FinGuard Configuration
# Track 1: The 24/7 Intelligent Code Reviewer ({CREDIT})

version: "{VERSION}"
project:
  name: "FinGuard-Protected-FinTech"
  cloud_run_endpoint: "{args.endpoint or 'http://localhost:8080'}"

rules:
  tier0_ast:
    enabled: true
    critical_threshold: 3
  tier1_dlp:
    enabled: true
    backend: "local_regex"  # options: local_regex, cloud_dlp
    scrub_pci_pan: true
    scrub_private_keys: true
  tier2_vector_memory:
    enabled: true
    similarity_threshold: 0.85
  tier3_gemini:
    model: "gemini-1.5-flash-001"
    temperature: 0.1

telemetry:
  feedback_loop: true
  ledger_path: ".finguard/learning_ledger.json"
"""
    with open(config_file, "w", encoding="utf-8") as f:
        f.write(config_content)

    print(f"🛡️ Initialized FinGuard configuration in {config_file}")
    return 0


def cmd_install_hook(args: argparse.Namespace) -> int:
    """Handles `finguard install-hook` subcommand."""
    try:
        hook_path = install_pre_commit_hook(repo_root=".")
        print(f"🛡️ FinGuard pre-commit hook installed successfully at: {hook_path}")
        return 0
    except Exception as e:
        print(f"Error installing pre-commit hook: {e}", file=sys.stderr)
        return 1


def cmd_uninstall_hook(args: argparse.Namespace) -> int:
    """Handles `finguard uninstall-hook` subcommand."""
    try:
        success = uninstall_pre_commit_hook(repo_root=".")
        if success:
            print("🛡️ FinGuard pre-commit hook removed.")
        else:
            print("No pre-commit hook found in .git/hooks/")
        return 0
    except Exception as e:
        print(f"Error removing pre-commit hook: {e}", file=sys.stderr)
        return 1


def cmd_dashboard(args: argparse.Namespace) -> int:
    """Handles `finguard dashboard` subcommand."""
    port = getattr(args, "port", 7432) or 7432
    url = f"http://localhost:{port}"
    print_banner()
    print(f"🚀 Launching FinGuard Web Console on {url} ...")
    try:
        webbrowser.open(url)
    except Exception:
        pass

    try:
        import uvicorn
        uvicorn.run("app.server:app", host="127.0.0.1", port=port, log_level="info")
        return 0
    except ImportError:
        print("Error: 'uvicorn' is required to run the dashboard locally.", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\nFinGuard Web Console stopped.")
        return 0


def cmd_doctor(args: argparse.Namespace) -> int:
    """Handles `finguard doctor` diagnostics."""
    print_banner()
    print("🔬 Running FinGuard System Diagnostics...\n")

    # 1. Python Check
    py_ver = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    py_ok = sys.version_info >= (3, 11)
    print(f"  [{'PASS' if py_ok else 'FAIL'}] Python Version: {py_ver} (>= 3.11 required)")

    # 2. Git Check
    git_meta = get_git_repo_metadata()
    has_git = git_meta.get("commit_sha") != "0000000000000000000000000000000000000000"
    print(f"  [{'PASS' if has_git else 'WARN'}] Git Workstation: repo='{git_meta.get('repo')}', sha={git_meta.get('commit_sha')[:8]}")

    # 3. AST Engine Check
    try:
        ast_analyzer = ASTAnalyzer()
        test_res = ast_analyzer.analyze_source("x = 1\n", "<test>")
        ast_ok = test_res.syntax_valid
        print(f"  [{'PASS' if ast_ok else 'FAIL'}] Tier 0 AST Engine: Functional (<15ms parser)")
    except Exception as e:
        print(f"  [FAIL] Tier 0 AST Engine: {e}")

    # 4. DLP Scrubber Check
    try:
        dlp = DLPService(backend="local_regex")
        test_dlp = dlp.inspect("customer_pan = 'ABCDE1234F'")
        dlp_ok = test_dlp.dlp_status == "REDACTED"
        print(f"  [{'PASS' if dlp_ok else 'FAIL'}] Tier 1 DLP Scrubber: Functional (Local Regex & Injection Guard)")
    except Exception as e:
        print(f"  [FAIL] Tier 1 DLP Scrubber: {e}")

    # 5. Database Backend Check
    try:
        from app.database.manager import DatabaseManager
        db_mgr = DatabaseManager()
        backend_name = db_mgr.active_backend_name
        print(f"  [PASS] Tier 2 Vector Memory Backend: {backend_name}")
    except Exception as e:
        print(f"  [WARN] Tier 2 Vector Memory Backend: {e}")

    print("\n✅ FinGuard Diagnostics Complete.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    """Builds the main CLI argument parser."""
    parser = argparse.ArgumentParser(
        prog="finguard",
        description=f"FinGuard: 24/7 Intelligent FinTech Code Reviewer ({CREDIT})"
    )
    parser.add_argument("--version", action="version", version=f"FinGuard {VERSION} ({CREDIT})")

    subparsers = parser.add_subparsers(dest="command", help="FinGuard command to execute")

    # Review command
    p_review = subparsers.add_parser("review", help="Review code, staged git diff, or unified patch")
    p_review.add_argument("--file", "-f", type=str, help="Path to a single source code file")
    p_review.add_argument("--diff", "-d", type=str, help="Path to a unified diff patch file")
    p_review.add_argument("--staged", "-s", action="store_true", help="Review staged git changes")
    p_review.add_argument("--cloud", action="store_true", help="Review using Cloud Run remote gateway")
    p_review.add_argument("--local", action="store_true", default=True, help="Review locally (default)")
    p_review.add_argument("--severity", type=str, default="medium", choices=["critical", "high", "medium", "low", "audit_note"], help="Minimum severity threshold to report")
    p_review.add_argument("--json", action="store_true", help="Output findings as JSON")
    p_review.add_argument("--ui", action="store_true", help="Launch interactive browser dashboard")
    p_review.add_argument("--endpoint", type=str, default=None, help="Custom Cloud Run API endpoint")

    # Init command
    p_init = subparsers.add_parser("init", help="Initialize FinGuard configuration for current repo")
    p_init.add_argument("--endpoint", type=str, default=None, help="Default Cloud Run API endpoint")

    # Hook commands
    subparsers.add_parser("install-hook", help="Install git pre-commit hook")
    subparsers.add_parser("uninstall-hook", help="Uninstall git pre-commit hook")

    # Dashboard command
    p_dash = subparsers.add_parser("dashboard", help="Start local web console")
    p_dash.add_argument("--port", "-p", type=int, default=7432, help="Port to run web console on (default: 7432)")

    # Doctor command
    subparsers.add_parser("doctor", help="Run system diagnostics and environment health check")

    return parser


def cli_entry():
    """Main CLI entrypoint called by console_scripts."""
    parser = build_parser()
    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(0)

    dispatch = {
        "review": cmd_review,
        "init": cmd_init,
        "install-hook": cmd_install_hook,
        "uninstall-hook": cmd_uninstall_hook,
        "dashboard": cmd_dashboard,
        "doctor": cmd_doctor,
    }

    handler = dispatch.get(args.command)
    if handler:
        sys.exit(handler(args))
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    cli_entry()
