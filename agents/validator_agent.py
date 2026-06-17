"""
agents/validator_agent.py

Agent 0.5 — Validator Agent  (merged with SenderTrustAgent)
─────────────────────────────────────────────────────────────
Runs before SpamFilterAgent. Validates the sender's email domain
and computes a trust score in a single pass.

Stage 1 — MX Validation
  Extracts the sender domain and performs a DNS MX record lookup.
  A domain with no MX records is fake, mistyped, or a throwaway —
  the email is immediately flagged as invalid and the rest of the
  pipeline is skipped for it.

Stage 2 — Trust Scoring  (only reached if MX is valid)
  Starts at 100 and deducts points for red flags:

    −10   No SPF record found
    −10   No DMARC record found
    −40   Disposable / throwaway domain
    −20   High-risk TLD (.xyz, .top, .click, .work, .gq)
    −50   Display-name spoofing (brand name ≠ actual domain)

  Final score is clamped to [0, 100] and mapped to a trust level:

    ≥ 80  → trusted
    ≥ 40  → suspicious
     < 40  → dangerous

Outputs written to EmailMessage
  msg["invalid_sender"]   bool
  msg["trust_score"]      int   (0–100; absent when invalid_sender=True)
  msg["trust_level"]      str   ("trusted" | "suspicious" | "dangerous";
                                 absent when invalid_sender=True)

Pipeline position
  ValidatorAgent → SpamFilterAgent → ClassifierAgent → ...

Design notes
  • MX results are cached per domain to avoid redundant DNS lookups
    across multiple emails from the same sender in one run.
  • SPF / DMARC results are cached separately under self.trust_cache
    for the same reason.
  • ALWAYS_VALID_DOMAINS skips MX lookup for known high-volume senders.
  • Parent-domain fallback walks up the domain tree progressively
    (e.g. mail.uipath.com → uipath.com) before giving up.
  • Spoofing check allows subdomains of known brands (e.g. accounts.google.com).

Requires
  pip install dnspython
"""

import re
import dns.resolver
from core.message_bus import EmailMessage


# ── Constants ──────────────────────────────────────────────────────────────────

ALWAYS_VALID_DOMAINS = {
    # Personal email providers
    "gmail.com", "yahoo.com", "outlook.com", "hotmail.com",
    "protonmail.com", "icloud.com", "live.com", "me.com",
    "zohomail.in", "zohomail.com", "zoho.com",

    # Indian apps / payment
    "swiggy.in", "zomato.com", "flipkart.com", "myntra.com",
    "payu.in", "razorpay.com", "phonepe.com", "paytm.com",
    "naukri.com", "nykaa.com", "bigbasket.com",

    # Global platforms
    "amazon.com", "google.com", "github.com", "linkedin.com",
    "kaggle.com", "spotify.com", "chess.com", "bumble.com",
    "tinder.com", "wattpad.com", "inkitt.com", "goodreads.com",
    "substack.com", "wellfound.com", "openai.com",

    # Creative / AI tools
    "nightcafe.studio", "midjourney.com", "runwayml.com",
    "leonardo.ai", "stability.ai", "adobe.com",

    # Dev / learning tools
    "uipath.com", "resumeworded.com", "turbohire.co",
    "infosys.com", "tspsubmission.com", "canva.com",
    "geeksforgeeks.org",

    # AI / dev APIs
    "groq.com", "groq.co",

    # Social
    "redditmail.com", "reddit.com", "facebookmail.com", "twitter.com", "x.com",

    # Newsletters / link shorteners used by legit senders
    "stck.me",

    # Advocacy / newsletters
    "interactadvocates.org",

    # Indian government / banking
    "mybharat.gov.in", "sbi.co.in", "alerts.sbi.co.in", "alerts.sbi.bank.in",
    "hdfcbank.com", "icicibank.com", "axisbank.com",
    "communications.sbi.co.in",
}

DISPOSABLE_DOMAINS = {
    "mailinator.com",
    "10minutemail.com",
    "guerrillamail.com",
    "tempmail.com",
    "trashmail.com",
}

HIGH_RISK_TLDS = (
    ".xyz",
    ".top",
    ".click",
    ".work",
    ".gq",
)

KNOWN_BRANDS = {
    "amazon":    "amazon.com",
    "paypal":    "paypal.com",
    "microsoft": "microsoft.com",
    "google":    "google.com",
    "github":    "github.com",
    "linkedin":  "linkedin.com",
    "apple":     "apple.com",
    "facebook":  "facebook.com",
}

INVALID_LABEL = "Invalid Sender"


# ── Agent ──────────────────────────────────────────────────────────────────────

