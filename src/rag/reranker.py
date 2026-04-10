from __future__ import annotations

import logging
import os

import numpy as np

from src.rag.embeddings import _load_silently

logger = logging.getLogger(__name__)


class CrossEncoderReranker:
    """Singleton cross-encoder reranker (ms-marco-MiniLM-L-6-v2).

    Evaluates (query, document) pairs together through all transformer layers,
    capturing token-level interactions that bi-encoders miss.  +40% retrieval
    accuracy over cosine similarity alone on standard benchmarks.
    """

    _instance: "CrossEncoderReranker | None" = None
    DEFAULT_MODEL = "cross-encoder/ms-marco-MiniLM-L-6-v2"

    def __init__(self, model_name: str = DEFAULT_MODEL) -> None:
        from sentence_transformers import CrossEncoder  # lazy import

        self.model_name = model_name
        self.model = _load_silently(lambda: CrossEncoder(model_name))
        logger.debug("CrossEncoderReranker loaded: %s", model_name)

    @classmethod
    def get_instance(cls, model_name: str = DEFAULT_MODEL) -> "CrossEncoderReranker":
        if cls._instance is None or cls._instance.model_name != model_name:
            cls._instance = cls(model_name)
        return cls._instance

    def rerank(self, query: str, candidates: list[dict], top_k: int = 3) -> list[dict]:
        """Score each (query, candidate) pair and return top_k sorted by score.

        Adds a ``_rerank_score`` key to each returned document.
        """
        if not candidates:
            return []
        texts = [c.get("embedding_text", c.get("title", "")) for c in candidates]
        pairs = [(query, t) for t in texts]
        scores: list[float] = self.model.predict(pairs).tolist()

        ranked = sorted(
            zip(candidates, scores), key=lambda x: x[1], reverse=True
        )
        result = []
        for doc, score in ranked[:top_k]:
            doc = dict(doc)
            doc["_rerank_score"] = round(float(score), 4)
            result.append(doc)
        return result
