"""Upload NICE guidelines to Qdrant vector database.

Embeds each guideline using sentence-transformers and stores in Qdrant cloud.
The Treatment Agent queries this to find the top 3 matching guidelines.

Usage:
    python3 -m src.vectordb.setup_qdrant
"""

import json
import os
from pathlib import Path

from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct
from sentence_transformers import SentenceTransformer

from src.config import cfg

GUIDELINES_DIR = cfg.GUIDELINES_DIR
QDRANT_URL = os.environ.get("QDRANT_URL", "")
QDRANT_API_KEY = os.environ.get("QDRANT_API_KEY", "")
COLLECTION_NAME = cfg.QDRANT_COLLECTION


def setup():
    print(f"Loading embedding model: {cfg.EMBEDDING_MODEL}")
    model = SentenceTransformer(cfg.EMBEDDING_MODEL)
    embedding_dim = model.get_sentence_embedding_dimension()

    print(f"Connecting to Qdrant cloud...")
    client = QdrantClient(url=QDRANT_URL, api_key=QDRANT_API_KEY)

    # Create or recreate collection
    collections = [c.name for c in client.get_collections().collections]
    if COLLECTION_NAME in collections:
        client.delete_collection(COLLECTION_NAME)
        print(f"Deleted existing collection: {COLLECTION_NAME}")

    client.create_collection(
        collection_name=COLLECTION_NAME,
        vectors_config=VectorParams(size=embedding_dim, distance=Distance.COSINE),
    )
    print(f"Created collection: {COLLECTION_NAME} (dim={embedding_dim})")

    # Load and embed each guideline
    index_path = GUIDELINES_DIR / "guideline_index.json"
    index = json.loads(index_path.read_text())

    points = []
    seen_files = set()
    point_id = 1

    for disease_name, filename in index["mappings"].items():
        if filename in seen_files:
            # Same file used for multiple diseases — add extra point with disease alias
            guideline_path = GUIDELINES_DIR / filename
            guideline = json.loads(guideline_path.read_text())

            # Create embedding from disease name + guideline title
            text_to_embed = (
                f"{disease_name}. "
                f"{guideline.get('nice_title', '')}. "
                f"{guideline.get('disease', '')}."
            )

            embedding = model.encode(text_to_embed).tolist()

            points.append(PointStruct(
                id=point_id,
                vector=embedding,
                payload={
                    "disease_name": disease_name,
                    "nice_guideline": guideline.get("nice_guideline", ""),
                    "nice_title": guideline.get("nice_title", ""),
                    "source": guideline.get("source", ""),
                    "filename": filename,
                    "guideline_json": json.dumps(guideline),
                },
            ))
            print(f"  [{point_id}] {disease_name} → {filename} (alias)")
            point_id += 1
            continue

        seen_files.add(filename)
        guideline_path = GUIDELINES_DIR / filename
        if not guideline_path.exists():
            print(f"  SKIP: {filename} not found")
            continue

        guideline = json.loads(guideline_path.read_text())

        # Create rich text for embedding — disease name + title + first-line drugs
        first_line_text = ""
        for t in guideline.get("first_line_treatment", []):
            if isinstance(t, dict):
                first_line_text += f" {t.get('drug_class', '')} {' '.join(t.get('examples', []))}."

        text_to_embed = (
            f"{disease_name}. "
            f"{guideline.get('nice_title', '')}. "
            f"{guideline.get('disease', '')}. "
            f"First-line treatment: {first_line_text}"
        )

        embedding = model.encode(text_to_embed).tolist()

        points.append(PointStruct(
            id=point_id,
            vector=embedding,
            payload={
                "disease_name": disease_name,
                "nice_guideline": guideline.get("nice_guideline", ""),
                "nice_title": guideline.get("nice_title", ""),
                "source": guideline.get("source", ""),
                "filename": filename,
                "guideline_json": json.dumps(guideline),
            },
        ))
        print(f"  [{point_id}] {disease_name} → {filename}")
        point_id += 1

    # Upload
    client.upsert(collection_name=COLLECTION_NAME, points=points)
    print(f"\nUploaded {len(points)} guidelines to Qdrant cloud")

    # Verify with a test query
    print("\nTest query: 'heart failure'")
    test_embedding = model.encode("heart failure").tolist()
    results = client.query_points(
        collection_name=COLLECTION_NAME,
        query=test_embedding,
        limit=3,
    )
    for r in results.points:
        print(f"  Score={r.score:.3f} | {r.payload['disease_name']} ({r.payload['nice_guideline']})")

    print("\nDone!")


if __name__ == "__main__":
    setup()
