"""
FinGuard FastAPI Production Server & Gateway
Serves the Live Evaluator Web Console and two-step review SSE streaming pipeline.
Satisfies AIM Code Kitchen Deliverable #1 (Cloud Run URL) and local CLI (finguard dashboard).
"""
import os
import sys
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import HTMLResponse, StreamingResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Dict, Any, List, Optional

from app.ai.models import ReviewStartRequest, ReviewStartResponse
from app.ai.sse_streamer import ReviewCoordinator
from app.telemetry.models import TelemetryEvent
from app.telemetry.listener import TelemetryListener
from app.telemetry.ledger import LearningLedgerManager
from app.database.manager import DatabaseManager
from app.sandbox.patcher import apply_patch, PatchApplicationError
from app.presets import DEMO_PRESETS

# Initialize FastAPI App
app = FastAPI(
    title="FinGuard Verifiable Review Engine",
    description="24/7 Intelligent FinTech Code Reviewer with deterministic AST filtering, Cloud DLP, pgvector memory, and Vertex AI Gemini 1.5 Flash SSE streaming.",
    version="1.0.0"
)

# Enable CORS for developer workstation / CLI sidecar
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Shared Core Services
db_backend = os.getenv("DATABASE_BACKEND", "sqlite")
db_url = os.getenv("DATABASE_URL")
sqlite_path = os.getenv("SQLITE_DB_PATH", ".finguard/memory.db")

db_manager = DatabaseManager(backend=db_backend, sqlite_path=sqlite_path, cloudsql_dsn=db_url)
coordinator = ReviewCoordinator(db_manager=db_manager)
telemetry_listener = TelemetryListener()
ledger_manager = LearningLedgerManager()

# Static Files Path
STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")
os.makedirs(STATIC_DIR, exist_ok=True)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


# --- 1. Root & Health Check Endpoints ---

@app.get("/", response_class=HTMLResponse)
async def serve_dashboard():
    """Serves the rich FinGuard Live Evaluator Web Console."""
    index_file = os.path.join(STATIC_DIR, "index.html")
    if os.path.exists(index_file):
        with open(index_file, "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read())
    return HTMLResponse("<h1>FinGuard Engine Active</h1><p>Static UI building...</p>")


@app.get("/healthz")
@app.get("/api/v1/health")
async def health_check():
    """Health check endpoint for Cloud Run container probes."""
    return {
        "status": "healthy",
        "service": "FinGuard Verifiable Review Engine",
        "version": "1.0.0",
        "active_backend": db_manager.active_backend_name,
        "track": "AIM Code Kitchen Season 01 - Track 1",
        "joint_credit": "created at Code Kitchen Season 01"
    }


# --- 2. Presets Endpoint ---

@app.get("/api/v1/presets")
async def get_presets():
    """Returns preset vulnerability scenarios for 1-click evaluation."""
    return {"presets": DEMO_PRESETS}


# --- 3. Two-Step Review Handshake (POST Ingest -> GET SSE Stream) ---

@app.post("/api/v1/review/start", response_model=ReviewStartResponse)
async def start_review(request: ReviewStartRequest):
    """
    Step 1: Synchronous zero-token pre-flight ingestion (<200ms).
    Executes Tier 1 DLP scrubbing, Tier 0 AST inspection, and Tier 2 pgvector memory retrieval.
    Returns session_id for SSE streaming.
    """
    try:
        response = coordinator.start_review(request)
        return response
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Review initialization failed: {str(e)}")


@app.get("/api/v1/review/stream/{session_id}")
async def stream_review(session_id: str):
    """
    Step 2: Opens Server-Sent Events (SSE) connection streaming real-time
    Gemini 1.5 Flash reasoning tokens, structured findings, and repro specs.
    """
    context = coordinator._active_sessions.get(session_id)
    if not context:
        raise HTTPException(status_code=404, detail=f"Session {session_id} not found.")

    return StreamingResponse(
        coordinator.stream_review(session_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )


# --- 4. Patch Application Endpoint ---

class ApplyPatchRequest(BaseModel):
    original_code: str
    patch_diff: str


@app.post("/api/v1/patch/apply")
async def apply_code_patch(req: ApplyPatchRequest):
    """Applies a suggested one-click patch to the source code."""
    try:
        patched = apply_patch(req.original_code, req.patch_diff)
        return {"patched_code": patched, "status": "APPLIED"}
    except PatchApplicationError as e:
        raise HTTPException(status_code=400, detail=str(e))


# --- 5. Telemetry & Bayesian Rule Tuning Endpoints ---

@app.post("/api/v1/telemetry/event")
async def ingest_telemetry_event(event: Dict[str, Any]):
    """Ingests CI flakiness, post-deploy git reverts, and developer feedback."""
    try:
        result = telemetry_listener.handle_event(event)
        return result.model_dump()
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to process telemetry: {str(e)}")


@app.get("/api/v1/rules")
async def list_rules():
    """Lists dynamic rule registry and Bayesian priority weights."""
    rules = db_manager.list_rules()
    return {"rules": [r.to_dict() for r in rules]}


@app.get("/api/v1/kpis")
async def get_pilot_kpis():
    """Returns baseline, current, and stretch pilot KPIs."""
    return {"kpis": ledger_manager.get_kpis()}


# --- 6. Historical CSV Learning & User Growth Endpoints (Track 1 Focus) ---

class CSVIngestRequest(BaseModel):
    csv_content: str


@app.post("/api/v1/rules/ingest-csv")
async def ingest_historical_csv_rules(req: CSVIngestRequest):
    """
    Ingests and vectorizes historical review data provided in schema: <id>, <type>, <description>.
    Integrates historical rules directly into vector memory for grounding.
    """
    if not req.csv_content.strip():
        raise HTTPException(status_code=400, detail="CSV content cannot be empty.")
    result = db_manager.ingest_csv(req.csv_content)
    return result


@app.get("/api/v1/users/{user_id}/growth")
async def get_user_growth(user_id: str):
    """
    Returns persistent development growth, historical quality score trajectory,
    and optimization patterns tracked over time for the specified user.
    """
    growth_data = db_manager.get_user_growth(user_id)
    return growth_data


@app.get("/api/v1/languages")
async def get_supported_languages():
    """Returns supported languages and best-practice guidelines."""
    from app.multilang import LANGUAGE_GUIDELINES
    return {
        "supported_languages": list(LANGUAGE_GUIDELINES.keys()),
        "guidelines": {k: v.__dict__ for k, v in LANGUAGE_GUIDELINES.items()}
    }
