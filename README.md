# merinaukri — AI Job Application Assistant

A personal job application assistant that automates job discovery, generates ATS-optimized resumes and cover letters, finds LinkedIn referrals, and provides a web dashboard to track everything — all controlled via a Telegram bot.

## Features

- **Job Discovery** — Searches Indeed, LinkedIn, and Glassdoor using [python-jobspy](https://github.com/Bunsly/JobSpy)
- **Automated Scout** — Runs job searches on a schedule (default: every 6 hours) and sends new matches to Telegram
- **ATS-Optimized Resume Generation** — Extracts keywords from job descriptions and tailors your resume with keyword matching and ATS score
- **Cover Letter Generation** — Creates targeted cover letters for each role
- **LinkedIn Referral Finder** — Searches your LinkedIn connections (1st and 2nd degree) at the target company using cookie-based Voyager API; surfaces warm paths via trusted contacts
- **Document Export** — Generates PDF (via WeasyPrint) and DOCX output
- **Web Dashboard** — FastAPI-based tracker for all your applications with filters, bulk actions, and status tracking
- **Telegram Bot Interface** — Apply to jobs, search, find referrals, and trigger scouts directly from Telegram

## Tech Stack

| Component | Technology |
|---|---|
| Language | Python 3.13 |
| LLM | Groq (llama-3.3-70b-versatile) — configurable to Anthropic |
| Bot | python-telegram-bot v22 (async) |
| Job Search | python-jobspy |
| LinkedIn | Cookie-based Voyager API |
| Web Dashboard | FastAPI + Jinja2 (server-side rendered) |
| PDF Rendering | WeasyPrint (optional) + python-docx |
| Data Models | Pydantic v2 |
| Storage | SQLite |

## Quick Start (3 steps)

```bash
# 1. Clone and run the setup script
git clone https://github.com/sanggpel/naukri.git
cd naukri
bash setup.sh

# 2. Edit the 3 config files the script created (see below)

# 3. Run it
source .venv/bin/activate
python dashboard.py              # web dashboard at http://127.0.0.1:8080
python main.py                   # telegram bot (in a separate terminal)
```

The setup script automatically:
- Creates a Python virtual environment
- Installs all dependencies
- Copies example config files for you to fill in
- Checks for optional PDF dependencies (pango)
- Creates data directories

## What you need before starting

| What | Where to get it | How long | Required? |
|---|---|---|---|
| Python 3.10+ | [python.org/downloads](https://www.python.org/downloads/) or `brew install python3` | 5 min | Yes |
| Groq API key (free) | [console.groq.com](https://console.groq.com/) — sign up, create key | 2 min | Yes |
| Telegram bot token | Message [@BotFather](https://t.me/BotFather) on Telegram → `/newbot` | 2 min | No — only if you want the Telegram bot |
| LinkedIn cookies | For referral search — see [step 5](#5-export-linkedin-cookies-optional) below | 5 min | No — only for LinkedIn referral search |

> **You don't need Telegram.** The web dashboard works on its own — you can scout for jobs, generate resumes, find referrals, and track applications entirely from your browser. The Telegram bot is an optional extra for mobile convenience.

## Configuration

After running `bash setup.sh`, fill in these 3 files:

### 1. `.env` — your API key

```
GROQ_API_KEY=gsk_paste_your_key_here
```

### 2. `config/profile.yaml` — your resume

This is the most important file. The better it describes you, the better your generated resumes will be.

You don't need to write it by hand — see [Building Your Profile with AI](#building-your-profile-with-ai) below to have ChatGPT or Claude generate it from your LinkedIn or existing resume.

The file should contain: your name, email, phone, location, summary, skills, work experience (with bullet points), and education. See `config/profile.example.yaml` for the exact format.

### 3. `config/settings.yaml` — your preferences

The key things to fill in:

```yaml
telegram:
  merinaukri: YOUR_TELEGRAM_BOT_TOKEN     # from @BotFather

discovery:
  default_location: "Calgary, AB, Canada"  # your city
  default_country: "Canada"                 # your country

scout:
  queries:                                  # job titles you're looking for
    - "Engineering Manager"
    - "Director of Engineering"
  location: "Canada"
  country: "Canada"
```

Everything else has sensible defaults. See `config/settings.example.yaml` for all options.

### 4. Trusted connections (optional — for warm path referrals)

If you want the referral finder to highlight people you already know:

```bash
# The setup script already copied this for you
# Just edit config/trusted_connections.yaml
```

Add your 1st-degree LinkedIn connections you'd feel comfortable asking for help:

```yaml
trusted_connections:
  - name: "Jane Smith"
    linkedin_url: "https://www.linkedin.com/in/janesmith"
    note: "Ex-colleague at Acme"
```

When searching referrals, these contacts get a **★ Trusted** badge, and 2nd-degree contacts reachable through them show a **🔗 Warm path via Jane Smith** link.

### 5. Export LinkedIn cookies (optional)

Only needed for LinkedIn referral search:

1. Log into LinkedIn in your browser
2. Install the [Cookie-Editor](https://cookie-editor.com/) browser extension
3. On any LinkedIn page, click Cookie-Editor → Export → JSON
4. Save the file as `cookies.json` in the project root

## Running

You can use the **web dashboard**, the **Telegram bot**, or both at the same time.

```bash
source .venv/bin/activate

# Web dashboard (open http://127.0.0.1:8080 in your browser)
python dashboard.py

# Telegram bot (in a separate terminal)
python main.py
```

## Telegram Bot Commands

| Command | Description |
|---|---|
| `/start` | Welcome message (also saves your chat ID for scheduled scouts) |
| `/apply <url>` | Generate a tailored resume + cover letter for a job posting URL |
| `/search <query>` | Search job boards for matching positions |
| `/scout` | Run a manual scout using your configured queries |
| `/referrals <company>` | Find your LinkedIn connections at a company |
| `/profile` | Show your profile summary |
| *Paste a URL* | Auto-triggers the apply flow |

## Web Dashboard

The dashboard at `http://127.0.0.1:8080` provides:

- **Status tracking** — Track jobs through: Discovered → Generated → Applied → Interviewing → Offered → Rejected / Not Relevant / Withdrawn
- **Filters** — Search by title/company/description, filter by company, source, remote/hybrid
- **Bulk actions** — Select multiple jobs and change their status at once
- **Job description peek** — Click "peek" on any role to view the full description in a modal
- **Document downloads** — Download generated resumes and cover letters
- **Referral search** — Find LinkedIn connections at any company directly from the dashboard
- **Detail view** — Full job details, notes, status updates, and referral info

## Project Structure

```
merinaukri/
├── main.py                    # Telegram bot entry point
├── dashboard.py               # Web dashboard entry point
├── requirements.txt
├── .env                       # GROQ_API_KEY (not committed)
├── config/
│   ├── profile.yaml           # Your resume/profile data (not committed)
│   ├── settings.yaml          # LLM, Telegram, LinkedIn, scout config (not committed)
│   ├── trusted_connections.yaml        # Your trusted LinkedIn contacts (not committed)
│   └── trusted_connections.example.yaml  # Example — copy and fill in
├── src/
│   ├── models.py              # Pydantic data models
│   ├── llm_client.py          # Unified Groq/Anthropic LLM client
│   ├── profile_loader.py      # Loads profile.yaml
│   ├── tracker.py             # Application CRUD (SQLite)
│   ├── bot/
│   │   ├── app.py             # Bot setup, command registration, scheduler
│   │   └── handlers.py        # All Telegram command handlers
│   ├── discovery/
│   │   └── scraper.py         # Job board scraping via python-jobspy
│   ├── generator/
│   │   ├── keywords.py        # ATS keyword extraction
│   │   ├── resume.py          # Resume generation
│   │   ├── cover_letter.py    # Cover letter generation
│   │   └── renderer.py        # PDF/DOCX rendering
│   ├── network/
│   │   └── linkedin.py        # LinkedIn Voyager API (cookie auth)
│   └── web/
│       └── app.py             # FastAPI dashboard routes
├── templates/
│   ├── resume_template.html   # Resume HTML template
│   ├── cover_letter_template.html
│   └── web/
│       ├── base.html          # Dashboard base layout
│       ├── dashboard.html     # Main dashboard page
│       └── detail.html        # Application detail page
├── static/
│   └── style.css              # Dashboard styles
└── data/                      # Generated at runtime (not committed)
    ├── tracker.db             # SQLite database (applications)
    ├── jobs/                  # Cached job listings
    ├── resumes/               # Generated resumes
    └── cover_letters/         # Generated cover letters
```

## Building Your Profile with AI

The most important file is `config/profile.yaml` — the better it describes you, the better the generated resumes and cover letters will be. You don't need to write it by hand. Use any AI assistant (ChatGPT, Claude, Gemini, etc.) to generate it from your existing resume or LinkedIn profile.

### Option 1: From your LinkedIn profile

1. Open your LinkedIn profile and copy all text (About, Experience, Education, Skills, Certifications)
2. Go to [ChatGPT](https://chat.openai.com), [Claude](https://claude.ai), or [Gemini](https://gemini.google.com)
3. Paste this prompt:

```
I'm setting up a job application assistant tool. I need you to convert my LinkedIn profile into a YAML configuration file that matches this exact structure:

[paste the contents of config/profile.example.yaml here]

Here is my LinkedIn profile:
[paste your LinkedIn profile text here]

Output only the YAML, no explanation.
```

4. Copy the output into `config/profile.yaml`

### Option 2: From your existing resume (PDF or Word)

1. Open your resume and copy all text, or upload the file directly to Claude/ChatGPT
2. Use this prompt:

```
Convert this resume into a YAML profile file for a job application assistant.
Use this exact structure (copy from config/profile.example.yaml):

[paste config/profile.example.yaml]

Resume:
[paste or attach your resume]

Output only valid YAML.
```

### Option 3: Write it yourself from scratch

Ask the AI to interview you:

```
I need to create a profile.yaml file for a job application assistant.
Please ask me questions one by one about my work experience, skills, education,
and achievements, then generate the YAML at the end using this structure:

[paste config/profile.example.yaml]
```

### Tips for a better profile

- **Be specific in bullet points** — quantify achievements ("Reduced latency by 40%", "Led team of 8 engineers") rather than vague descriptions. The LLM uses these verbatim in your resume.
- **List all skills** — even ones you consider basic. The keyword extractor matches these against job descriptions for ATS scoring.
- **Update the summary** — write it in first person and focus on the kind of roles you're targeting now, not a generic overview.
- **Keep `profile.yaml` private** — it's in `.gitignore` and should never be committed to a public repo.

## Notes

- **LLM Provider** — Groq is the default (free and fast). To use Anthropic instead, set `provider: anthropic` in `config/settings.yaml` and add `ANTHROPIC_API_KEY` to your `.env` file.
- **WeasyPrint** — Required for PDF output. If you only need DOCX, you can skip installing it. On macOS you may need `brew install pango` first.
- **Data storage** — Applications are stored in a SQLite database (`data/tracker.db`). If upgrading from a previous JSON-based version, existing `applications.json` data is auto-migrated on first run.
- **LinkedIn cookies** — Cookies expire periodically. Re-export them when referral searches stop working.
- **Scheduled scouting** — The bot must be running for scheduled scouts to work. Send `/start` to your bot first so it knows your chat ID.

## License

MIT
