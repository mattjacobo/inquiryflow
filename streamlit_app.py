"""
InquiryFlow Phase 1.5 — Streamlit Dashboard
"""

import streamlit as st
from typing import Optional

from datetime import datetime
from supabase import create_client, Client
from workflow import process_inquiry, InquiryState
from dotenv import load_dotenv
from rag_utils import process_and_store_documents
from settings_utils import load_settings, save_settings, regenerate_knowledge_base
from prompts import drafter_prompt, ai_coach_prompt
import tempfile
import os

from langchain_openai import ChatOpenAI
from langchain_core.output_parsers import StrOutputParser

load_dotenv()

from supabase import create_client, Client

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

if SUPABASE_URL and SUPABASE_KEY:
    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
else:
    supabase = None

# ====================== SESSION STATE ======================
if "current_page" not in st.session_state:
    st.session_state.current_page = "Dashboard"
if "settings" not in st.session_state:
    st.session_state.settings = load_settings()
if "coach_messages" not in st.session_state:
    st.session_state.coach_messages = []
# ============================================================
def load_past_inquiries(limit=50):
    """Load past inquiries for the Conversations tab."""
    if not supabase:
        return []

    try:
        result = supabase.table("inquiries").select("*").order("created_at", desc=True).limit(limit).execute()
        return result.data if result.data else []
    except Exception as e:
        print(f"Error loading inquiries: {e}")
        return []

def save_inquiry(
    original_text: str, 
    customer_name: str = None, 
    customer_identifier: str = None,
    summary: str = None, 
    ai_draft: str = None, 
    final_response: str = None, 
    status: str = "approved"
):
    """Save an inquiry to the conversations table."""
    if not supabase:
        st.error("Supabase client not configured.")
        return None

    inquiry_number = f"INQ-{datetime.now().strftime('%Y%m%d')}-{str(hash(original_text))[-6:]}"

    try:
        data = {
            "inquiry_number": inquiry_number,
            "customer_name": customer_name,
            "customer_identifier": customer_identifier,   # ← Key for grouping
            "original_text": original_text,
            "ai_summary": summary,
            "ai_draft": ai_draft,
            "final_response": final_response,
            "status": status
        }
        result = supabase.table("inquiries").insert(data).execute()
        st.success(f"Inquiry saved: {inquiry_number}")
        return result
    except Exception as e:
        st.error(f"Failed to save inquiry: {str(e)}")
        return None
		
st.set_page_config(page_title="InquiryFlow — Phase 1.5", page_icon="🚗", layout="wide")

st.title("InquiryFlow — Phase 2.0 MVP")
st.caption("AI drafts. You approve. Customers get fast, professional responses.")

# ====================== SIDEBAR NAVIGATION ======================
with st.sidebar:
    st.header("Navigation")

    pages = ["Dashboard", "Conversations", "Settings"]
    st.session_state.current_page = st.radio(
        "Go to",
        pages,
        index=pages.index(st.session_state.current_page),
        label_visibility="collapsed"
    )

    st.divider()
    st.caption("Phase 1.5 • Human-in-the-loop by design • Built for maintainability")
# ============================================================

# AI Coach LLM
llm_coach = ChatOpenAI(model="gpt-4o", temperature=0.3)

