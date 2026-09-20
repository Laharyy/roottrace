# RootTrace

![CI](https://github.com/Laharyy/roottrace/actions/workflows/ci.yml/badge.svg)

**RootTrace** is an AI-driven incident investigation platform that automatically correlates code deployments with system logs to identify the likely root cause of a production incident — cutting down the manual detective work that normally eats into Mean Time to Recovery (MTTR).

Instead of just alerting "something is wrong" (like traditional monitoring), RootTrace reasons about *why* it went wrong by lining up deployment history against the exact moment a system started failing.

> **Status:** The full pipeline is complete: data ingestion, correlation, RAG retrieval, dual-model reasoning with cross-verification, a gated autonomous action layer, and Slack ChatOps delivery. See [Roadmap](#roadmap) for possible future extensions.

## Why this project

Production incidents are often caused by a recent deploy, but finding *which* deploy, out of dozens per day across services, is slow manual work. RootTrace automates the first, most time-consuming step: building a correlated timeline and surfacing the most likely suspect deployment — before an engineer even opens a dashboard.

---

## How it works (current implementation)

1. **Ingest** — reads structured logs and deployment history (from JSON, simulating log/CI sources like ELK, CloudWatch, or GitHub)
2. **Normalize** — converts both into one common event schema using validated Pydantic models
3. **Correlate** — merges everything into a single chronological timeline and identifies the most recent deployment before the first critical failure
4. **Retrieve** — embeds the incident's critical events with Voyage AI and searches a ChromaDB vector store of 50 historical postmortems (spanning 10 failure categories) to surface the most similar past incidents and how they were resolved
5. **Reason & verify** — sends the same evidence (timeline + retrieved postmortems) to two independently-trained models, which each produce a structured root-cause analysis; if they agree, confidence is combined, if they disagree, the incident is flagged for mandatory human review rather than any automated action being taken
6. **Act (gated)** — when both models agree and combined confidence clears a threshold, RootTrace can autonomously open a GitHub PR containing the incident report and recommended fix; defaults to a safe dry-run mode, and any disagreement or low confidence forces mandatory human review instead
7. **Serve** — exposes the whole pipeline as a REST API (`/investigate`, `/investigate-and-act`), so any system (a dashboard, a Slack bot, another service) can trigger an investigation — and optionally a real action — on demand
8. **Notify** — posts a formatted summary (root cause, confidence, models' agreement, and whether an action was taken) to Slack via an Incoming Webhook, so the team sees the finding where they already work



---

## Tech stack

| Layer | Choice | Why |
|---|---|---|
| Language | Python 3.14 | Standard for AI/ML tooling |
| Data validation | Pydantic v2 | Fail-fast schema validation at every data boundary |
| API | FastAPI | Async-ready, auto-generated OpenAPI docs |
| Config | pydantic-settings + `.env` | No hardcoded paths or secrets |
| Testing | pytest | Unit tests covering core correlation logic, including edge cases |
| Embeddings | Voyage AI (`voyage-3.5`) | Anthropic's recommended embedding partner; semantic search over incident history |
| Vector store | ChromaDB | Local, persistent vector database for similarity search | 
| Packaging | `src/` layout, `pyproject.toml` | Installable, import-safe package structure |
| Containerization | Docker | Identical runtime behavior on any machine |
| CI | GitHub Actions | Tests run automatically on every push |
| Reasoning | OpenRouter (free-tier router) + Google Gemini | Two independently-trained models for cross-verified diagnosis |
| Autonomous actions | PyGithub | Opens real GitHub PRs when the safety gate allows it |
| ChatOps | Slack Incoming Webhooks | Delivers investigation results directly to a Slack channel |
> **Note on model choices:** the original design called for GPT-4o and Claude 3.5 Sonnet. During development, OpenAI and Anthropic's APIs required prepaid billing with no meaningful free tier, so the dual-model verification is currently implemented with OpenRouter's free model router and Google Gemini instead — genuinely independent training lineages, zero cost. The reasoning module (`src/roottrace/reasoning.py`) is provider-agnostic, so swapping in GPT-4o/Claude is a small, contained change once budget allows.


## Safety design

The autonomous action layer is deliberately conservative:

- **Dry-run by default** — no real GitHub write ever happens unless a caller explicitly opts in (`?dry_run=false` on the API, or `dry_run=False` in code).
- **Two independent gates** — action only proceeds if (1) both reasoning models agree on the root cause, AND (2) their combined confidence clears a threshold (currently 70%). Either failing blocks action.
- **Every decision is explained** — the gate returns a human-readable reason alongside its boolean decision, so every action (or refusal to act) is auditable.

- **Notification failures don't break the pipeline** — if Slack is unreachable, the investigation result is still returned; only the notification step is affected.

See a real example PR generated by this pipeline: https://github.com/Laharyy/roottrace-demo-target/pull/1

---

## The RAG dataset

`mock_data/postmortems/` contains 50 synthetic incident postmortems spanning 10 failure archetypes (connection pool exhaustion, memory leaks, schema migrations, rate limiting, DNS issues, auth failures, cache invalidation, disk space exhaustion, thread pool exhaustion, and bad config deploys), generated by `scripts/generate_postmortems.py`. Each archetype produces 5 varied instances (different services, dates, and specifics) so retrieval has to genuinely discriminate between categories rather than trivially matching everything.

Regenerate the dataset with:
```bash
python scripts/generate_postmortems.py
```

---

## Getting started

### Option 1: Docker (recommended — zero local setup)

```bash
docker build -t roottrace:latest .
docker run -p 8000:8000 roottrace:latest
```

### Option 2: Local Python environment

```bash
python -m venv venv
venv\Scripts\activate        # Windows
source venv/bin/activate     # macOS/Linux

pip install -r requirements.txt
> **Note:** the `/investigate` endpoint's retrieval step requires a `VOYAGE_API_KEY` in a `.env` file at the project root. Without it, `/ingest` still works, but `/investigate` returns a 503. See `.env` setup in the RAG dataset section above.
pip install -e .

uvicorn roottrace.api:app --reload
```

Either way, once running:
- Interactive API docs: **http://127.0.0.1:8000/docs**
- Health check: `GET /health`
- Run an investigation: `POST /ingest`

---

## Example

```bash
curl -X POST http://127.0.0.1:8000/ingest
```

```json
{
  "first_critical_event_at": "2025-01-15T14:02:00Z",
  "suspect_deployment": {
    "title": "Feature: New Caching Logic",
    "commit_sha": "f7a8b9c",
    "minutes_before_incident": 2.0
  }
}
```

---

## Running tests

```bash
pytest -v
```

Tests cover the core correlation logic (`find_suspect_deployment`), including edge cases: no prior deployment, and multiple deployments where only the most recent (not oldest) before the incident should be flagged.
---

## Roadmap

- [x] Mock data generator + ingestion pipeline
- [x] Pydantic validation, structured logging, typed config
- [x] REST API with auto-generated docs
- [x] Dockerized, CI-tested
- [x] RAG layer over historical incident post-mortems
- [x] Multi-model reasoning loop (GPT-4o + Claude cross-verification)
- [x] Autonomous revert-PR / rollback actions
- [x] ChatOps delivery via Slack/Teams

