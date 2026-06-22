"""
routers/export.py

Email export/import router — /api/export/*
────────────────────────────────────
Endpoints:
    GET  /api/export/folders
        Returns all folders with type, label, and special_use metadata.
        Includes INBOX, system folders (Sent, Drafts, Trash etc.),
        and custom labels. Provider-agnostic via RFC 6154 special-use.

    POST /api/export/download
        Downloads selected folders (+ optionally starred) as a zip archive.

    POST /api/export/sync-to-inbox
        Copies selected folders (+ optionally starred) into another
        IMAP account's INBOX. No SMTP — raw IMAP APPEND.

    POST /api/export/check-destination-folders
        Connects to an arbitrary destination mailbox (any IMAP provider,
        not necessarily the currently active session) using the given
        credentials and returns its folder list. Used by the Upload UI
        to populate a real destination-folder dropdown before uploading,
        mirroring /folders but for a mailbox the user hasn't logged into.

    POST /api/export/upload
        Uploads a local .eml file OR a .zip archive (matching the structure
        produced by /download) and appends the email(s) into a DESTINATION
        mailbox via IMAP APPEND — same destination-credentials pattern as
        /sync-to-inbox, fully independent of whichever mailbox is currently
        active. Missing destination folders are created automatically. By
        default, folder structure inside a zip is preserved against the
        destination; pass dest_folder to force everything into one folder.
"""

import logging
import shutil
import tempfile
from pathlib import Path

from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from fastapi.responses import FileResponse
from pydantic import BaseModel

from routers.auth import get_active_service
from services.export_service import ExportService
from services.import_service import ImportService
from services.imap_service import IMAPService

logger = logging.getLogger(__name__)


router = APIRouter(
    prefix="/export",
    tags=["export"]
)


# ── Request / Response Models ─────────────────────────────────────────────

class FolderInfo(BaseModel):
    name:        str   # raw IMAP name e.g. "[Gmail]/Sent Mail"
    label:       str   # friendly name e.g. "Sent"
    type:        str   # "inbox" | "system" | "custom"
    special_use: str   # RFC 6154 attribute e.g. "\\sent", or ""


class FolderListResponse(BaseModel):
    folders: list[FolderInfo]


class DownloadRequest(BaseModel):
    folders:         list[str]
    include_starred: bool = False
    starred_folder:  str  = ""   # raw IMAP name if server exposes one


class DestinationCredentials(BaseModel):
    email:    str
    password: str


class SyncToInboxRequest(BaseModel):
    folders:         list[str]
    include_starred: bool = False
    starred_folder:  str  = ""
    destination:     DestinationCredentials


class SyncToInboxResponse(BaseModel):
    synced: int
    failed: list[dict]


class UploadResponse(BaseModel):
    imported: int
    failed:   list[dict]


# ── Endpoints ──────────────────────────────────────────────────────────────

@router.get(
    "/folders",
    response_model=FolderListResponse
)
async def list_folders():
    """
    Returns all available IMAP folders with type and friendly label.
    System folders are identified by RFC 6154 special-use attributes,
    not by hardcoded names — works across all providers.
    """
    service = get_active_service()

    try:
        service.connect()
        folders = service.list_folders_rich()
        return FolderListResponse(
            folders=[FolderInfo(**f) for f in folders]
        )

    except Exception as e:
        logger.exception("Unhandled error in export endpoint")
        raise HTTPException(status_code=500, detail=str(e))

    finally:
        service.disconnect()


