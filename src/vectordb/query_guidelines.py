"""Query NICE guidelines from Qdrant vector database.

Used by the Treatment Agent to find the top 3 matching guidelines
for a diagnosed disease using semantic search.

Usage:
    from src.vectordb.query_guidelines import search_guidelines
    results = search_guidelines("heart failure with reduced ejection fraction")
"""

import json
import os
from qdrant_client import QdrantClient
from sentence_transformers import SentenceTransformer

QDRANT_URL = os.environ.get("QDRANT_URL", "")
QDRANT_API_KEY = os.environ.get("QDRANT_API_KEY", "")
COLLECTION_NAME = "nice_guidelines"

# Lazy-loaded singletons
_client = None
_model = None


def _get_client():
    global _client
    if _client is None:
        _client = QdrantClient(url=QDRANT_URL, api_key=QDRANT_API_KEY)
    return _client


def _get_model():
    global _model
    if _model is None:
        _model = SentenceTransformer("FremyCompany/BioLORD-2023")
    return _model


def search_guidelines(disease_name: str, top_k: int = 3) -> list[dict]:
    """Search Qdrant for NICE guidelines matching the disease name.

    Args:
        disease_name: The diagnosed disease (e.g., "Atherosclerotic CAD")
        top_k: Number of top matches to return (default 3)

    Returns:
        List of dicts, each with:
            - disease_name: matched disease
            - nice_guideline: guideline reference (e.g., "NG106")
            - nice_title: guideline title
            - score: similarity score (0-1)
            - guideline: full parsed guideline JSON dict
    """
    client = _get_client()
    model = _get_model()

    embedding = model.encode(disease_name).tolist()

    results = client.query_points(
        collection_name=COLLECTION_NAME,
        query=embedding,
        limit=top_k,
    )

    guidelines = []
    for r in results.points:
        guideline_json = r.payload.get("guideline_json", "{}")
        guidelines.append({
            "disease_name": r.payload.get("disease_name", "?"),
            "nice_guideline": r.payload.get("nice_guideline", "?"),
            "nice_title": r.payload.get("nice_title", "?"),
            "source": r.payload.get("source", "?"),
            "score": round(r.score, 3),
            "guideline": json.loads(guideline_json),
        })

    return guidelines
