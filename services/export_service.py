"""
services/export_service.py

Exports IMAP folders/labels to .eml files and creates zip archives.
Also supports syncing folders directly into another mailbox's INBOX
via IMAP APPEND (no files written, no SMTP involved).
Supports starred/flagged emails as a special virtual category.

Responsibilities:
    - Export a single folder
    - Export multiple folders
    - Export starred (\\Flagged) emails
    - Save each email as Subject.eml
    - Sanitize invalid filename characters
    - Create a downloadable .zip archive
    - Sync (copy) folders into a second IMAP account's INBOX
    - Sync starred emails into a second IMAP account's INBOX

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

    def __init__(self, imap_service: IMAPService):
        self.imap_service = imap_service

    # ──────────────────────────────────────────────────────────────
    # Existing: download/export (unchanged)
    # ──────────────────────────────────────────────────────────────

    def export_folder(self, folder_name: str) -> str:
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

    def export_with_starred(
        self,
        folders: list[str],
        include_starred: bool,
        starred_folder: str = "",
    ) -> str:
        """
        Exports the given folders plus optionally starred emails,
        all into one zip archive.

        The archive (and its internal base directory) is named after the
        single label being exported when there's exactly one source of
        emails involved:
            - one folder, no starred              -> "<folder>.zip"
            - no folders, starred only             -> "Starred.zip"
        Anything broader (multiple folders, and/or folders + starred
        together) falls back to the generic "mail_export.zip" name,
        since there's no single label that describes the contents.

        starred_folder: if the server exposes a real Starred/Flagged
          folder (e.g. [Gmail]/Starred), pass its name here — it will
          be fetched like any other folder.
          If empty, falls back to SEARCH FLAGGED on INBOX.
        """
        EXPORT_ROOT.mkdir(exist_ok=True)

        export_name = self._derive_export_name(
            folders=folders,
            include_starred=include_starred,
        )

        export_dir = EXPORT_ROOT / export_name

        if export_dir.exists():
            shutil.rmtree(export_dir)
        export_dir.mkdir(parents=True)

        for folder in folders:
            self._export_single_folder(
                folder_name=folder,
                root_dir=export_dir
            )

        if include_starred:
            if starred_folder:
                # Real folder — treat like any other folder
                self._export_single_folder(
                    folder_name=starred_folder,
                    root_dir=export_dir
                )
            else:
                # Fallback: flag search on INBOX
                self._export_starred_fallback(export_dir)

        zip_path = shutil.make_archive(
            str(export_dir),
            "zip",
            root_dir=EXPORT_ROOT,
            base_dir=export_name
        )

        print(f"  ✓ Exported archive: {zip_path}")
        return zip_path

    # ──────────────────────────────────────────────────────────────
    # Existing: sync to another mailbox (unchanged)
    # ──────────────────────────────────────────────────────────────

    def sync_multiple(
        self,
        folders: list[str],
        dest_service: IMAPService,
        dest_folder: str = "INBOX",
    ) -> dict:
        """
        Copies every email from the given source folders directly into
        dest_service's mailbox via IMAP APPEND.
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
                status, msg_data = self.imap_service.imap.fetch(eid, "(RFC822)")

                if status != "OK":
                    continue

                raw_email = msg_data[0][1]

                subject = ""
                try:
                    parsed = self.imap_service._parse_email(raw_email, eid.decode())
                    if parsed:
                        subject = parsed.get("subject", "")
                except Exception:
                    pass

                try:
                    dest_service.imap.append(dest_folder, None, None, raw_email)
                    synced += 1
                except Exception as e:
                    failed.append({
                        "folder": folder,
                        "subject": subject or "(no subject)",
                        "error": str(e),
                    })

            print(f"  ✓ Synced folder '{folder}' ({len(email_ids)} email(s) attempted)")

        print(f"  ✓ Sync complete: {synced} synced, {len(failed)} failed")
        return {"synced": synced, "failed": failed}

    def sync_with_starred(
        self,
        folders: list[str],
        dest_service: IMAPService,
        include_starred: bool,
        starred_folder: str = "",
        dest_folder: str = "INBOX",
    ) -> dict:
        """
        Syncs the given folders plus optionally starred emails
        into the destination mailbox.

        starred_folder: real IMAP folder name for Starred if the server
          exposes one (e.g. [Gmail]/Starred). Empty = flag-search fallback.
        """
        result = self.sync_multiple(folders, dest_service, dest_folder)

        if include_starred:
            starred_result = self._sync_starred(
                dest_service=dest_service,
                starred_folder=starred_folder,
                dest_folder=dest_folder,
            )
            result["synced"] += starred_result["synced"]
            result["failed"] += starred_result["failed"]

        return result

    # ──────────────────────────────────────────────────────────────
    # Internal helpers
    # ──────────────────────────────────────────────────────────────

    def _derive_export_name(
        self,
        folders: list[str],
        include_starred: bool,
    ) -> str:
        """
        Works out what to call the export directory/zip.

        - Exactly one folder, no starred  -> name after that folder
        - No folders, starred only        -> "Starred"
        - Anything else (0 folders + no starred, 2+ folders, or
          folders + starred combined)     -> "mail_export"
        """
        if len(folders) == 1 and not include_starred:
            return self._folder_to_name(folders[0])

        if len(folders) == 0 and include_starred:
            return "Starred"

        return "mail_export"

    def _export_single_folder(
        self,
        folder_name: str,
        root_dir: Path
    ) -> None:
        folder_path = root_dir / self._folder_to_name(folder_name)
        folder_path.mkdir(parents=True, exist_ok=True)

        self.imap_service.imap.select(f'"{folder_name}"')

        status, data = self.imap_service.imap.search(None, "ALL")

        if status != "OK":
            return

        email_ids = data[0].split()

        for index, eid in enumerate(email_ids, start=1):
            status, msg_data = self.imap_service.imap.fetch(eid, "(RFC822)")

            if status != "OK":
                continue

            raw_email = msg_data[0][1]

            parsed = self.imap_service._parse_email(raw_email, eid.decode())
            subject = parsed.get("subject", "") if parsed else ""

            if not subject.strip():
                filename = f"email_{index}.eml"
            else:
                filename = self._sanitize_filename(subject)
                if not filename.lower().endswith(".eml"):
                    filename += ".eml"

            file_path = folder_path / filename

            counter = 1
            while file_path.exists():
                stem = Path(filename).stem
                file_path = folder_path / f"{stem}_{counter}.eml"
                counter += 1

            with open(file_path, "wb") as f:
                f.write(raw_email)

        print(f"  ✓ Exported {len(email_ids)} email(s) from {folder_name}")

    def _export_starred_fallback(self, root_dir: Path) -> None:
        """
        Exports starred (\\Flagged) emails from INBOX into a
        'Starred' subfolder inside root_dir.
        Used when the provider has no dedicated Starred folder.
        """
        raw_emails = self.imap_service.get_starred_raw_emails("INBOX")

        if not raw_emails:
            return

        folder_path = root_dir / "Starred"
        folder_path.mkdir(parents=True, exist_ok=True)

        for index, raw_email in enumerate(raw_emails, start=1):
            parsed = self.imap_service._parse_email(raw_email, str(index))
            subject = parsed.get("subject", "") if parsed else ""

            if not subject.strip():
                filename = f"email_{index}.eml"
            else:
                filename = self._sanitize_filename(subject)
                if not filename.lower().endswith(".eml"):
                    filename += ".eml"

            file_path = folder_path / filename
            counter = 1
            while file_path.exists():
                stem = Path(filename).stem
                file_path = folder_path / f"{stem}_{counter}.eml"
                counter += 1

            with open(file_path, "wb") as f:
                f.write(raw_email)

        print(f"  ✓ Exported {len(raw_emails)} starred email(s)")

    def _sync_starred(
        self,
        dest_service: IMAPService,
        starred_folder: str,
        dest_folder: str,
    ) -> dict:
        """
        Appends starred emails into the destination mailbox.
        Uses the real starred folder if available, otherwise flag-search fallback.
        """
        synced = 0
        failed = []

        if starred_folder:
            # Real folder — reuse sync_multiple for one folder
            r = self.sync_multiple([starred_folder], dest_service, dest_folder)
            return r

        # Fallback: SEARCH FLAGGED on INBOX
        raw_emails = self.imap_service.get_starred_raw_emails("INBOX")

        for raw_email in raw_emails:
            try:
                dest_service.imap.append(dest_folder, None, None, raw_email)
                synced += 1
            except Exception as e:
                parsed = self.imap_service._parse_email(raw_email, "?")
                subject = parsed.get("subject", "(no subject)") if parsed else "(no subject)"
                failed.append({
                    "folder": "Starred",
                    "subject": subject,
                    "error": str(e),
                })

        print(f"  ✓ Synced {synced} starred email(s)")
        return {"synced": synced, "failed": failed}

    @staticmethod
    def _folder_to_name(folder_name: str) -> str:
        return folder_name.replace("/", "_")

    @staticmethod
    def _sanitize_filename(subject: str) -> str:
        subject = subject.strip()
        subject = re.sub(r'[\\/:*?"<>|]', "_", subject)
        subject = re.sub(r"\s+", " ", subject)
        subject = subject[:150]
        if not subject:
            subject = "email"
        return subject