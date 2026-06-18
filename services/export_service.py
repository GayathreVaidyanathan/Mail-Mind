"""
services/export_service.py

Exports IMAP folders/labels to .eml files and creates zip archives.
Also supports syncing folders directly into another mailbox's INBOX
via IMAP APPEND (no files written, no SMTP involved).

Responsibilities:
    - Export a single folder
    - Export multiple folders
    - Save each email as Subject.eml
    - Sanitize invalid filename characters
    - Create a downloadable .zip archive
    - Sync (copy) folders into a second IMAP account's INBOX

This service does NOT interact with agents or the orchestrator.
It only uses IMAPService.
"""

import os
import re
import shutil
from pathlib import Path

from services.imap_service import IMAPService


EXPORT_ROOT = Path("exports")


class ExportService:
    """
    Handles email export, archive creation, and cross-account sync.

    Usage:

        export_service = ExportService(service)

        zip_path = export_service.export_folder(
            "Auto/Spam"
        )

        zip_path = export_service.export_multiple(
            ["Finance", "Career"]
        )

        result = export_service.sync_multiple(
            ["Finance", "Career"],
            dest_service
        )
    """

    def __init__(self, imap_service: IMAPService):
        self.imap_service = imap_service

    # ──────────────────────────────────────────────────────────────
    # Public methods — existing download/export (unchanged)
    # ──────────────────────────────────────────────────────────────

    def export_folder(self, folder_name: str) -> str:
        """
        Exports one folder and returns the path to the zip archive.
        """

        return self.export_multiple([folder_name])

    def export_multiple(self, folders: list[str]) -> str:
        """
        Exports multiple folders and returns zip path.
        """

        EXPORT_ROOT.mkdir(exist_ok=True)

        export_name = (
            self._folder_to_name(folders[0])
            if len(folders) == 1
            else "mail_export"
        )

        export_dir = EXPORT_ROOT / export_name

        # Start fresh
        if export_dir.exists():
            shutil.rmtree(export_dir)

        export_dir.mkdir(parents=True)

        for folder in folders:
            self._export_single_folder(
                folder_name=folder,
                root_dir=export_dir
            )

        zip_path = shutil.make_archive(
            str(export_dir),
            "zip",
            root_dir=EXPORT_ROOT,
            base_dir=export_name
        )

        print(f"  ✓ Exported archive: {zip_path}")

        return zip_path

    # ──────────────────────────────────────────────────────────────
    # Public methods — new: sync to another mailbox's INBOX
    # ──────────────────────────────────────────────────────────────

    def sync_multiple(
        self,
        folders: list[str],
        dest_service: IMAPService,
        dest_folder: str = "INBOX",
    ) -> dict:
        """
        Copies every email from the given source folders directly into
        dest_service's mailbox (default: INBOX) using IMAP APPEND.

        No files are written to disk and no SMTP send is performed —
        this is a raw IMAP-to-IMAP message copy, the same mechanism
        mail sync/migration tools use. Messages keep their original
        sender, date, and headers.

        dest_service must already be connected (dest_service.connect()
        called by the caller) so this method can be reused/tested
        independently of the router.

        Returns:
            {
                "synced": <int>,
                "failed": [{"folder": str, "subject": str, "error": str}, ...]
            }
        """

        synced = 0
        failed = []

        for folder in folders:
            try:
                self.imap_service.imap.select(f'"{folder}"')
            except Exception as e:
                failed.append({
                    "folder": folder,
                    "subject": "(folder select failed)",
                    "error": str(e),
                })
                continue

            status, data = self.imap_service.imap.search(None, "ALL")

            if status != "OK":
                continue

            email_ids = data[0].split()

            for eid in email_ids:

                status, msg_data = self.imap_service.imap.fetch(
                    eid,
                    "(RFC822)"
                )

                if status != "OK":
                    continue

                raw_email = msg_data[0][1]

                subject = ""
                try:
                    parsed = self.imap_service._parse_email(
                        raw_email,
                        eid.decode()
                    )
                    if parsed:
                        subject = parsed.get("subject", "")
                except Exception:
                    pass

                try:
                    dest_service.imap.append(
                        dest_folder,
                        None,
                        None,
                        raw_email
                    )
                    synced += 1
                except Exception as e:
                    failed.append({
                        "folder": folder,
                        "subject": subject or "(no subject)",
                        "error": str(e),
                    })

            print(
                f"  ✓ Synced folder '{folder}' "
                f"({len(email_ids)} email(s) attempted)"
            )

        print(f"  ✓ Sync complete: {synced} synced, {len(failed)} failed")

        return {
            "synced": synced,
            "failed": failed,
        }

    # ──────────────────────────────────────────────────────────────
    # Internal methods
    # ──────────────────────────────────────────────────────────────

    def _export_single_folder(
        self,
        folder_name: str,
        root_dir: Path
    ) -> None:
        """
        Saves all emails inside a folder as .eml files.
        """

        folder_path = root_dir / self._folder_to_name(folder_name)
        folder_path.mkdir(parents=True, exist_ok=True)

        self.imap_service.imap.select(f'"{folder_name}"')

        status, data = self.imap_service.imap.search(None, "ALL")

        if status != "OK":
            return

        email_ids = data[0].split()

        for index, eid in enumerate(email_ids, start=1):

            status, msg_data = self.imap_service.imap.fetch(
                eid,
                "(RFC822)"
            )

            if status != "OK":
                continue

            raw_email = msg_data[0][1]

            parsed = self.imap_service._parse_email(
                raw_email,
                eid.decode()
            )

            if parsed:
                subject = parsed.get("subject", "")

            else:
                subject = ""

            if not subject.strip():
                filename = f"email_{index}.eml"

            else:
                filename = self._sanitize_filename(subject)

                if not filename.lower().endswith(".eml"):
                    filename += ".eml"

            file_path = folder_path / filename

            # Handle duplicate subjects
            counter = 1

            while file_path.exists():

                stem = Path(filename).stem

                file_path = (
                    folder_path /
                    f"{stem}_{counter}.eml"
                )

                counter += 1

            with open(file_path, "wb") as f:
                f.write(raw_email)

        print(
            f"  ✓ Exported {len(email_ids)} email(s) "
            f"from {folder_name}"
        )

    @staticmethod
    def _folder_to_name(folder_name: str) -> str:
        """
        Converts:

            Auto/Spam

        into:

            Auto_Spam
        """

        return folder_name.replace("/", "_")

    @staticmethod
    def _sanitize_filename(subject: str) -> str:
        """
        Removes invalid filename characters.
        """

        subject = subject.strip()

        subject = re.sub(
            r'[\\/:*?"<>|]',
            "_",
            subject
        )

        subject = re.sub(
            r"\s+",
            " ",
            subject
        )

        subject = subject[:150]

        if not subject:
            subject = "email"

        return subject