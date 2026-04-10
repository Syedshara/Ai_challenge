"""Shared pytest fixtures for the Query Intelligence test suite."""
from __future__ import annotations

import json
import os
import pytest

from src.config import settings


@pytest.fixture(scope="session")
def knowledge_base():
    return json.loads(open(settings.knowledge_base_path).read())


@pytest.fixture(scope="session")
def schemas():
    return json.loads(open(settings.schemas_path).read())


@pytest.fixture(scope="session")
def metrics_history():
    return json.loads(open(settings.metrics_path).read())


@pytest.fixture(scope="session")
def rule_engine():
    from src.analyzer.rule_engine import QueryRuleEngine
    return QueryRuleEngine(settings.patterns_path)


@pytest.fixture(scope="session")
def rewriter():
    from src.rewriter.rewriter import QueryRewriter
    return QueryRewriter(settings.schemas_path)


@pytest.fixture(scope="session")
def anomaly_detector():
    from src.anomaly.detector import AnomalyDetector
    return AnomalyDetector(
        settings.anomaly_zscore_threshold,
        settings.anomaly_iqr_factor,
        settings.anomaly_window_size,
    )


@pytest.fixture
def api_client():
    from fastapi import FastAPI
    from api.routes import router
    from fastapi.testclient import TestClient
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


@pytest.fixture(scope="session")
def orchestrator():
    """Offline orchestrator (no OpenAI key)."""
    from src.agent.factory import create_orchestrator
    import src.agent.factory as fac
    fac._orchestrator = None  # reset singleton for test isolation
    orch = create_orchestrator()
    return orch
