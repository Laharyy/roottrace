"""
ChatOps delivery for RootTrace.

Formats an investigation result (timeline + diagnosis + action outcome) as
a Slack Block Kit message and posts it via an Incoming Webhook.

Scope note: this delivers findings and action outcomes to Slack, matching
the core "ChatOps delivery" goal in the project abstract. Interactive
approve/reject buttons are intentionally out of scope -- they require a
public HTTPS endpoint for Slack to call back to (request verification,
hosting, etc.), which is real infrastructure beyond a local dev project.
Documented here as a known next step, not silently omitted.
"""

import logging

import requests

from roottrace.config import settings
from roottrace.models import IncidentTimeline, VerifiedDiagnosis, RemediationAction

logger = logging.getLogger(__name__)


class SlackWebhookMissing(RuntimeError):
    """Raised when a Slack notification is attempted without
    SLACK_WEBHOOK_URL configured."""
    pass


def _confidence_emoji(confidence: int) -> str:
    """A status icon so engineers can gauge severity/certainty at a glance.
    Uses Slack's standard alerting-style icons (checkmark/warning/alert)
    rather than colored circles, matching the visual convention of real
    incident-management tools like PagerDuty or Datadog alerts."""
    if confidence >= 85:
        return ":white_check_mark:"
    if confidence >= 70:
        return ":warning:"
    return ":rotating_light:"


def build_slack_message(
    timeline: IncidentTimeline,
    diagnosis: VerifiedDiagnosis,
    action: RemediationAction,
) -> dict:
    """Builds a Slack Block Kit payload. Returns a plain dict (not a Pydantic
    model) because this is the exact shape Slack's API expects -- no
    validation benefit to wrapping it further for a one-way outbound
    payload we control completely ourselves."""
    critical_count = sum(1 for e in timeline.events if e.severity == "CRITICAL")
    emoji = _confidence_emoji(diagnosis.combined_confidence)

    action_line = "No action taken (dry run or below threshold)."
    if action.action_taken and action.pr_url:
       action_line = f":white_check_mark: Remediation PR opened: {action.pr_url}"
    elif diagnosis.requires_human_review:
       action_line = ":rotating_light: *Human review required* before any action is taken."

    blocks = [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": f"{emoji} RootTrace Incident Investigation"},
        },
        {
            "type": "section",
            "fields": [
                {"type": "mrkdwn", "text": f"*Critical events:*\n{critical_count}"},
                {"type": "mrkdwn", "text": f"*Combined confidence:*\n{diagnosis.combined_confidence}%"},
                {"type": "mrkdwn", "text": f"*Models agree:*\n{diagnosis.models_agree}"},
                {"type": "mrkdwn", "text": f"*Human review needed:*\n{diagnosis.requires_human_review}"},
            ],
        },
        {"type": "divider"},
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": f"*Root cause:*\n{diagnosis.final_root_cause}"},
        },
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": f"*Suggested fix:*\n{diagnosis.llama_analysis.suggested_fix}"},
        },
        {"type": "divider"},
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": action_line},
        },
    ]

    return {"blocks": blocks}


def notify_slack(timeline: IncidentTimeline, diagnosis: VerifiedDiagnosis, action: RemediationAction) -> bool:
    """Posts the investigation result to Slack. Returns True on success.
    Failures are logged but never raised as exceptions that would break the
    caller's response -- a Slack outage shouldn't cause /investigate-and-act
    itself to fail; the investigation result is still valid and useful even
    if the notification couldn't be delivered."""
    if not settings.slack_webhook_url:
        raise SlackWebhookMissing("SLACK_WEBHOOK_URL is not set.")

    payload = build_slack_message(timeline, diagnosis, action)

    try:
        response = requests.post(settings.slack_webhook_url, json=payload, timeout=10)
        response.raise_for_status()
        logger.info("Slack notification sent successfully")
        return True
    except requests.RequestException:
        logger.exception("Failed to send Slack notification")
        return False