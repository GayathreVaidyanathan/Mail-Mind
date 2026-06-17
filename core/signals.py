"""
core/signals.py

Centralised signal definitions for the classifier pipeline.
───────────────────────────────────────────────────────────
All keyword lists and domain lists used by:
  - SpamFilterAgent
  - ClassifierAgent
  - PreFilterAgent

Keeping signal data here means:
  - Agents contain only logic, not data
  - Tuning keywords never requires touching agent code
  - Multiple agents can share the same lists without duplication

Organisation mirrors the classifier tiers:
  Tier 2  — Spam
  Tier 3  — Account notification (transactional)
  Tier 3.5— Social platform notifications
  Tier 4  — Promotional
  Tier 5  — Academic / info
  Tier 5.5— Newsletter / advocacy (content-based)
  Tier 6  — Personal work

Changelog:
  - Added "notifications@" to AUTOMATED_SENDER_FRAGMENTS so that
    notifications@stck.me is caught by _is_automated() as a backstop.
  - Moved "spotify.com" from PROMOTIONAL_SENDER_DOMAINS to DELIVERY_APP_DOMAINS
    so transactional keyword check fires before promotional domain rule —
    fixes order confirmations and cancellation emails being misclassified.
  - Moved "nykaa.com" from PROMOTIONAL_SENDER_DOMAINS to DELIVERY_APP_DOMAINS
    so delivery updates are correctly classified as account_notification.
"""


# ══════════════════════════════════════════════════════════════════════════════
# TIER 2 — SPAM
# ══════════════════════════════════════════════════════════════════════════════

# Crowdfunding / donation platform domains — always spam
SPAM_SENDER_DOMAINS = [
    # Indian crowdfunding
    "impactguru.com", "milaap.org", "ketto.org",
    # Global crowdfunding
    "gofundme.com", "fundly.com", "causes.com",
    "donorbox.org", "givebutter.com",
]

# Emotional manipulation / crowdfunding language in subject
SPAM_SUBJECT_KEYWORDS = [
    # Medical guilt
    "cancer cells", "rushed to hospital", "picu", "vomited blood",
    "please help my", "my baby", "my child is", "chemo",
    "blood transfusion", "surgery for my", "after birth",
    "discovered a hole", "fighting for life", "days to live",
    "newborn", "critical condition", "icu",
    # Phishing / scam
    "you have won", "you've won", "lottery winner",
    "prize of rs", "prize of $", "selected for prize",
    "verify your bank account", "your account will be suspended",
    "claim your reward", "you are selected",
    "nigerian prince", "inheritance",
]

# Guilt-trip / manipulation signals in body
SPAM_BODY_SIGNALS = [
    "please donate", "please help us", "kindly donate",
    "contribute to save", "save my child", "save my baby",
    "fund my", "crowdfunding", "fundraiser",
    "we need your help to", "help us raise",
]


# ══════════════════════════════════════════════════════════════════════════════
# TIER 3 — ACCOUNT NOTIFICATION (TRANSACTIONAL)
# ══════════════════════════════════════════════════════════════════════════════

# Keywords triggered by the user's own action on a platform
TRANSACTIONAL_SUBJECT_KEYWORDS = [
    # Delivery / order
    "order summary", "monthly summary", "weekly summary",
    "order delivered", "delivered on time", "delivered before time",
    "out for delivery", "order placed", "order confirmed",
    "order successful", "order shipped", "order dispatched",
    "your order", "your purchase", "order #", "order no",
    # Payment / receipt
    "payment successful", "payment received", "payment of",
    "payment confirmation", "payment failed", "payment declined",
    "amount debited", "amount credited", "transaction successful",
    "transaction failed", "is successful", "your order at",
    "receipt", "invoice", "refund initiated", "refund processed",
    "refund successful", "money sent", "money received",
    "transfer successful", "transfer failed",
    # Ticket / booking / travel
    "bus ticket", "train ticket", "flight ticket", "ticket booked",
    "ticket confirmed", "booking confirmed", "ticket cancelled",
    "booking cancelled", "pnr", "reservation confirmed",
    "itinerary", "boarding pass", "check-in",
    # University / institution passes
    "home pass", "gate pass", "leave pass",
    # Security / account
    "otp", "one time password", "one-time password",
    "login alert", "new login detected", "new sign-in",
    "security alert", "password reset", "password changed",
    "account verification", "verify your email",
    "verify your account", "confirm your email",
    "2fa", "2-factor", "two-factor", "authentication code",
    "suspicious activity", "unusual activity",
    # Form / submission
    "thanks for filling", "form submitted", "response received",
    "thanks for filling out", "your response has been",
    "your application", "application received",
    "application confirmed", "registration confirmed",
    "your registration",
    # Subscription / billing
    "subscription renewed", "subscription cancelled",
    "subscription confirmed", "your subscription",
    "billing", "renewal", "plan changed", "plan upgraded",
    "plan downgraded", "trial started", "trial ending",
    # Reports / support
    "your report", "your ticket", "your case",
    "support ticket", "case number",
    # Plan / storage updates (e.g. Google One, Dropbox, iCloud)
    "your plan", "your storage", "more storage", "storage upgrade",
    "plan update", "plan now", "plan has been", "added to your",
    "now includes", "has been upgraded", "storage increased",
    "you are now a", "welcome to", "member", "membership activated",
    "subscription activated", "account activated",
    "membership activated", "membership details",
    "you are now a", "member!", "membership has been activated",
    "congrats on redeeming", "your membership",
    # Spotify-specific (order confirmation, cancellation)
    "order confirmation", "you're no longer on", "no longer on",
]


