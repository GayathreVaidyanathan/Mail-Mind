"""
config.py

Central configuration for the Gmail Multi-Agent System v2.
All settings are loaded from environment variables with sensible defaults.
Sensitive values (email, password) are never stored here —
they come from the UI at runtime and live in memory only.

Changes from v1:
  - Removed Gmail OAuth settings (GMAIL_SCOPES, CREDENTIALS_FILE, TOKEN_FILE)
  - Removed time window filter (MONITOR_START, MONITOR_END, MONITOR_TZ)
  - Removed GROQ_API_KEY (legacy)
  - Added IMAP settings (MAX_EMAILS, MARK_AS_READ kept, EMAIL_LABEL removed)
  - Added APP_HOST and APP_PORT for uvicorn
"""

import os
from dotenv import load_dotenv

load_dotenv()


# ── Ollama settings ────────────────────────────────────────────────────────────
# Runs locally — no API key needed.
# Make sure Ollama is running before starting the app.

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1")
OLLAMA_MODEL    = os.getenv("OLLAMA_MODEL",    "qwen2.5:3b")


# ── Email / IMAP settings ──────────────────────────────────────────────────────
# Credentials (email + app password) are NOT stored here.
# They are collected via the UI at runtime and kept in memory only.

MAX_EMAILS  = int(os.getenv("MAX_EMAILS",  "20"))
MARK_AS_READ = os.getenv("MARK_AS_READ", "true").lower() == "true"


# ── App settings ───────────────────────────────────────────────────────────────
# Used by uvicorn when starting the server.

APP_HOST = os.getenv("APP_HOST", "0.0.0.0")
APP_PORT = int(os.getenv("APP_PORT", "8000"))

# Autonomous mode — if True, ComposerAgent sends replies without
# showing drafts. If False, replies are staged but not sent.
AUTONOMOUS_MODE = os.getenv("AUTONOMOUS_MODE", "true").lower() == "true"