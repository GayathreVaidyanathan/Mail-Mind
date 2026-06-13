"""
core/message_bus.py

The shared data contract — every agent reads and writes EmailMessage dicts.
No agent imports from another agent directly; they all speak this format.

EmailMessage is a TypedDict so VS Code gives you autocomplete and type hints.

Field lifecycle:
  InboxAgent.fetch()       → fills: id, thread_id, sender, to, subject, date, body, snippet
  ClassifierAgent.run()    → fills: category
  LabelerAgent.run()       → fills: platform_label, topic_label, label
  ComposerAgent.run()      → fills: draft, final_reply, status (sent/skipped/quit)
  DigestAgent.run()        → fills: summary, status (summarized/deleted)
  InboxAgent.act()         → reads: status, final_reply → performs Gmail action
  InboxAgent.apply_label() → reads: label → applies Gmail label (called twice —
                             once for platform_label, once for topic_label)
"""

from typing import TypedDict


class EmailMessage(TypedDict, total=False):
    # ── Set by InboxAgent.fetch() ──────────────────────────────────────────────
    id:             str        # Gmail message ID
    thread_id:      str        # Gmail thread ID (for threading replies)
    sender:         str        # "Name <email@domain.com>"
    to:             str        # recipient address
    subject:        str
    date:           str
    body:           str        # plain text body
    snippet:        str        # Gmail's auto-generated preview

    # ── Set by ClassifierAgent ─────────────────────────────────────────────────
    category:       str        # personal_work | academic_info | account_notification
                               # | promotional | spam

    # ── Set by LabelerAgent (two independent labels) ───────────────────────────
    platform_label: str        # WHERE it came from — rule-based domain detection
                               # e.g. "Swiggy", "Reddit", "GitHub", "" if unknown
    topic_label:    str        # WHAT it's about — AI-assigned topic
                               # e.g. "Finance", "Coding", "PhD Stuff", "" if none
    label:          str        # legacy field — set to topic_label for backward compat
                               # InboxAgent.apply_label() reads this field

    # ── Set by ComposerAgent ───────────────────────────────────────────────────
    draft:          str        # AI-generated draft (before human edits)
    final_reply:    str        # what actually gets sent (may differ from draft)

    # ── Set by DigestAgent ─────────────────────────────────────────────────────
    summary:        str        # structured summary text

    # ── Set by any agent, read by InboxAgent.act() ────────────────────────────
    status:         str        # pending | sent | summarized | spammed
                               # | deleted | skipped | quit


# ── Factory ───────────────────────────────────────────────────────────────────

def make_message(raw: dict) -> EmailMessage:
    """
    Wraps a raw Gmail API email dict into a typed EmailMessage.
    Sets all agent-filled fields to safe defaults so no agent
    ever gets a KeyError on an unset field.

    Args:
        raw: dict from gmail_client._parse_email()

    Returns:
        EmailMessage ready to pass through the agent pipeline
    """
    return EmailMessage(
        # From Gmail API
        id=raw.get("id", ""),
        thread_id=raw.get("thread_id", ""),
        sender=raw.get("sender", ""),
        to=raw.get("to", ""),
        subject=raw.get("subject", "(No subject)"),
        date=raw.get("date", ""),
        body=raw.get("body", ""),
        snippet=raw.get("snippet", ""),

        # Agent-filled defaults
        category="",
        platform_label="",
        topic_label="",
        label="",
        draft="",
        final_reply="",
        summary="",
        status="pending",
    )


def is_valid(msg: EmailMessage) -> bool:
    """
    Basic sanity check — every message needs at minimum an id and a sender.
    Malformed messages from the API get dropped before entering the pipeline.
    """
    return bool(msg.get("id")) and bool(msg.get("sender"))