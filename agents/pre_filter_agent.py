"""
agents/pre_filter_agent.py

Agent 0 — Pre-Filter Agent
───────────────────────────
Runs before every other agent. Responsible for three things:

  1. Deduplication
     Detects emails with identical (sender, subject, date) and marks
     them as duplicates so the orchestrator can skip them.
     Uses MD5 hash for fast comparison across the full batch.

  2. Forward detection
     Identifies forwarded emails (Fwd:/Fw: prefix) and attempts to
     extract the original sender from the body. If the original sender
     is a real person on a personal domain, upgrades the forward to
     personal_work so ClassifierAgent doesn't have to guess.

  3. Body cleaning
     Strips quoted reply threads, forward headers, and excessive
     whitespace from msg["body"] before any other agent reads it.
     This improves classification and summarisation quality since
     agents see only the relevant content, not a wall of quoted text.

Sets the following fields on EmailMessage:
  msg["duplicate"]         → True if this email is a duplicate
  msg["forwarded"]         → True if this is a forwarded email
  msg["original_sender"]   → extracted original sender string (or "")
  msg["pre_category"]      → "personal_work" if forward from real person,
                             else "" (ClassifierAgent decides)
  msg["body"]              → cleaned body text

The Orchestrator checks msg["duplicate"] and skips the pipeline entirely
for duplicates. It checks msg["pre_category"] and passes it to
ClassifierAgent as a hint.

Design note:
  This agent never calls AI. It is purely deterministic and must be
  fast — it runs on every single email before anything else.
"""

import hashlib
import re
from core.message_bus import EmailMessage
from core.signals import PERSONAL_SENDER_DOMAINS, AUTOMATED_SENDER_FRAGMENTS


