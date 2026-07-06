from fastapi import FastAPI, Form
from datetime import datetime
import os
from dotenv import load_dotenv
from supabase import create_client, Client

load_dotenv()

app = FastAPI()

# Supabase setup
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)


@app.post("/webhook/sms")
async def receive_sms(
    From: str = Form(...),
    Body: str = Form(...),
):
    """Receive incoming SMS from Twilio and save it."""
    print(f"Received SMS from {From}: {Body}")

    try:
        data = {
            "customer_identifier": From,
            "channel": "SMS/Text",
            "original_text": Body,
            "status": "pending_review",
            "inquiry_number": f"SMS-{datetime.now().strftime('%Y%m%d%H%M%S')}"
        }
        supabase.table("inquiries").insert(data).execute()
        print("Inquiry saved to Supabase.")
    except Exception as e:
        print(f"Error saving inquiry: {e}")

    return {"status": "received"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
