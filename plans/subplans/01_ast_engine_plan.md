# Subplan 01: Token-Free AST Engine & Static Linters (Tier 0)

**Owner:** `AGENT-AST-PERF`  
**Parent:** [MASTER_IMPLEMENTATION_PLAN.md](file:///c:/Users/Vansh/Desktop/codeKitchenHack/plans/MASTER_IMPLEMENTATION_PLAN.md)

---

## 1. Objectives & Scope

Intercept code diffs at wire speed (0ms–15ms) using Python's native `ast` module to detect deterministic FinTech violations with 100% precision and zero LLM cost.

> **Dual Hybrid Execution Topology:**
> The AST Engine operates identically in two environments:
> 1. **Client-Side (Local CLI / Git Hook):** Runs instantly on the developer's laptop (`finguard review` or pre-commit hook). Halts immediately if syntax is broken or critical violations exist, saving developer time and network bandwidth.
> 2. **Server-Side (Cloud Run Ingestion Gateway):** Runs as the wire-speed pre-flight gate inside the Cloud Run FastAPI service when reviews arrive via GitHub webhook or the hosted Web Console. Protects the GCP Vertex AI quota and 300 sandbox credit points from being wasted on syntax errors or deterministic anti-patterns.

## 2. Technical Architecture & Rule Specifications

### 2.1 Rule Set Definitions

1. **`AST-FIN-001` (Float In Currency):**
   * Target: Arithmetic operations (`Add`, `Sub`, `Mult`, `Div`) where operands are `float` or cast to `float()` in ledger/billing modules.
   * Action: Flag critical error and suggest `decimal.Decimal` or integer micro-units.
2. **`AST-FIN-002` (Missing Idempotency Key):**
   * Target: FastAPI/Flask routes with path prefixes `/pay`, `/transfer`, `/settle`, `/refund` that lack an `Idempotency-Key` header parameter in function arguments or dependency injections.
   * Action: Flag high-severity warning with boiler-plate dependency snippet.
3. **`AST-FIN-003` (Network Call in Transaction Lock):**
   * Target: HTTP calls (`requests.`, `httpx.`, `urllib.`) invoked inside `with db.begin():` or `with session.begin_nested():` blocks.
   * Action: Flag critical deadlock / connection exhaustion risk.
4. **`AST-FIN-004` (Unchecked Return on Balance Debit):**
   * Target: Call to debit function without conditional check or exception handling.

### 2.2 Short-Circuit Engine

* If the file has a raw Python syntax error (`SyntaxError`), immediately halt analysis with `SHORT_CIRCUIT_CRITICAL`—do not invoke Vertex AI.
* If deterministic rules find >3 critical flaws, provide immediate AST report and give the user an option to review before sending to Gemini.

## 3. Interface & Deliverables

* Module: `app/ast_engine/analyzer.py`, `app/ast_engine/rules.py`, `app/ast_engine/visitor.py`
* Tests: `tests/test_ast_engine.py` covering positive/negative cases for all 4 rules.
