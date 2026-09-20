"""
Unit tests for roottrace.chatops.

Tests message-building logic without sending any real Slack request.
"""

from datetime import datetime, timezone

from roottrace.chatops import build_slack_message, _confidence_emoji
from roottrace.models import (
    IncidentTimeline, VerifiedDiagnosis, RootCauseAnalysis, RemediationAction,
    TimelineEvent, EventType,
)

analysis = RootCauseAnalysis(root_cause="test cause", confidence=90, suggested_fix="test fix", evidence="test evidence")


def make_timeline(critical_count: int) -> IncidentTimeline:
    events = [
        TimelineEvent(
            timestamp=datetime.now(timezone.utc),
            type=EventType.LOG,
            severity="CRITICAL",
            service="test-service",
            summary=f"critical event {i}",
        )
        for i in range(critical_count)
    ]
    return IncidentTimeline(generated_at=datetime.now(timezone.utc), event_count=critical_count, events=events)


def test_confidence_emoji_thresholds():
    assert _confidence_emoji(95) == ":white_check_mark:"
    assert _confidence_emoji(75) == ":warning:"
    assert _confidence_emoji(40) == ":rotating_light:"


def test_message_includes_pr_link_when_action_taken():
    timeline = make_timeline(3)
    diagnosis = VerifiedDiagnosis(
        llama_analysis=analysis, gemini_analysis=analysis, models_agree=True,
        combined_confidence=95, final_root_cause="test cause", requires_human_review=False,
    )
    action = RemediationAction(action_taken=True, dry_run=False, reason="high confidence", pr_url="https://github.com/test/repo/pull/1")

    message = build_slack_message(timeline, diagnosis, action)
    all_text = str(message)

    assert "https://github.com/test/repo/pull/1" in all_text


def test_message_flags_human_review_when_required():
    timeline = make_timeline(3)
    diagnosis = VerifiedDiagnosis(
        llama_analysis=analysis, gemini_analysis=analysis, models_agree=False,
        combined_confidence=40, final_root_cause="unclear", requires_human_review=True,
    )
    action = RemediationAction(action_taken=False, dry_run=True, reason="not confident enough")

    message = build_slack_message(timeline, diagnosis, action)
    all_text = str(message)

    assert "Human review required" in all_text