@router.post("/download")
async def download_folders(
    request: DownloadRequest
):
    """
    Downloads selected folders (and optionally starred emails) as a zip.
    """
    if not request.folders and not request.include_starred:
        raise HTTPException(
            status_code=400,
            detail="No folders selected."
        )

    service = get_active_service()

    try:
        service.connect()
        export_service = ExportService(service)

        zip_path = export_service.export_with_starred(
            folders=request.folders,
            include_starred=request.include_starred,
            starred_folder=request.starred_folder,
        )

        filename = zip_path.split("/")[-1]

        return FileResponse(
            path=zip_path,
            filename=filename,
            media_type="application/zip"
        )

    except Exception as e:
        logger.exception("Unhandled error in export endpoint")
        raise HTTPException(status_code=500, detail=str(e))

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
    Copies selected folders (and optionally starred emails) into another
    IMAP account's INBOX via IMAP APPEND. No SMTP, no files written.
    Destination provider is auto-detected from the email domain.
    """
    if not request.folders and not request.include_starred:
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
            raise HTTPException(
                status_code=400,
                detail=f"Could not connect to destination mailbox: {e}"
            )

        export_service = ExportService(source_service)

        result = export_service.sync_with_starred(
            folders=request.folders,
            dest_service=dest_service,
            include_starred=request.include_starred,
            starred_folder=request.starred_folder,
        )

        return SyncToInboxResponse(
            synced=result["synced"],
            failed=result["failed"],
        )

    except HTTPException:
        raise

    except Exception as e:
        logger.exception("Unhandled error in export endpoint")
        raise HTTPException(status_code=500, detail=str(e))

    finally:
        source_service.disconnect()
        dest_service.disconnect()


@router.post(
    "/check-destination-folders",
    response_model=FolderListResponse
)
async def check_destination_folders(
    destination: DestinationCredentials
):
    """
    Connects to an arbitrary destination mailbox using the given
    credentials and returns its folder list. This is the destination-side
    equivalent of GET /folders — used so the Upload UI can offer a real
    dropdown of the DESTINATION's actual folders, instead of guessing or
    reusing folders from whichever mailbox happens to be currently active.

    Does not affect or require the currently active session at all.
    """
    dest_service = IMAPService(
        email_address=destination.email,
        password=destination.password,
    )

    try:
        dest_service.connect()
    except ValueError as e:
        raise HTTPException(
            status_code=400,
            detail=f"Could not connect to destination mailbox: {e}"
        )

    try:
        folders = dest_service.list_folders_rich()
        return FolderListResponse(
            folders=[FolderInfo(**f) for f in folders]
        )

    except Exception as e:
        logger.exception("Unhandled error in check-destination-folders endpoint")
        raise HTTPException(status_code=500, detail=str(e))

    finally:
        dest_service.disconnect()


@router.post(
    "/upload",
    response_model=UploadResponse
)
async def upload_emails(
    file: UploadFile = File(...),
    dest_email: str = Form(...),
    dest_password: str = Form(...),
    dest_folder: str = Form(""),
):
    """
    Uploads a local .eml file or a .zip archive of .eml files and appends
    them into a DESTINATION mailbox via IMAP APPEND — independent of
    whichever mailbox is currently active in this session, same as how
    /sync-to-inbox targets an arbitrary destination rather than reusing
    the active connection.

    file:
        A single .eml file, or a .zip archive (e.g. produced by /download).

    dest_email / dest_password:
        Credentials for the destination mailbox. Provider is auto-detected
        from the email domain, same as everywhere else in this router.

    dest_folder:
        Optional. If empty (default), folder structure inside a zip is
        preserved against the destination — each subfolder name becomes
        the destination IMAP folder, and a loose .eml at the zip root (or
        a standalone .eml upload) goes into INBOX. If set, every email is
        appended into this single destination folder instead, regardless
        of original structure. Missing folders are created automatically.
    """
    filename = file.filename or ""
    suffix = Path(filename).suffix.lower()

    if suffix not in (".eml", ".zip"):
        raise HTTPException(
            status_code=400,
            detail="Only .eml or .zip files are supported.",
        )

    dest_service = IMAPService(
        email_address=dest_email,
        password=dest_password,
    )

    with tempfile.TemporaryDirectory(prefix="mail_upload_") as tmp_dir:
        tmp_path = Path(tmp_dir) / (filename or f"upload{suffix}")

        try:
            with open(tmp_path, "wb") as f:
                shutil.copyfileobj(file.file, f)
        except Exception as e:
            raise HTTPException(
                status_code=400,
                detail=f"Could not read uploaded file: {e}",
            )

        try:
            dest_service.connect()
        except ValueError as e:
            raise HTTPException(
                status_code=400,
                detail=f"Could not connect to destination mailbox: {e}"
            )

        try:
            import_service = ImportService(dest_service)

            if suffix == ".zip":
                result = import_service.import_zip(
                    zip_path=tmp_path,
                    dest_folder_override=dest_folder,
                )
            else:
                result = import_service.import_single_eml(
                    eml_path=tmp_path,
                    dest_folder=dest_folder or "INBOX",
                )

            return UploadResponse(
                imported=result["imported"],
                failed=result["failed"],
            )

        except Exception as e:
            logger.exception("Unhandled error in upload endpoint")
            raise HTTPException(status_code=500, detail=str(e))

        finally:
            dest_service.disconnect()