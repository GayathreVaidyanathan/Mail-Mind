"""
agents/labeler_agent.py

Agent 5 — Labeler Agent
────────────────────────
Applies TWO labels to every email:

  1. Platform label  — WHERE it came from (rule-based domain matching)
  2. Topic label     — WHAT it's about (rule-based with AI fallback
                       only for academic_info)

Topic vocabulary (fixed):
  Personal      — all personal_work emails
  Promotional   — all spam and promotional emails
  Notifications — account_notification default
  Finance       — account_notification with finance signals
  Subscription  — account_notification with subscription signals
  Policy        — account_notification with policy/legal signals
  Research      — academic_info with research/collaboration signals
  Coding        — academic_info with programming/ML/dev signals
  Career        — academic_info with job/internship/training signals
  (AI fallback) — academic_info with no keyword match → Ollama call

Design:
  - personal_work, promotional, spam → assigned directly, no AI needed
  - account_notification → keyword hierarchy (Finance > Subscription
    > Policy > Notifications)
  - academic_info → keyword scan first; AI only if no match found
  - Platform detection is always rule-based, never uses AI
"""

import re
from openai import OpenAI
from config import OLLAMA_BASE_URL, OLLAMA_MODEL
from core.message_bus import EmailMessage


# ══════════════════════════════════════════════════════════════════════════════
# PLATFORM MAP
# keyword (in sender domain) → Gmail label name
# ══════════════════════════════════════════════════════════════════════════════

PLATFORM_MAP = {
    # Food delivery
    "swiggy":            "Swiggy",
    "zomato":            "Zomato",
    "blinkit":           "Blinkit",
    "dunzo":             "Dunzo",
    "zepto":             "Zepto",

    # Social / content
    "reddit":            "Reddit",
    "linkedin":          "LinkedIn",
    "twitter":           "Twitter",
    "instagram":         "Instagram",
    "youtube":           "YouTube",
    "substack":          "Substack",
    "medium":            "Medium",

    # Dev / tech
    "github":            "GitHub",
    "gitlab":            "GitLab",
    "stackoverflow":     "StackOverflow",
    "leetcode":          "LeetCode",
    "hackerrank":        "HackerRank",
    "kaggle":            "Kaggle",

    # Learning
    "nptel":             "NPTEL",
    "coursera":          "Coursera",
    "udemy":             "Udemy",
    "springboard":       "Infosys Springboard",
    "infosys":           "Infosys Springboard",
    "interactadvocates": "interACT",

    # Google
    "googleone":         "Google One",
    "google":            "Google",

    # E-commerce
    "amazon":            "Amazon",
    "flipkart":          "Flipkart",
    "myntra":            "Myntra",
    "meesho":            "Meesho",
    "ajio":              "AJIO",
    "nykaa":             "Nykaa",

    # Finance / banking
    "paytm":             "Paytm",
    "phonepe":           "PhonePe",
    "razorpay":          "Razorpay",
    "hdfc":              "HDFC Bank",
    "icici":             "ICICI Bank",
    "sbi":               "SBI",
    "axis":              "Axis Bank",
    "kotak":             "Kotak Bank",
    "payu":              "PayU",
    "upi":               "UPI",

    # Travel
    "makemytrip":        "MakeMyTrip",
    "irctc":             "IRCTC",
    "ola":               "Ola",
    "uber":              "Uber",
    "rapido":            "Rapido",
    "ezeeinfosolutions": "A1 Travels",
    "redbus":            "RedBus",
    "abhibus":           "AbhiBus",

    # Jobs
    "naukri":            "Naukri",
    "internshala":       "Internshala",
    "unstop":            "Unstop",
    "wellfound":         "Wellfound",
    "dare2compete":      "Dare2Compete",

    # Crowdfunding (spam but still labeled for tracking)
    "impactguru":        "Crowdfunding",
    "milaap":            "Crowdfunding",
    "ketto":             "Crowdfunding",
}


# ══════════════════════════════════════════════════════════════════════════════
# TOPIC KEYWORD RULES
# ══════════════════════════════════════════════════════════════════════════════

