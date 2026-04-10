from __future__ import annotations

import json
import logging
import os
from pathlib import Path

import chromadb
from chromadb.config import Settings as ChromaSettings

from src.rag.embeddings import EmbeddingModel, _load_silently

logger = logging.getLogger(__name__)


class VectorStore:
    """ChromaDB-backed vector store for knowledge base cases.

    On first use, auto-populates from ``knowledge_base_path`` if the
    collection is empty.  Subsequent runs load the persisted index.
    """

    def __init__(
        self,
        persist_dir: str = "chroma_db",
        collection_name: str = "cases",
        embedding_model: EmbeddingModel | None = None,
    ) -> None:
        Path(persist_dir).mkdir(parents=True, exist_ok=True)
        # Wrap ChromaDB init in fd-redirect to suppress ONNX GPU warning
        self._client = _load_silently(
            lambda: chromadb.PersistentClient(path=persist_dir)
        )
        self._collection = self._client.get_or_create_collection(
            name=collection_name,
            metadata={"hnsw:space": "cosine"},
        )
        self._embed = embedding_model or EmbeddingModel.get_instance()

    # ─── Public API ──────────────────────────────────────────────────────────

    def populate(self, cases: list[dict]) -> None:
        """Embed each case's *embedding_text* and upsert into ChromaDB."""
        if not cases:
            return
        ids = [c["case_id"] for c in cases]
        texts = [c.get("embedding_text", c.get("title", "")) for c in cases]
        embeddings = self._embed.encode_batch(texts)
        metadatas = [
            {
                "case_id": c["case_id"],
                "title": c.get("title", ""),
                "category": c.get("category", ""),
                "severity": c.get("severity", ""),
                "tags": ",".join(c.get("tags", [])),
            }
            for c in cases
        ]
        documents = [json.dumps(c) for c in cases]
        self._collection.upsert(
            ids=ids,
            embeddings=[e.tolist() for e in embeddings],
            metadatas=metadatas,
            documents=documents,
        )
        logger.info("Populated VectorStore with %d cases.", len(cases))

    def query(self, query_text: str, n_results: int = 10) -> list[dict]:
        """Query the collection and return matched case dicts."""
        total = self._collection.count()
        if total == 0:
            return []
        n_results = min(n_results, total)
        results = _load_silently(lambda: self._collection.query(
            query_texts=[query_text],
            n_results=n_results,
            include=["documents", "distances", "metadatas"],
        ))
        cases: list[dict] = []
        for doc, dist in zip(results["documents"][0], results["distances"][0]):
            case = json.loads(doc)
            case["_distance"] = float(dist)
            cases.append(case)
        return cases

    def rebuild(self, cases: list[dict]) -> None:
        """Clear the collection and re-populate from *cases*."""
        # Delete all existing documents
        existing = self._collection.get()
        if existing["ids"]:
            self._collection.delete(ids=existing["ids"])
        self.populate(cases)
        logger.info("Rebuilt VectorStore with %d cases.", len(cases))

    def count(self) -> int:
        return self._collection.count()

    def _auto_populate_if_empty(self, knowledge_base_path: str) -> None:
        """Load cases from JSON and populate if the collection is empty."""
        if self._collection.count() == 0:
            logger.info("VectorStore empty — auto-populating from %s", knowledge_base_path)
            with open(knowledge_base_path) as f:
                cases = json.load(f)
            self.populate(cases)
