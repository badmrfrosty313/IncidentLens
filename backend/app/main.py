"""FastAPI application. Thin: validation and HTTP mapping only; logic lives in the pipeline."""

from __future__ import annotations

import os
from typing import Literal

from fastapi import FastAPI, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response

from . import __version__
from .config import DEFAULT_LIMITS
from .demo import list_scenarios, run_scenario
from .errors import IncidentLensError
from .middleware import BodySizeLimitMiddleware
from .models import AnalysisResponse, AnalyzeRequest, DemoResponse, ScenarioInfo
from .pipeline import analyze_text
from .redaction import redact_text
from .reporting import render_json, render_markdown

DESCRIPTION = """
Turns raw application logs (plaintext, JSON, JSONL) into a structured incident analysis.

* Analysis is **deterministic** and runs entirely in-process: no external services, no API keys.
* Common secrets are **redacted before analysis**; raw logs are never stored.
* Hypothesis **evidence scores are heuristic ranking scores, not probabilities**.
"""

app = FastAPI(title="IncidentLens API", version=__version__, description=DESCRIPTION)

# Request bodies are JSON-escaped text; allow some headroom over the decoded-size limit.
# The exact decoded-size limit is enforced again in the pipeline.
app.add_middleware(BodySizeLimitMiddleware, max_body_bytes=DEFAULT_LIMITS.max_input_bytes * 2 + 65_536)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in os.environ.get("INCIDENTLENS_CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",") if o.strip()],
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)


@app.exception_handler(IncidentLensError)
async def _domain_error(_: Request, exc: IncidentLensError) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content={"code": exc.code, "detail": exc.message})


@app.exception_handler(RequestValidationError)
async def _validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
    """FastAPI's default 422 body echoes the offending ``input`` - for this API that is the raw,
    unredacted log upload (or whatever a client put in a field). Return only where and what kind
    of error occurred; never the submitted value, the message text or the error context."""
    errors = [
        {"loc": [redact_text(str(part))[:64] for part in err.get("loc", ())][:6], "type": str(err.get("type", "invalid"))[:64]}
        for err in exc.errors()[:20]
    ]
    return JSONResponse(
        status_code=422,
        content={"code": "validation_error", "detail": "Request validation failed; submitted values are not echoed.", "errors": errors},
    )


@app.get("/api/health", tags=["system"], summary="Liveness check")
def health() -> dict[str, str]:
    return {"status": "ok", "version": __version__}


@app.post(
    "/api/analyze", response_model=AnalysisResponse, tags=["analysis"],
    summary="Analyze raw logs",
    responses={413: {"description": "Input exceeds size or event-count limits"}, 422: {"description": "Empty or invalid input"}},
)
def analyze(req: AnalyzeRequest) -> AnalysisResponse:
    return analyze_text(req.content, format_hint=req.format)


@app.get("/api/demo", response_model=list[ScenarioInfo], tags=["demo"], summary="List demo scenarios and expected outcomes")
def demo_list() -> list[ScenarioInfo]:
    return list_scenarios()


@app.get(
    "/api/demo/{scenario}", response_model=DemoResponse, tags=["demo"], summary="Analyze a demo scenario",
    responses={404: {"description": "Unknown scenario"}},
)
def demo_run(scenario: str) -> DemoResponse:
    return run_scenario(scenario)


def _report_response(result: AnalysisResponse, fmt: Literal["markdown", "json"], stem: str) -> Response:
    if fmt == "markdown":
        return Response(render_markdown(result), media_type="text/markdown; charset=utf-8",
                        headers={"Content-Disposition": f'attachment; filename="{stem}.md"'})
    return Response(render_json(result), media_type="application/json",
                    headers={"Content-Disposition": f'attachment; filename="{stem}.json"'})


@app.post("/api/report", tags=["reporting"], summary="Analyze raw logs and export an incident report")
def report(req: AnalyzeRequest, format: Literal["markdown", "json"] = Query("markdown")) -> Response:
    return _report_response(analyze_text(req.content, format_hint=req.format), format, "incident-report")


@app.get("/api/demo/{scenario}/report", tags=["reporting"], summary="Export an incident report for a demo scenario")
def demo_report(scenario: str, format: Literal["markdown", "json"] = Query("markdown")) -> Response:
    return _report_response(run_scenario(scenario).analysis, format, f"incident-report-{scenario}")
