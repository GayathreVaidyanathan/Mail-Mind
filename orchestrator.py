"""
orchestrator.py

The brain of the multi-agent system.
Owns the pipeline and routes each EmailMessage through the right agents.

Pipeline for each email:
  1. InboxAgent         → fetch emails, wrap into EmailMessage objects
  2. PreFilterAgent     → deduplicate, clean body, detect forwards
  3. ValidatorAgent     → validate sender legitimacy
  4. SpamFilterAgent    → detect and route confirmed spam
  5. ClassifierAgent    → classify into category
  6. LabelerAgent       → assign platform_label + topic_label
  7. Route by category:
       personal_work        → ComposerAgent     → InboxAgent.act()
       academic_info        → DigestAgent       → InboxAgent.act()
       account_notification → DigestAgent       → InboxAgent.act()
       promotional          → InboxAgent.act()  (Auto/Promotional label)
       spam                 → InboxAgent.act()  (Auto/Spam label)
  8. InboxAgent.apply_label() × 2 — platform label + topic label

The Orchestrator is the ONLY place that imports all agents.
Agents never import each other — they only read/write EmailMessage dicts.

Changes from v1:
  - Removed time_filter and scheduler logic
  - InboxAgent is injected via __init__ instead of created internally
  - run() is now a generator that yields status dicts for SSE streaming
  - print() calls replaced with yield events for frontend consumption
"""

import time
from typing import Generator

from agents.inbox_agent import InboxAgent
from agents.pre_filter_agent import PreFilterAgent
from agents.validator_agent import ValidatorAgent
from agents.spam_filter_agent import SpamFilterAgent
from agents.classifier_agent import ClassifierAgent
from agents.labeler_agent import LabelerAgent
from agents.composer_agent import ComposerAgent
from agents.digest_agent import DigestAgent

from core.message_bus import EmailMessage


CATEGORY_ICONS = {
    "personal_work":        "👤 Personal/Work",
    "academic_info":        "📚 Academic/Info",
    "account_notification": "🔔 Account Notification",
    "promotional":          "📢 Promotional",
    "spam":                 "🚫 Spam",
}


