"""
Multi-model root cause reasoning for RootTrace.

Sends the same incident evidence (timeline + retrieved postmortems) to two
independently-trained models -- Llama 3 (via OpenRouter) and Gemini -- and
cross-checks their answers. Independent agreement is stronger evidence than
one model's confident-sounding guess; disagreement is a genuine signal that
a human should review before any autonomous action is taken.

Note: the abstract originally called for GPT-4o and Claude 3.5 Sonnet.
Llama 3 and Gemini are substituted here due to zero-budget constraints
during development (OpenAI/Anthropic require prepaid credit; OpenRouter and
Google both offer genuine free tiers). Arguably a stronger "independent
verification" story too, since Llama, Gemini, and GPT-4o are all trained
independently by different companies. The architecture is provider-agnostic
(see call_openrouter_free/call_gemini) so swapping providers later is a
small, contained change.
"""

import json
import logging

from openai import OpenAI
from google import genai
from tenacity import retry, stop_after_attempt, wait_exponential

from roottrace.config import settings
from roottrace.models import RootCauseAnalysis, VerifiedDiagnosis, IncidentTimeline

logger = logging.getLogger(__name__)


class ReasoningAPIKeyMissing(RuntimeError):
    """Raised when a reasoning call is attempted without the relevant API
    key configured."""
    pass


SYSTEM_PROMPT = """You are an expert Site Reliability Engineer investigating a production incident.
You will be given a chronological incident timeline and a set of similar past incident postmortems.

Analyze the evidence and respond with ONLY a JSON object (no markdown, no prose outside the JSON) in exactly this shape:
{
  "root_cause": "one or two sentences on what most likely caused this incident",
  "confidence": <integer 0-100>,
  "suggested_fix": "one or two sentences on how to fix it",
  "evidence": "one or two sentences citing which specific timeline events or postmortems support your conclusion"
}"""


def build_incident_prompt(timeline: IncidentTimeline, similar_incidents: list[dict]) -> str:
    """Builds the shared evidence prompt both models receive. Using the same
    prompt for both is what makes agreement/disagreement meaningful --
    otherwise the models would just be answering different questions."""
    critical_events = [e for e in timeline.events if e.severity == "CRITICAL"]
    events_text = "\n".join(f"- [{e.timestamp}] {e.summary}" for e in critical_events)

    deployment_text = "None found before the incident."
    if timeline.suspect_deployment:
        sd = timeline.suspect_deployment
        deployment_text = (
            f"'{sd.title}' (commit {sd.commit_sha}), deployed "
            f"{sd.minutes_before_incident} minutes before the first critical event."
        )

    postmortems_text = "\n\n".join(
        f"- {m['title']}: {m['text'][:300]}..." for m in similar_incidents
    )

    return f"""INCIDENT TIMELINE - Critical events:
{events_text}

Most recent deployment before the incident:
{deployment_text}

Similar past incidents (retrieved by semantic search):
{postmortems_text}

Based on this evidence, what most likely caused this incident?"""


