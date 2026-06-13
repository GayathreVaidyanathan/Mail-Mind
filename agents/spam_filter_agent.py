"""
agents/spam_filter_agent.py

Agent 1.5 — Spam Filter Agent
───────────────────────────────
Runs immediately after PreFilterAgent and before ClassifierAgent.
Owns Tier 2 spam detection entirely.

Responsible for:
  - Crowdfunding / donation domain detection
  - Emotional manipulation language in subject
  - Guilt-trip / crowdfunding signals in body

If spam is detected:
  - Sets msg["category"] = "spam"
  - Sets msg["status"]   = "labeled_spam"
  - Returns early — ClassifierAgent is skipped entirely for this email

If no spam signal is found:
  - Returns msg unchanged — ClassifierAgent takes over

Why a separate agent?
  ClassifierAgent's job is to distinguish between legitimate email
  categories (personal, transactional, promotional, academic).
  Spam is a fundamentally different problem — it's about detecting
  malicious or manipulative intent, not categorising content.
  Keeping it separate means:
    - ClassifierAgent never sees confirmed spam — cleaner logic
    - Spam rules can be tuned independently without touching
      the main classification pipeline
    - SpamFilterAgent can be disabled or swapped out without
      affecting the rest of the system

Action:
  Spam emails are moved to a dedicated Gmail label "Auto/Spam"
  rather than deleted. This means:
    - Nothing is permanently lost
    - User can review and recover false positives
    - Label is applied by InboxAgent.act() when it reads
      msg["status"] == "labeled_spam"

Design note:
  This agent never calls AI. All spam detection is rule-based
  and deterministic. Speed is important here since it runs
  before the main pipeline on every email.
"""

from core.message_bus import EmailMessage
from core.signals import (
    SPAM_SENDER_DOMAINS,
    SPAM_SUBJECT_KEYWORDS,
    SPAM_BODY_SIGNALS,
)


class SpamFilterAgent:
    """
    Detects spam emails using rule-based signals before ClassifierAgent runs.

    Checks in order:
      1. Sender domain   — crowdfunding/donation platforms
      2. Subject keywords — emotional manipulation, phishing
      3. Body signals    — guilt-trip language, crowdfunding appeals

    Usage:
        agent = SpamFilterAgent()
        msg = agent.run(msg)
        # if msg["category"] == "spam" → skip ClassifierAgent
        # else → pass to ClassifierAgent as normal
    """

    def __init__(self):
        self.name = "SpamFilterAgent"

    def run(self, msg: EmailMessage) -> EmailMessage:
        """
        Checks the email for spam signals.

        Returns:
            msg with category="spam" and status="labeled_spam" if detected,
            or msg unchanged if no spam signal found.
        """
        sender     = msg.get("sender", "").lower()
        subject    = msg.get("subject", "").lower()
        body_short = msg.get("body", "")[:1000].lower()

        reason = self._detect(sender, subject, body_short)

        if reason:
            msg["category"] = "spam"
            msg["status"]   = "labeled_spam"
            print(f"  [{self.name}] 🚫 Spam detected ({reason})")
            return msg

        # No spam signal — pass through unchanged
        return msg

    # ── Detection logic ────────────────────────────────────────────────────────

    def _detect(self, sender: str, subject: str, body: str) -> str:
        """
        Runs all spam checks in priority order.

        Returns:
            A short reason string if spam is detected (used for logging),
            or "" if no spam signal found.
        """
        # ── Check 1: Sender domain ─────────────────────────────────────────
        for domain in SPAM_SENDER_DOMAINS:
            if domain in sender:
                return f"sender domain: {domain}"

        # ── Check 2: Subject keywords ──────────────────────────────────────
        for keyword in SPAM_SUBJECT_KEYWORDS:
            if keyword in subject:
                return f"subject keyword: '{keyword}'"

        # ── Check 3: Body signals ──────────────────────────────────────────
        for signal in SPAM_BODY_SIGNALS:
            if signal in body:
                return f"body signal: '{signal}'"

        return ""