class ValidatorAgent:
    """
    Validates sender email domains (MX lookup) and computes a
    trust score (SPF, DMARC, disposable, TLD, spoofing) in one pass.

    Usage
        agent = ValidatorAgent()
        msg   = agent.run(msg)

        if msg.get("invalid_sender"):
            # skip rest of pipeline — label already applied
            ...

        # Otherwise use msg["trust_score"] / msg["trust_level"]
        # downstream (e.g. SpamFilterAgent can weight its decision).
    """

    def __init__(self):
        self.name          = "ValidatorAgent"
        self._mx_cache:    dict[str, bool] = {}   # domain → MX valid?
        self._trust_cache: dict[str, int]  = {}   # domain → base score

    # ── Public entry point ─────────────────────────────────────────────────────

    def run(self, msg: EmailMessage) -> EmailMessage:

        sender = msg.get("sender", "")
        domain = self._extract_domain(sender)

        # ── Guard: unparseable sender ──────────────────────────────
        if not domain:
            print(f"  [{self.name}] ⚠  Could not extract domain from: {sender[:50]!r}")
            msg["invalid_sender"] = False
            return msg

        # ── Stage 1: MX validation ─────────────────────────────────
        if not self._is_valid_domain(domain):
            print(f"  [{self.name}] 🚩 Invalid sender — no MX records: {domain}")
            msg["invalid_sender"] = True
            msg["label"]          = INVALID_LABEL
            msg["status"]         = "invalid_sender"
            return msg

        msg["invalid_sender"] = False

        # ── Stage 2: Trust scoring ─────────────────────────────────
        # Domain-level deductions are cached; spoofing is per-message.
        if domain in self._trust_cache:
            base_score = self._trust_cache[domain]
        else:
            base_score = 100

            if not self._has_spf(domain):
                base_score -= 10

            if not self._has_dmarc(domain):
                base_score -= 10

            if domain in DISPOSABLE_DOMAINS:
                base_score -= 40

            if domain.endswith(HIGH_RISK_TLDS):
                base_score -= 20

            self._trust_cache[domain] = base_score

        # Spoofing check is always per-message (display name can vary)
        score = base_score
        if self._looks_spoofed(sender, domain):
            score -= 50

        score = max(score, 0)

        if score >= 80:
            level = "trusted"
        elif score >= 40:
            level = "suspicious"
        else:
            level = "dangerous"

        msg["trust_score"] = score
        msg["trust_level"] = level

        # ── Print result ───────────────────────────────────────────
        status_icon = {"trusted": "✅", "suspicious": "⚠️ ", "dangerous": "🚨"}.get(level, "")
        print(
            f"  [{self.name}] {status_icon} {domain} — "
            f"valid sender | score={score} | level={level}"
        )

        return msg

    # ── Domain extraction ──────────────────────────────────────────────────────

    def _extract_domain(self, sender: str) -> str:
        """
        Handles both:
          "Display Name <email@domain.com>"
          "email@domain.com"
        """
        match = re.search(r"@([\w.-]+)", sender)
        return match.group(1).lower() if match else ""

    # ── MX lookup ─────────────────────────────────────────────────────────────

    def _is_valid_domain(self, domain: str) -> bool:
        if domain in self._mx_cache:
            return self._mx_cache[domain]

        # Fast path: known valid domain
        if domain in ALWAYS_VALID_DOMAINS:
            self._mx_cache[domain] = True
            return True

        # Fast path: subdomain of a known valid domain
        # Walk ALL parent levels — e.g. tx.nightcafe.studio → nightcafe.studio
        parts = domain.split(".")
        for i in range(1, len(parts)):
            parent = ".".join(parts[i:])
            if parent in ALWAYS_VALID_DOMAINS:
                self._mx_cache[domain] = True
                return True

        # Build list of candidates: domain itself + each parent (≥2 labels)
        domains_to_try = []
        for i in range(len(parts) - 1):
            candidate = ".".join(parts[i:])
            if len(candidate.split(".")) >= 2:
                domains_to_try.append(candidate)

        resolver = dns.resolver.Resolver()
        resolver.lifetime = 3.0   # max total time per query (seconds)
        resolver.timeout  = 1.5   # per-nameserver timeout

        for candidate in domains_to_try:
            # MX record → definitely valid
            try:
                resolver.resolve(candidate, "MX")
                self._mx_cache[domain] = True
                return True
            except Exception:
                pass

            # A record → domain exists, just outbound-only
            try:
                resolver.resolve(candidate, "A")
                self._mx_cache[domain] = True
                return True
            except Exception:
                pass

            # TXT record → domain exists (SPF etc.)
            try:
                resolver.resolve(candidate, "TXT")
                self._mx_cache[domain] = True
                return True
            except Exception:
                pass

        # No DNS records anywhere in the chain → truly fake
        self._mx_cache[domain] = False
        return False

    # ── SPF lookup ────────────────────────────────────────────────────────────

    def _has_spf(self, domain: str) -> bool:
        try:
            for r in dns.resolver.resolve(domain, "TXT"):
                if "v=spf1" in str(r).lower():
                    return True
        except Exception:
            pass
        return False

    # ── DMARC lookup ──────────────────────────────────────────────────────────

    def _has_dmarc(self, domain: str) -> bool:
        try:
            for r in dns.resolver.resolve(f"_dmarc.{domain}", "TXT"):
                if "v=dmarc1" in str(r).lower():
                    return True
        except Exception:
            pass
        return False

    # ── Spoofing detection ────────────────────────────────────────────────────

    def _looks_spoofed(self, sender: str, domain: str) -> bool:
        display = sender.lower()
        for brand, real_domain in KNOWN_BRANDS.items():
            if brand in display:
                # Allow exact match OR subdomain of the real domain
                if domain == real_domain or domain.endswith("." + real_domain):
                    continue
                print(
                    f"  [{self.name}] ⚠  Possible display-name spoofing "
                    f"({brand!r} in display name but domain is {domain!r})"
                )
                return True
        return False