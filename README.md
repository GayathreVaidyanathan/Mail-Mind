# Gmail Multi-Agent System · Powered by Ollama AI

A locally-run, privacy-first email management system that automatically classifies, summarises, labels, and replies to emails using a multi-agent pipeline powered by a local Ollama LLM. Ships with a React UI and a FastAPI backend.

---

## Features

- **Automatic email classification** into 5 categories: Personal/Work, Academic/Info, Account Notification, Promotional, Spam
- **AI-powered summarisation** for academic and transactional emails
- **Autonomous reply drafting** for personal and work emails
- **Smart labeling** with platform detection (Google, Kaggle, SBI, Swiggy, etc.) and topic tagging
- **Spam and phishing detection** before classification
- **Sender validation** via MX record checks and trust scoring
- **Forward detection** with original sender extraction
- **Duplicate email deduplication**
- **Provider-agnostic IMAP/SMTP** — works with Gmail, Outlook, Yahoo, Zoho, iCloud, and more
- **Real-time streaming UI** via Server-Sent Events (SSE)
- **Fully local** — no data leaves your machine except to your email provider

---

## Architecture

```
Frontend (React + Vite)
        ↓  REST + SSE
Backend (FastAPI)
        ↓
    Orchestrator
        ↓
┌─────────────────────────────────────┐
│  PreFilterAgent                     │  Dedup, body clean, forward detect
│  ValidatorAgent                     │  MX check, trust score
│  SpamFilterAgent                    │  Keyword + domain spam detection
│  ClassifierAgent                    │  Flat rule engine + Ollama AI fallback
│  LabelerAgent                       │  Platform + topic label assignment
│  ComposerAgent  (personal_work)     │  Draft + send reply via Ollama
│  DigestAgent    (academic/transact) │  Summarise via Ollama
│  InboxAgent                         │  All IMAP/SMTP operations
└─────────────────────────────────────┘
        ↓
   Email Provider (IMAP/SMTP)
```

---

## Project Structure

```
UI-OLLAMA/
├── agents/
│   ├── classifier_agent.py     # Flat rule engine + AI fallback classifier
│   ├── composer_agent.py       # Drafts and sends replies for personal mail
│   ├── digest_agent.py         # Summarises academic and transactional emails
│   ├── inbox_agent.py          # All IMAP/SMTP operations
│   ├── labeler_agent.py        # Assigns platform and topic labels
│   ├── pre_filter_agent.py     # Dedup, body cleaning, forward detection
│   ├── spam_filter_agent.py    # Spam and phishing detection
│   └── validator_agent.py      # Sender MX validation and trust scoring
├── core/
│   ├── approval.py             # Approval flow helpers
│   ├── message_bus.py          # EmailMessage type definition
│   └── signals.py              # All keyword/domain signal lists
├── frontend/
│   └── src/
│       ├── api/
│       │   └── client.js       # SSE + REST API client
│       ├── components/         # UI components
│       ├── pages/              # Page views
│       ├── App.jsx
│       ├── main.jsx
│       └── index.css
├── routers/
│   ├── auth.py                 # /api/auth/connect endpoint
│   └── pipeline.py             # /api/pipeline/run SSE endpoint
├── services/
│   └── imap_service.py         # IMAP/SMTP wrapper, provider auto-detection
├── .env                        # Environment variables (not committed)
├── .gitignore
├── config.py                   # App configuration
├── credentials.json            # Email credentials (not committed)
├── main.py                     # FastAPI app entry point
├── orchestrator.py             # Pipeline coordinator
└── requirements.txt
```

---

## Classification Pipeline

Emails are processed through a flat rule engine first. The AI is called only when no rule matches.

