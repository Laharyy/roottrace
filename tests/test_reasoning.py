"""
Unit tests for roottrace.reasoning.

Like test_retrieval.py, these avoid real API calls -- they test the pure
logic (agreement detection, confidence combining) directly, so they run
fast and free in CI without needing live model API keys.
"""

from roottrace.reasoning import _root_causes_overlap


def test_identical_root_causes_are_detected_as_agreement():
    a = "Database connection pool exhausted due to a caching feature leaking connections"
    b = "The caching feature leaked database connections, exhausting the pool"
    assert _root_causes_overlap(a, b) is True


def test_completely_different_root_causes_are_not_agreement():
    a = "Database connection pool exhausted due to a caching feature leaking connections"
    b = "DNS resolver cache TTL was too short, causing resolution timeouts under load"
    assert _root_causes_overlap(a, b) is False


def test_empty_strings_never_count_as_agreement():
    """Edge case: if either model somehow returned an empty root_cause, we
    should never treat that as 'agreement' just because there's nothing to
    disagree about -- this could silently mask a real parsing bug."""
    assert _root_causes_overlap("", "Some real root cause here") is False
    assert _root_causes_overlap("Some real root cause here", "") is False
    assert _root_causes_overlap("", "") is False