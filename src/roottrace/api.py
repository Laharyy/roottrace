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