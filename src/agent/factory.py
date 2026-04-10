"""Factory function to wire up all components into a ready AgentOrchestrator.

Called once at startup by CLI, API, and MCP server.
"""
from __future__ import annotations

import json

_orchestrator = None  # module-level singleton


def create_orchestrator():
    """Build and wire all components. Cached after first call."""
    global _orchestrator
    if _orchestrator is not None:
        return _orchestrator

    from src.config import settings
    from src.rag.embeddings import EmbeddingModel
    from src.rag.vector_store import VectorStore
    from src.rag.reranker import CrossEncoderReranker
    from src.rag.retriever import HybridRetriever
    from src.analyzer.rule_engine import QueryRuleEngine
    from src.anomaly.detector import AnomalyDetector
    from src.rewriter.rewriter import QueryRewriter
    from src.agent.cache import QueryCache
    from src.agent.orchestrator import AgentOrchestrator

    embed = EmbeddingModel.get_instance(settings.embedding_model)

    vs = VectorStore(
        persist_dir=settings.chroma_persist_dir,
        embedding_model=embed,
    )
    vs._auto_populate_if_empty(settings.knowledge_base_path)

    reranker = CrossEncoderReranker.get_instance(settings.reranker_model)
    cases = json.loads(open(settings.knowledge_base_path).read())
    retriever = HybridRetriever(vs, reranker, embed, cases)

    rule_engine = QueryRuleEngine(settings.patterns_path)
    anomaly_detector = AnomalyDetector(
        settings.anomaly_zscore_threshold,
        settings.anomaly_iqr_factor,
        settings.anomaly_window_size,
    )
    rewriter = QueryRewriter(settings.schemas_path)
    schemas = json.loads(open(settings.schemas_path).read())
    cache = QueryCache(embed, settings.cache_threshold, settings.cache_max_size)

    _orchestrator = AgentOrchestrator(
        retriever=retriever,
        rule_engine=rule_engine,
        anomaly_detector=anomaly_detector,
        rewriter=rewriter,
        schemas=schemas,
        cache=cache,
        settings=settings,
    )
    return _orchestrator
