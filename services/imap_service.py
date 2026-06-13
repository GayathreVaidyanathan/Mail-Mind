"""
services/imap_service.py

Low-level IMAP/SMTP email wrapper.
Replaces gmail_client.py — provider-agnostic, works with any email platform.

Provider auto-detection:
  The domain of the email address is used to pick the right IMAP/SMTP servers.
  Supported out of the box: Gmail, Outlook/Hotmail, Yahoo, iCloud, Protonmail.
  Any other domain falls back to asking for manual IMAP/SMTP host config.

Label → Folder mapping:
  Gmail has labels; IMAP has folders. This module creates IMAP folders
  to replicate the labeling behavior. Emails are COPIED to the folder
  (not moved) so they remain in INBOX too.

Authentication:
  Uses app passwords, not OAuth. Every provider supports this:
    Gmail   → myaccount.google.com/apppasswords
    Outlook → account.microsoft.com (App passwords under security)
    Yahoo   → security.yahoo.com/

Requires:
  pip install secure-smtplib  (usually included with Python)
  No extra packages — imaplib and smtplib are Python stdlib.
"""

import imaplib
import smtplib
import email
import re
import base64

from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.header import decode_header
from typing import Optional


# ── Provider registry ──────────────────────────────────────────────────────────

PROVIDER_MAP = {
    "gmail.com":      ("imap.gmail.com",            993, "smtp.gmail.com",            587),
    "googlemail.com": ("imap.gmail.com",            993, "smtp.gmail.com",            587),
    "outlook.com":    ("imap-mail.outlook.com",     993, "smtp-mail.outlook.com",     587),
    "hotmail.com":    ("imap-mail.outlook.com",     993, "smtp-mail.outlook.com",     587),
    "live.com":       ("imap-mail.outlook.com",     993, "smtp-mail.outlook.com",     587),
    "yahoo.com":      ("imap.mail.yahoo.com",       993, "smtp.mail.yahoo.com",       587),
    "icloud.com":     ("imap.mail.me.com",          993, "smtp.mail.me.com",          587),
    "me.com":         ("imap.mail.me.com",          993, "smtp.mail.me.com",          587),
    "protonmail.com": ("127.0.0.1",                 1143, "127.0.0.1",                1025),
    "gmx.com":        ("imap.gmx.com",              993, "mail.gmx.com",              587),
    "zohomail.in":    ("imap.zoho.in",              993, "smtp.zoho.in",              587),
}

# Folders created for routing (mirrors Gmail labels)
FOLDER_SPAM        = "Auto/Spam"
FOLDER_PROMOTIONAL = "Auto/Promotional"


# ── IMAPService ────────────────────────────────────────────────────────────────

