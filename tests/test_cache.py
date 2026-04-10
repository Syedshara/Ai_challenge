"""Tests for the semantic query cache."""
import pytest
import numpy as np


def test_cache_miss_on_empty():
    from src.rag.embeddings import EmbeddingModel
    from src.agent.cache import QueryCache
    embed = EmbeddingModel.get_instance()
    cache = QueryCache(embed, threshold=0.95)
    assert cache.get("some unique test query xyz") is None


def test_cache_hit_on_identical_query():
    from src.rag.embeddings import EmbeddingModel
    from src.agent.cache import QueryCache
    from src.models import AnalysisResponse
    embed = EmbeddingModel.get_instance()
    cache = QueryCache(embed, threshold=0.95)
    query = "test cache hit query unique abc123"
    response = AnalysisResponse(
        problem="test problem",
        root_cause="test root cause",
        suggestion=["fix1"],
        confidence=0.8,
        category="test",
        severity="low",
        similar_cases=[],
        metadata={},
    )
    cache.put(query, response)
    result = cache.get(query)
    assert result is not None
    assert result.metadata.get("cache_hit") is True


def test_cache_hit_metadata_has_original_query():
    from src.rag.embeddings import EmbeddingModel
    from src.agent.cache import QueryCache
    from src.models import AnalysisResponse
    embed = EmbeddingModel.get_instance()
    cache = QueryCache(embed, threshold=0.95)
    query = "test original query for metadata check"
    response = AnalysisResponse(
        problem="test", root_cause="test", suggestion=[],
        confidence=0.5, category="test", severity="low", similar_cases=[], metadata={},
    )
    cache.put(query, response)
    result = cache.get(query)
    assert result.metadata.get("original_query") == query


def test_cache_no_hit_on_different_query():
    from src.rag.embeddings import EmbeddingModel
    from src.agent.cache import QueryCache
    from src.models import AnalysisResponse
    embed = EmbeddingModel.get_instance()
    cache = QueryCache(embed, threshold=0.95)
    response = AnalysisResponse(
        problem="test", root_cause="test", suggestion=[],
        confidence=0.5, category="test", severity="low", similar_cases=[], metadata={},
    )
    cache.put("SELECT * FROM policy_data slow performance", response)
    # Very different query should not hit
    result = cache.get("anomaly detection latency spike investigation")
    assert result is None


def test_cache_fifo_eviction():
    from src.rag.embeddings import EmbeddingModel
    from src.agent.cache import QueryCache
    from src.models import AnalysisResponse
    embed = EmbeddingModel.get_instance()
    cache = QueryCache(embed, threshold=0.95, max_size=3)
    base = AnalysisResponse(
        problem="test", root_cause="test", suggestion=[],
        confidence=0.5, category="test", severity="low", similar_cases=[], metadata={},
    )
    for i in range(4):
        cache.put(f"unique distinct query number {i} different", base)
    assert cache.size() <= 3
