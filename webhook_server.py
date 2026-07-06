from fastapi import FastAPI, Form
from twilio.rest import Client
import os
from dotenv import load_dotenv
from supabase import create_client, Client as SupabaseClient
from datetime import datetime

load_dotenv()

app = FastAPI()

# Twilio credentials
TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
TWILIO_PHONE_NUMBER = os.getenv("TWILIO_PHONE_NUMBER")

twilio_client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)

# Supabase
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
supabase: SupabaseClient = create_client(SUPABASE_URL, SUPABASE_KEY)


@app.post("/webhook/sms")
async def receive_sms(
    From: str = Form(...),
    Body: str = Form(...),
    MessageSid: str = Form(...)
):
    """Handle incoming SMS from Twilio."""
    print(f"Incoming SMS from {From}: {Body}")

    # Save to Supabase
    try:
        data = {
            "customer_identifier": From,
            "channel": "SMS/Text",
            "original_text": Body,
            "status": "pending_review",
            "inquiry_number": f"SMS-{datetime.now().strftime('%Y%m%d%H%M%S')}"
        }
        supabase.table("inquiries").insert(data).execute()
        print("Inquiry saved successfully.")
    except Exception as e:
        print(f"Error saving inquiry: {e}")

    return {"status": "received"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