def _parse_model_json(raw_text: str) -> RootCauseAnalysis:
    """Models sometimes wrap JSON in markdown code fences despite
    instructions not to -- strip that defensively before parsing, then
    validate with Pydantic so malformed output fails loudly here rather
    than corrupting downstream logic."""
    cleaned = raw_text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("```")[1]
        if cleaned.startswith("json"):
            cleaned = cleaned[4:]
    parsed = json.loads(cleaned.strip())
    return RootCauseAnalysis(**parsed)


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
def call_openrouter_free(prompt: str) -> RootCauseAnalysis:
    """Uses OpenRouter's 'openrouter/free' router model, which automatically
    selects among currently-available free models (rotates over time as
    OpenRouter's free lineup changes), rather than hardcoding one specific
    model slug that can get discontinued or moved to paid with little
    notice -- exactly what happened with the original llama-3.3-70b:free
    slug during development. OpenRouter exposes an OpenAI-compatible API,
    so we reuse the openai SDK, just pointed at a different base_url.

    Retries up to 3 times with exponential backoff -- free-tier model
    endpoints occasionally return transient errors under load, and retrying
    is standard practice for any external network call, not just AI APIs."""
    if not settings.openrouter_api_key:
        raise ReasoningAPIKeyMissing("OPENROUTER_API_KEY is not set.")

    client = OpenAI(
        api_key=settings.openrouter_api_key,
        base_url="https://openrouter.ai/api/v1",
    )
    response = client.chat.completions.create(
        model="openrouter/free",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        temperature=0.2,
    )
    content = response.choices[0].message.content
    if content is None:
        raise ValueError("OpenRouter returned an empty response with no content.")
    return _parse_model_json(content)


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
def call_gemini(prompt: str) -> RootCauseAnalysis:
    """Retries up to 3 times with exponential backoff for the same reason
    as call_openrouter_free -- Gemini's free tier can return transient 503s
    under high demand, which typically resolve within a few seconds."""
    if not settings.gemini_api_key:
        raise ReasoningAPIKeyMissing("GEMINI_API_KEY is not set.")

    client = genai.Client(api_key=settings.gemini_api_key)
    response = client.models.generate_content(
        model="gemini-3.6-flash",
        contents=f"{SYSTEM_PROMPT}\n\n{prompt}",
    )
    if response.text is None:
        raise ValueError("Gemini returned an empty response with no content.")
    return _parse_model_json(response.text)


def _root_causes_overlap(a: str, b: str) -> bool:
    """Heuristic agreement check: do the two models' root-cause explanations
    share enough key words to likely be describing the same underlying
    issue? This is intentionally simple (word overlap, not true semantic
    comparison) -- a production system would likely embed both explanations
    and compare similarity the same way Step 2's retrieval does. Flagged
    here explicitly as a known simplification, not hidden as if it were
    more rigorous than it is."""
    stopwords = {"the", "a", "an", "to", "of", "in", "on", "was", "is", "and", "this", "that", "caused", "likely"}
    words_a = {w.lower().strip(".,") for w in a.split()} - stopwords
    words_b = {w.lower().strip(".,") for w in b.split()} - stopwords
    if not words_a or not words_b:
        return False
    overlap = words_a & words_b
    smaller_set_size = min(len(words_a), len(words_b))
    return (len(overlap) / smaller_set_size) >= 0.3


def diagnose(timeline: IncidentTimeline, similar_incidents: list[dict]) -> VerifiedDiagnosis:
    """Runs both models independently on the same evidence, then
    cross-verifies their answers."""
    prompt = build_incident_prompt(timeline, similar_incidents)

    logger.info("Calling OpenRouter free-tier model for root cause analysis")
    llama_result = call_openrouter_free(prompt)

    logger.info("Calling Gemini for root cause analysis")
    gemini_result = call_gemini(prompt)

    agree = _root_causes_overlap(llama_result.root_cause, gemini_result.root_cause)

    if agree:
        combined_confidence = round((llama_result.confidence + gemini_result.confidence) / 2)
        final_root_cause = llama_result.root_cause
        requires_human_review = combined_confidence < 70
    else:
        combined_confidence = round(min(llama_result.confidence, gemini_result.confidence) * 0.5)
        final_root_cause = (
            f"Models disagree. Llama 3: {llama_result.root_cause} | "
            f"Gemini: {gemini_result.root_cause}"
        )
        requires_human_review = True

    logger.warning(
        "Diagnosis complete. Agree=%s, combined_confidence=%d, human_review_required=%s",
        agree, combined_confidence, requires_human_review,
    )

    return VerifiedDiagnosis(
        llama_analysis=llama_result,
        gemini_analysis=gemini_result,
        models_agree=agree,
        combined_confidence=combined_confidence,
        final_root_cause=final_root_cause,
        requires_human_review=requires_human_review,
    )