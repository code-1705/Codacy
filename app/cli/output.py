"""
FinGuard CLI: Terminal Output & Aesthetics Formatter
Supports ANSI color highlighting, structured findings reporting, diff display, and metrics.
"""
import sys
from typing import List, Dict, Any, Optional

# ANSI Color Codes
RESET = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"
RED = "\033[31m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
BLUE = "\033[34m"
MAGENTA = "\033[35m"
CYAN = "\033[36m"
WHITE = "\033[37m"
BG_RED = "\033[41m"
BG_GREEN = "\033[42m"
BG_YELLOW = "\033[43m"

# Ensure UTF-8 output on Windows terminals
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
if hasattr(sys.stderr, "reconfigure"):
    try:
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


BANNER = rf"""{CYAN}{BOLD}
 ███████╗██╗███╗   ██╗ ██████╗ ██╗   ██╗ █████╗ ██████╗ ██████╗ 
 ██╔════╝██║████╗  ██║██╔════╝ ██║   ██║██╔══██╗██╔══██╗██╔══██╗
 █████╗  ██║██╔██╗ ██║██║  ███╗██║   ██║███████║██████╔╝██║  ██║
 ██╔══╝  ██║██║╚██╗██║██║   ██║██║   ██║██╔══██║██╔══██╗██║  ██║
 ██║     ██║██║ ╚████║╚██████╔╝╚██████╔╝██║  ██║██║  ██║██████╔╝
 ╚═╝     ╚═╝╚═╝  ╚═══╝ ╚═════╝  ╚═════╝ ╚═╝  ╚═╝╚═╝  ╚═╝╚═════╝ 
{RESET}{WHITE}{BOLD} [FinGuard] Intelligent FinTech Verifiable Code Review Engine{RESET}
{DIM} Track 1: The 24/7 Intelligent Code Reviewer | created at Code Kitchen Season 01{RESET}
"""


def print_banner():
    """Prints the FinGuard ASCII brand banner."""
    try:
        print(BANNER)
    except UnicodeEncodeError:
        print("\n=== FinGuard: Intelligent FinTech Verifiable Code Review Engine ===")
        print("Track 1: The 24/7 Intelligent Code Reviewer | created at Code Kitchen Season 01\n")


def format_severity(severity: str) -> str:
    """Formats severity badge with high-contrast ANSI colors."""
    s = severity.upper()
    if s == "CRITICAL":
        return f"{BG_RED}{WHITE}{BOLD} CRITICAL {RESET}"
    elif s == "HIGH":
        return f"{RED}{BOLD}[HIGH]{RESET}"
    elif s == "MEDIUM":
        return f"{YELLOW}{BOLD}[MEDIUM]{RESET}"
    elif s == "LOW":
        return f"{BLUE}[LOW]{RESET}"
    else:
        return f"{CYAN}[AUDIT]{RESET}"


def print_diff_highlighted(diff_text: str):
    """Prints a unified git diff with green(+) and red(-) syntax highlighting."""
    for line in diff_text.splitlines():
        if line.startswith("+++") or line.startswith("---"):
            print(f"{BOLD}{line}{RESET}")
        elif line.startswith("+"):
            print(f"{GREEN}{line}{RESET}")
        elif line.startswith("-"):
            print(f"{RED}{line}{RESET}")
        elif line.startswith("@@"):
            print(f"{CYAN}{line}{RESET}")
        else:
            print(f"{DIM}{line}{RESET}")


