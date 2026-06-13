"""
agents/inbox_agent.py

Agent 1 — Inbox Agent
─────────────────────
The ONLY agent that touches the email service directly.
All other agents work purely on EmailMessage dicts.

Responsibilities:
  - Connect to any email provider via IMAP
  - Fetch unread emails and wrap them into EmailMessage objects
  - Send replies via SMTP
  - Apply labels (as IMAP folders), mark as read/important

Status → Action mapping:
  "sent"                → send final_reply, mark as read
  "summarized"          → mark as important (flagged in IMAP)
  "labeled_spam"        → move to Auto/Spam folder, mark as read
  "labeled_promotional" → move to Auto/Promotional folder, mark as read
  "skipped"             → mark as read (if MARK_AS_READ is True)
  "invalid_sender"      → move to Auto/Spam folder, mark as read

Why folders instead of labels?
  Gmail has labels; IMAP has folders. The behavior is equivalent —
  emails are copied into named folders for organization. Nothing is
  permanently deleted. Everything is recoverable.

    Auto/Spam        — confirmed spam + invalid senders
    Auto/Promotional — marketing, digests, job alerts

Why is IMAPService injected instead of created here?
  The UI collects credentials (email + app password) before the pipeline
  runs. FastAPI creates the IMAPService with those credentials and passes
  it into InboxAgent. This way InboxAgent doesn't need to know where
  credentials come from — it just uses whatever service it's given.

All other agents call methods here via the Orchestrator —
they never import imap_service directly.

Changes from v1:
  - Replaced gmail_client (Google OAuth) with IMAPService (IMAP/SMTP)
  - IMAPService instance injected via __init__ (not created internally)
  - apply_label uses IMAP folder copy instead of Gmail label API
  - spam/promotional routing uses move_to_folder instead of Gmail modify
  - invalid_sender status now explicitly handled
  - Provider-agnostic — works with Gmail, Outlook, Yahoo, iCloud, etc.
"""

from services.imap_service import IMAPService
from core.message_bus import EmailMessage, make_message, is_valid
from config import MARK_AS_READ


# IMAP folder names for routed emails
# These mirror the Gmail label names from v1 for consistency
FOLDER_SPAM        = "Auto/Junk"
FOLDER_PROMOTIONAL = "Auto/Promotional"


