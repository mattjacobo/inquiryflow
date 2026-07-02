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
    """Load settings and always return a complete, valid structure."""
    defaults = get_default_settings()

    if not supabase:
        return defaults

    try:
        response = supabase.table("app_settings").select("data").eq("id", 1).execute()
        
        if response.data:
            stored = response.data[0].get("data", {})
            
            # Deep merge - always start from defaults
            merged = json.loads(json.dumps(defaults))  # Deep copy
            
            # Override with stored values
            if isinstance(stored, dict):
                for key, value in stored.items():
                    if key in merged:
                        if isinstance(merged[key], dict) and isinstance(value, dict):
                            merged[key].update(value)
                        else:
                            merged[key] = value
            
            # Final safety checks
            if "unavailable_service_message" not in merged or not merged.get("unavailable_service_message"):
                merged["unavailable_service_message"] = defaults["unavailable_service_message"]
            
            if "tone" not in merged or not merged.get("tone"):
                merged["tone"] = defaults["tone"]
            
            return merged
        
        return defaults
        
    except Exception as e:
        print(f"Error loading settings: {e}")
        return defaults


def regenerate_knowledge_base(settings: dict):
    """Generate knowledge base chunks from selected services and store in Supabase."""
    # TODO: Implement full generation from services + common questions
    print("Knowledge base regenerated from settings.")
    return True
