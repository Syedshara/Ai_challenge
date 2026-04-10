from __future__ import annotations

import re
import logging
from collections import defaultdict

logger = logging.getLogger(__name__)

# SQL tokens that are worth boosting in keyword search
_SQL_KEYWORDS = {
    "select", "from", "where", "join", "group by", "order by", "limit",
    "update", "insert", "delete", "with", "having", "on",
    "json_extract", "json_table", "count", "sum", "avg", "max", "min",
}

_TABLE_NAMES = {"policy_data", "claims_data", "config_table", "audit_log", "config"}


# ─── Keyword Utilities ────────────────────────────────────────────────────────

def extract_sql_keywords(query: str) -> list[str]:
    """Pull SQL tokens and table names from *query* for keyword-based search."""
    q_lower = query.lower()
    tokens: list[str] = []
    for kw in _SQL_KEYWORDS:
        if kw in q_lower:
            tokens.append(kw)
    for table in _TABLE_NAMES:
        if table in q_lower:
            tokens.append(table)
    # Also grab any word that looks like a column name (all lowercase, underscores)
    words = re.findall(r"\b[a-z_]{3,}\b", q_lower)
    tokens.extend(words)
    return list(dict.fromkeys(tokens))  # deduplicate


def keyword_search(keywords: list[str], cases: list[dict]) -> list[dict]:
    """Rank *cases* by how many *keywords* appear in their embedding_text."""
    if not keywords:
        return []
    scored: list[tuple[int, dict]] = []
    for case in cases:
        text = (case.get("embedding_text", "") + " " + case.get("title", "")).lower()
        score = sum(1 for kw in keywords if kw in text)
        if score > 0:
            scored.append((score, case))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [c for _, c in scored]


# ─── Reciprocal Rank Fusion ───────────────────────────────────────────────────

def reciprocal_rank_fusion(*result_lists: list[dict], k: int = 60) -> list[dict]:
    """Merge ranked result lists using Reciprocal Rank Fusion.

    RRF score = Σ 1/(k + rank_i) across all lists.
    Handles score incompatibility between dense and sparse retrieval.
    """
    rrf_scores: dict[str, float] = defaultdict(float)
    case_by_id: dict[str, dict] = {}

    for results in result_lists:
        for rank, doc in enumerate(results):
            doc_id = doc.get("case_id", str(rank))
            rrf_scores[doc_id] += 1.0 / (k + rank + 1)
            case_by_id[doc_id] = doc

    sorted_ids = sorted(rrf_scores, key=rrf_scores.__getitem__, reverse=True)
    return [case_by_id[doc_id] for doc_id in sorted_ids]


# ─── Hybrid Retriever ─────────────────────────────────────────────────────────

class HybridRetriever:
    """Three-stage RAG retrieval pipeline.

    Stage 1 — Broad retrieval  : Dense (ChromaDB cosine) + Sparse (keyword)
                                  merged via Reciprocal Rank Fusion → top 10
    Stage 2 — Threshold filter : Drop candidates with cosine distance > 0.7
    Stage 3 — Precise reranking: Cross-encoder scores top-10 → returns top_k
    """

    def __init__(
        self,
        vector_store,
        reranker,
        embedding_model,
        cases: list[dict],
        distance_threshold: float = 0.8,
    ) -> None:
        self.vector_store = vector_store
        self.reranker = reranker
        self.embedding_model = embedding_model
        self.cases = cases
        self.distance_threshold = distance_threshold
        # Populated after each retrieve() — used by TUI to show RAG sub-steps
        self._last_stats: dict = {}

    def retrieve(self, query: str, top_k: int = 3) -> list[dict]:
        """Run the full 3-stage retrieval pipeline."""
        # ── Stage 1a: Dense vector search ────────────────────────────────────
        raw_vector = self.vector_store.query(query, n_results=min(10, len(self.cases)))

        # ── Stage 1b: Keyword search ──────────────────────────────────────────
        keywords = extract_sql_keywords(query)
        keyword_results = keyword_search(keywords, self.cases)

        # ── Stage 1c: RRF merge ───────────────────────────────────────────────
        merged = reciprocal_rank_fusion(raw_vector, keyword_results)

        # ── Stage 2: Distance threshold filter ───────────────────────────────
        filtered = [
            c for c in merged
            if c.get("_distance", 0.0) <= self.distance_threshold
        ] or merged  # fallback: keep all if everything filtered out

        # ── Stage 3: Cross-encoder reranking ─────────────────────────────────
        if len(filtered) > top_k:
            final = self.reranker.rerank(query, filtered, top_k=top_k)
        else:
            final = filtered[:top_k]

        # Expose sub-step counts for TUI 14-step display (set after every call)
        self._last_stats = {
            "dense_count":    len(raw_vector),
            "keyword_count":  len(keyword_results),
            "merged_count":   len(merged),
            "filtered_count": len(filtered),
            "keywords_used":  keywords[:6],
        }
        return final
