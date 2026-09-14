"""
Unit Tests for FinGuard Tier 6: FastAPI Web Console & Server Endpoints
Validates HTML serving, health checks, presets, two-step SSE handshake, and patch endpoints.
"""
import pytest
from fastapi.testclient import TestClient
from app.server import app

client = TestClient(app)


# --- 1. Root & Health Check Probes ---

def test_root_serves_html_console():
    response = client.get("/")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "FinGuard" in response.text
    assert "AIM Code Kitchen" in response.text


def test_health_check_satisfies_competition_mandates():
    response = client.get("/healthz")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "FinGuard" in data["service"]
    # Competition mandate check
    assert "created at Code Kitchen Season 01" in data["joint_credit"]

    # Also test /api/v1/health alias
    res_api = client.get("/api/v1/health")
    assert res_api.status_code == 200


# --- 2. Presets Endpoint ---

def test_get_presets_returns_five_scenarios():
    response = client.get("/api/v1/presets")
    assert response.status_code == 200
    data = response.json()
    assert "presets" in data
    presets = data["presets"]
    assert len(presets) == 5

    categories = [p["category"] for p in presets]
    assert "RACE_CONDITION" in categories
    assert "IDEMPOTENCY" in categories
    assert "FLOAT_PRECISION" in categories
    assert "SECURITY_DLP" in categories


# --- 3. Two-Step Review Handshake (POST /start -> GET /stream) ---

def test_two_step_review_api_lifecycle():
    diff_payload = """--- a/services/wallet.py
+++ b/services/wallet.py
@@ -10,3 +10,4 @@
+def withdraw(account_id, amount):
+    account = get_account(account_id)
+    account.balance -= amount
"""
    # Step 1: Ingest (POST)
    post_res = client.post("/api/v1/review/start", json={
        "diff": diff_payload,
        "repo": "org/wallets",
        "commit_sha": "a1b2c3d4e5f67890",
        "author_id": "alice@corp.com"
    })
    assert post_res.status_code == 200
    post_data = post_res.json()
    session_id = post_data["session_id"]
    assert session_id is not None
    assert post_data["status"] == "QUEUED"
    assert post_data["dlp_status"] == "CLEAN"

    # Step 2: Open SSE Stream (GET)
    stream_res = client.get(f"/api/v1/review/stream/{session_id}")
    assert stream_res.status_code == 200
    assert "text/event-stream" in stream_res.headers["content-type"]
    stream_text = stream_res.text
    assert "event: init" in stream_text
    assert "event: ast_summary" in stream_text
    assert "event: complete" in stream_text


def test_review_stream_returns_404_for_invalid_session():
    response = client.get("/api/v1/review/stream/non-existent-session-id")
    assert response.status_code == 404


# --- 4. Patch Application API ---

def test_apply_patch_endpoint():
    original = "def compute(): return 1\n"
    patch = """--- a/service.py
+++ b/service.py
@@ -1,1 +1,1 @@
-def compute(): return 1
+def compute(): return 2
"""
    response = client.post("/api/v1/patch/apply", json={
        "original_code": original,
        "patch_diff": patch
    })
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "APPLIED"
    assert "return 2" in data["patched_code"]


# --- 5. Telemetry & Rules Endpoints ---

def test_telemetry_event_endpoint():
    response = client.post("/api/v1/telemetry/event", json={
        "event_type": "DEV_ACCEPTED_PATCH",
        "repo_name": "org/payments",
        "commit_sha": "abcdef123456",
        "rule_id": "AST-FIN-001"
    })
    assert response.status_code == 200
    data = response.json()
    assert data["rule_id"] == "AST-FIN-001"
    assert data["updated_weight"] > 0


def test_list_rules_and_kpis():
    rules_res = client.get("/api/v1/rules")
    assert rules_res.status_code == 200
    assert len(rules_res.json()["rules"]) > 0

    kpi_res = client.get("/api/v1/kpis")
    assert kpi_res.status_code == 200
    assert kpi_res.json()["kpis"]["baseline_median_hours"] == 48.0
