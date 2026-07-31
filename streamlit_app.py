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

def archive_inquiry(inquiry_id: str) -> bool:
    """Soft delete – move inquiry to archived status."""
    if not supabase:
        st.error("Supabase client not configured.")
        return False
    try:
        supabase.table("inquiries").update({"status": "archived"}).eq("id", inquiry_id).execute()
        return True
    except Exception as e:
        st.error(f"Failed to archive inquiry: {e}")
        return False


def unarchive_inquiry(inquiry_id: str) -> bool:
    """Restore an archived inquiry back to pending_review."""
    if not supabase:
        st.error("Supabase client not configured.")
        return False
    try:
        supabase.table("inquiries").update({"status": "pending_review"}).eq("id", inquiry_id).execute()
        return True
    except Exception as e:
        st.error(f"Failed to unarchive inquiry: {e}")
        return False


def delete_inquiry(inquiry_id: str) -> bool:
    """Hard delete – permanently remove from database. Only use from Archive section."""
    if not supabase:
        st.error("Supabase client not configured.")
        return False
    try:
        supabase.table("inquiries").delete().eq("id", inquiry_id).execute()
        return True
    except Exception as e:
        st.error(f"Failed to permanently delete inquiry: {e}")
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
    # Compact header
    st.markdown("### Conversations")
    st.caption("Review and respond to customer inquiries")

    # ============================================================
    # EMAIL INTAKE (always visible, no dropdown)
    # ============================================================
    from email_utils import process_new_emails, send_email_reply

    if st.button("📥 Fetch New Emails", type="primary", use_container_width=True):
        with st.spinner("Checking inbox and running AI..."):
            created_ids = process_new_emails(
                auto_run_ai=True,
                settings=st.session_state.settings
            )
            if created_ids:
                st.success(f"Created and processed {len(created_ids)} new inquiry(ies).")
                st.rerun()
            else:
                st.info("No new unread emails found.")

    st.divider()

    # ============================================================
    # LOAD + GROUP
    # ============================================================
    past_inquiries = load_past_inquiries(limit=100)

    awaiting_review = []
    awaiting_response = []
    archived = []

    for inq in past_inquiries:
        status = (inq.get("status") or "").lower()
        if status in ["pending_review", "approved"]:
            awaiting_review.append(inq)
        elif status in ["replied", "sent"]:
            awaiting_response.append(inq)
        elif status == "archived":
            archived.append(inq)
        else:
            awaiting_review.append(inq)

    # Newest first
    awaiting_review = sorted(awaiting_review, key=lambda x: x.get("created_at") or "", reverse=True)
    awaiting_response = sorted(awaiting_response, key=lambda x: x.get("created_at") or "", reverse=True)
    archived = sorted(archived, key=lambda x: x.get("created_at") or "", reverse=True)

    # ============================================================
    # FOCUSED TILE RENDERER (one at a time + auto-advance)
    # ============================================================
    def render_focused_queue(inquiries, tab_key: str, empty_message: str):
        if not inquiries:
            st.info(empty_message)
            return

        # Session state index for this tab
        index_key = f"queue_index_{tab_key}"
        if index_key not in st.session_state:
            st.session_state[index_key] = 0

        # Keep index in bounds
        if st.session_state[index_key] >= len(inquiries):
            st.session_state[index_key] = max(0, len(inquiries) - 1)
        if st.session_state[index_key] < 0:
            st.session_state[index_key] = 0

        idx = st.session_state[index_key]
        inquiry = inquiries[idx]
        total = len(inquiries)

        # ----- Header / counter -----
        st.markdown(f"**{idx + 1} of {total}**")

        # ----- Navigation -----
        nav1, nav2, nav3 = st.columns([1, 2, 1])
        with nav1:
            if st.button("← Previous", key=f"prev_{tab_key}", use_container_width=True, disabled=(idx == 0)):
                st.session_state[index_key] = idx - 1
                st.rerun()
        with nav3:
            if st.button("Next →", key=f"next_{tab_key}", use_container_width=True, disabled=(idx >= total - 1)):
                st.session_state[index_key] = idx + 1
                st.rerun()

        # ----- Current tile summary -----
        identifier = inquiry.get("customer_identifier") or inquiry.get("customer_name") or "Unknown"
        channel = inquiry.get("channel") or "Other"
        category = (inquiry.get("category") or "general").replace("_", " ").title()
        summary = inquiry.get("ai_summary") or inquiry.get("summary") or "No summary"
        inquiry_number = inquiry.get("inquiry_number") or ""

        metadata = inquiry.get("metadata") or {}
        v_info = metadata.get("vehicle_verification") or {}
        normalized = v_info.get("normalized_vehicle")
        vehicle_exists = v_info.get("vehicle_exists")
        confidence = v_info.get("confidence")

        if vehicle_exists and confidence == "high" and normalized:
            vehicle_line = f"✅ {normalized}"
        elif normalized:
            vehicle_line = f"⚠️ {normalized} (unverified)"
        else:
            vehicle_line = "⚠️ Vehicle not verified"

        st.markdown(f"""
        <div style="
            background: #1a1a1a;
            border: 1px solid #333;
            border-radius: 14px;
            padding: 20px;
            margin: 12px 0 18px 0;
            color: #eee;
        ">
            <div style="font-size: 12px; color: #888; margin-bottom: 6px;">{channel.upper()} · {inquiry_number}</div>
            <div style="font-weight: 600; font-size: 17px; margin-bottom: 8px; word-break: break-all;">{identifier}</div>
            <div style="font-size: 14px; margin-bottom: 6px;">{vehicle_line}</div>
            <div style="font-size: 13px; color: #aaa; margin-bottom: 10px;">{category}</div>
            <div style="font-size: 14px; color: #ccc; line-height: 1.45;">{summary}</div>
        </div>
        """, unsafe_allow_html=True)

        # ----- Expandable full conversation + actions -----
        with st.expander("Open conversation & respond", expanded=True):
            inquiry_id = inquiry.get("id")
            status = inquiry.get("status") or ""
            ai_draft = inquiry.get("ai_draft") or inquiry.get("final_response") or ""
            original_message_id = metadata.get("message_id")
            original_subject = metadata.get("subject") or "Your Inquiry"

            # ========== TOP ACTIONS (minimize scrolling) ==========
            if ai_draft:
                if st.button("Send AI Draft", key=f"send_ai_top_{tab_key}_{inquiry_id}", type="primary", use_container_width=True):
                    success = False
                    if channel == "Email":
                        success = send_email_reply(
                            to_email=inquiry.get("customer_identifier"),
                            subject=original_subject,
                            body=ai_draft,
                            in_reply_to=original_message_id,
                            references=original_message_id
                        )
                    if success:
                        add_reply_to_inquiry(inquiry_id, ai_draft, sender="ai")
                        update_inquiry_status(inquiry_id, "replied")
                        if idx < total - 1:
                            st.session_state[index_key] = idx + 1
                        st.success("Sent. Moving to next task.")
                        st.rerun()

            st.markdown("---")

            # ========== CONTEXT ==========
            st.markdown("**Customer Message**")
            st.info(inquiry.get("original_text") or "")

            if ai_draft:
                st.markdown("**AI Draft**")
                st.success(ai_draft)
            else:
                st.warning("No AI draft available.")

            st.markdown("---")

            # ========== BOTTOM ACTIONS ==========
            if ai_draft:
                if st.button("Send AI Draft", key=f"send_ai_bottom_{tab_key}_{inquiry_id}", type="primary", use_container_width=True):
                    success = False
                    if channel == "Email":
                        success = send_email_reply(
                            to_email=inquiry.get("customer_identifier"),
                            subject=original_subject,
                            body=ai_draft,
                            in_reply_to=original_message_id,
                            references=original_message_id
                        )
                    if success:
                        add_reply_to_inquiry(inquiry_id, ai_draft, sender="ai")
                        update_inquiry_status(inquiry_id, "replied")
                        if idx < total - 1:
                            st.session_state[index_key] = idx + 1
                        st.success("Sent. Moving to next task.")
                        st.rerun()

            reply_text = st.text_area("Manual reply", key=f"manual_{tab_key}_{inquiry_id}", height=100)

            c1, c2 = st.columns(2)
            with c1:
                if st.button("Send Manual Reply", key=f"send_manual_{tab_key}_{inquiry_id}", use_container_width=True):
                    if reply_text.strip():
                        success = False
                        if channel == "Email":
                            success = send_email_reply(
                                to_email=inquiry.get("customer_identifier"),
                                subject=original_subject,
                                body=reply_text.strip(),
                                in_reply_to=original_message_id,
                                references=original_message_id
                            )
                        if success:
                            add_reply_to_inquiry(inquiry_id, reply_text.strip(), sender="human")
                            update_inquiry_status(inquiry_id, "replied")
                            if idx < total - 1:
                                st.session_state[index_key] = idx + 1
                            st.success("Sent. Moving to next task.")
                            st.rerun()
                    else:
                        st.warning("Enter a reply first.")

            with c2:
                if status == "archived":
                    if st.button("Unarchive", key=f"unarch_{tab_key}_{inquiry_id}", use_container_width=True):
                        if unarchive_inquiry(inquiry_id):
                            st.rerun()
                    if st.button("Delete Permanently", key=f"del_{tab_key}_{inquiry_id}", use_container_width=True):
                        if delete_inquiry(inquiry_id):
                            st.rerun()
                else:
                    if st.button("Archive", key=f"arch_{tab_key}_{inquiry_id}", use_container_width=True):
                        if archive_inquiry(inquiry_id):
                            st.rerun()
    # ============================================================
    # TABS
    # ============================================================
    tab1, tab2, tab3 = st.tabs([
        f"Awaiting Review ({len(awaiting_review)})",
        f"Awaiting Response ({len(awaiting_response)})",
        f"Archived ({len(archived)})"
    ])

    with tab1:
        render_focused_queue(awaiting_review, "review", "No tasks awaiting review.")

    with tab2:
        render_focused_queue(awaiting_response, "response", "No tasks awaiting response.")

    with tab3:
        render_focused_queue(archived, "archived", "No archived conversations.")


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