# account_notification keyword tiers (checked in priority order)
# First match wins: Finance > Subscription > Policy > Notifications (default)

FINANCE_KEYWORDS = [
    "payment", "transaction", "receipt", "invoice", "bill",
    "amount debited", "amount credited", "bank", "upi", "neft",
    "imps", "salary", "tax", "gst", "credit card", "debit card",
    "insurance", "refund", "order successful", "ticket booked",
    "bus ticket", "train ticket", "booking confirmed", "payu",
    "razorpay", "paytm", "phonepe", "rs.", "inr", "rupees",
    "credited", "debited", "balance", "statement", "reward points",
]

SUBSCRIPTION_KEYWORDS = [
    "subscription", "subscribed", "subscribe", "unsubscribe",
    "plan", "renewal", "renew", "billing cycle", "trial",
    "premium", "membership", "cancelled", "cancellation",
    "auto-renew", "auto renew", "your plan", "your subscription",
]

POLICY_KEYWORDS = [
    "terms", "policy", "policies", "privacy", "legal",
    "terms of service", "terms and conditions", "compliance",
    "gdpr", "data protection", "guidelines", "rules",
    "intermediary", "user agreement", "cookie",
]

# academic_info keyword tiers (checked in priority order)
# First match wins: Research > Coding > Career
# No match → AI call

RESEARCH_KEYWORDS = [
    "research", "collaboration", "paper", "publication",
    "conference", "journal", "thesis", "dissertation",
    "phd", "ms", "masters", "grad school", "graduate",
    "professor", "fellowship", "scholarship", "admit",
    "admission", "statement of purpose", "sop", "lor",
    "gre", "toefl", "ielts", "research assistant",
    "deep learning", "machine learning", "neural network",
    "transformer", "attention mechanism", "dataset",
    "benchmark", "model", "arxiv",
]

CODING_KEYWORDS = [
    "leetcode", "hackerrank", "codeforces", "competitive programming",
    "hackathon", "open source", "github", "pull request", "repository",
    "coding contest", "algorithm", "data structure", "bootcamp",
    "course update", "infosys springboard", "udemy", "nptel", "coursera",
    "programming", "developer", "software engineer", "tech stack",
    "kaggle", "notebook", "cli", "local development", "vscode",
    "python", "javascript", "deployment", "api", "framework",
]

CAREER_KEYWORDS = [
    "internship", "intern", "stipend", "placement", "recruitment",
    "hiring", "interview", "job offer", "offer letter",
    "campus recruitment", "off campus", "application deadline",
    "job opening", "we are hiring", "apply for", "shortlisted",
    "selection process", "training program", "certification",
    "workshop", "semiconductor", "skill", "nsqf", "ministry",
    "tribal", "programme", "program", "enrollment", "enroll",
]

# AI fallback prompt — only for academic_info with no keyword match
TOPIC_AI_SYSTEM_PROMPT = """You are an email topic labeler. Output EXACTLY one label or 'none'.

LABELS:
  Research   — research papers, collaboration, PhD, ML/AI studies, academic work
  Coding     — programming, dev tools, hackathons, coding platforms, tech courses
  Career     — internships, jobs, training programs, certifications, workshops

Output only the label name exactly as shown above, or: none
No explanation. No punctuation."""


# ══════════════════════════════════════════════════════════════════════════════
# LABELER AGENT
# ══════════════════════════════════════════════════════════════════════════════