class IMAPService:
    """
    Handles all IMAP and SMTP operations.
    Used exclusively by InboxAgent — no other agent imports this.

    Usage:
        service = IMAPService(email="you@gmail.com", password="app_password")
        service.connect()
        emails = service.get_unread_emails()
        service.apply_label(email_id, "Finance")
        service.mark_as_important(email_id)
        service.disconnect()
    """

    def __init__(self, email_address: str, password: str):
        self.email_address = email_address
        self.password      = password
        self.domain        = email_address.split("@")[-1].lower()

        provider = PROVIDER_MAP.get(self.domain)
        if provider:
            self.imap_host, self.imap_port, self.smtp_host, self.smtp_port = provider
        else:
            self.imap_host = f"imap.{self.domain}"
            self.imap_port = 993
            self.smtp_host = f"smtp.{self.domain}"
            self.smtp_port = 587

        self.imap: Optional[imaplib.IMAP4_SSL] = None
        self._label_cache: dict[str, bool] = {}

    # ── Connection ─────────────────────────────────────────────────────────────

    def connect(self) -> None:
        """Opens IMAP connection and logs in."""
        self.imap = imaplib.IMAP4_SSL(self.imap_host, self.imap_port)
        self.imap.login(self.email_address, self.password)
        print(f"  ✓ Authenticated with {self.domain}")

    def disconnect(self) -> None:
        """Closes IMAP connection cleanly."""
        if self.imap:
            try:
                self.imap.logout()
            except Exception:
                pass
            self.imap = None

    def test_connection(self) -> bool:
        """
        Tries to connect and immediately disconnects.
        Used by /api/auth/connect to validate credentials before running pipeline.
        Returns True if successful, raises exception otherwise.
        """
        try:
            self.connect()
            self.disconnect()
            return True
        except imaplib.IMAP4.error as e:
            raise ValueError(f"Authentication failed: {e}")
        except Exception as e:
            raise ValueError(f"Could not connect to {self.imap_host}: {e}")

    # ── Fetch ──────────────────────────────────────────────────────────────────

    def get_unread_emails(self, max_emails: int = 20) -> list[dict]:
        """
        Fetches unread emails from INBOX.
        Returns a list of parsed email dicts compatible with make_message().
        """
        if not self.imap:
            raise RuntimeError("Not connected. Call connect() first.")

        self.imap.select("INBOX")
        _, data = self.imap.search(None, "UNSEEN")

        email_ids = data[0].split()
        if not email_ids:
            return []

        email_ids = email_ids[-max_emails:][::-1]

        emails = []
        for eid in email_ids:
            _, msg_data = self.imap.fetch(eid, "(RFC822)")
            raw = msg_data[0][1]
            parsed = self._parse_email(raw, eid.decode())
            if parsed:
                emails.append(parsed)

        print(f"  ✓ Fetched {len(emails)} unread email(s)")
        return emails

    # ── Parse ──────────────────────────────────────────────────────────────────

    def _parse_email(self, raw: bytes, imap_id: str) -> Optional[dict]:
        """Parses a raw RFC822 email into a dict compatible with make_message()."""
        try:
            msg = email.message_from_bytes(raw)

            subject = self._decode_header(msg.get("Subject", "(No subject)"))
            sender  = self._decode_header(msg.get("From", "Unknown"))
            to      = self._decode_header(msg.get("To", ""))
            date    = msg.get("Date", "")
            body    = self._extract_body(msg)
            snippet = body[:100].replace("\n", " ").strip() if body else ""

            return {
                "id":        imap_id,
                "thread_id": msg.get("Message-ID", imap_id),
                "subject":   subject,
                "sender":    sender,
                "to":        to,
                "date":      date,
                "body":      body,
                "snippet":   snippet,
            }
        except Exception as e:
            print(f"  ✗ Failed to parse email {imap_id}: {e}")
            return None

    def _decode_header(self, value: str) -> str:
        """Decodes encoded email headers (e.g. =?utf-8?b?...?=)."""
        parts = decode_header(value)
        decoded = []
        for part, charset in parts:
            if isinstance(part, bytes):
                decoded.append(part.decode(charset or "utf-8", errors="replace"))
            else:
                decoded.append(part)
        return "".join(decoded)

    def _extract_body(self, msg) -> str:
        """Extracts plain text body from MIME email, falling back to HTML."""
        plain = None
        html  = None

        if msg.is_multipart():
            for part in msg.walk():
                ct = part.get_content_type()
                cd = str(part.get("Content-Disposition", ""))
                if "attachment" in cd:
                    continue
                if ct == "text/plain" and plain is None:
                    plain = self._decode_payload(part)
                elif ct == "text/html" and html is None:
                    html = self._decode_payload(part)
        else:
            ct = msg.get_content_type()
            if ct == "text/plain":
                plain = self._decode_payload(msg)
            elif ct == "text/html":
                html = self._decode_payload(msg)

        if plain:
            return plain.strip()
        if html:
            return self._strip_html(html).strip()
        return ""

    def _decode_payload(self, part) -> str:
        """Decodes email part payload to string."""
        payload = part.get_payload(decode=True)
        if not payload:
            return ""
        charset = part.get_content_charset() or "utf-8"
        return payload.decode(charset, errors="replace")

    def _strip_html(self, html: str) -> str:
        """Strips HTML tags to get readable plain text."""
        try:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html, "html.parser")
            for tag in soup(["script", "style", "head"]):
                tag.decompose()
            text = soup.get_text(separator=" ")
        except ImportError:
            text = re.sub(r"<[^>]+>", " ", html)

        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()

    # ── Actions ────────────────────────────────────────────────────────────────

    def mark_as_read(self, email_id: str) -> None:
        """Marks an email as read (removes \\Unseen flag)."""
        try:
            self.imap.select("INBOX")
            self.imap.store(email_id, "+FLAGS", "\\Seen")
        except Exception as e:
            print(f"  ✗ Could not mark as read: {e}")

    def mark_as_important(self, email_id: str) -> None:
        """Marks an email as flagged (IMAP equivalent of important)."""
        try:
            self.imap.select("INBOX")
            self.imap.store(email_id, "+FLAGS", "\\Flagged")
            print("  ★ Marked as important")
        except Exception as e:
            print(f"  ✗ Could not mark as important: {e}")

    def apply_label(self, email_id: str, label_name: str) -> None:
        """
        Creates an IMAP folder if it doesn't exist, then copies
        the email into it. Email remains in INBOX too.
        """
        if not label_name:
            return
        try:
            self._ensure_folder(label_name)
            self.imap.select("INBOX")
            self.imap.copy(email_id, label_name)
            print(f"  🏷  Applied label: {label_name}")
        except Exception as e:
            print(f"  ✗ Could not apply label '{label_name}': {e}")

    def move_to_folder(self, email_id: str, folder: str) -> None:
        """
        Moves an email to a folder (copy + delete from INBOX).
        Used for spam and promotional routing.
        """
        try:
            self._ensure_folder(folder)
            self.imap.select("INBOX")
            self.imap.copy(email_id, folder)
            self.imap.store(email_id, "+FLAGS", "\\Deleted")
            self.imap.expunge()
            print(f"  [{folder}] Email moved.")
        except Exception as e:
            print(f"  ✗ Could not move to '{folder}': {e}")

    def send_reply(self, original: dict, reply_text: str) -> bool:
        """Sends a reply via SMTP."""
        try:
            msg = MIMEMultipart()
            msg["From"]        = self.email_address
            msg["To"]          = original["sender"]
            msg["Subject"]     = f"Re: {original['subject']}"
            msg["In-Reply-To"] = original.get("thread_id", "")
            msg.attach(MIMEText(reply_text, "plain"))

            with smtplib.SMTP(self.smtp_host, self.smtp_port) as server:
                server.ehlo()
                server.starttls()
                server.login(self.email_address, self.password)
                server.sendmail(
                    self.email_address,
                    original["sender"],
                    msg.as_string()
                )
            print(f"  ✓ Reply sent to {original['sender']}")
            return True
        except Exception as e:
            print(f"  ✗ Failed to send reply: {e}")
            return False

    # ── Internal helpers ───────────────────────────────────────────────────────

    def _ensure_folder(self, folder_name: str) -> None:
        """
        Creates an IMAP folder if it doesn't already exist.
        Handles nested folders (e.g. Auto/Spam) by creating
        the parent folder first before the child.

        Uses LIST to check existence instead of SELECT —
        SELECT on a non-existent folder behaves unpredictably
        across providers (Zoho, Gmail, Outlook all differ).
        """
        if folder_name in self._label_cache:
            return

        try:
            # ── Step 1: Create parent folder first if nested ───────
            # e.g. "Auto/Spam" → create "Auto" first
            if "/" in folder_name:
                parent = folder_name.rsplit("/", 1)[0]
                if parent not in self._label_cache:
                    try:
                        self.imap.create(parent)
                        print(f"  ✓ Created parent folder: {parent}")
                    except Exception:
                        # Parent already exists — that's fine
                        pass
                    self._label_cache[parent] = True

            # ── Step 2: Check if folder exists using LIST ──────────
            # LIST is more reliable than SELECT for existence check
            status, folders = self.imap.list('""', folder_name)

            folder_exists = False
            if status == "OK" and folders and folders[0] is not None:
                folder_str = str(folders[0]).lower()
                if folder_name.lower() in folder_str:
                    folder_exists = True

            # ── Step 3: Create folder if it doesn't exist ──────────
            if not folder_exists:
                create_status, _ = self.imap.create(folder_name)
                if create_status == "OK":
                    print(f"  ✓ Created folder: {folder_name}")
                else:
                    print(f"  ✗ Failed to create folder: {folder_name}")

            self._label_cache[folder_name] = True

            # Go back to INBOX after folder operations
            self.imap.select("INBOX")

        except Exception as e:
            print(f"  ✗ Could not ensure folder '{folder_name}': {e}")