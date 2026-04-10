from __future__ import annotations

import os
import sys
import numpy as np


def _load_silently(loader_fn):
    """Run *loader_fn* with stdout/stderr temporarily redirected to /dev/null.
    Suppresses the safetensors Rust LOAD REPORT that bypasses Python logging.
    """
    devnull_fd = os.open(os.devnull, os.O_WRONLY)
    old_stdout = os.dup(1)
    old_stderr = os.dup(2)
    try:
        os.dup2(devnull_fd, 1)
        os.dup2(devnull_fd, 2)
        return loader_fn()
    finally:
        os.dup2(old_stdout, 1)
        os.dup2(old_stderr, 2)
        os.close(devnull_fd)
        os.close(old_stdout)
        os.close(old_stderr)


class EmbeddingModel:
    """Singleton wrapper around SentenceTransformer all-MiniLM-L6-v2.

    Loads once at startup; subsequent ``get_instance()`` calls return the
    already-loaded model with no I/O overhead.
    """

    _instance: "EmbeddingModel | None" = None

    def __init__(self, model_name: str = "all-MiniLM-L6-v2") -> None:
        from sentence_transformers import SentenceTransformer  # lazy import

        self.model_name = model_name
        self.model = _load_silently(lambda: SentenceTransformer(model_name))

    @classmethod
    def get_instance(cls, model_name: str = "all-MiniLM-L6-v2") -> "EmbeddingModel":
        if cls._instance is None or cls._instance.model_name != model_name:
            cls._instance = cls(model_name)
        return cls._instance

    def encode(self, text: str) -> np.ndarray:
        """Encode a single string to a numpy vector."""
        return self.model.encode(text, convert_to_numpy=True)

    def encode_batch(self, texts: list[str]) -> list[np.ndarray]:
        """Encode multiple strings at once (more efficient than looping)."""
        return [v for v in self.model.encode(texts, convert_to_numpy=True)]