def render_findings_report(findings: List[Dict[str, Any]], stats: Optional[Dict[str, Any]] = None):
    """Renders comprehensive, beautiful CLI report of FinGuard findings."""
    print("\n" + "=" * 76)
    if not findings:
        print(f"{GREEN}{BOLD}✨ FINTECH AUDIT PASSED: ZERO REGRESSIONS DETECTED{RESET}")
        print(f"{DIM}No race conditions, missing idempotency keys, unhandled rollbacks, or DLP leaks.{RESET}")
        print("=" * 76 + "\n")
        return

    crit_count = sum(1 for f in findings if f.get("severity", "").upper() == "CRITICAL")
    high_count = sum(1 for f in findings if f.get("severity", "").upper() == "HIGH")
    med_count = sum(1 for f in findings if f.get("severity", "").upper() == "MEDIUM")
    low_count = sum(1 for f in findings if f.get("severity", "").upper() in ("LOW", "AUDIT_NOTE"))

    from app.scoring import calculate_quality_rating
    rating = calculate_quality_rating(findings)

    print(f"{BOLD}FinGuard Findings Summary:{RESET} "
          f"{RED}{BOLD}{crit_count} Critical{RESET} | "
          f"{MAGENTA}{high_count} High{RESET} | "
          f"{YELLOW}{med_count} Medium{RESET} | "
          f"{CYAN}{low_count} Low/Note{RESET}")
    print(f"{BOLD}Code Quality Rating (1 to 10):{RESET} {YELLOW if rating.score < 7.5 else GREEN}{BOLD}{rating.score:.1f} / 10.0 (Grade {rating.grade}){RESET} — {DIM}{rating.verdict}{RESET}")
    print("=" * 76 + "\n")

    for i, finding in enumerate(findings, 1):
        sev_badge = format_severity(finding.get("severity", "MEDIUM"))
        cat = finding.get("category", "AUDIT")
        file_path = finding.get("file_path", "unknown")
        lines = finding.get("line_range", [0, 0])
        summary = finding.get("summary", "")
        analysis = finding.get("detailed_analysis", "")
        rule_id = finding.get("rule_id", finding.get("id", ""))

        print(f"{BOLD}Finding #{i}{RESET} {sev_badge} {CYAN}{BOLD}{cat}{RESET} (Rule: {rule_id})")
        print(f"  {BOLD}Location:{RESET} {file_path}:{lines[0]}-{lines[1]}")
        print(f"  {BOLD}Summary:{RESET}  {summary}")
        if analysis:
            print(f"  {BOLD}Analysis:{RESET} {DIM}{analysis}{RESET}")

        repro = finding.get("sandboxed_repro_script")
        if repro and isinstance(repro, dict):
            expected = repro.get("expected_failure", "Expected test failure")
            print(f"  {YELLOW}{BOLD}🔬 Sandboxed Repro ({repro.get('test_framework', 'pytest')}):{RESET} {expected}")

        patch = finding.get("suggested_patch")
        if patch and isinstance(patch, dict):
            status = patch.get("automated_verification_status", "PENDING")
            diff = patch.get("diff", "")
            print(f"  {GREEN}{BOLD}🔧 Suggested Patch (Status: {status}):{RESET}")
            if diff:
                print("  " + "-" * 70)
                for diff_line in diff.splitlines()[:15]:  # print first 15 lines of diff
                    if diff_line.startswith("+"):
                        print(f"    {GREEN}{diff_line}{RESET}")
                    elif diff_line.startswith("-"):
                        print(f"    {RED}{diff_line}{RESET}")
                    elif diff_line.startswith("@@"):
                        print(f"    {CYAN}{diff_line}{RESET}")
                    else:
                        print(f"    {DIM}{diff_line}{RESET}")
                if len(diff.splitlines()) > 15:
                    print(f"    {DIM}... ({len(diff.splitlines()) - 15} lines truncated){RESET}")
                print("  " + "-" * 70)

        print()

    if stats:
        print("-" * 76)
        token_cost = stats.get("token_cost_usd", 0.0)
        latency = stats.get("latency_ms", 0)
        tokens_saved = stats.get("token_free_rules_fired", 0)
        print(f"{DIM}Performance Telemetry: Latency: {latency:.1f}ms | Est Cost: ${token_cost:.4f} | Token-Free AST Short-Circuits: {tokens_saved}{RESET}")
    print("=" * 76 + "\n")
