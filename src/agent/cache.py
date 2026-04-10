from __future__ import annotations

import logging
from datetime import datetime

import numpy as np

from src.models import AnalysisResponse

logger = logging.getLogger(__name__)


class QueryCache:
    """Lightweight semantic cache for AnalysisResponse objects.

    On a cache hit the response is returned instantly — skipping RAG,
    rule engine, and LLM entirely.  Uses cosine similarity between
    the embedding of the incoming query and stored query embeddings.
    """

    def __init__(
        self,
        embedding_model,
        threshold: float = 0.95,
        max_size: int = 100,
    ) -> None:
        self.embed = embedding_model
        self.threshold = threshold
        self.max_size = max_size
        self._entries: list[dict] = []  # {query, embedding, result, timestamp}

    # ─── Public API ──────────────────────────────────────────────────────────

    def get(self, query: str) -> AnalysisResponse | None:
        """Return a cached result if a sufficiently similar query exists."""
        if not self._entries:
            return None
        q_emb = self.embed.encode(query)
        for entry in self._entries:
            sim = self._cosine(q_emb, entry["embedding"])
            if sim >= self.threshold:
                result = entry["result"].model_copy(deep=True)
                result.metadata["cache_hit"] = True
                result.metadata["original_query"] = entry["query"]
                logger.debug("Cache HIT (similarity=%.3f) for: %s", sim, query[:60])
                return result
        return None

    def put(self, query: str, result: AnalysisResponse) -> None:
        """Store *result* keyed by *query*."""
        embedding = self.embed.encode(query)
        self._entries.append(
            {
                "query": query,
                "embedding": embedding,
                "result": result,
                "timestamp": datetime.now().isoformat(),
            }
        )
        # FIFO eviction when over capacity
        if len(self._entries) > self.max_size:
            self._entries.pop(0)
        logger.debug("Cache PUT: %s", query[:60])

    def clear(self) -> None:
        self._entries.clear()

    def size(self) -> int:
        return len(self._entries)

    # ─── Private ─────────────────────────────────────────────────────────────

    @staticmethod
    def _cosine(a: np.ndarray, b: np.ndarray) -> float:
        norm = np.linalg.norm(a) * np.linalg.norm(b)
        if norm == 0:
            return 0.0
        return float(np.dot(a, b) / norm)