class PreFilterAgent:
    """
    Runs before ClassifierAgent on every email.
    Handles deduplication, forward detection, and body cleaning.

    Usage:
        agent = PreFilterAgent()
        messages = agent.run(messages)   # takes full batch, returns cleaned batch
    """

    def __init__(self):
        self.name = "PreFilterAgent"
        self._seen: set[str] = set()

    def run(self, messages: list[EmailMessage]) -> list[EmailMessage]:
        """
        Processes the full batch of fetched emails.
        Returns the cleaned, deduplicated list.

        Args:
            messages: Raw EmailMessage list from InboxAgent.fetch()

        Returns:
            Filtered and cleaned list ready for the main pipeline
        """
        self._seen.clear()
        results = []
        skipped = 0

        for msg in messages:
            # ── Step 1: Deduplication ─────────────────────────────────────
            if self._is_duplicate(msg):
                skipped += 1
                print(
                    f"  [{self.name}] ⚠  Duplicate skipped: "
                    f"'{msg['subject'][:50]}' from {msg['sender']}"
                )
                continue

            # ── Step 2: Body cleaning ─────────────────────────────────────
            msg["body"] = self._clean_body(msg.get("body", ""))

            # ── Step 3: Forward detection ─────────────────────────────────
            msg = self._detect_forward(msg)

            results.append(msg)

        if skipped:
            print(f"  [{self.name}] ✓ Removed {skipped} duplicate(s).")

        print(f"  [{self.name}] ✓ {len(results)} email(s) passed pre-filter.")
        return results

    # ── Deduplication ──────────────────────────────────────────────────────────

    def _is_duplicate(self, msg: EmailMessage) -> bool:
        """
        Returns True if an email with the same (sender, subject, date)
        has already been seen in this batch.
        Uses MD5 for speed — not for security.
        """
        key = self._make_hash(msg)
        if key in self._seen:
            return True
        self._seen.add(key)
        return False

    def _make_hash(self, msg: EmailMessage) -> str:
        """Builds a stable MD5 hash from (sender, subject, date)."""
        raw = "|".join([
            msg.get("sender", "").strip().lower(),
            msg.get("subject", "").strip().lower(),
            msg.get("date", "").strip(),
        ])
        return hashlib.md5(raw.encode()).hexdigest()

    # ── Body cleaning ──────────────────────────────────────────────────────────

    def _clean_body(self, body: str) -> str:
        """
        Removes quoted reply threads and forward headers from email body.
        Agents downstream see only the top-level content.

        Handles:
          - Gmail-style "On <date>, <name> wrote:" quoted blocks
          - Outlook-style "-----Original Message-----" blocks
          - Forwarded message header blocks
          - Lines starting with ">" (quoted text marker)
          - Excessive blank lines
        """
        if not body:
            return body

        lines = body.splitlines()
        cleaned = []
        skip_rest = False

        for line in lines:
            stripped = line.strip()

            # Stop at common quoted/forwarded block markers
            if self._is_quote_marker(stripped):
                skip_rest = True

            if skip_rest:
                continue

            # Skip individual quoted lines ("> quoted text")
            if stripped.startswith(">"):
                continue

            cleaned.append(line)

        # Collapse runs of more than 2 blank lines into 2
        result = re.sub(r"\n{3,}", "\n\n", "\n".join(cleaned))
        return result.strip()

    def _is_quote_marker(self, line: str) -> bool:
        """
        Returns True if the line marks the start of a quoted/forwarded block.
        Covers Gmail, Outlook, Apple Mail, and common forward headers.
        """
        line_lower = line.lower()

        # Gmail / Apple Mail: "On Mon, 6 Apr 2026, Name wrote:"
        if re.match(r"on .{5,50} wrote:$", line_lower):
            return True

        # Outlook separator
        if "-----original message-----" in line_lower:
            return True

        # Forward header block
        if re.match(r"-+\s*forwarded message\s*-+", line_lower):
            return True

        # Generic dashed separator often used before quoted content
        if re.match(r"^-{5,}$", line):
            return True

        # "From:", "Sent:", "To:", "Subject:" in sequence (Outlook forward headers)
        if re.match(r"^(from|sent|to|subject)\s*:", line_lower):
            return True

        return False

    # ── Forward detection ──────────────────────────────────────────────────────

    def _detect_forward(self, msg: EmailMessage) -> EmailMessage:
        """
        Detects forwarded emails and attempts to extract the original sender.

        Sets:
          msg["forwarded"]       → True / False
          msg["original_sender"] → extracted sender string or ""
          msg["pre_category"]    → "personal_work" if original sender is a
                                   real person, else ""
        """
        subject = msg.get("subject", "").lower()
        is_forward = subject.startswith("fwd:") or subject.startswith("fw:")

        msg["forwarded"] = is_forward
        msg["original_sender"] = ""
        msg["pre_category"] = ""

        if not is_forward:
            return msg

        # Try to extract the original sender from the body
        original = self._extract_original_sender(msg.get("body", ""))
        msg["original_sender"] = original or ""

        if original and self._is_personal_sender(original):
            msg["pre_category"] = "personal_work"
            print(
                f"  [{self.name}] 📨 Forward from personal sender detected: "
                f"{original[:60]}"
            )
        else:
            print(
                f"  [{self.name}] 📨 Forward detected — original sender unclear, "
                f"passing to ClassifierAgent."
            )

        return msg

    def _extract_original_sender(self, body: str) -> str | None:
        """
        Extracts the original sender from a forwarded email body.
        Looks for common forwarding header patterns.

        Pattern 1: From: Display Name <email@domain.com>
        Pattern 2: From: email@domain.com  (no display name)

        Returns the raw sender string or None if not found.
        """
        # Pattern 1: "From: Display Name <email>"
        match = re.search(
            r"(?:from|von|de)\s*:\s*([^<\n]+<[^>\n]+>)",
            body,
            re.IGNORECASE
        )
        if match:
            return match.group(1).strip()

        # Pattern 2: "From: email@domain.com"
        match = re.search(
            r"(?:from|von|de)\s*:\s*([\w.+-]+@[\w.-]+\.\w+)",
            body,
            re.IGNORECASE
        )
        if match:
            return match.group(1).strip()

        return None

    def _is_personal_sender(self, sender: str) -> bool:
        """
        Returns True if the sender looks like a real person on a personal
        email domain (not an automated/platform address).

        Checks:
          - Display name has at least two words (First Last)
          - Domain is in PERSONAL_SENDER_DOMAINS
          - Address is not an automated/role address
        """
        sender = sender.lower()

        # Must not be an automated address
        if any(frag in sender for frag in AUTOMATED_SENDER_FRAGMENTS):
            return False

        # Extract display name
        name_match = re.match(r'^"?([^"<]+)"?\s*<', sender)
        display_name = name_match.group(1).strip() if name_match else ""

        # Must have at least two words in display name
        if len(display_name.split()) < 2:
            return False

        # Domain must be a personal provider
        domain_match = re.search(r"@([\w.-]+)>?$", sender)
        if not domain_match:
            return False
        domain = domain_match.group(1)

        return any(pd in domain for pd in PERSONAL_SENDER_DOMAINS)