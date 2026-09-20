"""
Unit tests for roottrace.actions.

Tests the safety gate logic in isolation -- no real GitHub calls. This is
the most important test file in the project: it proves the autonomous
action layer actually refuses to act under the conditions it's supposed to
refuse under, which is the core safety claim of the whole system.
"""

from roottrace.models import VerifiedDiagnosis, RootCauseAnalysis
from roottrace.actions import should_act_autonomously, take_action

analysis = RootCauseAnalysis(root_cause="test", confidence=95, suggested_fix="fix", evidence="evidence")


def make_diagnosis(agree: bool, confidence: int, requires_review: bool) -> VerifiedDiagnosis:
    return VerifiedDiagnosis(
        llama_analysis=analysis,
        gemini_analysis=analysis,
        models_agree=agree,
        combined_confidence=confidence,
        final_root_cause="test root cause",
        requires_human_review=requires_review,
    )


def test_high_confidence_agreement_is_actionable():
    diagnosis = make_diagnosis(agree=True, confidence=95, requires_review=False)
    should_act, reason = should_act_autonomously(diagnosis)
    assert should_act is True


def test_disagreement_blocks_action_even_with_high_confidence():
    """The critical safety test: even if combined_confidence were somehow
    high, requires_human_review=True must still block action. This
    protects against a future bug where confidence and review-required
    become inconsistent."""
    diagnosis = make_diagnosis(agree=False, confidence=90, requires_review=True)
    should_act, reason = should_act_autonomously(diagnosis)
    assert should_act is False


def test_low_confidence_blocks_action_even_when_not_flagged_for_review():
    diagnosis = make_diagnosis(agree=True, confidence=50, requires_review=False)
    should_act, reason = should_act_autonomously(diagnosis)
    assert should_act is False


def test_dry_run_never_calls_github_even_when_actionable():
    """Confirms dry_run genuinely prevents any real action, using a
    diagnosis that WOULD otherwise pass the confidence gate."""
    diagnosis = make_diagnosis(agree=True, confidence=95, requires_review=False)
    result = take_action(diagnosis, dry_run=True)
    assert result.action_taken is False
    assert result.dry_run is True
    assert result.pr_url is None