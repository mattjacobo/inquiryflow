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
def auto_detect_channel(identifier: str) -> str:
    """Auto-detect channel based on identifier format."""
    if not identifier:
        return "Other"
    
    identifier = identifier.strip().lower()
    
    if identifier.startswith('+') or identifier.replace(' ', '').replace('-', '').isdigit():
        return "SMS/Text"
    elif '@' in identifier:
        return "Email"
    elif any(word in identifier for word in ['instagram', 'ig', 'dm', '@']):
        return "Instagram DM"
    else:
        return "Other"

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
    channel: str = "Other",                  # Auto-detected or manual
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
            "customer_identifier": customer_identifier,
            "channel": channel,                     # Channel is now stored
            "original_text": original_text,
            "ai_summary": summary,
            "ai_draft": ai_draft,
            "final_response": final_response,
            "status": status
        }
        result = supabase.table("inquiries").insert(data).execute()
        st.success(f"Inquiry saved: {inquiry_number} ({channel})")
        return result
    except Exception as e:
        st.error(f"Failed to save inquiry: {str(e)}")
        return None

def delete_inquiry(inquiry_id: str) -> bool:
    """Permanently delete an inquiry from Supabase."""
    if not supabase:
        st.error("Supabase client not configured.")
        return False
    try:
        supabase.table("inquiries").delete().eq("id", inquiry_id).execute()
        return True
    except Exception as e:
        st.error(f"Failed to delete inquiry: {e}")
        return False

def update_inquiry_status(inquiry_id: str, new_status: str):
    """Update the status of an inquiry in Supabase."""
    if not supabase:
        st.error("Supabase client not configured.")
        return False

    try:
        supabase.table("inquiries").update({"status": new_status}).eq("id", inquiry_id).execute()
        st.success(f"Status updated to: {new_status}")
        return True
    except Exception as e:
        st.error(f"Failed to update status: {str(e)}")
        return False

