"""
FastAPI service exposing RootTrace's ingestion pipeline over HTTP.

Why this file exists: an API is what lets other systems (a ChatOps bot, a
frontend dashboard, another service) trigger an incident investigation,
instead of RootTrace only being runnable as a local script.
"""

import logging
from fastapi import FastAPI, HTTPException

from roottrace.config import settings
from roottrace.ingestion import build_incident_timeline
from roottrace.models import IncidentTimeline
from roottrace.retrieval import retrieve_similar_postmortems, VoyageAPIKeyMissing
from roottrace.reasoning import diagnose, ReasoningAPIKeyMissing

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

logger = logging.getLogger(__name__)

app = FastAPI(
    title="RootTrace",
    description="Autonomous AI-driven incident investigation platform",
    version="0.1.0",
)


@app.get("/health")
def health_check() -> dict:
    """Basic liveness check -- lets monitoring tools (or a hiring manager
    running this) confirm the service is up before calling anything else."""
    return {"status": "ok"}


@app.post("/ingest", response_model=IncidentTimeline)
def ingest() -> IncidentTimeline:
    """Runs the ingestion pipeline against the configured mock data files
    and returns the resulting IncidentTimeline as JSON."""
    try:
        return build_incident_timeline(settings.logs_path, settings.deployments_path)
    except FileNotFoundError as e:
        logger.exception("Data file missing during ingestion")
        raise HTTPException(status_code=500, detail=f"Data file not found: {e}")


@app.post("/investigate")
def investigate() -> dict:
    """Runs the full pipeline: ingestion -> correlation -> RAG retrieval ->
    dual-model reasoning with cross-verification. This is the complete
    'autonomous investigation' flow described in the project abstract."""
    try:
        timeline = build_incident_timeline(settings.logs_path, settings.deployments_path)
    except FileNotFoundError as e:
        logger.exception("Data file missing during ingestion")
        raise HTTPException(status_code=500, detail=f"Data file not found: {e}")

    critical_summaries = [
        e.summary for e in timeline.events if e.severity == "CRITICAL"
    ]
    if not critical_summaries:
        return {"timeline": timeline, "similar_incidents": [], "diagnosis": None}

    incident_description = " ".join(critical_summaries)
    if timeline.suspect_deployment:
        incident_description += f" Deployed shortly before: {timeline.suspect_deployment.title}."

    try:
        matches = retrieve_similar_postmortems(incident_description, top_k=3)
    except VoyageAPIKeyMissing as e:
        logger.exception("Voyage API key missing")
        raise HTTPException(status_code=503, detail=str(e))

    try:
        diagnosis = diagnose(timeline, matches)
    except ReasoningAPIKeyMissing as e:
        logger.exception("Reasoning API key missing")
        raise HTTPException(status_code=503, detail=str(e))

    return {"timeline": timeline, "similar_incidents": matches, "diagnosis": diagnosis}