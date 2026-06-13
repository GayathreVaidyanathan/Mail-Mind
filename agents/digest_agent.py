"""
agents/digest_agent.py

Agent 4 — Digest Agent
───────────────────────
Handles academic_info and account_notification emails.
  1. Summarizes the email using Ollama (local LLaMA 3.2)
  2. Stores the summary in msg["summary"]
  3. Sets msg["status"] = "summarized"

Two summarization modes based on category:

  account_notification
    → Transactional mode
    → Short, factual, extracts key numbers and IDs
    → e.g. order amount, delivery time, order ID, savings
    → No fluff — just the facts the user needs at a glance

  academic_info
    → Informational mode
    → Richer summary with topic, key arguments, and action items
    → Suitable for newsletters, advocacy emails, course updates
    → Preserves nuance and context

Why two modes?
  A Swiggy order confirmation and an IOC policy newsletter are
  fundamentally different kinds of content. The same summarization
  prompt applied to both produces either too sparse or too verbose
  output. Separate prompts let each mode be tuned independently.

The Orchestrator reads msg["status"] == "summarized" and delegates
the actual Gmail action to InboxAgent.act().
"""

from openai import OpenAI
from config import OLLAMA_BASE_URL, OLLAMA_MODEL
from core.message_bus import EmailMessage


# ══════════════════════════════════════════════════════════════════════════════
# PROMPTS
# ══════════════════════════════════════════════════════════════════════════════

TRANSACTIONAL_SYSTEM_PROMPT = """You are an assistant that summarizes transactional emails.
These are order confirmations, delivery updates, payment receipts,
security alerts, and similar automated notifications.

Format your summary exactly like this:

Topic: <one-line description>

Key Points:
  - <fact 1 — include numbers, amounts, IDs where present>
  - <fact 2>
  - <fact 3 if needed>

Action Required: <any link to click, deadline, or thing to do — or "None">

Rules:
  - Be extremely concise — one short line per bullet
  - Always extract: order ID, amount paid, savings, delivery time if present
  - Skip marketing language, greetings, footers
  - No filler phrases like "The email confirms that..."
  - If it's a security alert, highlight what happened and what to do"""


INFORMATIONAL_SYSTEM_PROMPT = """You are an assistant that summarizes informational and academic emails.
These are newsletters, research updates, advocacy emails, course announcements,
and similar content-rich communications.

Format your summary exactly like this:

Topic: <one-line description of the main subject>

Key Points:
  - <key argument, finding, or update — 1-2 sentences>
  - <second point if present>
  - <third point if present>

Action Required: <any deadlines, links to click, or things to do — or "None">

Rules:
  - Preserve the nuance and context of the original
  - Highlight the most important argument or finding first
  - If the email covers multiple topics, summarise the most significant one
  - Use plain language — no jargon unless necessary
  - No filler phrases"""


# ══════════════════════════════════════════════════════════════════════════════
# DIGEST AGENT
# ══════════════════════════════════════════════════════════════════════════════

class DigestAgent:
    """
    Summarizes academic/informational and account notification emails.
    Uses Ollama (local LLaMA 3.2).

    Picks summarization mode based on msg["category"]:
      account_notification → TRANSACTIONAL_SYSTEM_PROMPT (concise, factual)
      academic_info        → INFORMATIONAL_SYSTEM_PROMPT (richer, contextual)

    Usage:
        agent = DigestAgent()
        msg = agent.run(msg)
        # msg["summary"] is now set
        # msg["status"] == "summarized"
    """

    def __init__(self):
        self.client = OpenAI(base_url=OLLAMA_BASE_URL, api_key="ollama")
        self.model = OLLAMA_MODEL
        self.name = "DigestAgent"

    def run(self, msg: EmailMessage) -> EmailMessage:
        """
        Summarizes the email using the appropriate mode and sets
        status to "summarized".
        """
        category = msg.get("category", "account_notification")
        mode = "transactional" if category == "account_notification" else "informational"

        print(f"  [{self.name}] Summarizing ({mode}): '{msg['subject'][:50]}'...")

        summary = self._summarize(msg, mode)
        msg["summary"] = summary
        msg["status"]  = "summarized"

        self._display_summary(msg)
        print(f"  [{self.name}] Done. Status → summarized.")
        return msg

    # ── Summarization ──────────────────────────────────────────────────────────

    def _summarize(self, msg: EmailMessage, mode: str) -> str:
        """
        Calls Ollama with the appropriate system prompt for the mode.

        Args:
            msg:  The EmailMessage to summarize
            mode: "transactional" or "informational"
        """
        system_prompt = (
            TRANSACTIONAL_SYSTEM_PROMPT
            if mode == "transactional"
            else INFORMATIONAL_SYSTEM_PROMPT
        )

        user_prompt = f"""Summarize this email:

From: {msg['sender']}
Subject: {msg['subject']}
Date: {msg['date']}

Email body:
{msg['body'][:3000]}"""

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user",   "content": user_prompt},
                ],
                temperature=0.3,
                max_tokens=400,
            )
            return response.choices[0].message.content.strip()

        except Exception as e:
            print(f"  [{self.name}] Summarization error: {e}")
            return f"[ERROR generating summary: {e}]"

    # ── Display ────────────────────────────────────────────────────────────────

    def _display_summary(self, msg: EmailMessage) -> None:
        """Prints the summary to the console in a formatted block."""
        width = 60
        print(f"\n{'═' * width}")
        print(f"  Summary")
        print(f"{'═' * width}")
        print(f"  From   : {msg['sender']}")
        print(f"  Subject: {msg['subject']}")
        print(f"  Date   : {msg['date']}")
        print(f"{'─' * width}")
        for line in msg["summary"].splitlines():
            print(f"  {line}")
        print(f"{'═' * width}")