def add_reply_to_inquiry(inquiry_id: str, reply_text: str, sender: str = "human"):
    """Save a reply to the inquiry's replies array in Supabase."""
    if not supabase:
        st.error("Supabase client not configured.")
        return False

    try:
        # Get current replies
        result = supabase.table("inquiries").select("replies").eq("id", inquiry_id).execute()
        current_replies = result.data[0].get("replies", []) if result.data else []

        # Create new reply object
        new_reply = {
            "text": reply_text,
            "sender": sender,
            "timestamp": datetime.now().isoformat()
        }

        current_replies.append(new_reply)

        # Update the inquiry
        supabase.table("inquiries").update({
            "replies": current_replies,
            "status": "replied"
        }).eq("id", inquiry_id).execute()

        return True
    except Exception as e:
        st.error(f"Failed to save reply: {e}")
        return False
		
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
        customer_name = st.text_input("Customer name (optional display name)", value="")
        
        customer_identifier = st.text_input(
            "Customer Identifier * (phone/email/social handle)",
            value="",
            placeholder="e.g. +15551234567 or john@email.com"
        )
        
        process_btn = st.button("Process Inquiry →", type="primary", use_container_width=True)

    # Processing + Results
    if process_btn and inquiry_text.strip():
        if not customer_identifier.strip():
            st.error("Customer Identifier is required.")
        else:
            channel = auto_detect_channel(customer_identifier)
            
            with st.spinner("Analyzing inquiry and drafting response..."):
                result: InquiryState = process_inquiry(
                    original_text=inquiry_text.strip(),
                    customer_name=customer_name.strip() or None,
                    settings=st.session_state.settings
                )
                st.session_state.current_result = result
                st.session_state.sample_inquiry = ""

            st.info(f"Detected Channel: **{channel}**")

    if "current_result" in st.session_state:
        result = st.session_state.current_result

        st.divider()
        st.subheader("AI Analysis & Draft")

        # Metrics (keep your existing metrics code)
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
        
                channel = auto_detect_channel(customer_identifier)
        
                save_inquiry(
                    original_text=result.get("original_text", ""),
                    customer_name=result.get("customer_name"),
                    customer_identifier=customer_identifier.strip() or None,
                    channel=channel,
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

    # ============================================================
    # EMAIL INTAKE BUTTON
    # ============================================================
    from email_utils import process_new_emails, send_email_reply

    st.markdown("### 📥 Email Intake")
    col1, col2 = st.columns([1, 3])

    with col1:
        if st.button("Fetch New Emails", type="primary", use_container_width=True):
            with st.spinner("Checking inbox and running AI..."):
                created_ids = process_new_emails(auto_run_ai=True)
                if created_ids:
                    st.success(f"Created and processed {len(created_ids)} new inquiry(ies).")
                    st.rerun()
                else:
                    st.info("No new unread emails found.")

    with col2:
        st.caption("Checks your connected inbox for new unread emails and runs them through the AI workflow.")

    st.divider()

    # ============================================================
    # CONVERSATIONS LIST
    # ============================================================
    past_inquiries = load_past_inquiries()

    if not past_inquiries:
        st.info("No past inquiries yet.")
    else:
        # Filters
        col1, col2, col3 = st.columns([2, 2, 1])
        with col1:
            channel_filter = st.selectbox(
                "Filter by Channel",
                ["All"] + sorted(set(i.get("channel") for i in past_inquiries if i.get("channel")))
            )
        with col2:
            status_filter = st.selectbox(
                "Filter by Status",
                ["All", "pending_review", "approved", "sent", "replied", "closed"]
            )
        with col3:
            search_term = st.text_input("Search", placeholder="Search inquiries...")

        # Apply filters
        filtered = past_inquiries
        if channel_filter != "All":
            filtered = [i for i in filtered if i.get("channel") == channel_filter]
        if status_filter != "All":
            filtered = [i for i in filtered if i.get("status") == status_filter]
        if search_term:
            filtered = [i for i in filtered if search_term.lower() in str(i).lower()]

        st.write(f"Showing {len(filtered)} conversations")

        from collections import defaultdict
        grouped = defaultdict(list)
        for inquiry in filtered:
            key = f"{inquiry.get('channel', 'Unknown')} – {inquiry.get('customer_identifier') or inquiry.get('customer_name') or 'Unknown'}"
            grouped[key].append(inquiry)

        for customer_key, conversations in grouped.items():
            with st.expander(f"👤 {customer_key} ({len(conversations)} messages)", expanded=False):

                for inquiry in sorted(conversations, key=lambda x: x.get("created_at", ""), reverse=True):
                    inquiry_id = inquiry.get("id")
                    channel = inquiry.get("channel", "Other")
                    status = inquiry.get("status", "unknown").replace("_", " ").title()
                    ai_draft = inquiry.get("ai_draft") or inquiry.get("final_response") or ""

                    # Header
                    st.markdown(f"**{inquiry.get('inquiry_number')}** · {status} · `{channel}`")
                    st.caption(f"Created: {inquiry.get('created_at')}")

                    # Original message
                    st.markdown("**Customer Message:**")
                    st.info(inquiry.get("original_text", ""))

                    # ========== BETTER AI DRAFT DISPLAY ==========
                    if ai_draft:
                        st.markdown("**AI Draft:**")
                        st.success(ai_draft)
                    else:
                        st.warning("No AI draft available yet.")

                    # Saved replies (threading)
                    replies = inquiry.get("replies") or []
                    if replies:
                        st.markdown("**Conversation History:**")
                        for reply in replies:
                            sender = "You" if reply.get("sender") == "human" else "AI"
                            st.write(f"- **{sender}:** {reply.get('text')}")

                    st.divider()

                    # ========== ACTION BUTTONS ==========
                    btn_col1, btn_col2, btn_col3, btn_col4 = st.columns(4)

                    # 1. Send AI Draft
                    with btn_col1:
                        if ai_draft and st.button("Send AI Draft", key=f"send_ai_{inquiry_id}", use_container_width=True):
                            success = False
                            if channel == "Email":
                                success = send_email_reply(
                                    to_email=inquiry.get("customer_identifier"),
                                    subject="Re: Your Inquiry",
                                    body=ai_draft
                                )
                            else:
                                # Fallback for SMS / other (will fail gracefully if send_sms not available)
                                try:
                                    success = send_sms(
                                        to_number=inquiry.get("customer_identifier"),
                                        message=ai_draft
                                    )
                                except NameError:
                                    st.error("SMS sending is not configured.")
                                    success = False

                            if success:
                                add_reply_to_inquiry(inquiry_id, ai_draft, sender="ai")
                                update_inquiry_status(inquiry_id, "replied")
                                st.success("AI Draft sent and logged!")
                                st.rerun()

                    # 2. Manual Reply Box + Send
                    with btn_col2:
                        reply_key = f"reply_{inquiry_id}"
                        reply_text = st.text_area(
                            "Manual reply",
                            key=reply_key,
                            placeholder="Type your own reply...",
                            height=80,
                            label_visibility="collapsed"
                        )

                    with btn_col3:
                        if st.button("Send Manual Reply", key=f"send_manual_{inquiry_id}", use_container_width=True):
                            if not reply_text.strip():
                                st.warning("Please enter a reply first.")
                            else:
                                success = False
                                if channel == "Email":
                                    success = send_email_reply(
                                        to_email=inquiry.get("customer_identifier"),
                                        subject="Re: Your Inquiry",
                                        body=reply_text.strip()
                                    )
                                else:
                                    try:
                                        success = send_sms(
                                            to_number=inquiry.get("customer_identifier"),
                                            message=reply_text.strip()
                                        )
                                    except NameError:
                                        st.error("SMS sending is not configured.")
                                        success = False

                                if success:
                                    add_reply_to_inquiry(inquiry_id, reply_text.strip(), sender="human")
                                    update_inquiry_status(inquiry_id, "replied")
                                    st.success("Manual reply sent and logged!")
                                    st.rerun()

                    # 3. Delete Conversation
                    with btn_col4:
                        if st.button("🗑️ Delete", key=f"delete_{inquiry_id}", use_container_width=True):
                            if delete_inquiry(inquiry_id):
                                st.success("Conversation deleted.")
                                st.rerun()

elif st.session_state.current_page == "Settings":
    st.subheader("⚙️ Settings & Maintenance")

    settings = st.session_state.settings

    # Tone
    st.markdown("**Tone & Communication Style**")
    settings["tone"] = st.text_area(
        "How should the AI sound?",
        value=settings.get("tone", ""),
        height=100
    )

    # Service Roster
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

    # Save / Discard buttons
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