| Rule | Signal | Category |
|---|---|---|
| 1 | Pre-category hint from PreFilterAgent | any |
| 2 | Known promotional sender domains | promotional |
| 3 | Social platform domains | account_notification / promotional |
| 4 | Delivery/lifestyle app domains | account_notification / promotional |
| 5 | Known academic sender domains | academic_info |
| 6 | Automated sender + transactional subject | account_notification |
| 7 | Automated sender + extra transactional keywords | account_notification |
| 8 | Non-personal sender + transactional keywords | account_notification |
| 9 | Promotional subject keywords | promotional |
| 10 | Unsubscribe link + newsletter body signals | academic_info |
| 11 | Unsubscribe link, no newsletter signals | promotional |
| 12 | Academic subject keywords | academic_info |
| 13 | Newsletter body signals (2+ hits) | academic_info |
| 14 | Personal sender, no unsubscribe, not forwarded | personal_work |
| 15 | AI fallback (Ollama) | any |

---

## Supported Email Providers

| Provider | IMAP Host | Notes |
|---|---|---|
| Gmail | imap.gmail.com | Requires App Password |
| Outlook / Hotmail | imap-mail.outlook.com | Requires App Password |
| Yahoo | imap.mail.yahoo.com | Requires App Password |
| iCloud / Me | imap.mail.me.com | Requires App-Specific Password |
| Zoho Mail (.in) | imap.zoho.in | Requires App Password |
| Zoho Mail (.com) | imap.zoho.com | Requires App Password |
| GMX | imap.gmx.com | Requires App Password |
| ProtonMail | 127.0.0.1:1143 | Requires Proton Bridge |
| Any other | imap.<domain> | Auto-detected fallback |

---

## Prerequisites

- Python 3.11+
- Node.js 18+
- [Ollama](https://ollama.com) running locally
- A supported email account with IMAP enabled and an app password generated

---

## Setup

### 1. Clone the repository

```bash
git clone https://github.com/your-username/your-repo-name.git
cd your-repo-name
```

### 2. Backend setup

```bash
python -m venv venv
venv\Scripts\activate        # Windows
# source venv/bin/activate   # macOS/Linux

pip install -r requirements.txt
```

### 3. Configure environment

Create a `.env` file in the project root:

```env
OLLAMA_BASE_URL=http://localhost:11434/v1
OLLAMA_MODEL=qwen2.5:3b
MARK_AS_READ=true
```

### 4. Pull the Ollama model

```bash
ollama pull qwen2.5:3b
```

### 5. Frontend setup

```bash
cd frontend
npm install
npm run build
cd ..
```

### 6. Run the app

```bash
python main.py
```

Then open `http://localhost:8000` in your browser.

---

## Usage

1. Open the app in your browser
2. Enter your email address and app password
3. Click **Connect** — the system validates your credentials
4. Click **Run Pipeline** — emails are fetched and processed in real time
5. Watch the live feed as each email is classified, labeled, summarised, or replied to

---

## Email Folder Structure (IMAP)

The system creates these folders in your mailbox:

| Folder | Contents |
|---|---|
| `Auto/Promotional` | Marketing, digests, job alerts |
| `Junk` | Spam, phishing, invalid senders |

Academic, account notification, and personal emails remain in INBOX and are flagged as important.

---

## Adding New Signal Keywords

All keyword and domain lists live in `core/signals.py`. No agent code needs to change — just add to the relevant list:

- `TRANSACTIONAL_SUBJECT_KEYWORDS` — order confirmations, OTPs, bank alerts
- `PROMOTIONAL_SENDER_DOMAINS` — known marketing sender domains
- `ACADEMIC_SENDER_DOMAINS` — course platforms, research orgs
- `SPAM_SUBJECT_KEYWORDS` — phishing and scam patterns
- `PERSONAL_SENDER_DOMAINS` — personal email provider domains

For AI edge cases, add a few-shot example to `CLASSIFY_SYSTEM_PROMPT` in `agents/classifier_agent.py`.

---

## Tech Stack

| Layer | Technology |
|---|---|
| Frontend | React, Vite, SSE |
| Backend | FastAPI, Python 3.11 |
| AI | Ollama (local LLM) |
| Email | IMAP / SMTP (imaplib, smtplib) |
| HTML parsing | BeautifulSoup4 |

---

## Security Notes

- Credentials are never stored on disk by the app — they are held in memory for the session only
- `credentials.json` and `.env` are excluded from version control via `.gitignore`
- All AI inference runs locally — no email content is sent to any external API
- Sender validation includes MX record checks to detect spoofed or invalid senders

---

## License

MIT
