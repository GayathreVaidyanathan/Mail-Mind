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

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
import os

from routers import auth, pipeline


# ── App ────────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="Gmail Multi-Agent System",
    description="AI-powered email pipeline — Powered by Ollama",
    version="2.0.0",
)


# ── CORS ───────────────────────────────────────────────────────────────────────
# Allows the React dev server (localhost:5173) to talk to FastAPI
# during development. In production both are served from the same
# origin so CORS isn't needed — but keeping it doesn't hurt.

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

app.include_router(auth.router, prefix="/api")
app.include_router(pipeline.router, prefix="/api")

# ── Health check ───────────────────────────────────────────────────────────────

@app.get("/api/health")
async def health():
    """Quick check that the API is up."""
    return {"status": "ok", "version": "2.0.0"}


# ── Serve React frontend ───────────────────────────────────────────────────────
# In production, FastAPI serves the built React app from frontend/dist.
# Any route not matched by the API falls through to index.html so
# React Router can handle client-side navigation.

FRONTEND_DIST = os.path.join(os.path.dirname(__file__), "frontend", "dist")

if os.path.exists(FRONTEND_DIST):
    # Serve static assets (JS, CSS, images)
    app.mount(
        "/assets",
        StaticFiles(directory=os.path.join(FRONTEND_DIST, "assets")),
        name="assets",
    )

    @app.get("/{full_path:path}")
    async def serve_frontend(full_path: str):
        """
        Catch-all route — serves index.html for any non-API route.
        Lets React Router handle /connect, /dashboard etc. on the client.
        """
        index = os.path.join(FRONTEND_DIST, "index.html")
        return FileResponse(index)