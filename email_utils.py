def fetch_new_emails(limit: int = 20) -> list[dict]:
    """
    Connect via IMAP, fetch unread emails, return structured data.
    Returns list of dicts with: from_email, subject, body, received_at, message_id
    """

def create_inquiry_from_email(email_data: dict) -> str | None:
    """
    Insert into Supabase inquiries table with channel="Email".
    Returns inquiry_id or None on failure.
    """

def send_email_reply(to_email: str, subject: str, body: str, reply_to_message_id: str = None) -> bool:
    """
    Send reply via SMTP (Gmail App Password or Outlook).
    """
