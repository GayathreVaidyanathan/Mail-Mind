"""
routers/export.py

Email export router — /api/export/*
────────────────────────────────────
Provides endpoints for downloading one or more IMAP folders
as .zip archives containing .eml files, and for syncing those
same folders directly into another mailbox's INBOX over IMAP.

Endpoints:
    GET  /api/export/folders
        Returns all available folders/labels.

    POST /api/export/download
        Downloads selected folders as a zip archive.

    POST /api/export/sync-to-inbox
        Copies selected folders into another IMAP account's INBOX.
        No SMTP, no files written — raw IMAP APPEND, same mechanism
        mail sync/migration tools use.
"""

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from routers.auth import get_active_service
from services.export_service import ExportService
from services.imap_service import IMAPService


router = APIRouter(
    prefix="/export",
    tags=["export"]
)


# ── Request / Response Models ─────────────────────────────────────────────

class FolderListResponse(BaseModel):
    folders: list[str]


class DownloadRequest(BaseModel):
    folders: list[str]


class DestinationCredentials(BaseModel):
    email: str
    password: str


class SyncToInboxRequest(BaseModel):
    folders: list[str]
    destination: DestinationCredentials


class SyncToInboxResponse(BaseModel):
    synced: int
    failed: list[dict]


# ── Endpoints ──────────────────────────────────────────────────────────────

@router.get(
    "/folders",
    response_model=FolderListResponse
)
async def list_folders():
    """
    Returns all available IMAP folders.
    """

    service = get_active_service()

    try:
        service.connect()

        folders = service.list_folders()

        return FolderListResponse(
            folders=folders
        )

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=str(e)
        )

    finally:
        service.disconnect()


@router.post("/download")
async def download_folders(
    request: DownloadRequest
):
    """
    Downloads one or more folders as a zip archive.
    """

    if not request.folders:
        raise HTTPException(
            status_code=400,
            detail="No folders selected."
        )

    service = get_active_service()

    try:
        service.connect()

        export_service = ExportService(service)

        zip_path = export_service.export_multiple(
            request.folders
        )

        filename = zip_path.split("/")[-1]

        return FileResponse(
            path=zip_path,
            filename=filename,
            media_type="application/zip"
        )

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=str(e)
        )

    finally:
        service.disconnect()


@router.post(
    "/sync-to-inbox",
    response_model=SyncToInboxResponse
)
async def sync_to_inbox(
    request: SyncToInboxRequest
):
    """
    Copies the selected folders' emails directly into another
    mailbox's INBOX, via IMAP APPEND on a second connection.

    Destination provider is auto-detected from the email domain
    by IMAPService (same logic used for the primary account) —
    the caller only supplies an email + app password, no host/port.

    This is additive: the existing /download endpoint is untouched
    and both features can be used independently.
    """

    if not request.folders:
        raise HTTPException(
            status_code=400,
            detail="No folders selected."
        )

    source_service = get_active_service()

    dest_service = IMAPService(
        email_address=request.destination.email,
        password=request.destination.password,
    )

    try:
        source_service.connect()

        try:
            dest_service.connect()
        except ValueError as e:
            # surfaces a clear "destination auth failed" message
            raise HTTPException(
                status_code=400,
                detail=f"Could not connect to destination mailbox: {e}"
            )

        export_service = ExportService(source_service)

        result = export_service.sync_multiple(
            request.folders,
            dest_service,
        )

        return SyncToInboxResponse(
            synced=result["synced"],
            failed=result["failed"],
        )

    except HTTPException:
        raise

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=str(e)
        )

    finally:
        source_service.disconnect()
        dest_service.disconnect()