# ══════════════════════════════════════════════════════════════════════════════
# TIER 3.5 — SOCIAL PLATFORM NOTIFICATIONS
# ══════════════════════════════════════════════════════════════════════════════

# These platforms send both genuine notifications AND promotional digests.
# Transactional keywords are checked first; only fall to promotional if no match.
SOCIAL_NOTIFICATION_DOMAINS = [
    "redditmail.com",
    "facebookmail.com",
    "youtube.com",
    "instagram.com",
    "tiktok.com",
    "twitter.com",
    "x.com",
]

# Subject signals that indicate a genuine social notification (not a digest)
SOCIAL_NOTIFICATION_KEYWORDS = [
    # Reddit
    "replied to your comment", "commented on your post",
    "mentioned you in", "sent you a message", "upvoted your",
    "gave your post", "gave your comment",
    # Facebook / Instagram
    "commented on your", "reacted to your", "tagged you in",
    "sent you a friend request", "accepted your friend request",
    "liked your", "shared your",
    # YouTube
    "commented on your video", "subscribed to your channel",
    "replied to your comment on",
    # Twitter / X
    "retweeted your", "liked your tweet", "mentioned you",
    "replied to your tweet", "followed you",
    # Generic cross-platform
    "replied to you", "mentioned you", "sent you",
]

# ══════════════════════════════════════════════════════════════════════════════
# TIER 3.7 — DELIVERY & LIFESTYLE APP NOTIFICATIONS
# ══════════════════════════════════════════════════════════════════════════════

# These apps send both transactional and promotional emails.
# Transactional keywords checked first; fall to promotional only if no match.
#
# NOTE: "spotify.com" moved here from PROMOTIONAL_SENDER_DOMAINS — Spotify
# sends genuine transactional emails (order confirmations, plan cancellations)
# that must be classified as account_notification, not promotional.
#
# NOTE: "nykaa.com" moved here from PROMOTIONAL_SENDER_DOMAINS — Nykaa
# sends delivery updates (account_notification) alongside marketing emails.
DELIVERY_APP_DOMAINS = [
    # Food delivery
    "swiggy.in", "zomato.com", "blinkit.com",
    "dunzo.com", "zepto.com", "bigbasket.com",
    # Dating / lifestyle
    "bumble.com", "tinder.com", "hinge.co",
    # Gaming / entertainment
    "chess.com",
    # Music / streaming — sends order confirmations, plan change alerts
    "spotify.com",
    # Beauty / e-commerce — sends delivery updates alongside marketing
    "nykaa.com",
]

# ══════════════════════════════════════════════════════════════════════════════
# TIER 4 — PROMOTIONAL
# ══════════════════════════════════════════════════════════════════════════════

# Known digest/newsletter sender domains — always promotional.
# NOTE: Social platforms moved to SOCIAL_NOTIFICATION_DOMAINS above.
# NOTE: spotify.com and nykaa.com moved to DELIVERY_APP_DOMAINS above.
# NOTE: wattpad.com, substack.com, stck.me handled by _STORY_PLATFORM_DOMAINS
#       in classifier_agent.py — do NOT add them here.
PROMOTIONAL_SENDER_DOMAINS = [
    # Job spam
    "naukri.com", "shine.com", "foundit.in",
    "monster.com", "ziprecruiter.com",
    # E-commerce marketing
    "flipkart.com", "myntra.com", "ajio.com",
]

# Marketing language in subject — strong promotional signal
PROMOTIONAL_SUBJECT_KEYWORDS = [
    # Sales / offers
    "% off", "percent off", "flat off", "upto rs",
    "save rs", "save $", "save £",
    "discount", "flash sale", "sale ends",
    "limited time", "limited offer", "exclusive offer",
    "coupon", "promo code", "use code",
    "shop now", "buy now", "order now", "grab now",
    "deal of the day", "today only", "offer ends",
    # Marketing hooks
    "don't miss out", "hurry", "last chance",
    "expires soon", "we miss you", "come back",
    "re-engage", "check out our", "just launched",
    "introducing", "new arrival", "now available",
    # Digest / newsletter signals
    "top posts", "this week ", "weekly digest",
    "monthly digest", "newsletter", "roundup",
    "trending now", "what's new", "best of",
    # Job spam
    "jobs with no degree", "salary upto", "apply now",
    "hiring for freshers", "walk-in interview",
    "immediate joiners", "urgent opening",
]


