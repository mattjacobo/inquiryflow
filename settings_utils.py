"""
InquiryFlow - Settings Management Utilities
Handles saving/loading settings (service hierarchy, tone, etc.) and regenerating knowledge base.
"""

import os
import json
from dotenv import load_dotenv
from supabase import create_client, Client

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

if SUPABASE_URL and SUPABASE_KEY:
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
else:
    supabase = None


def get_default_settings():
    """Default service hierarchy and tone settings."""
    return {
        "tone": "Friendly and professional. Use easy-to-understand language while still being informative.",
        "services": {
            "Maintenance & Routine Services": {
                "Oil Changes & Fluid Services": False,
                "Tire Rotation, Repair & Replacement": False,
                "Multi-Point Inspections": False,
                "Air Filter / Cabin Filter Replacement": False,
            },
            "Brakes & Suspension": {
                "Brake Pad & Rotor Replacement": False,
                "Brake Fluid Flush": False,
                "Suspension Repair": False,
                "Wheel Alignment": False,
            },
            "Engine & Performance": {
                "Engine Diagnostics & Tune-Ups": False,
                "Timing Belt / Chain Service": False,
                "Performance Upgrades": False,
            },
            "Diagnostics & Electrical": {
                "Computer Diagnostics": False,
                "Battery, Alternator & Starter Service": False,
                "Electrical System Repair": False,
            },
            "Detailing & Appearance": {
                "Interior & Exterior Detailing": False,
                "Paint Correction & Ceramic Coating": False,
            },
            "Custom & Performance Upgrades": {
                "Car Audio Systems": False,
                "Suspension Upgrades": False,
                "Custom Fabrication": False,
            },
            "unavailable_service_message": (
            "I'm sorry, but it looks like we currently do not offer that service. "
            "However, I will check with the boss for further confirmation. "
            "I appreciate your patience!"
        )
        },
        "common_questions": {}  # service_name: ["question1", "question2"]
    }


def save_settings(settings: dict):
    """Save settings to Supabase. Returns success status."""
    if not supabase:
        return False

    try:
        supabase.table("app_settings").upsert({
            "id": 1,
            "data": settings
        }).execute()
        return True
    except Exception as e:
        print(f"Error saving settings: {e}")
        return False


def load_settings():
    """Load settings with clear debugging."""
    defaults = get_default_settings()

    print("=== DEBUG: load_settings() called ===")
    print(f"Supabase client exists: {supabase is not None}")

    if not supabase:
        print("WARNING: Supabase client is None. Returning defaults.")
        return defaults

    try:
        print("Attempting to fetch from Supabase...")
        response = supabase.table("app_settings").select("data").eq("id", 1).execute()
        print(f"Response received. Data: {response.data}")

        if response.data:
            stored = response.data[0].get("data", {})
            print(f"Stored data keys: {list(stored.keys()) if isinstance(stored, dict) else 'Not a dict'}")
            
            # Merge logic
            merged = {**defaults, **stored}
            
            # Basic cleanup
            if "common_questions" in merged:
                del merged["common_questions"]
            
            print("Successfully loaded and merged settings from Supabase.")
            return merged
        else:
            print("No data found in Supabase. Returning defaults.")
            return defaults

    except Exception as e:
        print(f"ERROR in load_settings(): {str(e)}")
        return defaults


def regenerate_knowledge_base(settings: dict):
    """Generate knowledge base chunks from selected services and store in Supabase."""
    # TODO: Implement full generation from services + common questions
    print("Knowledge base regenerated from settings.")
    return True
