"""
agents/classifier_agent.py

Agent 2 — Classifier Agent
───────────────────────────
Receives an EmailMessage, classifies it into one of five categories,
sets msg["category"], and returns the message.

Categories:
    personal_work        → ComposerAgent   (draft + send reply)
    academic_info        → DigestAgent     (summarize + mark important)
    account_notification → DigestAgent     (summarize + mark important)
    promotional          → InboxAgent      (move to Auto/Promotional label)
    spam                 → SpamFilterAgent handles this — never reaches here

Design principle: flat rule engine + AI fallback only for genuine ambiguity.
  - Rules are ordered by confidence, not by tier number.
  - Each rule is a single, independent check — no tier interdependencies.
  - AI is called only when NO rule fires.
  - All signal lists imported from core/signals.py — no hardcoded keywords here.

Pipeline position:
  PreFilterAgent → SpamFilterAgent → ClassifierAgent
  By the time an email reaches here:
    - Duplicates removed          (PreFilterAgent)
    - Confirmed spam routed out   (SpamFilterAgent)
    - Body cleaned                (PreFilterAgent)
    - Forwards detected           (PreFilterAgent)

Changelog:
  - stck.me / Substack misclassified as personal_work → fixed by adding
    "stck.me" and "substack.com" to SOCIAL_NOTIFICATION_DOMAINS (signals.py)
    and "notifications@" to AUTOMATED_SENDER_FRAGMENTS (signals.py).
  - Spotify order/cancellation emails misclassified as promotional → fixed by
    moving "spotify.com" to DELIVERY_APP_DOMAINS (signals.py) so transactional
    keyword check fires before promotional domain rule.
  - Nykaa sends both transactional and promotional → moved to DELIVERY_APP_DOMAINS.
  - Wattpad sends only marketing/digest → added to PROMOTIONAL_SENDER_DOMAINS.
"""

import re
import time
from openai import OpenAI
from config import OLLAMA_BASE_URL, OLLAMA_MODEL
from core.message_bus import EmailMessage
from core.signals import (
    TRANSACTIONAL_SUBJECT_KEYWORDS,
    SOCIAL_NOTIFICATION_DOMAINS,
    SOCIAL_NOTIFICATION_KEYWORDS,
    DELIVERY_APP_DOMAINS,
    PROMOTIONAL_SENDER_DOMAINS,
    PROMOTIONAL_SUBJECT_KEYWORDS,
    ACADEMIC_SENDER_DOMAINS,
    ACADEMIC_SUBJECT_KEYWORDS,
    NEWSLETTER_BODY_SIGNALS,
    UNSUBSCRIBE_PATTERNS,
    PERSONAL_SENDER_DOMAINS,
    AUTOMATED_SENDER_FRAGMENTS,
)


# ══════════════════════════════════════════════════════════════════════════════
# ADDITIONAL SIGNALS (structural patterns — not content keywords)
# These are kept here rather than signals.py because they are
# structural/regex patterns used only by the classifier.
# ══════════════════════════════════════════════════════════════════════════════

# Sender address fragments that indicate automated/system mail.
# Broader than AUTOMATED_SENDER_FRAGMENTS in signals.py — covers bank
# alert patterns like cbsalerts.sbi@alerts.sbi.bank.in
#
# NOTE: "notifications@" is now in AUTOMATED_SENDER_FRAGMENTS (signals.py)
# so stck.me (notifications@stck.me) is caught by _is_automated() before
# reaching the personal sender check at Rule 14.
_AUTO_SENDER_FRAGMENTS = AUTOMATED_SENDER_FRAGMENTS + [
    "no_reply", "do_not_reply",
    "support@",
    "info@",
    "hello@",
    "contact@",
    "admin@",
    "postmaster@",
    "cbsalerts", "viralerts",   # Indian bank alert patterns
    ".bank.",                    # any .bank. subdomain
    "alerts.",                   # alerts.anything
    "googleplay"
]

