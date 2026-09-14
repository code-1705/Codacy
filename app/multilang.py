"""
FinGuard Multi-Language Inspection & Heuristics
Provides language detection, syntax analysis, and architectural guidance for:
Python, JavaScript, TypeScript, Go, Java.
Satisfies Track 1 mandate: Multi-language Reviews.
"""
import re
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, asdict


@dataclass
class LanguageGuideline:
    language: str
    best_practices: List[str]
    common_anti_patterns: List[str]
    transaction_concurrency_note: str


LANGUAGE_GUIDELINES: Dict[str, LanguageGuideline] = {
    "python": LanguageGuideline(
        language="python",
        best_practices=[
            "Use decimal.Decimal for monetary calculations instead of IEEE 754 floats.",
            "Enforce Idempotency-Key validation in state-mutating route handlers (@app.post).",
            "Keep database transactions atomic and minimal; never perform external HTTP requests inside db.transaction().",
            "Handle account debit return statuses explicitly to prevent unrecorded fund transfers."
        ],
        common_anti_patterns=[
            "Float casting in currency calculations: `amount * 0.025`",
            "Unchecked debit operations without validation or exception handling.",
            "Missing row-level locks (SELECT ... FOR UPDATE) leading to race conditions."
        ],
        transaction_concurrency_note="Python GIL does not prevent database race conditions. Always use transactional locks or atomic increments."
    ),
    "javascript": LanguageGuideline(
        language="javascript",
        best_practices=[
            "Use BigInt or precision libraries (e.g. bignumber.js, currency.js) instead of Number for currency values.",
            "Avoid unhandled Promise rejections in asynchronous payment settlement workflows.",
            "Ensure parameterized queries with ORM/query builder to prevent SQL injection in raw template strings.",
            "Validate and require Idempotency-Key headers in Express/Koa/Fastify POST routes."
        ],
        common_anti_patterns=[
            "Direct template string interpolation into queries: `db.query(`SELECT * FROM tx WHERE id = ${id}`)`",
            "Floating point operations with `Number` for financial balance calculations.",
            "Async functions with missing `await` inside transaction scopes causing unhandled race conditions."
        ],
        transaction_concurrency_note="Node.js single-threaded event loop can still experience race conditions across async I/O boundaries."
    ),
    "typescript": LanguageGuideline(
        language="typescript",
        best_practices=[
            "Use strict branded types for currency/units (e.g. `type Cents = number & { readonly __brand: unique symbol }`).",
            "Avoid `any` types in financial payload schemas.",
            "Enforce strict null checks (`strictNullChecks: true`) on optional customer ledger balances."
        ],
        common_anti_patterns=[
            "Unsafe type assertions: `(payload as any).amount`",
            "Ignoring optional chaining on nullable customer accounts."
        ],
        transaction_concurrency_note="Type safety does not prevent runtime ACID race conditions. Enforce database constraints."
    ),
    "go": LanguageGuideline(
        language="go",
        best_practices=[
            "Use `shopspring/decimal` or integer micro-units (int64) for monetary quantities.",
            "Always check and propagate `sql.Tx.Rollback()` using deferred error checks.",
            "Use channels or `sync.Mutex` to protect shared in-memory ledger state from concurrent goroutines.",
            "Never ignore errors returned by `tx.Commit()` or database balance updates."
        ],
        common_anti_patterns=[
            "Unchecked `_ = tx.Commit()` or unhandled database query errors.",
            "Goroutine leaks in long-running settlement loops without context cancellation.",
            "Using `float64` for billing amounts."
        ],
        transaction_concurrency_note="Goroutines execute concurrently. Race detector (`go test -race`) and row-level locks are required."
    ),
    "java": LanguageGuideline(
        language="java",
        best_practices=[
            "Always use `java.math.BigDecimal` with explicit `RoundingMode` for currency math; never `double` or `float`.",
            "Ensure `@Transactional(isolation = Isolation.SERIALIZABLE)` or row-level locking on account operations.",
            "Prevent SQL injection by strictly using JPA / Hibernate parameterized queries or PreparedStatements.",
            "Handle optimistic locking exceptions (`OptimisticLockException`) with structured retry logic."
        ],
        common_anti_patterns=[
            "Constructing `BigDecimal` with a double literal (`new BigDecimal(0.025)`) instead of String (`new BigDecimal(\"0.025\")`).",
            "Raw SQL string concatenation in JDBC queries.",
            "Catching generic `Exception` and swallowing transaction rollback triggers."
        ],
        transaction_concurrency_note="Java multithreading requires synchronized blocks, ReentrantLocks, or database-level isolation to ensure atomic ledger mutations."
    )
}


def detect_language(code: str, filename: Optional[str] = None) -> str:
    """
    Detects code programming language from filename extension or code syntax characteristics.
    Returns: 'python' | 'javascript' | 'typescript' | 'go' | 'java' (default: 'python')
    """
    if filename:
        fn = filename.lower()
        if fn.endswith(".py"):
            return "python"
        elif fn.endswith(".ts") or fn.endswith(".tsx"):
            return "typescript"
        elif fn.endswith(".js") or fn.endswith(".jsx") or fn.endswith(".mjs"):
            return "javascript"
        elif fn.endswith(".go"):
            return "go"
        elif fn.endswith(".java"):
            return "java"

    # Syntax heuristics
    code_strip = code.strip()
    if re.search(r"\bpackage\s+[a-zA-Z0-9_]+", code_strip) and re.search(r"\bfunc\s+[a-zA-Z0-9_]+", code_strip):
        return "go"
    if re.search(r"\bpublic\s+(?:class|interface|record)\s+[A-Z]", code_strip) or re.search(r"\bimport\s+java\.", code_strip):
        return "java"
    if re.search(r"\binterface\s+[A-Z]", code_strip) or re.search(r":\s*(?:string|number|boolean|any)\[\]", code_strip):
        return "typescript"
    if re.search(r"\bconst\s+[a-zA-Z0-9_]+\s*=", code_strip) or re.search(r"\bfunction\s+[a-zA-Z0-9_]+", code_strip) or re.search(r"=>\s*{", code_strip):
        return "javascript"
    if re.search(r"\bdef\s+[a-zA-Z0-9_]+\s*\(", code_strip) or re.search(r"\bimport\s+[a-zA-Z0-9_]+", code_strip):
        return "python"

    return "python"


def get_language_guidelines(lang: str) -> LanguageGuideline:
    """Returns guidelines and best practices for the specified language."""
    norm_lang = lang.lower().strip()
    return LANGUAGE_GUIDELINES.get(norm_lang, LANGUAGE_GUIDELINES["python"])
