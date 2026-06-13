"""
agents/composer_agent.py

Agent 3 — Composer Agent
─────────────────────────
Handles personal_work emails.
  1. Generates an AI draft reply using Ollama (local LLaMA 3.2)
  2. Either sends automatically (AUTONOMOUS_MODE=true)
     or shows to human for approval (AUTONOMOUS_MODE=false)
  3. Sets msg["final_reply"] and msg["status"]

AUTONOMOUS_MODE=false (interactive):
  status = "sent"    → human approved (as-is or edited)
  status = "skipped" → human chose to skip
  status = "quit"    → human wants to stop the whole agent

AUTONOMOUS_MODE=true (local scheduled run):
  status = "sent"    → AI draft sent automatically
  status = "skipped" → draft generation failed
"""

from openai import OpenAI
from config import OLLAMA_BASE_URL, OLLAMA_MODEL, AUTONOMOUS_MODE
from core.message_bus import EmailMessage
from core.approval import display_email, get_approval


REPLY_SYSTEM_PROMPT = """You are a helpful email assistant. Your job is to draft professional,
concise email replies on behalf of the user.

Guidelines:
- Be polite and professional
- Match the tone of the original email (formal if they're formal, casual if casual)
- Keep replies concise — no fluff or unnecessary filler
- Do NOT include a subject line — just the body text
- Do NOT include "Dear [Name]," or sign-off unless the original email had them
- If the email needs info you don't have, draft a reply asking for that info
"""


class ComposerAgent:
    """
    Drafts replies for personal/work emails.
    Uses Ollama (local LLaMA 3.2) instead of Groq.

    Interactive mode (AUTONOMOUS_MODE=false):
        Shows draft to human, waits for Send/Edit/Regenerate/Skip/Quit.

    Autonomous mode (AUTONOMOUS_MODE=true):
        Generates draft and sends immediately — no human involved.

    Usage:
        agent = ComposerAgent()
        msg = agent.run(msg, index, total)
    """

    def __init__(self):
        self.client = OpenAI(base_url=OLLAMA_BASE_URL, api_key="ollama")
        self.model = OLLAMA_MODEL
        self.name = "ComposerAgent"

    def run(self, msg: EmailMessage, index: int, total: int) -> EmailMessage:
        """Routes to autonomous or interactive mode based on config."""
        if AUTONOMOUS_MODE:
            return self._autonomous(msg)
        else:
            return self._interactive(msg, index, total)

    def _autonomous(self, msg: EmailMessage) -> EmailMessage:
        """Generates and sends reply automatically without human review."""
        print(f"  [{self.name}] AUTONOMOUS MODE — generating and sending reply...")
        draft = self._generate_draft(msg)

        if draft.startswith("[ERROR"):
            print(f"  [{self.name}] Draft generation failed — skipping.")
            msg["status"] = "skipped"
            return msg

        msg["draft"] = draft
        msg["final_reply"] = draft
        msg["status"] = "sent"

        print(f"  [{self.name}] Auto-sending reply:")
        print(f"  {'─' * 50}")
        for line in draft[:300].splitlines():
            print(f"    {line}")
        if len(draft) > 300:
            print(f"    [... truncated ...]")
        print(f"  {'─' * 50}")
        print(f"  [{self.name}] Status → sent (autonomous)")
        return msg

    def _interactive(self, msg: EmailMessage, index: int, total: int) -> EmailMessage:
        """Full draft → human approval loop."""
        print(f"  [{self.name}] Generating draft reply...")
        draft = self._generate_draft(msg)

        while True:
            display_email(msg, draft, index, total)
            action, final_reply = get_approval(msg, draft)

            if action == "send":
                msg["draft"] = draft
                msg["final_reply"] = final_reply
                msg["status"] = "sent"
                print(f"  [{self.name}] Reply approved. Status → sent.")
                return msg

            elif action == "regenerate":
                print(f"  [{self.name}] Regenerating draft...")
                draft = self._generate_draft(msg)

            elif action == "skip":
                msg["status"] = "skipped"
                print(f"  [{self.name}] Skipped by user.")
                return msg

            elif action == "quit":
                msg["status"] = "quit"
                print(f"  [{self.name}] User requested quit.")
                return msg

    def _generate_draft(self, msg: EmailMessage) -> str:
        """Calls Ollama LLaMA 3.2 to generate a reply draft."""
        user_prompt = f"""Please draft a reply to this email:

From: {msg['sender']}
Subject: {msg['subject']}
Date: {msg['date']}

Email body:
{msg['body'][:3000]}

Draft a reply now (just the body text, no subject line):"""

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": REPLY_SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.7,
                max_tokens=500,
            )
            return response.choices[0].message.content.strip()

        except Exception as e:
            return f"[ERROR generating reply: {e}]"