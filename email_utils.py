"""
email_utils.py
Phase 1 – Email Intake utilities for InquiryFlow
"""

import imaplib
import email
from email.header import decode_header
from email.utils import parseaddr
from datetime import datetime
import os
from typing import Optional
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()

# ============================================================
# Configuration
# ============================================================
EMAIL_HOST = os.getenv("EMAIL_HOST", "imap.gmail.com")
EMAIL_PORT = int(os.getenv("EMAIL_PORT", 993))
EMAIL_USER = os.getenv("EMAIL_USER")
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD")  # Gmail App Password

SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", 587))

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)


# ============================================================
# Helper: Decode email headers safely
# ============================================================
def decode_mime_words(s: str) -> str:
    if not s:
        return ""
    decoded = decode_header(s)
    parts = []
    for content, encoding in decoded:
        if isinstance(content, bytes):
            parts.append(content.decode(encoding or "utf-8", errors="ignore"))
        else:
            parts.append(content)
    return "".join(parts)


# ============================================================
# 1. Fetch new (unread) emails
# ============================================================
def fetch_new_emails(limit: int = 15) -> list[dict]:
    """
    Connects to the inbox via IMAP and returns a list of unread emails.
    Each item contains: from_email, from_name, subject, body, message_id, received_at
    """
    if not all([EMAIL_USER, EMAIL_PASSWORD]):
        raise ValueError("EMAIL_USER and EMAIL_PASSWORD must be set in environment variables.")

    emails = []

    try:
        mail = imaplib.IMAP4_SSL(EMAIL_HOST, EMAIL_PORT)
        mail.login(EMAIL_USER, EMAIL_PASSWORD)
        mail.select("INBOX")

        # Search for unread emails
        status, messages = mail.search(None, "UNSEEN")
        if status != "OK":
            return []

        email_ids = messages[0].split()
        # Get the most recent ones
        email_ids = email_ids[-limit:] if len(email_ids) > limit else email_ids

        for e_id in reversed(email_ids):  # newest first
            status, msg_data = mail.fetch(e_id, "(RFC822)")
            if status != "OK":
                continue

            raw_email = msg_data[0][1]
            msg = email.message_from_bytes(raw_email)

            # Sender
            from_header = msg.get("From", "")
            from_name, from_email = parseaddr(from_header)
            from_name = decode_mime_words(from_name)

            # Subject
            subject = decode_mime_words(msg.get("Subject", "(No Subject)"))

            # Message-ID (useful for threading later)
            message_id = msg.get("Message-ID", "")

            # Body
            body = ""
            if msg.is_multipart():
                for part in msg.walk():
                    content_type = part.get_content_type()
                    content_disposition = str(part.get("Content-Disposition"))

                    if content_type == "text/plain" and "attachment" not in content_disposition:
                        try:
                            body = part.get_payload(decode=True).decode(errors="ignore")
                            break
                        except Exception:
                            continue
            else:
                try:
                    body = msg.get_payload(decode=True).decode(errors="ignore")
                except Exception:
                    body = str(msg.get_payload())

            emails.append({
                "from_email": from_email.lower().strip(),
                "from_name": from_name.strip() if from_name else None,
                "subject": subject,
                "body": body.strip(),
                "message_id": message_id,
                "received_at": datetime.utcnow().isoformat()
            })

            # Mark as read so we don't process it again
            mail.store(e_id, "+FLAGS", "\\Seen")

        mail.logout()
        return emails

    except Exception as e:
        print(f"Error fetching emails: {e}")
        return []


# ============================================================
# 2. Create inquiry from email data
# ============================================================
def create_inquiry_from_email(email_data: dict) -> Optional[str]:
    """
    Inserts a new inquiry into Supabase using the agreed conventions.
    Returns the new inquiry id or None on failure.
    """
    try:
        inquiry_number = f"EMAIL-{datetime.utcnow().strftime('%Y%m%d-%H%M%S')}"

        data = {
            "inquiry_number": inquiry_number,
            "customer_identifier": email_data["from_email"],
            "customer_name": email_data.get("from_name"),
            "channel": "Email",
            "original_text": email_data["body"] or email_data.get("subject", ""),
            "status": "pending_review",
            "metadata": {
                "subject": email_data.get("subject"),
                "message_id": email_data.get("message_id"),
                "received_at": email_data.get("received_at")
            }
            # source is left as null on purpose
        }

        result = supabase.table("inquiries").insert(data).execute()

        if result.data:
            return result.data[0]["id"]
        return None

    except Exception as e:
        print(f"Error creating inquiry from email: {e}")
        return None


# ============================================================
# 3. High-level helper: Fetch + Create
# ============================================================
def process_new_emails(auto_process: bool = False) -> list[str]:
    """
    Fetches new emails and creates inquiry records.
    Returns list of created inquiry IDs.
    
    Set auto_process=True later if you want to automatically run the AI workflow.
    """
    new_emails = fetch_new_emails()
    created_ids = []

    for email_data in new_emails:
        inquiry_id = create_inquiry_from_email(email_data)
        if inquiry_id:
            created_ids.append(inquiry_id)
            print(f"Created inquiry {inquiry_id} from {email_data['from_email']}")

    return created_ids


# ============================================================
# 4. Send reply via email (basic version)
# ============================================================
def send_email_reply(to_email: str, subject: str, body: str) -> bool:
    """
    Sends a plain text email reply using SMTP.
    """
    import smtplib
    from email.mime.text import MIMEText

    try:
        msg = MIMEText(body)
        msg["Subject"] = subject if subject.lower().startswith("re:") else f"Re: {subject}"
        msg["From"] = EMAIL_USER
        msg["To"] = to_email

        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.starttls()
            server.login(EMAIL_USER, EMAIL_PASSWORD)
            server.send_message(msg)

        return True
    except Exception as e:
        print(f"Failed to send email: {e}")
        return False
