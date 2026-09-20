"""
Pydantic models for RootTrace's core data shapes.

Why this file exists: instead of passing raw dicts around (which can silently
contain typos or missing fields), we declare exactly what a valid LogEntry,
DeploymentEvent, or TimelineEvent looks like. Pydantic validates data against
these shapes automatically and raises a clear error the moment something
doesn't match -- much better than a mysterious KeyError three functions later.
"""

from datetime import datetime
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field


class LogLevel(str, Enum):
    """Restricting log levels to a fixed set of values (an Enum) means a typo
    like 'CRITCAL' is caught immediately, instead of silently becoming a new,
    unrecognized severity that later code doesn't know how to handle."""
    INFO = "INFO"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"


class LogEntry(BaseModel):
    """A single raw log line, exactly as it appears in logs.json."""
    timestamp: datetime
    level: LogLevel
    service: str
    message: str
    stack_trace: Optional[str] = None


class DeploymentEvent(BaseModel):
    """A single raw deployment record, exactly as it appears in
    deployment_history.json."""
    deployment_id: str
    timestamp: datetime
    service: str
    title: str
    author: str
    commit_sha: str
    pr_url: Optional[str] = None
    status: str = "success"


class EventType(str, Enum):
    LOG = "log"
    DEPLOYMENT = "deployment"


class TimelineEvent(BaseModel):
    """The common, normalized shape that BOTH log entries and deployment
    events get converted into. This is what makes it possible to sort them
    together on one timeline."""
    timestamp: datetime
    type: EventType
    severity: str
    service: str
    summary: str


class SuspectDeployment(BaseModel):
    title: str
    timestamp: datetime
    commit_sha: str
    pr_url: Optional[str] = None
    minutes_before_incident: float


class IncidentTimeline(BaseModel):
    """The final output object: everything ingestor.py produces."""
    generated_at: datetime
    event_count: int
    first_critical_event_at: Optional[datetime] = None
    suspect_deployment: Optional[SuspectDeployment] = None
    events: list[TimelineEvent] = Field(default_factory=list)


class Postmortem(BaseModel):
    """A single historical incident write-up, used as retrieval context for
    the RAG layer. summary/root_cause/fix are what gets embedded -- tags and
    title are metadata for humans and filtering, not part of the semantic
    search itself (see the Part C discussion on why tags alone don't drive
    retrieval)."""
    id: str
    title: str
    date: str
    summary: str
    root_cause: str
    fix: str
    tags: list[str] = Field(default_factory=list)


class RootCauseAnalysis(BaseModel):
    """Structured output we require from each reasoning model. Enforcing
    this shape (rather than accepting free-form text) is what makes it
    possible to programmatically compare two independent models' answers."""
    root_cause: str
    confidence: int = Field(ge=0, le=100)
    suggested_fix: str
    evidence: str

class VerifiedDiagnosis(BaseModel):
    """The final output after cross-checking both models' independent
    analyses."""
    llama_analysis: RootCauseAnalysis
    gemini_analysis: RootCauseAnalysis
    models_agree: bool
    combined_confidence: int = Field(ge=0, le=100)
    final_root_cause: str
    requires_human_review: bool