# ══════════════════════════════════════════════════════════════════════════════
# TIER 5 — ACADEMIC / INFO
# ══════════════════════════════════════════════════════════════════════════════

# Known educational / developer platform sender domains.
# NOTE: interactadvocates.org and substack.com removed — too broad or
# misclassified. Both handled by content-based detection in Tier 5.5.
ACADEMIC_SENDER_DOMAINS = [
    # Course platforms
    "nptel.ac.in", "coursera.org", "udemy.com",
    "edx.org", "khanacademy.org", "skillshare.com",
    "pluralsight.com", "linkedin.com",
    "infosys.com", "springboard.com",
    "kaggle.com", "fast.ai",
    # Dev / research platforms
    "github.com", "github.io", "gitlab.com",
    "stackoverflow.com", "stackexchange.com",
    "hackerrank.com", "leetcode.com",
    "arxiv.org", "researchgate.net",
    "acm.org", "ieee.org",
    # Verified learning newsletters
    "tldrnewsletter.com", "morningbrew.com",
    "bensbites.com", "alphasignal.ai",
]

# Academic content signals in subject
ACADEMIC_SUBJECT_KEYWORDS = [
    # GitHub / dev
    "pull request", "new issue", "issue opened",
    "new release", "new commit", "merged",
    "build failed", "build passed", "ci failed", "ci passed",
    # Course / learning
    "assignment due", "course update", "course transition",
    "new lecture", "new module", "quiz available",
    "certificate", "course completion",
    # Research / academic
    "exam result", "grade released", "result published",
    "paper accepted", "paper published",
    "conference", "journal", "research update",
    # University
    "academic calendar", "timetable", "semester",
    "examination schedule",
]


# ══════════════════════════════════════════════════════════════════════════════
# TIER 5.5 — NEWSLETTER / ADVOCACY (CONTENT-BASED)
# ══════════════════════════════════════════════════════════════════════════════

# Body signals that indicate informational/newsletter content.
# Used when sender domain isn't in ACADEMIC_SENDER_DOMAINS.
# Catches: substack.com, interactadvocates.org, medium.com, beehiiv.com, etc.
NEWSLETTER_BODY_SIGNALS = [
    # Research / policy
    "research shows", "according to", "study finds",
    "published in", "peer-reviewed", "policy brief",
    "white paper", "findings suggest",
    # Advocacy / awareness
    "human rights", "civil rights", "advocacy",
    "discrimination", "inclusion", "equity",
    "awareness", "legislation", "campaign",
    # Tech / dev learning
    "open source", "machine learning", "artificial intelligence",
    "deep learning", "neural network", "large language model",
    "framework", "library release", "new feature",
    # General informational
    "in this issue", "this week we", "today we cover",
    "key takeaways", "what you need to know",
    "explained", "breakdown", "deep dive",
]

# Unsubscribe / mailing list footer patterns
# Used by _has_unsubscribe() — covers standard and newsletter-style footers
UNSUBSCRIBE_PATTERNS = [
    # Standard
    "unsubscribe", "opt out", "opt-out",
    # Preference management
    "manage preferences", "manage your preferences",
    "email preferences", "notification settings",
    "update your email preferences", "update subscription",
    "manage subscription", "email settings",
    # Newsletter-style footers (interACT, Substack, Mailchimp, etc.)
    "you're receiving this", "you are receiving this",
    "you received this because", "why am i receiving",
    "no longer wish to receive", "unsubscribe from this list",
    "change your email preferences", "change preferences",
    "click here to unsubscribe", "to stop receiving",
    # Generic
    "stop receiving", "remove me from", "mailing list",
]


# ══════════════════════════════════════════════════════════════════════════════
# TIER 6 — PERSONAL WORK
# ══════════════════════════════════════════════════════════════════════════════

# Domains that are almost always personal senders
PERSONAL_SENDER_DOMAINS = [
    "gmail.com", "yahoo.com", "outlook.com",
    "hotmail.com", "protonmail.com", "icloud.com",
    "live.com", "me.com",
]

# Automated/role address fragments — sender containing these is NOT personal
#
# NOTE: "notifications@" added here so that notifications@stck.me and similar
# platform notification addresses are caught by _is_automated() as a backstop,
# even when the domain is not in _STORY_PLATFORM_DOMAINS.
AUTOMATED_SENDER_FRAGMENTS = [
    "noreply", "no-reply", "donotreply", "do-not-reply",
    "notifications@", "alerts@", "mailer@",
    "newsletter@", "updates@", "digest@",
]