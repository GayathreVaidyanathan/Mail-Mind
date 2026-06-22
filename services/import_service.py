"""
services/import_service.py

Imports local .eml files (or .zip archives of them) INTO an IMAP mailbox
via IMAP APPEND. This is the reverse of ExportService — files on disk
going back up into a mailbox, instead of a mailbox going down to disk.

Supports two upload shapes:
    1. A single .eml file              -> appended into one destination folder
    2. A .zip archive containing        -> structure is preserved (each
       folder(s) of .eml files             subfolder becomes/maps to an IMAP
                                            folder of the same name), unless
                                            the caller overrides with a single
                                            destination folder.

This mirrors the layout produced by ExportService.export_multiple() /
export_with_starred(), i.e.:

    mail_export.zip
        INBOX/
            Some Subject.eml
            Another Subject.eml
        Starred/
            Flagged Thing.eml

Missing destination folders are created automatically (same behavior as
IMAPService.apply_label / move_to_folder).

This service does NOT interact with agents or the orchestrator.
It only uses IMAPService.
"""

import shutil
import tempfile
import zipfile
from pathlib import Path

from services.imap_service import IMAPService


class ImportService:

    def __init__(self, imap_service: IMAPService):
        self.imap_service = imap_service

    # ──────────────────────────────────────────────────────────────
    # Public API
    # ──────────────────────────────────────────────────────────────

    def import_eml_bytes(self, raw_bytes: bytes, dest_folder: str) -> None:
        """
        Appends a single raw RFC822 email into dest_folder.
        Creates the folder first if it doesn't already exist.
        Raises on failure — callers collect failures themselves so one
        bad file doesn't abort an entire batch.
        """
        self.imap_service._ensure_folder(dest_folder)
        self.imap_service.imap.append(dest_folder, None, None, raw_bytes)

    def import_eml_file(self, file_path: Path, dest_folder: str) -> None:
        """Reads a single .eml file from disk and appends it to dest_folder."""
        raw_bytes = Path(file_path).read_bytes()
        self.import_eml_bytes(raw_bytes, dest_folder)

    def import_zip(
        self,
        zip_path: Path,
        dest_folder_override: str = "",
    ) -> dict:
        """
        Unzips zip_path and imports every .eml file found inside.

        If dest_folder_override is empty (default):
            Preserves structure — each top-level subfolder name inside the
            zip becomes the destination IMAP folder name for the .eml files
            within it. .eml files sitting directly at the zip root go into
            "INBOX".

        If dest_folder_override is set:
            Every .eml file in the zip, regardless of its subfolder, is
            appended into that single destination folder instead.

        Returns {"imported": int, "failed": [ {file, folder, error}, ... ]}
        """
        imported = 0
        failed = []

        with tempfile.TemporaryDirectory(prefix="mail_import_") as tmp_dir:
            tmp_path = Path(tmp_dir)

            try:
                with zipfile.ZipFile(zip_path, "r") as zf:
                    zf.extractall(tmp_path)
            except zipfile.BadZipFile as e:
                failed.append({
                    "file": str(zip_path),
                    "folder": dest_folder_override or "(unknown)",
                    "error": f"Not a valid zip file: {e}",
                })
                return {"imported": imported, "failed": failed}

            eml_files = sorted(tmp_path.rglob("*.eml"))

            if not eml_files:
                failed.append({
                    "file": str(zip_path),
                    "folder": dest_folder_override or "(unknown)",
                    "error": "No .eml files found in archive.",
                })
                return {"imported": imported, "failed": failed}

            for eml_path in eml_files:
                target_folder = (
                    dest_folder_override
                    or self._infer_folder_from_path(eml_path, tmp_path)
                )

                try:
                    self.import_eml_file(eml_path, target_folder)
                    imported += 1
                except Exception as e:
                    failed.append({
                        "file": eml_path.name,
                        "folder": target_folder,
                        "error": str(e),
                    })

        print(f"  ✓ Import complete: {imported} imported, {len(failed)} failed")
        return {"imported": imported, "failed": failed}

    def import_single_eml(
        self,
        eml_path: Path,
        dest_folder: str = "INBOX",
    ) -> dict:
        """
        Imports one standalone .eml file (not inside a zip).
        Returns the same {"imported", "failed"} shape as import_zip()
        so callers can treat both the same way.
        """
        imported = 0
        failed = []

        try:
            self.import_eml_file(eml_path, dest_folder)
            imported = 1
        except Exception as e:
            failed.append({
                "file": eml_path.name,
                "folder": dest_folder,
                "error": str(e),
            })

        return {"imported": imported, "failed": failed}

    # ──────────────────────────────────────────────────────────────
    # Internal helpers
    # ──────────────────────────────────────────────────────────────

    @staticmethod
    def _infer_folder_from_path(eml_path: Path, extract_root: Path) -> str:
        """
        Given an extracted .eml path, figures out the IMAP destination
        folder name.

        Depth-agnostic by design: ExportService always writes a file as
        `folder_path / filename`, i.e. the immediate parent directory of
        any .eml IS the folder it came from — no matter how many wrapper
        directories (mail_export/, a single-label name, future nesting,
        etc.) sit above it. So we just take the immediate parent's name,
        full stop. This stays correct even if export nesting changes.

        Examples (extract_root = /tmp/xyz):
            /tmp/xyz/INBOX/Subject.eml             -> "INBOX"
            /tmp/xyz/mail_export/INBOX/x.eml       -> "INBOX"
            /tmp/xyz/mail_export/Starred/x.eml     -> "Starred"
            /tmp/xyz/a/b/c/Some_Label/x.eml        -> "Some_Label" -> "Some/Label"
            /tmp/xyz/Subject.eml                   -> "INBOX"  (no subfolder = root)
        """
        relative = eml_path.relative_to(extract_root)
        parts = relative.parts

        # Drop the filename, keep directory parts only
        dir_parts = parts[:-1]

        if not dir_parts:
            # File sat at the zip root with no subfolder at all
            return "INBOX"

        # Immediate parent directory is always the real folder name —
        # reverse the "/" -> "_" sanitization ExportService applies via
        # _folder_to_name() when naming nested folders (e.g. Gmail's
        # "[Gmail]_Starred" on disk back to "[Gmail]/Starred" on the server).
        return dir_parts[-1].replace("_", "/")