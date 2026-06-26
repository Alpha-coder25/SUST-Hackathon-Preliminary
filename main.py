"""
QueueStorm Investigator — FastAPI Application.

Endpoints:
  GET  /health          → Health check
  POST /analyze-ticket  → Analyze a support ticket and return evidence-backed result

Safety, evidence reasoning, and schema validation are applied at every level.
"""

from __future__ import annotations

import logging
import os
import traceback
from typing import Optional

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from evidence_engine import investigate
from models import (
    AnalyzeTicketRequest,
    AnalyzeTicketResponse,
    ErrorResponse,
    HealthResponse,
)
from safety_layer import apply_safety_layer

load_dotenv()

ENABLE_METRICS = os.getenv("ENABLE_METRICS", "false").lower() in ("true", "1", "yes")

# ── Logging ────────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=getattr(logging, os.getenv("LOG_LEVEL", "INFO").upper(), logging.INFO),
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
logger = logging.getLogger("queuestorm")
# Never log full PII, secrets, or API keys

# ── App ─────────────────────────────────────────────────────────────────────────
app = FastAPI(
    title="QueueStorm Investigator",
    description="AI/API service for fintech support-ops ticket investigation",
    version="1.0.0",
)




# ── Exception Handlers ─────────────────────────────────────────────────────────

@app.exception_handler(ValidationError)
async def pydantic_validation_handler(request: Request, exc: ValidationError):
    """Handle Pydantic validation errors → 400."""
    errors = exc.errors()
    # Build a non-sensitive error message
    field_errors = []
    for err in errors:
        loc = " → ".join(str(l) for l in err.get("loc", []))
        msg = err.get("msg", "Invalid value")
        field_errors.append(f"'{loc}': {msg}")

    detail = "; ".join(field_errors[:5])  # Limit to first 5 for brevity
    if not detail:
        detail = "Request validation failed"

    logger.warning(f"Validation error (400): {detail[:200]}")
    return JSONResponse(
        status_code=400,
        content={"detail": detail, "error_code": "VALIDATION_ERROR"},
    )


@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    """Handle unexpected internal errors → 500, no stack traces exposed."""
    logger.error(f"Internal error: {traceback.format_exc()[:500]}")
    return JSONResponse(
        status_code=500,
        content={
            "detail": "An unexpected internal error occurred. Please try again later.",
            "error_code": "INTERNAL_ERROR",
        },
    )


# ── Endpoints ───────────────────────────────────────────────────────────────────

@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint. Must respond within 60s of cold start."""
    return {"status": "ok"}


@app.post("/analyze-ticket", response_model=AnalyzeTicketResponse)
async def analyze_ticket(request: AnalyzeTicketRequest):
    """
    Analyze a support ticket.

    Accepts a JSON body matching the AnalyzeTicketRequest schema.
    Returns an AnalyzeTicketResponse with evidence-based reasoning.
    """
    logger.info(
        f"Analyzing ticket: ticket_id={request.ticket_id[:20]}, "
        f"complaint_len={len(request.complaint)}, "
        f"tx_count={len(request.transaction_history or [])}"
    )

    # ── Step 1: Structural validation (handled automatically by Pydantic) ──

    # ── Step 2: Semantically validate input ──
    if not request.complaint.strip():
        return JSONResponse(
            status_code=422,
            content={
                "detail": "The complaint field must contain meaningful text.",
                "error_code": "EMPTY_COMPLAINT",
            },
        )

    # ── Step 3: Run the investigation ──
    result = investigate(request)

    # ── Step 4: Apply safety layer ──
    result = apply_safety_layer(result, request.complaint)

    # ── Step 5: Build and validate the response ──
    # Note: Pydantic will validate the dict; FastAPI auto-serializes to JSON
    return result


# ── Startup / Shutdown ──────────────────────────────────────────────────────────

@app.on_event("startup")
async def startup_event():
    logger.info("QueueStorm Investigator starting up...")
    # Expose /metrics endpoint if metrics are enabled (lazy import)
    if ENABLE_METRICS:
        from prometheus_fastapi_instrumentator import Instrumentator
        Instrumentator().instrument(app).expose(app)
        logger.info("Prometheus metrics enabled at /metrics")
    # Preload any models or resources here if needed
    logger.info("QueueStorm Investigator ready.")


@app.on_event("shutdown")
async def shutdown_event():
    logger.info("QueueStorm Investigator shutting down.")


# ── Direct run ──────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", "8000"))
    host = os.getenv("HOST", "0.0.0.0")
    uvicorn.run("main:app", host=host, port=port, reload=False)
