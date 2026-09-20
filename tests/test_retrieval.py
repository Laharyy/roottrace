"""
Unit tests for roottrace.retrieval.

These deliberately avoid real Voyage API calls or ChromaDB operations --
they test pure logic only, so they run fast, free, and reliably in CI
(which has no VOYAGE_API_KEY configured). Testing the live embedding/
retrieval behavior is done manually, not as part of the automated suite --
see the module docstring reasoning in retrieval.py.
"""

import pytest
from roottrace.retrieval import postmortem_to_text, _require_voyage_client, VoyageAPIKeyMissing
from roottrace.models import Postmortem
from roottrace.config import settings


def make_postmortem() -> Postmortem:
    return Postmortem(
        id="pm_test",
        title="Test Incident",
        date="2024-01-01",
        summary="Something broke.",
        root_cause="A bug caused it.",
        fix="We fixed the bug.",
        tags=["test"],
    )


def test_postmortem_to_text_includes_all_narrative_fields():
    pm = make_postmortem()
    text = postmortem_to_text(pm)

    assert "Test Incident" in text
    assert "Something broke." in text
    assert "A bug caused it." in text
    assert "We fixed the bug." in text


def test_postmortem_to_text_excludes_tags():
    """tags are metadata, not semantic content -- see models.py docstring on
    why tags don't drive retrieval. Uses a tag word guaranteed not to appear
    anywhere else in the postmortem, so this test actually isolates whether
    tags leak into the embedded text."""
    pm = Postmortem(
        id="pm_test",
        title="Something Broke",
        date="2024-01-01",
        summary="A failure happened.",
        root_cause="A bug caused it.",
        fix="We fixed the bug.",
        tags=["zephyrsaurus"],  # deliberately nonsense, can't collide with real words
    )
    text = postmortem_to_text(pm)

    assert "zephyrsaurus" not in text.lower()


def test_require_voyage_client_raises_clear_error_when_key_missing(monkeypatch):
    """Simulates a missing API key (like in CI) without needing a real one."""
    monkeypatch.setattr(settings, "voyage_api_key", None)

    with pytest.raises(VoyageAPIKeyMissing):
        _require_voyage_client()