class InboxAgent:
    """
    Owns the IMAP service object and all email operations.

    Receives an IMAPService instance at construction time — this is
    created by FastAPI after the user submits their credentials in the UI.
    The agent itself is stateless beyond holding the service reference.

    Usage:
        service = IMAPService(email="you@gmail.com", password="app_pass")
        agent   = InboxAgent(imap_service=service)
        agent.connect()                  # opens IMAP connection
        messages = agent.fetch()         # returns list[EmailMessage]
        agent.apply_label(msg)           # after LabelerAgent sets msg["label"]
        agent.act(msg)                   # after Orchestrator fills msg["status"]
    """

    def __init__(self, imap_service: IMAPService):
        self.service = imap_service
        self.name    = "InboxAgent"

    # ── Lifecycle ──────────────────────────────────────────────────────────────

    def connect(self) -> None:
        """
        Opens IMAP connection and authenticates.
        Must be called once before fetch() or act().

        Delegates to IMAPService.connect() which handles
        provider-specific IMAP host/port selection automatically.
        """
        print(f"  [{self.name}] Connecting to inbox...")
        self.service.connect()
        print(f"  [{self.name}] Ready.")

    # ── Fetch ──────────────────────────────────────────────────────────────────

    def fetch(self) -> list[EmailMessage]:
        """
        Fetches all unread emails from INBOX and wraps each into
        an EmailMessage dict ready for the pipeline.

        Malformed emails (missing id or sender) are silently skipped
        rather than crashing the pipeline.

        Returns:
            List of EmailMessage dicts with status="pending",
            ordered most-recent first.
        """
        print(f"  [{self.name}] Fetching unread emails...")
        raw_emails = self.service.get_unread_emails()

        if not raw_emails:
            print(f"  [{self.name}] No unread emails found.")
            return []

        messages = []
        for raw in raw_emails:
            msg = make_message(raw)
            if is_valid(msg):
                messages.append(msg)
            else:
                print(f"  [{self.name}] Skipping malformed email: {raw.get('id', '?')}")

        print(f"  ✓ Fetched {len(messages)} unread email(s)")
        return messages

    # ── Label ──────────────────────────────────────────────────────────────────

    def apply_label(self, msg: EmailMessage) -> None:
        """
        Copies the email into an IMAP folder matching msg["label"].

        Called by the Orchestrator twice per email —
        once for platform_label, once for topic_label.
        Does nothing if label is empty.

        IMAP note: the email is COPIED into the folder, not moved.
        It remains in INBOX so the user still sees it there.
        The folder acts as an additional tag/category.

        Args:
            msg: EmailMessage with label set by LabelerAgent
        """
        label = msg.get("label", "")
        if not label:
            return

        self.service.apply_label(msg["id"], label)

    # ── Act ────────────────────────────────────────────────────────────────────

    def act(self, msg: EmailMessage) -> None:
        """
        Performs the final email action based on msg["status"].

        Called by the Orchestrator after ALL other agents have
        processed the message and set its final status.

        Status → Action mapping:
            "sent"                → send final_reply via SMTP, mark as read
            "summarized"          → flag as important (IMAP \\Flagged)
            "labeled_spam"        → move to Spam, mark as read
            "labeled_promotional" → move to Auto/Promotional, mark as read
            "invalid_sender"      → move to Auto/Spam, mark as read
            "skipped"             → mark as read (if MARK_AS_READ is True)
            anything else         → log and take no action

        Args:
            msg: fully processed EmailMessage with status set
        """
        status   = msg.get("status", "pending")
        email_id = msg["id"]

        if status == "sent":
            self._send(msg)

        elif status == "summarized":
            self.service.mark_as_important(email_id)
            print(f"  [{self.name}] Marked as Important.")

        elif status == "labeled_spam":
            self.service.move_to_folder(email_id, FOLDER_SPAM)
            self.service.mark_as_read(email_id)
            print(f"  [{self.name}] → Labeled: {FOLDER_SPAM}")

        elif status == "labeled_promotional":
            self.service.move_to_folder(email_id, FOLDER_PROMOTIONAL)
            self.service.mark_as_read(email_id)
            print(f"  [{self.name}] → Labeled: {FOLDER_PROMOTIONAL}")

        elif status == "invalid_sender":
            # Treat invalid senders same as spam — move and mark read
            self.service.move_to_folder(email_id, FOLDER_SPAM)
            self.service.mark_as_read(email_id)
            print(f"  [{self.name}] → Invalid sender, moved to {FOLDER_SPAM}")

        elif status == "skipped":
            if MARK_AS_READ:
                self.service.mark_as_read(email_id)
            print(f"  [{self.name}] Skipped.")

        else:
            print(f"  [{self.name}] Unknown status '{status}' — no action taken.")

    # ── Internal helpers ───────────────────────────────────────────────────────

    def _send(self, msg: EmailMessage) -> None:
        """
        Sends msg["final_reply"] as a reply to the original email
        via SMTP, then marks the original as read.

        Skips silently if final_reply is empty — this can happen
        when ComposerAgent couldn't generate a reply.

        Args:
            msg: EmailMessage with final_reply set by ComposerAgent
        """
        reply_text = msg.get("final_reply", "").strip()
        if not reply_text:
            print(f"  [{self.name}] No final_reply found — skipping send.")
            return

        success = self.service.send_reply(msg, reply_text)

        if success and MARK_AS_READ:
            self.service.mark_as_read(msg["id"])