"""
Transactional email over SMTP with STARTTLS (e.g. Gmail with an App Password).
"""
import asyncio
import html
import logging
import os
import smtplib
from email.message import EmailMessage
from email.utils import make_msgid

logger = logging.getLogger(__name__)

SMTP_HOST = os.getenv('SMTP_HOST', 'smtp.gmail.com')
SMTP_PORT = int(os.getenv('SMTP_PORT', '587'))
SMTP_USER = os.getenv('SMTP_USER', '')
SMTP_PASSWORD = os.getenv('SMTP_PASSWORD', '')
SMTP_FROM_EMAIL = os.getenv('SMTP_FROM_EMAIL', '') or (f'UPGRADE <{SMTP_USER}>' if SMTP_USER else '')

FRONTEND_URL = os.getenv('FRONTEND_URL', 'http://localhost:3000').rstrip('/')


class EmailSendError(Exception):
    """Raised when an email could not be handed off to the SMTP server."""


def _smtp_send_blocking(message: EmailMessage) -> None:
    with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=15) as server:
        server.starttls()
        server.login(SMTP_USER, SMTP_PASSWORD)
        server.send_message(message)


async def send_email(to: str, subject: str, html_body: str, text_body: str) -> str:
    """
    Send one email (plain text + HTML alternative).

    Returns:
        Message-ID of the sent email

    Raises:
        EmailSendError: if SMTP is not configured or the server rejects the email
    """
    if not (SMTP_USER and SMTP_PASSWORD):
        raise EmailSendError("SMTP_USER / SMTP_PASSWORD are not configured")

    message = EmailMessage()
    message['From'] = SMTP_FROM_EMAIL
    message['To'] = to
    message['Subject'] = subject
    message['Message-ID'] = make_msgid(domain=SMTP_USER.split('@')[-1])
    message.set_content(text_body)
    message.add_alternative(html_body, subtype='html')

    try:
        # smtplib is blocking; keep it off the event loop
        await asyncio.to_thread(_smtp_send_blocking, message)
    except (smtplib.SMTPException, OSError) as e:
        raise EmailSendError(f"SMTP send failed: {e}") from e

    logger.info(f"Email sent via SMTP (id={message['Message-ID']}, subject={subject!r})")
    return message['Message-ID']



def build_verification_link(token: str) -> str:
    return f"{FRONTEND_URL}/verify-email?token={token}"


async def send_verification_email(to: str, username: str, token: str) -> str:
    """Send the signup confirmation email containing a one-time link."""
    link = build_verification_link(token)
    safe_name = html.escape(username)
    safe_link = html.escape(link, quote=True)

    subject = 'Confirm your UPGRADE account'
    text_body = (
        f"Hi {username},\n\n"
        "Thanks for signing up for UPGRADE - Urban Pathogen Genomic Surveillance Platform.\n\n"
        f"Confirm your email address by opening this link:\n{link}\n\n"
        "The link expires in 24 hours and can be used once.\n"
        "If you did not create this account, you can ignore this email.\n"
    )
    html_body = f"""\
<!doctype html>
<html>
  <body style="margin:0;padding:0;background:#f1f5f9;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Arial,sans-serif;">
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#f1f5f9;padding:32px 16px;">
      <tr>
        <td align="center">
          <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:520px;background:#ffffff;border-radius:12px;padding:40px 32px;">
            <tr>
              <td>
                <div style="font-size:26px;font-weight:800;color:#0052ff;letter-spacing:-0.5px;">UPGRADE</div>
                <div style="font-size:11px;font-weight:600;letter-spacing:1px;color:#94a3b8;text-transform:uppercase;margin-top:4px;">
                  Urban Pathogen Genomic Surveillance Platform
                </div>
                <h1 style="font-size:20px;color:#0f172a;margin:32px 0 12px;">Confirm your email address</h1>
                <p style="font-size:15px;line-height:1.6;color:#475569;margin:0 0 24px;">
                  Hi {safe_name}, thanks for signing up. Click the button below to activate your account.
                </p>
                <a href="{safe_link}" style="display:inline-block;background:#0052ff;color:#ffffff;text-decoration:none;font-weight:600;font-size:15px;padding:12px 28px;border-radius:8px;">
                  Confirm email
                </a>
                <p style="font-size:13px;line-height:1.6;color:#64748b;margin:28px 0 0;">
                  Or paste this link into your browser:<br>
                  <a href="{safe_link}" style="color:#0052ff;word-break:break-all;">{safe_link}</a>
                </p>
                <p style="font-size:13px;line-height:1.6;color:#94a3b8;margin:24px 0 0;">
                  The link expires in 24 hours and can be used once. If you did not create this account, you can ignore this email.
                </p>
              </td>
            </tr>
          </table>
        </td>
      </tr>
    </table>
  </body>
</html>
"""
    return await send_email(to, subject, html_body, text_body)


