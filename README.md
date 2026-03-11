# merinaukri — AI Job Application Assistant

A personal job application assistant that automates job discovery, generates ATS-optimized resumes and cover letters, finds LinkedIn referrals, and provides a web dashboard to track everything — all controlled via a Telegram bot.

## Features

- **Job Discovery** — Searches Indeed, LinkedIn, and Glassdoor using [python-jobspy](https://github.com/Bunsly/JobSpy)
- **Automated Scout** — Runs job searches on a schedule (default: every 6 hours) and sends new matches to Telegram
- **ATS-Optimized Resume Generation** — Extracts keywords from job descriptions and tailors your resume with keyword matching and ATS score
- **Cover Letter Generation** — Creates targeted cover letters for each role
- **LinkedIn Referral Finder** — Searches your LinkedIn connections (1st and 2nd degree) at the target company using cookie-based Voyager API
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

## Prerequisites

- Python 3.13+
- A [Groq API key](https://console.groq.com/) (free tier available)
- A Telegram bot token (create one via [@BotFather](https://t.me/BotFather))
- LinkedIn browser cookies exported as JSON (for referral search)

## Setup

### 1. Clone the repo

```bash
git clone https://github.com/sanggpel/naukri.git
cd naukri
```

### 2. Create a virtual environment

```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
pip install "python-telegram-bot[job-queue]"  # required for scheduled scouting
pip install python-multipart                   # required for web dashboard forms
pip install uvicorn                             # required for web dashboard
```

### 4. Set up environment variables

Create a `.env` file in the project root:

```
GROQ_API_KEY=your_groq_api_key_here
```

### 5. Configure your profile

Edit `config/profile.yaml` with your own details:

```yaml
name: "Your Name"
email: "you@example.com"
phone: "(555) 123-4567"
location: "Your City, State, Country"
citizenship: "Your Citizenship"
linkedin_url: "https://www.linkedin.com/in/yourprofile/"

summary: >
  Your professional summary here...

skills:
  Category1:
    - Skill A
    - Skill B
  Category2:
    - Skill C

experience:
  - title: "Your Title"
    company: "Company Name"
    start: "2020"
    end: "Present"
    location: "City, Country"
    bullets:
      - "Achievement 1"
      - "Achievement 2"

education:
  - institution: "University Name"
    degree: "Degree"
    field: "Field of Study"
    years: "2015-2019"
```

### 6. Configure settings

Edit `config/settings.yaml`:

```yaml
llm:
  provider: groq                          # or "anthropic"
  groq_model: llama-3.3-70b-versatile
  anthropic_model: claude-sonnet-4-20250514  # only if using anthropic
  max_tokens: 4096

telegram:
  merinaukri: YOUR_TELEGRAM_BOT_TOKEN

linkedin:
  cookies_file: cookies.json              # path to your exported LinkedIn cookies
  rate_limit_seconds: 3
  cache_ttl_hours: 24

discovery:
  default_sources:
    - linkedin
    - indeed
  default_location: "Your City, State, Country"
  default_country: "Your Country"
  max_results: 30

scout:
  queries:
    - "Software Engineer"
    - "Backend Developer"
    # add your target job titles
  location: "Your Country"
  country: "Your Country"
  sources:
    - indeed
    - linkedin
    - glassdoor
  max_per_query: 15
  remote_only: false
  interval_hours: 6
  chat_id: null                           # auto-populated when you send /start to your bot

output:
  format: pdf
  resume_template: templates/resume_template.html
  cover_letter_template: templates/cover_letter_template.html
```

### 7. Export LinkedIn cookies (for referral search)

1. Log into LinkedIn in your browser
2. Use a browser extension like [Cookie-Editor](https://cookie-editor.com/) to export cookies as JSON
3. Save the exported JSON file (e.g., `cookies.json`) in the project root
4. Update the `cookies_file` path in `config/settings.yaml`

## Running

### Start the Telegram bot

```bash
python main.py
```

### Start the web dashboard

```bash
python dashboard.py
```

The dashboard will be available at `http://127.0.0.1:8080`.

You can run both simultaneously in separate terminals.

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
│   ├── profile.yaml           # Your resume/profile data
│   └── settings.yaml          # LLM, Telegram, LinkedIn, scout config
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
