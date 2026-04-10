from __future__ import annotations
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # ── LLM — provider-agnostic ──────────────────────────────────────
    # Works with any OpenAI-compatible endpoint.
    # Switch provider by changing these 3 env vars in .env only.
    #
    #   Groq   : LLM_BASE_URL=https://api.groq.com/openai/v1
    #   Gemini : LLM_BASE_URL=https://generativelanguage.googleapis.com/v1beta/openai/
    #   OpenAI : leave LLM_BASE_URL blank (uses OpenAI default)
    #   Offline: leave LLM_API_KEY blank (falls back to rule engine + RAG)
    llm_api_key: str | None = None
    llm_model: str = "gpt-4o-mini"
    llm_base_url: str | None = None  # None → OpenAI default endpoint

    # ── Embeddings / RAG ─────────────────────────────────────────────
    embedding_model: str = "all-MiniLM-L6-v2"
    reranker_model: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"
    chroma_persist_dir: str = "chroma_db"

    # ── Data paths ───────────────────────────────────────────────────
    knowledge_base_path: str = "data/knowledge_base.json"
    schemas_path: str = "data/schemas.json"
    metrics_path: str = "data/metrics_history.json"
    patterns_path: str = "data/query_patterns.json"
    feedback_log_path: str = "data/feedback_log.json"

    # ── Cache ────────────────────────────────────────────────────────
    cache_threshold: float = 0.95
    cache_max_size: int = 100

    # ── RAG retrieval ────────────────────────────────────────────────
    rag_top_k_retrieve: int = 10
    rag_top_k_rerank: int = 3

    # ── Anomaly detection ────────────────────────────────────────────
    anomaly_zscore_threshold: float = 3.0
    anomaly_iqr_factor: float = 1.5
    anomaly_window_size: int = 5

    # ── Agent ────────────────────────────────────────────────────────
    agent_max_steps: int = 3

    # ── MySQL Live Monitor ────────────────────────────────────────────
    mysql_host: str = "localhost"
    mysql_port: int = 3307
    mysql_user: str = "monitor"
    mysql_password: str = "monitor_pw"
    mysql_database: str = "employees"
    monitor_slow_threshold_ms: float = 500.0

    @property
    def llm_available(self) -> bool:
        return bool(self.llm_api_key)

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
