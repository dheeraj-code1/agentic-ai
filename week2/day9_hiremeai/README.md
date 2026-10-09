# HireMeAI

Naukri auto-apply bot. A Selenium bot searches jobs, scores each JD against your resume, and applies to good matches, answering screening questions with an LLM.

- `backend/` – FastAPI app (Groq LLM): `/score` (resume vs JD match) and `/chat_naukari` (answers screening questions)
- `bot/` – Selenium bot that logs in to Naukri and applies
- `utils/mailer.py` – Gmail SMTP helper

## Requirements

- Python 3.11+
- Google Chrome (the matching ChromeDriver is downloaded automatically)
- A [Groq API key](https://console.groq.com/keys)

## Setup

1. Clone and enter the project:

```bash
git clone https://github.com/dheeraj-code1/agentic-ai.git
cd agentic-ai/week2/day9_hiremeai
```

2. Install dependencies, with uv:

```bash
uv sync
```

or with pip:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

3. Create the env files from the samples (`.env` files are gitignored):

```bash
cp backend/.env.sample backend/.env
cp bot/.env.sample bot/.env
```

4. Fill in your values:

| File | Variable | Value |
|---|---|---|
| `backend/.env` | `GROQ_API_KEY` | Your Groq API key |
| `backend/.env` | `GMAIL_SENDER`, `GMAIL_APP_PASSWORD` | Optional, for `utils/mailer.py` ([Gmail App Password](https://myaccount.google.com/apppasswords)) |
| `bot/.env` | `NAUKRI_EMAIL`, `NAUKRI_PASSWORD` | Your Naukri login (keep the password in quotes) |
| `bot/.env` | `CHAT_API_URL`, `SCORE_API_URL` | Optional, only if the backend is not on `127.0.0.1:8000` |

## Resume

On first start the backend parses your resume into `backend/profile.json`. Set `resume_path` in `backend/main.py` to your PDF/DOCX before the first run. Delete `profile.json` to re-parse.

Also update `personal_informations` in `backend/main.py` (salary, notice period, etc.) – it is used to answer screening questions.

## Run

Start the backend (from `backend/`, since it reads `profile.json` from the current folder):

```bash
cd backend
uv run uvicorn main:app --reload --port 8000
```

In another terminal, start the bot:

```bash
cd bot
uv run python main.py
```

Without uv, activate `.venv` and drop the `uv run` prefix.

## Bot settings

Edit the constants at the top of `bot/main.py`:

| Setting | Meaning |
|---|---|
| `SEARCH_KEYWORD` | Job search text |
| `MAX_JOBS_TO_APPLY` | Stop after this many applications |
| `MAX_JOBS_TO_CHECK` / `MAX_PAGES` | Limits on jobs opened and result pages walked |
| `FRESHNESS_DAYS`, `EXPERIENCE_YEARS` | Naukri filters |
| `SCORE_FILTER_ENABLED`, `MIN_MATCH_SCORE` | Apply only if the JD score is at least this |
| `EXCLUDED_COMPANIES` | Companies to skip (empty list = none) |
| `LOCATION_FILTER_ENABLED`, `LOCATIONS` | Location filter on/off and which cities |
| `HEADLESS_MODE` | Run Chrome without a window |

Jobs that pass the score but only offer "Apply on company site" are saved to `bot/company_site_jobs.csv`.

## Test the score API

With the backend running, `test.py` sends the JD in `test.txt` to `/score`:

```bash
uv run python test.py
```

## Notes

- Groq's free tier allows about 200k tokens/day for `openai/gpt-oss-20b`. Each `/score` call uses about 2k tokens; when the limit is hit, the API returns errors until it resets.
