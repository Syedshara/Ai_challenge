"""FastAPI application factory."""
from __future__ import annotations

import sys, os
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from src.utils.silence import suppress_all
suppress_all()

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routes import router


def create_app() -> FastAPI:
    app = FastAPI(
        title="Query Intelligence API",
        description="Insurance PAS SQL performance analyzer — RAG + ReAct agent + anomaly detection",
        version="1.0.0",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(router)
    return app


app = create_app()
