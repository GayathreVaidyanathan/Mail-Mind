"""
routers/pipeline.py

Pipeline router — /api/pipeline/*
───────────────────────────────────
Runs the multi-agent pipeline and streams progress to the
frontend via Server-Sent Events (SSE).

Why SSE instead of WebSockets?
  SSE is one-directional (server → client) which is exactly
  what we need — the pipeline runs and pushes updates as each
  email is processed. WebSockets would be overkill here.
  SSE is also simpler to implement and works natively in browsers
  without any extra library on the frontend.

How streaming works:
  1. Frontend calls GET /api/pipeline/run
  2. FastAPI starts the Orchestrator as a background generator
  3. Each yield from orchestrator.run() is JSON-encoded and
     pushed to the frontend as an SSE event
  4. Frontend receives events and updates the UI in real time
  5. Final "done" event signals the pipeline is complete

Event types streamed:
  {"event": "log",         "message": str}
  {"event": "start",       "total": int}
  {"event": "email_start", "index": int, "total": int,
                           "sender": str, "subject": str}
  {"event": "email_done",  "index": int, "total": int,
                           "msg": dict, "category": str,
                           "category_label": str}
  {"event": "done",        "counts": dict, "total": int}
  {"event": "error",       "detail": str}

Endpoints:
    GET  /api/pipeline/run    — start pipeline, stream SSE
    GET  /api/pipeline/status — check if pipeline is running
"""

import json
import asyncio
import threading
from typing import AsyncGenerator

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from orchestrator import Orchestrator
from agents.inbox_agent import InboxAgent
from routers.auth import get_active_service, get_active_email
from config import MAX_EMAILS


router = APIRouter(prefix="/pipeline", tags=["pipeline"])


# ── Pipeline state ─────────────────────────────────────────────────────────────
# Tracks whether a pipeline run is currently active.
# Prevents duplicate runs if the user clicks "Run" twice.

_state: dict = {
    "running": False,
    "last_counts": None,
    "last_total":  0,
}


# ── Response models ────────────────────────────────────────────────────────────

class StatusResponse(BaseModel):
    running:     bool
    last_total:  int
    last_counts: dict | None


# ── Endpoints ──────────────────────────────────────────────────────────────────

@router.get("/run")
async def run_pipeline():
    """
    Starts the multi-agent pipeline and streams progress via SSE.

    Requires active session credentials (set via /api/auth/connect).
    Returns HTTP 409 if a pipeline run is already in progress.

    Each SSE message is a JSON-encoded event dict.
    The stream ends when the pipeline finishes or errors.
    """
    if _state["running"]:
        raise HTTPException(
            status_code=409,
            detail="Pipeline is already running. Please wait for it to finish."
        )

    # Get active IMAP service from session
    imap_service = get_active_service()

    return StreamingResponse(
        _stream_pipeline(imap_service),
        media_type="text/event-stream",
        headers={
            # Disable buffering so events reach the client immediately
            "Cache-Control":               "no-cache",
            "X-Accel-Buffering":           "no",
            "Access-Control-Allow-Origin": "*",
        },
    )


@router.get("/status", response_model=StatusResponse)
async def pipeline_status():
    """
    Returns whether the pipeline is currently running
    and the results of the last completed run.
    """
    return StatusResponse(
        running=_state["running"],
        last_total=_state["last_total"],
        last_counts=_state["last_counts"],
    )


# ── SSE stream generator ───────────────────────────────────────────────────────

async def _stream_pipeline(imap_service) -> AsyncGenerator[str, None]:
    """
    Async generator that runs the Orchestrator and yields
    SSE-formatted strings for each pipeline event.

    SSE format (required by browser EventSource API):
        data: <json>\n\n

    The Orchestrator.run() is a synchronous generator — we run it
    in a background thread via threading.Thread and communicate
    with the async event loop via asyncio.Queue. This lets us
    stream events to the frontend in real time as each email is
    processed, instead of waiting for the full pipeline to finish.
    """
    _state["running"] = True

    try:
        # Build InboxAgent with the active IMAP service
        inbox_agent  = InboxAgent(imap_service=imap_service)
        orchestrator = Orchestrator(inbox_agent=inbox_agent)

        # Queue bridges the sync generator thread → async event loop
        queue = asyncio.Queue()
        loop  = asyncio.get_event_loop()

        def _run_sync():
            # Runs in a background thread — yields events into the queue
            for event in orchestrator.run():
                loop.call_soon_threadsafe(queue.put_nowait, event)
            # Sentinel value signals the stream is complete
            loop.call_soon_threadsafe(queue.put_nowait, None)

        # Start the pipeline in a background thread
        thread = threading.Thread(target=_run_sync, daemon=True)
        thread.start()

        # Consume events from the queue and stream to frontend
        while True:
            event = await queue.get()

            # None sentinel means pipeline is done
            if event is None:
                break

            # Store final counts when pipeline completes
            if event.get("event") == "done":
                _state["last_counts"] = event.get("counts", {})
                _state["last_total"]  = event.get("total", 0)

            # Format as SSE and yield to frontend
            yield _format_sse(event)

            # Small delay so the frontend can render between events
            await asyncio.sleep(0.05)

    except Exception as e:
        yield _format_sse({"event": "error", "detail": str(e)})

    finally:
        _state["running"] = False


def _format_sse(data: dict) -> str:
    """
    Formats a dict as an SSE message string.

    SSE protocol requires:
        data: <payload>\n\n

    The double newline signals the end of one event to the browser.
    """
    return f"data: {json.dumps(data)}\n\n"