class Orchestrator:
    """
    Coordinates all agents in the correct order for each email.

    InboxAgent is injected at construction time — it carries the
    active IMAP connection created by the pipeline router after
    the user authenticates via the UI.

    All other agents are instantiated once at startup and reused
    across all emails in a run. This avoids re-creating Ollama
    clients repeatedly.

    run() is a generator — yields event dicts that FastAPI streams
    to the frontend via SSE. Each yield is one UI update.

    Event types yielded:
        {"event": "log",         "message": str}
        {"event": "start",       "total": int}
        {"event": "email_start", "index": int, "total": int,
                                 "sender": str, "subject": str}
        {"event": "email_done",  "index": int, "total": int,
                                 "msg": dict, "category": str,
                                 "category_label": str}
        {"event": "done",        "counts": dict, "total": int}
        {"event": "error",       "detail": str}

    Usage:
        inbox_agent  = InboxAgent(imap_service=service)
        orchestrator = Orchestrator(inbox_agent=inbox_agent)
        for event in orchestrator.run():
            print(event)
    """

    def __init__(self, inbox_agent: InboxAgent):
        # ── InboxAgent injected from outside ───────────────────────
        # Created by pipeline router with the active IMAP service
        self.inbox = inbox_agent

        # ── All other agents instantiated once ────────────────────
        self.pre_filter  = PreFilterAgent()
        self.validator   = ValidatorAgent()
        self.spam_filter = SpamFilterAgent()
        self.classifier  = ClassifierAgent()
        self.labeler     = LabelerAgent()
        self.composer    = ComposerAgent()
        self.digest      = DigestAgent()

    def run(self) -> Generator[dict, None, None]:
        """
        Main entry point — runs the full pipeline for all unread emails.
        Yields status dicts for SSE streaming to the frontend.
        """

        try:
            # ── Step 1: Connect and fetch ──────────────────────────
            yield {"event": "log", "message": "Connecting to inbox..."}
            self.inbox.connect()
            yield {"event": "log", "message": "Authenticated successfully."}

            messages = self.inbox.fetch()

            if not messages:
                yield {"event": "done", "counts": {}, "total": 0}
                return

            # ── Step 2: Pre-filter ─────────────────────────────────
            messages = self.pre_filter.run(messages)

            if not messages:
                yield {"event": "done", "counts": {}, "total": 0}
                return

            total = len(messages)
            yield {"event": "start", "total": total}

            counts = {k: 0 for k in CATEGORY_ICONS}

            # ── Step 3: Process each email ─────────────────────────
            for index, msg in enumerate(messages, start=1):

                yield {
                    "event":   "email_start",
                    "index":   index,
                    "total":   total,
                    "sender":  msg["sender"],
                    "subject": msg["subject"],
                }

                # ── 3a. Validate sender ────────────────────────────
                msg = self.validator.run(msg)

                if msg.get("invalid_sender"):
                    msg["category"] = "spam"
                    msg["status"]   = "invalid_sender"
                    counts["spam"] += 1
                    self._apply_both_labels(msg)
                    self.inbox.act(msg)

                    yield {
                        "event":          "email_done",
                        "index":          index,
                        "total":          total,
                        "msg":            self._serialise(msg),
                        "category":       "spam",
                        "category_label": CATEGORY_ICONS["spam"],
                    }
                    continue

                # ── 3b. Spam filter ────────────────────────────────
                msg = self.spam_filter.run(msg)

                # ── 3c. Classifier ─────────────────────────────────
                if msg.get("category") != "spam":
                    msg = self.classifier.run(msg)

                category = msg["category"]
                counts[category] = counts.get(category, 0) + 1

                # ── 3d. Labeler ────────────────────────────────────
                if category != "spam":
                    msg = self.labeler.run(msg)
                # ── 3e. Route to proper agent ──────────────────────
                if category == "personal_work":
                    msg = self.composer.run(msg, index, total)

                elif category in ("academic_info", "account_notification"):
                    msg = self.digest.run(msg)

                elif category == "promotional":
                    msg["status"] = "labeled_promotional"

                elif category == "spam":
                    msg["status"] = "labeled_spam"

                # ── 3f. Apply labels ───────────────────────────────
                self._apply_both_labels(msg)

                # ── 3g. Final action ───────────────────────────────
                self.inbox.act(msg)

                yield {
                    "event":          "email_done",
                    "index":          index,
                    "total":          total,
                    "msg":            self._serialise(msg),
                    "category":       category,
                    "category_label": CATEGORY_ICONS.get(category, category),
                }

                time.sleep(0.3)

            # ── Step 4: Done ───────────────────────────────────────
            yield {
                "event":  "done",
                "counts": counts,
                "total":  total,
            }

        except Exception as e:
            yield {"event": "error", "detail": str(e)}

    # ── Internal helpers ───────────────────────────────────────────────────────

    def _apply_both_labels(self, msg: EmailMessage) -> None:
        """Applies platform and topic labels independently."""
        if msg.get("platform_label"):
            msg["label"] = msg["platform_label"]
            self.inbox.apply_label(msg)

        if msg.get("topic_label"):
            msg["label"] = msg["topic_label"]
            self.inbox.apply_label(msg)

    def _serialise(self, msg: EmailMessage) -> dict:
        """
        Strips non-serialisable fields and returns a plain dict
        safe to JSON-encode for SSE.
        """
        return {
            "id":             msg.get("id", ""),
            "sender":         msg.get("sender", ""),
            "subject":        msg.get("subject", ""),
            "date":           msg.get("date", ""),
            "category":       msg.get("category", ""),
            "platform_label": msg.get("platform_label", ""),
            "topic_label":    msg.get("topic_label", ""),
            "summary":        msg.get("summary", ""),
            "status":         msg.get("status", ""),
            "trust_score":    msg.get("trust_score", 0),
            "trust_level":    msg.get("trust_level", ""),
            "draft":          msg.get("draft", ""),
        }