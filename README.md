# RootTrace

![CI](https://github.com/Laharyy/roottrace/actions/workflows/ci.yml/badge.svg)

**RootTrace** is an AI-driven incident investigation platform that automatically correlates code deployments with system logs to identify the likely root cause of a production incident — cutting down the manual detective work that normally eats into Mean Time to Recovery (MTTR).

Instead of just alerting "something is wrong" (like traditional monitoring), RootTrace reasons about *why* it went wrong by lining up deployment history against the exact moment a system started failing.

> **Status:** Actively in development. Current release covers data ingestion, correlation, and a REST API. AI-powered root-cause reasoning (RAG + multi-model verification) is in progress — see [Roadmap](#roadmap).

---

## Why this project

Production incidents are often caused by a recent deploy, but finding *which* deploy, out of dozens per day across services, is slow manual work. RootTrace automates the first, most time-consuming step: building a correlated timeline and surfacing the most likely suspect deployment — before an engineer even opens a dashboard.

---

## How it works (current implementation)

1. **Ingest** — reads structured logs and deployment history (from JSON, simulating log/CI sources like ELK, CloudWatch, or GitHub)
2. **Normalize** — converts both into one common event schema using validated Pydantic models
3. **Correlate** — merges everything into a single chronological timeline and identifies the most recent deployment before the first critical failure
4. **Serve** — exposes the whole pipeline as a REST API (`/ingest`), so any system (a dashboard, a Slack bot, another service) can trigger an investigation on demand



---

## Tech stack

| Layer | Choice | Why |
|---|---|---|
| Language | Python 3.14 | Standard for AI/ML tooling |
| Data validation | Pydantic v2 | Fail-fast schema validation at every data boundary |
| API | FastAPI | Async-ready, auto-generated OpenAPI docs |
| Config | pydantic-settings + `.env` | No hardcoded paths or secrets |
| Testing | pytest | Unit tests covering core correlation logic, including edge cases |
| Packaging | `src/` layout, `pyproject.toml` | Installable, import-safe package structure |
| Containerization | Docker | Identical runtime behavior on any machine |
| CI | GitHub Actions | Tests run automatically on every push |

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

