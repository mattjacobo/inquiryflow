from twilio.rest import Client
import os

def send_sms(to_number: str, message: str):
    """Send SMS using Twilio API Key (recommended)."""
    account_sid = os.getenv("TWILIO_ACCOUNT_SID")
    api_key_sid = os.getenv("TWILIO_API_KEY_SID")
    api_key_secret = os.getenv("TWILIO_API_KEY_SECRET")
    from_number = os.getenv("TWILIO_PHONE_NUMBER")

    client = Client(api_key_sid, api_key_secret, account_sid)

    try:
        message = client.messages.create(
            body=message,
            from_=from_number,
            to=to_number
        )
        print(f"SMS sent successfully. SID: {message.sid}")
        return True
    except Exception as e:
        print(f"Failed to send SMS: {e}")
        return False
