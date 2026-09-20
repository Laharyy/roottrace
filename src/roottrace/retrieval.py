"""
RAG retrieval layer for RootTrace.

Loads historical post-mortems, embeds them with Voyage AI, stores them in a
local ChromaDB vector store, and retrieves the most similar past incidents
for a given new incident description.
"""

import json
import logging
from pathlib import Path

import chromadb
import voyageai

from roottrace.config import settings
from roottrace.models import Postmortem

class VoyageAPIKeyMissing(RuntimeError):
    """Raised when a Voyage AI operation is attempted without an API key
    configured. A dedicated exception type (rather than a generic
    RuntimeError) lets callers catch this specific failure mode and respond
    appropriately -- e.g. the API layer turns this into a clean HTTP error."""
    pass


def _require_voyage_client() -> voyageai.Client:
    if not settings.voyage_api_key:
        raise VoyageAPIKeyMissing(
            "VOYAGE_API_KEY is not set. Add it to your .env file to use retrieval."
        )
    return voyageai.Client(api_key=settings.voyage_api_key)

logger = logging.getLogger(__name__)

EMBEDDING_MODEL = "voyage-3.5"
COLLECTION_NAME = "postmortems"


def load_postmortems(directory: Path) -> list[Postmortem]:
    """Load and validate every *.json file in the postmortems directory."""
    postmortems = []
    for path in sorted(directory.glob("*.json")):
        with open(path, "r") as f:
            raw = json.load(f)
        postmortems.append(Postmortem(**raw))
    logger.info("Loaded %d postmortems from %s", len(postmortems), directory)
    return postmortems


def postmortem_to_text(pm: Postmortem) -> str:
    """Combine the fields that actually carry meaning into one string to
    embed. Deliberately excludes id/date/tags -- see the models.py docstring
    for why tags don't drive semantic search here."""
    return f"{pm.title}\n{pm.summary}\n{pm.root_cause}\n{pm.fix}"


def get_chroma_collection():
    """A persistent Chroma client stores its data on disk under ./chroma_db,
    so embeddings survive across runs -- you don't re-embed on every call."""
    client = chromadb.PersistentClient(path="chroma_db")
    return client.get_or_create_collection(name=COLLECTION_NAME)


def index_postmortems(directory: Path | None = None) -> int:
    """Embeds every postmortem and stores it in the vector store. Safe to
    re-run -- Chroma's `add` with the same ids overwrites, it doesn't
    duplicate."""
    directory = directory or settings.postmortems_dir
    postmortems = load_postmortems(directory)

    voyage_client = _require_voyage_client()
    texts = [postmortem_to_text(pm) for pm in postmortems]

    result = voyage_client.embed(texts, model=EMBEDDING_MODEL, input_type="document")
    embeddings = result.embeddings

    collection = get_chroma_collection()
    collection.add(
        ids=[pm.id for pm in postmortems],
        embeddings=embeddings,
        documents=texts,
        metadatas=[{"title": pm.title, "date": pm.date} for pm in postmortems],
    )
    logger.info("Indexed %d postmortems into ChromaDB", len(postmortems))
    return len(postmortems)


def retrieve_similar_postmortems(incident_summary: str, top_k: int = 2) -> list[dict]:
    """Given a plain-text description of the current incident, returns the
    top_k most semantically similar past postmortems. Note input_type=
    'query' here vs 'document' in index_postmortems -- Voyage's models are
    tuned slightly differently depending on which side of the search you're
    embedding, which improves retrieval quality."""
    voyage_client = _require_voyage_client()
    query_embedding = voyage_client.embed(
        [incident_summary], model=EMBEDDING_MODEL, input_type="query"
    ).embeddings[0]

    collection = get_chroma_collection()
    results = collection.query(query_embeddings=[query_embedding], n_results=top_k)

    matches = []
    for i in range(len(results["ids"][0])):
        matches.append({
            "id": results["ids"][0][i],
            "title": results["metadatas"][0][i]["title"],
            "distance": results["distances"][0][i],
            "text": results["documents"][0][i],
        })
    return matches