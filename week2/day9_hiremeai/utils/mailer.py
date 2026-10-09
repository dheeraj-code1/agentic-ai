import mimetypes
import os
import smtplib
import ssl
from email.message import EmailMessage
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")
load_dotenv(PROJECT_ROOT / "backend" / ".env")

SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 465
SENDER_EMAIL = os.getenv("GMAIL_SENDER", "dheeraj25062003@gmail.com")


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
        recipients = [recipients]

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


if __name__ == "__main__":
    send_email("HireMeAI test email", "If you can read this, Gmail SMTP is working.")
