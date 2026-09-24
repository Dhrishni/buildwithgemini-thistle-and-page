# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Semantic Search and Vibe Matching service for Thistle & Page.

Uses Vertex AI text-embedding-005 to generate embeddings and compute cosine similarity
for discovery by vibe, mood, theme, and reading environment.
"""

import math
from typing import Any, Dict, List, Optional
from google.genai import Client

PROJECT_ID = "qwiklabs-gcp-03-9683cc1b79ba"
LOCATION = "us-central1"
EMBEDDING_MODEL = "text-embedding-005"

# In-memory cache for precomputed catalog embeddings
_EMBEDDINGS_CACHE: Dict[str, List[float]] = {}
_GENAI_CLIENT: Optional[Client] = None


def get_genai_client() -> Client:
    """Returns a GenAI client initialized for Vertex AI."""
    global _GENAI_CLIENT
    if _GENAI_CLIENT is None:
        _GENAI_CLIENT = Client(vertexai=True, project=PROJECT_ID, location=LOCATION)
    return _GENAI_CLIENT


def get_embedding(text: str) -> List[float]:
    """Generates a 768-dimensional vector embedding for the input text."""
    client = get_genai_client()
    resp = client.models.embed_content(
        model=EMBEDDING_MODEL,
        contents=text,
    )
    return resp.embeddings[0].values


def cosine_similarity(v1: List[float], v2: List[float]) -> float:
    """Computes cosine similarity between two numeric vectors."""
    dot_product = sum(a * b for a, b in zip(v1, v2))
    norm_v1 = math.sqrt(sum(a * a for a in v1))
    norm_v2 = math.sqrt(sum(b * b for b in v2))
    if norm_v1 == 0 or norm_v2 == 0:
        return 0.0
    return dot_product / (norm_v1 * norm_v2)


def get_or_create_embedding(item_id: str, text: str) -> List[float]:
    """Retrieves an embedding from cache or computes and caches it."""
    if item_id in _EMBEDDINGS_CACHE:
        return _EMBEDDINGS_CACHE[item_id]
    emb = get_embedding(text)
    _EMBEDDINGS_CACHE[item_id] = emb
    return emb


def semantic_rank_items(
    query: str,
    items: List[Dict[str, Any]],
    text_key_func,
    top_k: int = 5,
    threshold: float = 0.55,
) -> List[Dict[str, Any]]:
    """Ranks a list of items against a natural language query using cosine similarity."""
    if not items or not query.strip():
        return items

    try:
        query_emb = get_embedding(query)
    except Exception as e:
        print(f"[Warning] Failed to generate query embedding: {e}")
        return items

    scored_items = []
    for item in items:
        item_id = item.get("item_id") or item.get("book_id") or str(id(item))
        synth_text = text_key_func(item)
        try:
            item_emb = get_or_create_embedding(item_id, synth_text)
            sim = cosine_similarity(query_emb, item_emb)
            if sim >= threshold:
                item_copy = dict(item)
                item_copy["semantic_score"] = round(sim, 3)
                scored_items.append((sim, item_copy))
        except Exception as e:
            print(f"[Warning] Failed to embed item {item_id}: {e}")

    scored_items.sort(key=lambda x: x[0], reverse=True)
    return [item for _, item in scored_items[:top_k]]
