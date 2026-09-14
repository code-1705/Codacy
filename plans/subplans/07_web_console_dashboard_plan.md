# Subplan 07: High-Aesthetics Review Console & Diff UI (Tier 6)
**Owner:** `AGENT-ORCHESTRATOR`  
**Parent:** [MASTER_IMPLEMENTATION_PLAN.md](file:///c:/Users/Vansh/Desktop/codeKitchenHack/plans/MASTER_IMPLEMENTATION_PLAN.md)

---

## 1. Objectives & Scope

Provide a stunning, responsive, dark-mode web console accessible at **`http://localhost:7432`** — launched by `finguard dashboard` or automatically opened by `finguard review --ui`. The console is a static web app served by the local FastAPI process. There is no hosted deployment. Every developer gets their own private instance on their own machine.

## 2. Technical Architecture & UX Design System

### 2.1 Aesthetic & Visual Requirements
* Modern FinTech dark-mode theme (`#0a0e17` background, vibrant neon accents: Emerald `#00E676` for verified fixes, Amber `#FFB300` for warnings, Crimson `#FF1744` for critical vulnerabilities, Electric Cyan `#00E5FF` for streaming tokens).
* Glassmorphism cards with smooth blur (`backdrop-filter: blur(12px)`), subtle glow borders, and clean typography (Inter / JetBrains Mono for code).
* Micro-animations on token stream updates, real-time counters for token savings ($ saved vs raw LLM), and terminal status displays.

### 2.2 Functional Modules
1. **Code & PR Ingestion Drawer:**
   * Instant preset demo buttons: "Double Spend Race Condition", "Missing Idempotency in Refund", "Float In Fee Math".
   * Live Monaco/CodeMirror editor or syntax-highlighted diff input.
2. **Real-Time SSE Audit Streamer:**
   * Live terminal-style output showing Tier 0 (AST 0ms filter), Tier 1 (Cloud DLP redaction mask), Tier 2 (pgvector incident match).
   * Streaming Gemini reasoning text token-by-token.
3. **Verifiable Proof & One-Click Patch Drawer:**
   * Embedded test runner view showing baseline failure output (Red) and post-patch test passing output (Green).
   * Side-by-side unified diff viewer with a one-click "Apply Patch" button.
4. **Telemetry & Learning Ledger Dashboard:**
   * Live telemetry panel displaying Bayesian rule weight adjustments and pilot metrics (48h $\to$ <30s review time).

## 3. Interface & Deliverables
* Static Web App served by local FastAPI at `localhost:7432`: `finguard/static/index.html`, `finguard/static/css/styles.css`, `finguard/static/js/app.js`
* SSE client connects to `http://localhost:7432/api/v1/review/stream/{session_id}`
* `finguard dashboard` keeps the server alive; `finguard review --ui` opens it temporarily.
* Tests: `tests/test_web_routes.py` verifying HTML serving and API connectivity on local port.
