"""
Send a weekly report (email + SMS) listing questions the app couldn't answer.
Runs from the scheduler Saturday morning. Email via Gmail SMTP; SMS via Twilio.
"""
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from config import config
from database import db


def send_unanswered_report() -> bool:
    """
    If there are pending unanswered questions, send email (Gmail SMTP) and SMS summary.
    Clears the list after sending. Returns True if at least one was sent.
    """
    rows = db.get_pending_unanswered_questions()
    if not rows:
        return False
    n = len(rows)
    to_email = getattr(config, "UNANSWERED_REPORT_EMAIL_TO", "").strip()
    sms_to = getattr(config, "UNANSWERED_REPORT_SMS_TO", "").strip()
    host = getattr(config, "UNANSWERED_REPORT_SMTP_HOST", "").strip()
    port = getattr(config, "UNANSWERED_REPORT_SMTP_PORT", 587)
    user = getattr(config, "UNANSWERED_REPORT_SMTP_USER", "").strip()
    password = getattr(config, "UNANSWERED_REPORT_SMTP_PASSWORD", "")
    from_addr = getattr(config, "UNANSWERED_REPORT_SMTP_FROM", "").strip() or user or to_email

    lines = []
    for _id, transcript, source, created_at in rows:
        ts = str(created_at)[:19] if created_at else ""
        lines.append(f"- [{ts}] ({source}) {transcript}")
    body = "Questions we couldn't answer (fallback 'still learning' was used):\n\n" + "\n".join(lines)
    subject = f"Zarchbot: {n} question(s) we couldn't answer"

    email_ok = False
    if to_email and host and user and password:
        try:
            msg = MIMEMultipart()
            msg["Subject"] = subject
            msg["From"] = from_addr
            msg["To"] = to_email
            msg.attach(MIMEText(body, "plain"))
            with smtplib.SMTP(host, port, timeout=30) as s:
                if port == 587:
                    s.starttls()
                s.login(user, password)
                s.sendmail(from_addr, [to_email], msg.as_string())
            email_ok = True
        except Exception as e:
            print(f"Unanswered report email failed: {e}")

    if sms_to:
        try:
            from twilio_handler import twilio_handler
            sms_body = f"Zarchbot: {n} question(s) we couldn't answer this week. Check email for the list."
            twilio_handler.send_sms(sms_to, sms_body[:160])
        except Exception as e:
            print(f"Unanswered report SMS failed: {e}")

    if email_ok:
        db.delete_unanswered_questions(ids=[r[0] for r in rows])
        return True
    return False
