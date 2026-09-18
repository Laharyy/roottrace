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