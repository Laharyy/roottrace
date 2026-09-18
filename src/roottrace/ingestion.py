"""
RootTrace ingestion logic.

Reads raw log and deployment JSON files, validates them into Pydantic models
immediately (validating at the boundary -- see models.py docstring for why),
normalizes both into a shared TimelineEvent shape, and merges them into one
chronological IncidentTimeline.
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from roottrace.models import (
    LogEntry,
    DeploymentEvent,
    TimelineEvent,
    EventType,
    SuspectDeployment,
    IncidentTimeline,
)

logger = logging.getLogger(__name__)


def load_logs(path: Path) -> list[LogEntry]:
    """Load and validate logs.json into a list of LogEntry objects."""
    with open(path, "r") as f:
        raw = json.load(f)
    return [LogEntry(**entry) for entry in raw]


def load_deployments(path: Path) -> list[DeploymentEvent]:
    """Load and validate deployment_history.json into DeploymentEvent objects."""
    with open(path, "r") as f:
        raw = json.load(f)
    return [DeploymentEvent(**entry) for entry in raw]


def log_to_timeline_event(log: LogEntry) -> TimelineEvent:
    return TimelineEvent(
        timestamp=log.timestamp,
        type=EventType.LOG,
        severity=log.level.value,
        service=log.service,
        summary=log.message,
    )


def deployment_to_timeline_event(dep: DeploymentEvent) -> TimelineEvent:
    return TimelineEvent(
        timestamp=dep.timestamp,
        type=EventType.DEPLOYMENT,
        severity="DEPLOYMENT",
        service=dep.service,
        summary=f"Deployed: {dep.title} (by {dep.author}, commit {dep.commit_sha})",
    )


def find_suspect_deployment(
    deployments: list[DeploymentEvent], first_critical_at: datetime
) -> SuspectDeployment | None:
    """The most recent deployment that happened before the first CRITICAL log."""
    prior = [d for d in deployments if d.timestamp < first_critical_at]
    if not prior:
        return None
    latest = max(prior, key=lambda d: d.timestamp)
    minutes_before = (first_critical_at - latest.timestamp).total_seconds() / 60
    return SuspectDeployment(
        title=latest.title,
        timestamp=latest.timestamp,
        commit_sha=latest.commit_sha,
        pr_url=latest.pr_url,
        minutes_before_incident=round(minutes_before, 2),
    )


def build_incident_timeline(logs_path: Path, deployments_path: Path) -> IncidentTimeline:
    logger.info("Loading logs from %s", logs_path)
    logs = load_logs(logs_path)
    logger.info("Loading deployments from %s", deployments_path)
    deployments = load_deployments(deployments_path)

    events = [log_to_timeline_event(l) for l in logs]
    events += [deployment_to_timeline_event(d) for d in deployments]
    events.sort(key=lambda e: e.timestamp)

    critical_events = [e for e in events if e.severity == "CRITICAL"]
    first_critical_at = critical_events[0].timestamp if critical_events else None

    suspect = None
    if first_critical_at:
        suspect = find_suspect_deployment(deployments, first_critical_at)
        logger.warning("Suspect deployment identified: %s", suspect.title if suspect else None)

    return IncidentTimeline(
        generated_at=datetime.now(timezone.utc),
        event_count=len(events),
        first_critical_event_at=first_critical_at,
        suspect_deployment=suspect,
        events=events,
    )