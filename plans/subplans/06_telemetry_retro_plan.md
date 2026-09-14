# Subplan 06: Telemetry Ingestion & Dynamic Weighting (Tier 5)

**Owner:** `AGENT-RETRO-LEARN`  
**Parent:** [MASTER_IMPLEMENTATION_PLAN.md](file:///c:/Users/Vansh/Desktop/codeKitchenHack/plans/MASTER_IMPLEMENTATION_PLAN.md)

---

## 1. Objectives & Scope

Create a self-optimizing closed loop that correlates post-deploy production bugs, git reverts, and CI flakiness with review rules, continuously updating rule weights via Bayesian adjustment.

## 2. Technical Architecture

### 2.1 Telemetry Signal Ingestion

* Webhook receiver `/api/v1/telemetry/event` capturing:
  * `POST_DEPLOY_REVERT`: Triggered when a commit is reverted in git (`git revert`).
  * `CI_BUILD_FLAKINESS`: Triggered when transactional integration tests fail intermittently.
  * `DEV_ACCEPTED_PATCH`: Developer clicked "Apply One-Click Fix" and merged.
  * `DEV_REJECTED_FINDING`: Developer dismissed warning as false positive with rationale.

### 2.2 Dynamic Bayesian Rule Weighting Algorithm

* Each rule $R_i$ maintains a dynamic weight $W_i \in [0.2, 5.0]$.
* If a rule was flagged on a PR that later suffered a revert, $W_i \leftarrow \min(W_i + (\alpha \times 2.0), 5.0)$ (elevating its prominence in future reviews).
* If a rule is repeatedly dismissed by senior developers as a false positive, $W_i \leftarrow \max(W_i - (\alpha \times 0.8), 0.2)$.
  > [!IMPORTANT FIX — NEW-02] Floor is `0.2`, NOT `0.1`. Consistent with Audit Report SG-05. No safety-critical rule can be suppressed below `0.2` regardless of dismissal volume.
* High-performing rules are surfaced at the top of the prompt and prioritized in AST analysis.

### 2.3 Learning Ledger Persistence

* Logs all feedback events and metric updates to `.finguard/learning_ledger.json` and Cloud SQL `review_rules`.

## 3. Interface & Deliverables

* Module: `app/telemetry/listener.py`, `app/telemetry/optimizer.py`, `app/telemetry/ledger.py`
* Tests: `tests/test_telemetry_optimizer.py` asserting Bayesian updates and bounds.