class LabelerAgent:
    """
    Applies platform + topic labels to every email.

    Platform detection: always rule-based, no AI.
    Topic detection:    rule-based for all categories;
                        AI fallback only for academic_info with no keyword match.

    Sets:
      msg["platform_label"] — e.g. "Swiggy", "Reddit", "GitHub"
      msg["topic_label"]    — e.g. "Finance", "Research", "Personal", ""
    """

    VALID_AI_TOPICS = {"Research", "Coding", "Career", "none"}

    def __init__(self):
        self.client = OpenAI(base_url=OLLAMA_BASE_URL, api_key="ollama")
        self.model  = OLLAMA_MODEL
        self.name   = "LabelerAgent"

    def run(self, msg: EmailMessage) -> EmailMessage:
        category = msg.get("category", "")

        # ── 1. Platform label — always rule-based ─────────────────────────
        platform = self._detect_platform(msg)
        msg["platform_label"] = platform
        if platform:
            print(f"  [{self.name}] Platform → 🏷  {platform}")
        else:
            print(f"  [{self.name}] Platform → (unknown)")

        # ── 2. Topic label — rule-based, AI only for academic_info ────────
        topic = self._detect_topic(msg, category)
        msg["topic_label"] = topic
        msg["label"]       = topic

        if topic:
            print(f"  [{self.name}] Topic    → 🏷  {topic}")
        else:
            print(f"  [{self.name}] Topic    → (none)")

        return msg

    # ── Platform detection ─────────────────────────────────────────────────────

    def _detect_platform(self, msg: EmailMessage) -> str:
        """Rule-based platform detection from sender domain."""
        sender = msg.get("sender", "").lower()
        domain_match = re.search(r"@([\w.-]+)", sender)
        domain = domain_match.group(1).lower() if domain_match else ""
        combined = sender + " " + domain

        for keyword, label in PLATFORM_MAP.items():
            if keyword in combined:
                return label

        return ""

    # ── Topic detection ────────────────────────────────────────────────────────

    def _detect_topic(self, msg: EmailMessage, category: str) -> str:
        """
        Assigns topic label based on category, then keyword rules.
        AI fallback only for academic_info with no keyword match.
        """
        # ── Direct category assignments ────────────────────────────────────
        if category in ("spam", "promotional"):
            return "Promotional"

        if category == "personal_work":
            return "Personal"

        # ── account_notification: keyword hierarchy ────────────────────────
        if category == "account_notification":
            return self._topic_for_notification(msg)

        # ── academic_info: keyword scan → AI fallback ──────────────────────
        if category == "academic_info":
            return self._topic_for_academic(msg)

        # unknown category
        return ""

    def _topic_for_notification(self, msg: EmailMessage) -> str:
        """
        Finance > Subscription > Policy > Notifications (default).
        Checks subject + first 500 chars of body.
        """
        combined = (msg.get("subject", "") + " " + msg.get("body", "")[:500]).lower()

        if any(kw in combined for kw in FINANCE_KEYWORDS):
            return "Finance"

        if any(kw in combined for kw in SUBSCRIPTION_KEYWORDS):
            return "Subscription"

        if any(kw in combined for kw in POLICY_KEYWORDS):
            return "Policy"

        return "Notifications"

    def _topic_for_academic(self, msg: EmailMessage) -> str:
        """
        Research > Coding > Career via keywords.
        Falls back to AI if no keyword matches.
        """
        combined = (msg.get("subject", "") + " " + msg.get("body", "")[:500]).lower()

        if any(kw in combined for kw in RESEARCH_KEYWORDS):
            return "Research"

        if any(kw in combined for kw in CODING_KEYWORDS):
            return "Coding"

        if any(kw in combined for kw in CAREER_KEYWORDS):
            return "Career"

        # No keyword match — fall back to AI
        print(f"  [{self.name}] No keyword match for academic_info — calling AI...")
        return self._ai_topic(msg)

    # ── AI fallback ────────────────────────────────────────────────────────────

    def _ai_topic(self, msg: EmailMessage) -> str:
        """
        Called only for academic_info emails that matched no keywords.
        Asks the model to pick from Research / Coding / Career / none.
        """
        user_prompt = f"""Label this email's topic:

From: {msg['sender']}
Subject: {msg['subject']}
Body (first 500 chars): {msg['body'][:500]}

Output only the label:"""

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": TOPIC_AI_SYSTEM_PROMPT},
                    {"role": "user",   "content": user_prompt},
                ],
                temperature=0.0,
                max_tokens=10,
            )
            result = response.choices[0].message.content.strip()
            # Match against valid labels (case-insensitive)
            for label in ("Research", "Coding", "Career"):
                if label.lower() in result.lower():
                    return label
            return ""

        except Exception as e:
            print(f"  [{self.name}] AI topic error: {e}")
            return ""