# ====================== MAIN CONTENT ======================
if st.session_state.current_page == "Dashboard":
    # ------------------ DASHBOARD ------------------
    st.subheader("1. New Inquiry")

    col1, col2 = st.columns([3, 1])
    with col1:
        inquiry_text = st.text_area(
            "Paste customer inquiry here",
            value=st.session_state.get("sample_inquiry", ""),
            height=150,
            placeholder="Paste the DM, email, or form submission..."
        )
    with col2:
        customer_name = st.text_input("Customer name (optional)", value="")
        customer_identifier = st.text_input(
            "Customer identifier (email/phone/social handle)", 
            value="",
            placeholder="email or phone recommended"
        )
        process_btn = st.button("Process Inquiry →", type="primary", use_container_width=True)

    # Processing + Results
    if process_btn and inquiry_text.strip():
        with st.spinner("Analyzing inquiry and drafting response..."):
            result: InquiryState = process_inquiry(
                original_text=inquiry_text.strip(),
                customer_name=customer_name.strip() or None,
                settings=st.session_state.settings
            )
            st.session_state.current_result = result
            st.session_state.sample_inquiry = ""

    if "current_result" in st.session_state:
        result = st.session_state.current_result

        st.divider()
        st.subheader("AI Analysis & Draft")

        # Metrics
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("Customer Type", result.get("customer_type", "—").title())
        with col2:
            st.metric("Category", result.get("category", "—").replace("_", " ").title())
        with col3:
            urgency = result.get("urgency", "medium").lower()
            emoji = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(urgency, "⚪")
            st.metric("Urgency", f"{emoji} {urgency.title()}")
        with col4:
            st.metric("Status", result.get("status", "pending_review").replace("_", " ").title())

        st.divider()

        left, right = st.columns([1, 1.2])
        with left:
            st.markdown("**AI Summary**")
            st.info(result.get("summary", "No summary generated."))
            with st.expander("🔍 View Retrieved Context"):
                st.text(result.get("retrieved_context", "No context retrieved."))

        with right:
            st.markdown("**Draft Response** (edit before approving)")
            current_draft = result.get("draft_response", "")
            edited_draft = st.text_area(
                "Editable draft",
                value=current_draft,
                height=200,
                key="draft_editor"
            )
            if edited_draft != current_draft:
                st.session_state.current_result["human_edited_draft"] = edited_draft

        st.divider()

        b1, b2, b3 = st.columns([1.2, 1.2, 2])
        with b1:
            if st.button("✅ Approve & Log", type="primary", use_container_width=True):
                final_text = st.session_state.get("draft_editor", edited_draft)
        
                # Save to Supabase with identifier
                save_inquiry(
                    original_text=result.get("original_text", ""),
                    customer_name=result.get("customer_name"),
                    customer_identifier=customer_identifier.strip() or None,
                    summary=result.get("summary", ""),
                    ai_draft=final_text,
                    final_response=final_text,
                    status="approved"
                )
        
                st.success("Response approved and logged.")
                st.balloons()

                with st.expander("What will be sent to customer"):
                    st.code(final_text)
        
                if st.button("Process Another Inquiry"):
                    del st.session_state.current_result
                    st.rerun()
            
        with b2:
            if st.button("Request More Info", use_container_width=True):
                st.info("Follow-up workflow (Phase 2)")

        with b3:
            st.caption("All actions are logged. In production this writes to Supabase.")

elif st.session_state.current_page == "Conversations":
    st.subheader("📋 Conversations History")

    past_inquiries = load_past_inquiries()

    st.write(f"Found {len(past_inquiries)} past inquiries")  # Debug line

    if not past_inquiries:
        st.info("No past inquiries yet. Process and approve some inquiries on the Dashboard tab.")
        st.write("Check Supabase 'inquiries' table to see if data is being saved.")
    else:
        for inquiry in past_inquiries:
            with st.expander(f"#{inquiry.get('inquiry_number', 'Unknown')} - {inquiry.get('customer_name', 'Unknown')}"):
                st.write(f"**Status**: {inquiry.get('status', 'unknown')}")
                st.write(f"**Original**: {inquiry.get('original_text', '')[:150]}...")
                if inquiry.get('final_response'):
                    st.write(f"**Final Response**: {inquiry.get('final_response')[:300]}...")
                st.caption(f"Created: {inquiry.get('created_at')}")

elif st.session_state.current_page == "Settings":
    st.subheader("⚙️ Settings & Maintenance")

    settings = st.session_state.settings

    st.markdown("**Tone & Communication Style**")
    settings["tone"] = st.text_area(
        "How should the AI sound?",
        value=settings.get("tone", ""),
        height=100
    )

    st.markdown("**Service Roster**")
    st.write("Check the services your shop offers.")

    services_data = settings.get("services", {})

    if isinstance(services_data, dict):
        for category, sub_services in services_data.items():
            if isinstance(sub_services, dict):
                st.markdown(f"**{category}**")
                for service, enabled in sub_services.items():
                    settings["services"][category][service] = st.checkbox(
                        service,
                        value=bool(enabled),
                        key=f"service_{category}_{service}"
                    )

    col1, col2 = st.columns(2)
    with col1:
        if st.button("💾 Save Changes", type="primary", use_container_width=True, key="save_btn"):
            if save_settings(settings):
                if regenerate_knowledge_base(settings):
                    st.success("Settings saved and knowledge base regenerated!")
                    st.session_state.settings = settings
                else:
                    st.warning("Settings saved, but knowledge base regeneration had issues.")
            else:
                st.error("Failed to save settings to Supabase.")

    with col2:
        if st.button("Discard Changes", use_container_width=True, key="discard_btn"):
            st.session_state.settings = load_settings()
            st.info("Changes discarded.")

    st.divider()

    # AI Coach
    st.subheader("🤖 AI Coach")
    st.write("Talk to the coach to update tone, services, or response behavior.")

    for message in st.session_state.coach_messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    if prompt := st.chat_input("Tell the AI Coach what to change..."):
        st.session_state.coach_messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        with st.chat_message("assistant"):
            with st.spinner("Thinking..."):
                chain = ai_coach_prompt | llm_coach | StrOutputParser()
                response = chain.invoke({"user_message": prompt})
                st.markdown(response)

        st.session_state.coach_messages.append({"role": "assistant", "content": response})

# ====================== FOOTER ======================
st.divider()
st.caption("Phase 1.5 → Phase 2 Transition • Conversations tab in progress")