def build_frontend_link(path: str) -> str:
    return f"{FRONTEND_URL}/{path.lstrip('/')}"


async def send_pipeline_finished_email(
    to: str,
    username: str,
    sample_label: str,
    succeeded: bool,
    link: str,
    details: list[tuple[str, str]],
    error_message: str | None = None,
) -> str:
    """
    Tell a user that the analysis of one of their samples finished.

    Args:
        details: (label, value) rows shown as a summary table, e.g. [('Duration', '2h 14m')]
        error_message: reason shown for a failed run
    """
    safe_name = html.escape(username)
    safe_label = html.escape(sample_label)
    safe_link = html.escape(link, quote=True)

    if succeeded:
        subject = f'Analysis completed: {sample_label}'
        heading = 'Your analysis is complete'
        intro = f'The pipeline finished processing sample <strong>{safe_label}</strong>. The results are ready to view.'
        intro_text = f'The pipeline finished processing sample {sample_label}. The results are ready to view.'
        button = 'View results'
        accent = '#0052ff'
    else:
        subject = f'Analysis failed: {sample_label}'
        heading = 'Your analysis failed'
        intro = f'The pipeline could not finish processing sample <strong>{safe_label}</strong>.'
        intro_text = f'The pipeline could not finish processing sample {sample_label}.'
        button = 'Open pipeline details'
        accent = '#dc2626'

    rows_html = ''.join(
        f'<tr><td style="padding:6px 0;color:#64748b;font-size:14px;">{html.escape(label)}</td>'
        f'<td style="padding:6px 0;color:#0f172a;font-size:14px;font-weight:600;text-align:right;">{html.escape(value)}</td></tr>'
        for label, value in details
    )
    rows_text = ''.join(f"  {label}: {value}\n" for label, value in details)

    error_html = ''
    error_text = ''
    if not succeeded and error_message:
        error_html = (
            '<div style="margin:0 0 24px;padding:12px 14px;background:#fef2f2;border-radius:8px;'
            'color:#991b1b;font-size:13px;line-height:1.5;font-family:SFMono-Regular,Consolas,monospace;'
            f'white-space:pre-wrap;word-break:break-word;">{html.escape(error_message)}</div>'
        )
        error_text = f"Error:\n{error_message}\n\n"

    text_body = (
        f"Hi {username},\n\n"
        f"{intro_text}\n\n"
        f"{rows_text}\n"
        f"{error_text}"
        f"{button}: {link}\n\n"
        "You receive this email because email notifications are turned on in your UPGRADE profile.\n"
    )
    html_body = f"""\
<!doctype html>
<html>
  <body style="margin:0;padding:0;background:#f1f5f9;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Arial,sans-serif;">
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#f1f5f9;padding:32px 16px;">
      <tr>
        <td align="center">
          <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:520px;background:#ffffff;border-radius:12px;padding:40px 32px;">
            <tr>
              <td>
                <div style="font-size:26px;font-weight:800;color:#0052ff;letter-spacing:-0.5px;">UPGRADE</div>
                <div style="font-size:11px;font-weight:600;letter-spacing:1px;color:#94a3b8;text-transform:uppercase;margin-top:4px;">
                  Urban Pathogen Genomic Surveillance Platform
                </div>
                <h1 style="font-size:20px;color:#0f172a;margin:32px 0 12px;">{heading}</h1>
                <p style="font-size:15px;line-height:1.6;color:#475569;margin:0 0 20px;">
                  Hi {safe_name}, {intro}
                </p>
                <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="border-top:1px solid #e2e8f0;border-bottom:1px solid #e2e8f0;margin:0 0 24px;padding:6px 0;">
                  {rows_html}
                </table>
                {error_html}
                <a href="{safe_link}" style="display:inline-block;background:{accent};color:#ffffff;text-decoration:none;font-weight:600;font-size:15px;padding:12px 28px;border-radius:8px;">
                  {button}
                </a>
                <p style="font-size:13px;line-height:1.6;color:#94a3b8;margin:28px 0 0;">
                  You receive this email because email notifications are turned on in your UPGRADE profile.
                </p>
              </td>
            </tr>
          </table>
        </td>
      </tr>
    </table>
  </body>
</html>
"""
    return await send_email(to, subject, html_body, text_body)
