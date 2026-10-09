import csv
import html as html_lib
import mimetypes
import os
import smtplib
import ssl
from datetime import datetime
from email.message import EmailMessage
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")
load_dotenv(PROJECT_ROOT / "backend" / ".env")

SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 465
SENDER_EMAIL = os.getenv("GMAIL_SENDER", "None")
REPORT_EMAIL_TO = os.getenv("REPORT_EMAIL_TO", SENDER_EMAIL)


def send_email(subject, body, to=None, attachments=None, html=False):
    """Send an email from SENDER_EMAIL through Gmail SMTP.

    Gmail rejects the normal account password here; GMAIL_APP_PASSWORD must be
    a 16-character App Password (Google Account > Security > App passwords).
    """
    app_password = os.getenv("GMAIL_APP_PASSWORD")
    if not app_password:
        raise ValueError("GMAIL_APP_PASSWORD not found in .env")

    recipients = to or [SENDER_EMAIL]
    if isinstance(recipients, str):
        recipients = [r.strip() for r in recipients.split(",") if r.strip()]

    message = EmailMessage()
    message["From"] = SENDER_EMAIL
    message["To"] = ", ".join(recipients)
    message["Subject"] = subject
    if html:
        message.set_content("This email needs an HTML-capable client.")
        message.add_alternative(body, subtype="html")
    else:
        message.set_content(body)

    for attachment in attachments or []:
        path = Path(attachment)
        mime_type, _ = mimetypes.guess_type(path.name)
        maintype, subtype = (mime_type or "application/octet-stream").split("/", 1)
        message.add_attachment(
            path.read_bytes(), maintype=maintype, subtype=subtype, filename=path.name
        )

    with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, context=ssl.create_default_context()) as server:
        server.login(SENDER_EMAIL, app_password.replace(" ", ""))
        server.send_message(message)

    print(f"Email sent to {', '.join(recipients)}: {subject}")


COUNT_LABELS = {
    "applied": "Applied",
    "skipped_company_site": "Skipped - apply on company site",
    "skipped_low_score": "Skipped - low match score",
    "skipped_excluded_company": "Skipped - excluded company",
    "skipped_already_applied": "Skipped - already applied",
    "skipped_questions": "Skipped - screening questions",
    "failed": "Failed",
}


def _jobs_table(jobs):
    if not jobs:
        return "<p>None</p>"
    rows = "".join(
        f"<tr><td>{html_lib.escape(j.get('title') or '')}</td>"
        f"<td>{html_lib.escape(j.get('company') or '')}</td>"
        f"<td>{j.get('score') or '-'}</td>"
        f"<td><a href='{html_lib.escape(j.get('url') or '')}'>Link</a></td></tr>"
        for j in jobs
    )
    return (
        '<table border="1" cellpadding="5" cellspacing="0">'
        "<tr><th>Title</th><th>Company</th><th>Score</th><th>URL</th></tr>"
        f"{rows}</table>"
    )


def send_job_report(counts, applied_jobs, company_site_jobs, attempts, pages_visited,
                    company_site_csv=None, applied_csv=None, to=None):
    """Email a summary of one bot run, attaching the job CSVs that exist."""
    today = datetime.now().strftime("%d %b %Y %H:%M")
    count_rows = "".join(
        f"<tr><td>{label}</td><td>{counts.get(key, 0)}</td></tr>"
        for key, label in COUNT_LABELS.items()
    )

    total_company_site = 0
    if company_site_csv and Path(company_site_csv).exists():
        with open(company_site_csv, newline="", encoding="utf-8") as f:
            total_company_site = sum(1 for _ in csv.DictReader(f))

    body = f"""
<h2>HireMeAI - Naukri Job Apply Summary ({today})</h2>
<table border="1" cellpadding="5" cellspacing="0">
<tr><td>Jobs opened</td><td>{attempts}</td></tr>
<tr><td>Pages visited</td><td>{pages_visited}</td></tr>
{count_rows}
</table>
<h3>Applied this run ({len(applied_jobs)})</h3>
{_jobs_table(applied_jobs)}
<h3>Company-site jobs this run ({len(company_site_jobs)})</h3>
{_jobs_table(company_site_jobs)}
<p>All saved company-site jobs: {total_company_site} (see attached CSV).</p>
"""
    attachments = [p for p in (company_site_csv, applied_csv) if p and Path(p).exists()]
    send_email(
        f"HireMeAI: Applied {counts.get('applied', 0)} job(s) - {today}",
        body,
        to=to or REPORT_EMAIL_TO,
        attachments=attachments,
        html=True,
    )


if __name__ == "__main__":
    send_email("HireMeAI test email", "If you can read this, Gmail SMTP is working.")
 