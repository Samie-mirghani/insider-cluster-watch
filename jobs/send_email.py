# jobs/send_email.py
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import os

def send_email(subject, html_content, plain_text=None):
    sender = os.getenv("GMAIL_USER")
    password = os.getenv("GMAIL_APP_PASSWORD")
    recipient = os.getenv("RECIPIENT_EMAIL")
    if not sender or not password or not recipient:
        raise ValueError("Missing GMAIL_USER / GMAIL_APP_PASSWORD / RECIPIENT_EMAIL in environment")

    msg = MIMEMultipart("alternative")
    msg["From"] = sender
    msg["To"] = recipient
    msg["Subject"] = subject

    if plain_text:
        part1 = MIMEText(plain_text, "plain")
        msg.attach(part1)
    part2 = MIMEText(html_content, "html")
    msg.attach(part2)

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(sender, password)
            server.sendmail(sender, recipient, msg.as_string())
        print(f"✅ Email sent: {subject}")
    except Exception as e:
        print(f"❌ Email failed: {e}")
        raise
