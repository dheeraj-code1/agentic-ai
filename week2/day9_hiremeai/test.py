import json
import os
import re
import sys
import urllib.error
import urllib.request
from html.parser import HTMLParser
from pathlib import Path

SCORE_API_URL = os.getenv("SCORE_API_URL", "http://127.0.0.1:8000/score")
JD_FILE = Path(__file__).with_name("test.txt")
TITLE = "Data Engineer"

BLOCK_TAGS = {
    "p", "div", "section", "ul", "ol", "li", "br", "h1", "h2", "h3", "h4",
    "h5", "h6", "label", "tr", "table",
}


class InnerTextParser(HTMLParser):
    """Rough stand-in for the browser's innerText, which the bot sends."""

    def __init__(self):
        super().__init__()
        self.parts = []

    def handle_starttag(self, tag, attrs):
        if tag in BLOCK_TAGS:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in BLOCK_TAGS:
            self.parts.append("\n")

    def handle_data(self, data):
        self.parts.append(data)

    def text(self):
        raw = "".join(self.parts)
        lines = [re.sub(r"[ \t\xa0]+", " ", line).strip() for line in raw.splitlines()]
        return "\n".join(line for line in lines if line)


def html_to_text(html):
    parser = InnerTextParser()
    parser.feed(html)
    return parser.text()


def score(title, job_description):
    payload = json.dumps({"title": title, "job_description": job_description}).encode("utf-8")
    request = urllib.request.Request(
        SCORE_API_URL,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=90) as response:
        return json.loads(response.read().decode("utf-8", errors="replace"))


def main():
    jd = html_to_text(JD_FILE.read_text(encoding="utf-8"))

    print("========== SCORE REQUEST ==========")
    print(f"URL: {SCORE_API_URL}")
    print(f"Title: {TITLE}")
    print(f"JD ({len(jd)} chars):")
    print(jd)
    print("========== END REQUEST ==========\n")

    try:
        result = score(TITLE, jd)
    except urllib.error.URLError as exc:
        print(f"Score API is not reachable at {SCORE_API_URL}: {exc}")
        print("Start it with: cd backend && uv run uvicorn main:app --reload --port 8000")
        sys.exit(1)

    print("========== SCORE RESPONSE ==========")
    print(result)
    print("========== END RESPONSE ==========")


def test_email_report():
    import csv
    from bot import main as bot

    company_site_csv = Path(__file__).parent / "bot" / bot.COMPANY_SITE_JOBS_FILE
    with open(company_site_csv, newline="", encoding="utf-8") as f:
        company_site_jobs = list(csv.DictReader(f))

    bot.SEND_REPORT_EMAIL = True
    bot.COMPANY_SITE_JOBS_FILE = str(company_site_csv)
    bot.APPLIED_JOBS_FILE = str(Path(__file__).parent / "bot" / bot.APPLIED_JOBS_FILE)

    run = {
        "counts": {"applied": 0, "skipped_company_site": len(company_site_jobs)},
        "applied_jobs": [],
        "company_site_jobs": company_site_jobs,
        "attempts": len(company_site_jobs),
        "pages_visited": 1,
    }
    bot.email_run_report(run)


if __name__ == "__main__":
    if sys.argv[1:] == ["email"]:
        test_email_report()
    else:
        main()
