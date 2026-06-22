"""
main.py

FastAPI application entry point.

Serves:
  - REST API routes (auth + pipeline) under /api/*
  - React frontend static files under /* (served from frontend/dist)

Run locally:
  uvicorn main:app --reload --port 8000

Build frontend first:
  cd frontend && npm run build

The React app is built into frontend/dist/ and FastAPI serves it
as static files. This means a single server handles both the API
and the UI — no separate frontend server needed.

For deployment on Render:
  - Build command : cd frontend && npm install && npm run build
  - Start command : uvicorn main:app --host 0.0.0.0 --port 8000
"""

import logging
import os

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware

from routers import auth, export, pipeline

# ── Logging ────────────────────────────────────────────────────────────────────
# Set to DEBUG to see full tracebacks from all routers and services.
# Change to logging.INFO for quieter production output.

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s  %(levelname)-8s  %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)

logger = logging.getLogger(__name__)

# ── App ────────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="Gmail Multi-Agent System",
    description="AI-powered email pipeline — Powered by Ollama",
    version="2.0.0",
)


# ── CORS ───────────────────────────────────────────────────────────────────────

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",   # Vite dev server
        "http://localhost:8000",   # FastAPI local
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── API routers ────────────────────────────────────────────────────────────────

app.include_router(auth.router,     prefix="/api")
app.include_router(pipeline.router, prefix="/api")
app.include_router(export.router,   prefix="/api")


# ── Health check ───────────────────────────────────────────────────────────────

@app.get("/api/health")
async def health():
    """Quick check that the API is up."""
    return {"status": "ok", "version": "2.0.0"}


# ── Serve React frontend ───────────────────────────────────────────────────────

FRONTEND_DIST = os.path.join(os.path.dirname(__file__), "frontend", "dist")

if os.path.exists(FRONTEND_DIST):
    app.mount(
        "/assets",
        StaticFiles(directory=os.path.join(FRONTEND_DIST, "assets")),
        name="assets",
    )

    @app.get("/{full_path:path}")
    async def serve_frontend(full_path: str):
        index = os.path.join(FRONTEND_DIST, "index.html")
        return FileResponse(index)