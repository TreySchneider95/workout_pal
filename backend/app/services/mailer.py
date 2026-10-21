"""Outgoing email over SMTP (configured with WORKOUT_SMTP_* environment variables)."""

import smtplib
import ssl
from email.message import EmailMessage

from app.config import get_settings


class EmailError(Exception):
    pass


def send_email(to: str, subject: str, body: str, attachments: list[tuple[str, str]] = ()) -> None:
    """Send a plain-text email. `attachments` are (filename, text) pairs."""
    settings = get_settings()
    if not settings.email_enabled:
        raise EmailError("Email isn't set up on the server")

    message = EmailMessage()
    message["From"] = settings.smtp_from or settings.smtp_username
    message["To"] = to
    message["Subject"] = subject
    message.set_content(body)
    for filename, text in attachments:
        message.add_attachment(text.encode("utf-8"), maintype="text", subtype="plain", filename=filename)

    try:
        if settings.smtp_security == "ssl":
            smtp = smtplib.SMTP_SSL(settings.smtp_host, settings.smtp_port, timeout=20,
                                    context=ssl.create_default_context())
        else:
            smtp = smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=20)
        with smtp:
            if settings.smtp_security == "starttls":
                smtp.starttls(context=ssl.create_default_context())
            if settings.smtp_username:
                smtp.login(settings.smtp_username, settings.smtp_password or "")
            smtp.send_message(message)
    except smtplib.SMTPAuthenticationError as exc:
        raise EmailError("The mail server rejected the username or password") from exc
    except (smtplib.SMTPException, OSError) as exc:
        raise EmailError(f"Couldn't send the email: {exc}") from exc
