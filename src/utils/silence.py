"""Suppress noisy-but-harmless third-party warnings at startup.

Call suppress_all() once, as early as possible (top of cli/main.py,
api/main.py, src/mcp/server.py) before any heavy imports.

Warnings silenced:
  1. HuggingFace Hub unauthenticated request notice
  2. sentence-transformers BertModel LOAD REPORT (UNEXPECTED key noise)
  3. ONNX Runtime GPU device discovery failure
  4. transformers general verbose output
"""
from __future__ import annotations

import os
import logging
import warnings


def suppress_all() -> None:
    """Call once at process startup before importing ML libraries."""

    # ── 1. HuggingFace Hub ──────────────────────────────────────────────────
    os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")
    os.environ.setdefault("HF_HUB_VERBOSITY", "error")
    os.environ.setdefault("TRANSFORMERS_VERBOSITY", "error")
    os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
    # Use cached models only — prevents SSL errors when HF Hub checks for
    # model updates. All three models (MiniLM, bge-small, ms-marco) are
    # already cached in ~/.cache/huggingface/hub/.
    os.environ.setdefault("HF_HUB_OFFLINE", "1")
    os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

    # ── 2. ONNX Runtime GPU warning ─────────────────────────────────────────
    # ORT_LOGGING_LEVEL: 0=VERBOSE 1=INFO 2=WARNING 3=ERROR 4=FATAL
    os.environ.setdefault("ORT_LOGGING_LEVEL", "3")

    # ── 3. Python warnings module ────────────────────────────────────────────
    warnings.filterwarnings("ignore", category=UserWarning)
    warnings.filterwarnings("ignore", category=FutureWarning)
    warnings.filterwarnings("ignore", message=".*position_ids.*")
    warnings.filterwarnings("ignore", message=".*UNEXPECTED.*")

    # ── 4. Logging levels for chatty libraries ───────────────────────────────
    for noisy_logger in [
        "transformers",
        "sentence_transformers",
        "huggingface_hub",
        "huggingface_hub.utils",
        "filelock",
        "urllib3",
        "httpx",
        "chromadb",
        "onnxruntime",
    ]:
        logging.getLogger(noisy_logger).setLevel(logging.ERROR)

    # ── 5. Redirect sentence-transformers LOAD REPORT to /dev/null ───────────
    # The LOAD REPORT prints directly to stdout via the Rust backend;
    # redirect at the C-level fd so it doesn't pollute the terminal.
    try:
        import sentence_transformers  # noqa: F401 — triggers logger setup
        # Silence the model-loading "LOAD REPORT" table printed by the
        # safetensors Rust backend (goes to fd 1 before Python can intercept).
        # We temporarily swap stdout for loading only — see embeddings.py
    except ImportError:
        pass