# Subject keywords that strongly indicate account_notification even
# without a noreply sender (e.g. bank alerts, subscription notices)
_EXTRA_TRANSACTIONAL_SUBJECTS = [
    "alert",                   # catches "CBSSBI ALERT", "SBI Alert"
    "credited",
    "debited",
    "salary credit",
    "salary deposited",
    "a/c",                     # Indian bank shorthand
    "acct",
    "will be cancelled",       # "Your subscription will be cancelled"
    "has been cancelled",
    "auto-renew",
    "auto renew",
    "verification code",       # catches "Email Verification Code" exactly
]

# Reddit activity keywords — signals that the email was triggered by
# something the user did or something directed at them personally.
_REDDIT_ACTIVITY_KEYWORDS = (
    "comment", "reply", "replied", "mention", "mentioned",
    "upvot", "award", "message", "inbox", "private message",
    "password", "verify", "security", "account",
)

# Reddit sender domains — both the mailing domain and the main domain.
_REDDIT_DOMAINS = ("redditmail.com", "reddit.com")

# Substack / story platform activity keywords — signals that the email
# is a genuine notification (new chapter, new post) rather than a
# marketing blast. Substack and stck.me are in SOCIAL_NOTIFICATION_DOMAINS
# so these are checked at Rule 3 before any AI fallback.
_STORY_PLATFORM_ACTIVITY_KEYWORDS = (
    "chapter", "chapters", "new post", "new issue", "published",
    "posted", "update", "part ", "episode", "story update",
    "new story", "just published", "latest post",
)


# ══════════════════════════════════════════════════════════════════════════════
# AI PROMPT
# ══════════════════════════════════════════════════════════════════════════════

CLASSIFY_SYSTEM_PROMPT = """Classify this email into exactly one category.

CATEGORIES:

  personal_work
    - A real human wrote this to you personally
    - Friend, colleague, professor, mentor, recruiter
    - Must feel like a 1-to-1 conversation, not a broadcast

  account_notification
    - Triggered by YOUR own action on a platform
    - Order confirmations, delivery updates, OTPs, password resets, security alerts
    - Bank transaction alerts, subscription changes
    - Story/newsletter platform notifications (new chapter, new post from someone you follow)
    - Ask: "Did I do something that caused this?" — if yes, pick this

  academic_info
    - Educational or informational content worth reading
    - Courses, research, professional learning, curated newsletters
    - Government schemes, training programs, opportunities
    - Newsletters from organizations, advocacy groups, institutions

  promotional
    - Marketing, sales, offers, announcements sent to many people
    - Default choice when genuinely unsure

  spam
    - Phishing, scams, fraud, manipulation

HARD RULES:
  - Unsubscribe link in body                          → NEVER personal_work
  - noreply / no-reply in sender                      → NEVER personal_work
  - Generic salutation (Dear Customer)                → NEVER personal_work
  - Sender is an organization, company, institution   → NEVER personal_work
  - Forwarded email → classify by content, not by who forwarded it
  - notifications@ in sender                          → NEVER personal_work
  - When unsure                                       → promotional

EXAMPLES:
From: director@interactadvocates.org
Subject: An Important Leadership Update from interACT
→ account_notification
(organizational newsletter, not a personal email)

From: googleplay-noreply@google.com
Subject: Your Bumble subscription benefits are ending soon
→ account_notification
(your own subscription is affected)

From: smruthi415@gmail.com
Subject: Research Collaboration Opportunity
→ personal_work
(real person writing directly to you)

From: noreply@spotify.com
Subject: Yuvan Shankar Raja live: concert recommendations near you
→ promotional
(marketing email, not triggered by your action)

From: gayathrevaidya@gmail.com
Subject: Fwd: New privacy settings for Search services
→ account_notification
(forwarded informational content about a platform update, not promotional)

From: notifications@stck.me
Subject: Chapters ~ 57 & 58 (Swords & Widow)
→ account_notification
(story platform notification for content you follow)

From: no-reply@substack.com
Subject: God, if I'm meant to be alone, take away my desire to be loved
→ account_notification
(newsletter digest from a publication you subscribed to)

Reply with ONLY the category name. No explanation. No punctuation."""

