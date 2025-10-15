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

    # Parse multiple recipients (comma or semicolon separated)
    # Support formats: "email1@example.com,email2@example.com" or "email1@example.com; email2@example.com"
    recipients = [r.strip() for r in recipient.replace(';', ',').split(',') if r.strip()]
    
    if not recipients:
        raise ValueError("No valid email recipients found in RECIPIENT_EMAIL")

    msg = MIMEMultipart("alternative")
    msg["From"] = sender
    msg["To"] = ", ".join(recipients)  # Display all recipients in header
    msg["Subject"] = subject

    if plain_text:
        part1 = MIMEText(plain_text, "plain")
        msg.attach(part1)
    part2 = MIMEText(html_content, "html")
    msg.attach(part2)

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(sender, password)
            # Send to all recipients
            server.sendmail(sender, recipients, msg.as_string())
        
        # Log success with recipient count
        recipient_display = recipients[0] if len(recipients) == 1 else f"{len(recipients)} recipients"
        print(f"✅ Email sent to {recipient_display}: {subject}")
    except Exception as e:
        print(f"❌ Email failed: {e}")
        raise