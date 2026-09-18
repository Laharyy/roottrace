"""
Unit tests for roottrace.ingestion.

We test find_suspect_deployment() in isolation (a true "unit" test) rather
than only testing the full pipeline end-to-end, because isolated tests tell
you exactly which piece broke when something fails.
"""

from datetime import datetime, timezone
from roottrace.ingestion import find_suspect_deployment
from roottrace.models import DeploymentEvent


def make_deployment(title: str, timestamp: datetime) -> DeploymentEvent:
    """A small helper so each test doesn't repeat all the boilerplate fields."""
    return DeploymentEvent(
        deployment_id="dep-test",
        timestamp=timestamp,
        service="checkout-api",
        title=title,
        author="test-author",
        commit_sha="abc1234",
    )


def test_finds_most_recent_deployment_before_incident():
    incident_time = datetime(2025, 1, 15, 14, 2, 0, tzinfo=timezone.utc)
    deployments = [
        make_deployment("Old fix", datetime(2025, 1, 14, 9, 30, 0, tzinfo=timezone.utc)),
        make_deployment("New Caching Logic", datetime(2025, 1, 15, 14, 0, 0, tzinfo=timezone.utc)),
    ]

    suspect = find_suspect_deployment(deployments, incident_time)

    assert suspect is not None
    assert suspect.title == "New Caching Logic"
    assert suspect.minutes_before_incident == 2.0


def test_returns_none_when_no_deployment_before_incident():
    incident_time = datetime(2025, 1, 15, 14, 2, 0, tzinfo=timezone.utc)
    deployments = [
        make_deployment("Future deploy", datetime(2025, 1, 16, 9, 0, 0, tzinfo=timezone.utc)),
    ]

    suspect = find_suspect_deployment(deployments, incident_time)

    assert suspect is None


def test_ignores_deployments_after_incident_and_picks_latest_before_it():
    incident_time = datetime(2025, 1, 15, 14, 2, 0, tzinfo=timezone.utc)
    deployments = [
        make_deployment("Oldest", datetime(2025, 1, 13, 9, 0, 0, tzinfo=timezone.utc)),
        make_deployment("Most recent before incident", datetime(2025, 1, 15, 13, 59, 0, tzinfo=timezone.utc)),
        make_deployment("After incident, should be ignored", datetime(2025, 1, 15, 15, 0, 0, tzinfo=timezone.utc)),
    ]

    suspect = find_suspect_deployment(deployments, incident_time)

    assert suspect is not None
    assert suspect.title == "Most recent before incident"