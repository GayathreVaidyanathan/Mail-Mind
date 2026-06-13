"""
routers/auth.py

Authentication router — /api/auth/*
─────────────────────────────────────
Handles credential validation before the pipeline runs.

The UI sends email + app password → this router tries an IMAP
connection → returns success or a clear error message.

Credentials are kept in memory for the session only.
They are never written to disk.

Endpoints:
    POST /api/auth/connect   — validate credentials, store in session
    POST /api/auth/disconnect — clear session credentials
    GET  /api/auth/status    — check if credentials are loaded
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, EmailStr

from services.imap_service import IMAPService


router = APIRouter(prefix="/auth", tags=["auth"])


# ── In-memory session store ────────────────────────────────────────────────────
# Holds the active IMAPService instance for the current session.
# In a multi-user deployment this would be replaced with a proper
# session store — for local/single-user use this is sufficient.

_session: dict = {
    "email":    None,
    "password": None,
    "service":  None,
}


# ── Request / Response models ──────────────────────────────────────────────────

class ConnectRequest(BaseModel):
    email:    str         # user's email address
    password: str         # app password (not their real password)


class ConnectResponse(BaseModel):
    success:  bool
    email:    str
    provider: str         # e.g. "gmail.com", "outlook.com"
    message:  str


class StatusResponse(BaseModel):
    connected: bool
    email:     str | None


# ── Endpoints ──────────────────────────────────────────────────────────────────

@router.post("/connect", response_model=ConnectResponse)
async def connect(request: ConnectRequest):
    """
    Validates IMAP credentials by attempting a real connection.

    On success:
      - Stores the IMAPService instance in the session
      - Returns provider info so the UI can confirm which account connected

    On failure:
      - Returns HTTP 401 with a clear error message
      - Does not store anything in session
    """
    service = IMAPService(
        email_address=request.email,
        password=request.password,
    )

    try:
        service.test_connection()
    except ValueError as e:
        raise HTTPException(status_code=401, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Unexpected error connecting to inbox: {str(e)}"
        )

    # Store in session for pipeline to use
    _session["email"]    = request.email
    _session["password"] = request.password
    _session["service"]  = service

    domain = request.email.split("@")[-1].lower()

    return ConnectResponse(
        success=True,
        email=request.email,
        provider=domain,
        message=f"Successfully connected to {domain}",
    )


@router.post("/disconnect")
async def disconnect():
    """
    Clears session credentials.
    Called when the user logs out or switches accounts in the UI.
    """
    _session["email"]    = None
    _session["password"] = None
    _session["service"]  = None

    return {"success": True, "message": "Disconnected."}


@router.get("/status", response_model=StatusResponse)
async def status():
    """
    Returns whether credentials are currently loaded in the session.
    Used by the UI to decide whether to show ConnectPage or DashboardPage.
    """
    return StatusResponse(
        connected=_session["service"] is not None,
        email=_session["email"],
    )


# ── Session accessor ───────────────────────────────────────────────────────────
# Used by routers/pipeline.py to get the active IMAPService
# without re-authenticating on every request.

def get_active_service() -> IMAPService:
    """
    Returns the active IMAPService from session.
    Raises HTTP 401 if no credentials are loaded.
    """
    if _session["service"] is None:
        raise HTTPException(
            status_code=401,
            detail="Not connected. Please connect your email first."
        )
    return _session["service"]


def get_active_email() -> str:
    """Returns the currently connected email address."""
    return _session["email"] or ""