# ══════════════════════════════════════════════════════════════════════════════
# CLASSIFIER AGENT
# ══════════════════════════════════════════════════════════════════════════════

class ClassifierAgent:
    """
    Classifies emails using a flat rule engine with AI fallback.

    Rule order (each rule is independent — no cascading interactions):
      1.  pre_category hint from PreFilterAgent
      2.  Known promotional sender domains
      3a. Reddit sender domains (override before generic social loop)
      3b. Story/newsletter platform domains (substack, stck.me) — override
          before generic social loop so chapter/post subjects don't fall
          through to AI fallback
      3.  Social platform domains
      4.  Delivery / lifestyle app domains
      5.  Known academic sender domains
      6.  Automated sender + transactional subject → account_notification
      7.  Automated sender + extra transactional subjects
      8.  Non-personal, non-automated sender + transactional keyword
      9.  Promotional subject keywords
      10. Unsubscribe + newsletter body signals → academic_info
      11. Unsubscribe present, no newsletter signals → promotional
      12. Academic subject keywords
      13. Newsletter body signals (2+ hits)
      14. Personal sender, no unsubscribe → personal_work
      15. AI fallback

    Usage:
        agent = ClassifierAgent()
        msg   = agent.run(msg)
    """

    VALID_CATEGORIES = {
        "personal_work",
        "academic_info",
        "account_notification",
        "promotional",
        "spam",
    }

    # Story / newsletter platforms — send genuine activity notifications
    # (new chapter, new post) that should be account_notification, and
    # marketing blasts that should be promotional.
    # Kept here (not signals.py) because the keyword check logic is
    # specific to this rule and not shared with other agents.
    _STORY_PLATFORM_DOMAINS = (
        "substack.com",
        "stck.me",
        "medium.com",
        "beehiiv.com",
        "ghost.io",
        "convertkit.com",
        "mailchimp.com",
    )

    def __init__(self):
        self.client = OpenAI(base_url=OLLAMA_BASE_URL, api_key="ollama")
        self.model  = OLLAMA_MODEL
        self.name   = "ClassifierAgent"

    # ── Public entry point ─────────────────────────────────────────────────────

    def run(self, msg: EmailMessage) -> EmailMessage:
        print(f"  [{self.name}] Classifying: '{msg['subject'][:60]}'...")

        t_start       = time.perf_counter()
        category, via = self._classify(msg)
        elapsed       = (time.perf_counter() - t_start) * 1000

        icon = "⚡" if via == "rule" else "🤖"
        print(f"  [{self.name}] {icon} {via.capitalize():<5} → {category}  ({elapsed:.1f} ms)")

        msg["category"] = category
        return msg

    # ── Main classification logic ──────────────────────────────────────────────

    def _classify(self, msg: EmailMessage) -> tuple[str, str]:
        """
        Returns (category, "rule") or (category, "AI").
        Rules are flat and independent — no tier fall-through interactions.
        """
        sender   = msg.get("sender",  "").lower()
        subject  = msg.get("subject", "").lower()
        body     = msg.get("body",    "")[:1000].lower()
        combined = subject + " " + body

        is_auto     = self._is_automated(sender)
        has_unsub   = self._has_any(body, UNSUBSCRIBE_PATTERNS)
        is_personal = self._is_personal_sender(sender)

        # ── 1. Pre-category hint from PreFilterAgent ───────────────────────
        if msg.get("pre_category"):
            return msg["pre_category"], "rule"

        # ── 2. Known promotional sender domains ───────────────────────────
        if self._has_any(sender, PROMOTIONAL_SENDER_DOMAINS):
            return "promotional", "rule"

        # ── 3a. Reddit override ───────────────────────────────────────────
        # Reddit sends two kinds of email:
        #   - Activity alerts (comment, reply, mention, upvote) → account_notification
        #   - Community digests (subreddit posts, trending threads) → academic_info
        # Neither is promotional. This must sit before the generic social
        # domain loop (Rule 3) so digest subjects like "Pipeline" or
        # "Goodbye ChatGPT" don't fall through to the promotional keyword
        # check at Rule 9.
        if any(d in sender for d in _REDDIT_DOMAINS):
            if self._has_any(combined, _REDDIT_ACTIVITY_KEYWORDS):
                return "account_notification", "rule"
            return "academic_info", "rule"

        # ── 3b. Story / newsletter platform override ──────────────────────
        # Substack, stck.me and similar platforms send two kinds of email:
        #   - Activity notifications (new chapter, new post from a followed
        #     author) → account_notification
        #   - Marketing / digest blasts → promotional
        # This must sit before Rule 3 (generic social domain loop) so that
        # chapter notification subjects don't reach the AI fallback and get
        # misclassified as personal_work.
        #
        # Detection logic:
        #   - If subject contains a story/post activity keyword → account_notification
        #   - If body has unsubscribe signal → promotional (marketing blast)
        #   - Otherwise → account_notification (safe default for followed content)
        if any(d in sender for d in self._STORY_PLATFORM_DOMAINS):
            if self._has_any(combined, _STORY_PLATFORM_ACTIVITY_KEYWORDS):
                return "account_notification", "rule"
            if has_unsub:
                return "promotional", "rule"
            return "account_notification", "rule"

        # ── 3. Social platform domains ────────────────────────────────────
        for domain in SOCIAL_NOTIFICATION_DOMAINS:
            if domain in sender:
                if self._has_any(combined, SOCIAL_NOTIFICATION_KEYWORDS):
                    return "account_notification", "rule"
                if self._has_any(combined, TRANSACTIONAL_SUBJECT_KEYWORDS):
                    return "account_notification", "rule"
                return "promotional", "rule"

        # ── 4. Delivery / lifestyle app domains ───────────────────────────
        # Covers: food delivery, dating apps, music (spotify), beauty (nykaa).
        # Transactional keywords checked first — only fall to promotional
        # if neither transactional nor extra-transactional subject matches.
        for domain in DELIVERY_APP_DOMAINS:
            if domain in sender:
                if self._has_any(combined, TRANSACTIONAL_SUBJECT_KEYWORDS):
                    return "account_notification", "rule"
                if self._has_any(combined, _EXTRA_TRANSACTIONAL_SUBJECTS):
                    return "account_notification", "rule"
                return "promotional", "rule"

        # ── 5. Known academic sender domains ──────────────────────────────
        if self._has_any(sender, ACADEMIC_SENDER_DOMAINS):
            return "academic_info", "rule"

        # ── 6. Automated sender + transactional subject ───────────────────
        if is_auto and self._has_any(combined, TRANSACTIONAL_SUBJECT_KEYWORDS):
            return "account_notification", "rule"

        # ── 7. Automated sender + extra transactional subjects ────────────
        if is_auto and self._has_any(combined, _EXTRA_TRANSACTIONAL_SUBJECTS):
            return "account_notification", "rule"

        # ── 8. Non-personal sender + transactional keywords ───────────────
        # Catches senders like cbsalerts.sbi@alerts.sbi.bank.in that don't
        # contain "noreply" but are clearly not personal senders.
        if not is_personal:
            if self._has_any(combined, TRANSACTIONAL_SUBJECT_KEYWORDS):
                return "account_notification", "rule"
            if self._has_any(combined, _EXTRA_TRANSACTIONAL_SUBJECTS):
                return "account_notification", "rule"

        # ── 9. Promotional subject keywords ───────────────────────────────
        if self._has_any(subject, PROMOTIONAL_SUBJECT_KEYWORDS):
            return "promotional", "rule"

        # ── 10. Unsubscribe + newsletter signals → academic_info ──────────
        if has_unsub and self._has_any(body, NEWSLETTER_BODY_SIGNALS):
            return "academic_info", "rule"

        # ── 11. Unsubscribe present, no newsletter signals → promotional ───
        if has_unsub and not self._has_any(combined, TRANSACTIONAL_SUBJECT_KEYWORDS):
            return "promotional", "rule"

        # ── 12. Academic subject keywords ─────────────────────────────────
        if self._has_any(subject, ACADEMIC_SUBJECT_KEYWORDS):
            return "academic_info", "rule"

        # ── 13. Newsletter body signals (2+ hits) ─────────────────────────
        newsletter_hits = sum(1 for sig in NEWSLETTER_BODY_SIGNALS if sig in body)
        if newsletter_hits >= 2:
            return "academic_info", "rule"

        # ── 14. Personal sender, no unsubscribe → personal_work ───────────
        if is_personal and not has_unsub and not msg.get("forwarded"):
            return "personal_work", "rule"

        # ── 15. AI fallback ────────────────────────────────────────────────
        return self._ai_classify(msg), "AI"

    # ── Helper methods ─────────────────────────────────────────────────────────

    def _is_automated(self, sender: str) -> bool:
        """True if the sender address looks automated or non-human."""
        return any(frag in sender for frag in _AUTO_SENDER_FRAGMENTS)

    def _is_personal_sender(self, sender: str) -> bool:
        """
        True if sender looks like a real person on a personal email domain.
        Checks: not automated + display name has 2+ words + personal domain.
        """
        if self._is_automated(sender):
            return False

        name_match   = re.match(r'^"?([^"<]+)"?\s*<', sender)
        display_name = name_match.group(1).strip() if name_match else ""

        if len(display_name.split()) < 2:
            return False

        domain_match = re.search(r"@([\w.-]+)>?$", sender)
        if not domain_match:
            return False

        domain = domain_match.group(1)
        return any(pd in domain for pd in PERSONAL_SENDER_DOMAINS)

    def _has_any(self, text: str, keywords: list[str]) -> bool:
        """True if any keyword from the list appears in text."""
        return any(kw in text for kw in keywords)

    # ── AI fallback ────────────────────────────────────────────────────────────

    def _ai_classify(self, msg: EmailMessage) -> str:
        """
        Called only when no rule matched — genuine ambiguity.
        Passes forward context hint if available.
        Falls back to "promotional" on any error or unrecognised label.
        """
        context_hint = ""
        if msg.get("forwarded"):
            original = msg.get("original_sender", "")
            if original:
                context_hint = (
                    f"\n\nContext: This is a forwarded email. "
                    f"Forwarded by: {msg['sender']}. "
                    f"Original sender: {original}. "
                    f"Classify by the email content, not the act of forwarding."
                )
            else:
                context_hint = (
                    f"\n\nContext: This is a forwarded email. "
                    f"Classify by the email content."
                )

        user_prompt = (
            f"From: {msg['sender']}\n"
            f"Subject: {msg['subject']}\n"
            f"Body:\n{msg['body'][:800]}"
            f"{context_hint}"
        )

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": CLASSIFY_SYSTEM_PROMPT},
                    {"role": "user",   "content": user_prompt},
                ],
                temperature=0.0,
                max_tokens=10,
            )

            raw   = response.choices[0].message.content.strip().lower()
            label = raw.split()[0].rstrip(".,!?:;")

            if label in self.VALID_CATEGORIES:
                return label

            # Scan full response in case model added a prefix
            for category in self.VALID_CATEGORIES:
                if category in raw:
                    return category

            print(
                f"  [{self.name}] ⚠ Unrecognised label '{raw}' "
                f"— defaulting to promotional"
            )
            return "promotional"

        except Exception as exc:
            print(f"  [{self.name}] ⚠ AI error: {exc} — defaulting to promotional")
            return "promotional"