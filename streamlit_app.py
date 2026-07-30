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
    st.subheader("📋 Conversations")

    # ============================================================
    # EMAIL INTAKE
    # ============================================================
    from email_utils import process_new_emails, send_email_reply

    with st.expander("📥 Email Intake", expanded=False):
        if st.button("Fetch New Emails", type="primary"):
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
    # LOAD + GROUP DATA
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
            # fallback
            awaiting_review.append(inq)

    # ============================================================
    # HELPER: Build one tile (HTML card)
    # ============================================================
    def build_tile_html(inquiry):
        identifier = inquiry.get("customer_identifier") or inquiry.get("customer_name") or "Unknown"
        category = (inquiry.get("category") or "general").replace("_", " ").title()
        summary = (inquiry.get("ai_summary") or inquiry.get("summary") or "")[:120]
        if summary and len(inquiry.get("ai_summary") or inquiry.get("summary") or "") > 120:
            summary += "..."

        # Vehicle verification
        metadata = inquiry.get("metadata") or {}
        v_info = metadata.get("vehicle_verification") or {}
        vehicle_exists = v_info.get("vehicle_exists")
        confidence = v_info.get("confidence")
        normalized = v_info.get("normalized_vehicle")

        if vehicle_exists and confidence == "high" and normalized:
            vehicle_display = f"✅ {normalized}"
        elif normalized:
            vehicle_display = f"⚠️ {normalized} (unverified)"
        else:
            vehicle_display = "⚠️ Vehicle not verified"

        inquiry_number = inquiry.get("inquiry_number") or ""
        created = str(inquiry.get("created_at") or "")[:16]

        return f"""
        <div style="
            min-width: 280px;
            max-width: 300px;
            background: #1e1e1e;
            border: 1px solid #333;
            border-radius: 12px;
            padding: 16px;
            margin-right: 16px;
            display: inline-block;
            vertical-align: top;
            color: #eee;
            box-shadow: 0 2px 8px rgba(0,0,0,0.3);
        ">
            <div style="font-size: 13px; color: #888; margin-bottom: 6px;">{inquiry_number}</div>
            <div style="font-weight: 600; font-size: 15px; margin-bottom: 8px; word-break: break-all;">{identifier}</div>
            <div style="font-size: 13px; margin-bottom: 6px;">{vehicle_display}</div>
            <div style="font-size: 13px; color: #aaa; margin-bottom: 8px;">📂 {category}</div>
            <div style="font-size: 12px; color: #bbb; line-height: 1.4;">{summary}</div>
            <div style="font-size: 11px; color: #666; margin-top: 10px;">{created}</div>
        </div>
        """

    def render_horizontal_tiles(inquiries, empty_message, tab_key: str):
        if not inquiries:
            st.info(empty_message)
            return

        # Build horizontal tiles
        tiles_html = "".join([build_tile_html(inq) for inq in inquiries])
        html = f"""
        <div style="
            overflow-x: auto;
            white-space: nowrap;
            padding: 12px 0 20px 0;
            -webkit-overflow-scrolling: touch;
        ">
            {tiles_html}
        </div>
        """
        st.markdown(html, unsafe_allow_html=True)

        st.markdown("##### Take Action")

        # Stable options list
        options = {
            f"{inq.get('inquiry_number')} — {inq.get('customer_identifier') or 'Unknown'}": inq.get("id")
            for inq in inquiries
        }
        labels = ["— Select a conversation —"] + list(options.keys())

        selected_label = st.selectbox(
            "Select a conversation to review / reply",
            options=labels,
            key=f"select_{tab_key}"
        )

        # Store selection in session state
        if selected_label and selected_label != "— Select a conversation —":
            selected_id = options[selected_label]
            st.session_state[f"selected_inquiry_{tab_key}"] = selected_id
        else:
            st.session_state[f"selected_inquiry_{tab_key}"] = None

        # Render action panel if something is selected
        selected_id = st.session_state.get(f"selected_inquiry_{tab_key}")
        if selected_id:
            # Find the full inquiry object
            inquiry = next((i for i in inquiries if i.get("id") == selected_id), None)
            if inquiry:
                render_inquiry_actions(inquiry)

    # ============================================================
    # ACTION PANEL (re-uses your existing logic)
    # ============================================================
    def render_inquiry_actions(inquiry):
        inquiry_id = inquiry.get("id")
        channel = inquiry.get("channel", "Other")
        ai_draft = inquiry.get("ai_draft") or inquiry.get("final_response") or ""
        status = inquiry.get("status")

        metadata = inquiry.get("metadata") or {}
        original_message_id = metadata.get("message_id")
        original_subject = metadata.get("subject") or "Your Inquiry"

        st.markdown("---")
        st.markdown(f"**Customer Message**")
        st.info(inquiry.get("original_text", ""))

        if ai_draft:
            st.markdown("**AI Draft**")
            st.success(ai_draft)
        else:
            st.warning("No AI draft available.")

        # Vehicle verification detail
        v_info = metadata.get("vehicle_verification") or {}
        if v_info:
            st.caption(f"Vehicle check: exists={v_info.get('vehicle_exists')} | confidence={v_info.get('confidence')} | {v_info.get('normalized_vehicle')}")

        col1, col2, col3 = st.columns(3)

        with col1:
            if ai_draft and st.button("Send AI Draft", key=f"send_ai_{inquiry_id}", use_container_width=True):
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
                    st.success("AI Draft sent!")
                    st.rerun()

        with col2:
            reply_text = st.text_area("Manual reply", key=f"reply_{inquiry_id}", height=80)
            if st.button("Send Manual Reply", key=f"send_manual_{inquiry_id}", use_container_width=True):
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
                        st.success("Reply sent!")
                        st.rerun()

        with col3:
            if status == "archived":
                if st.button("Unarchive", key=f"unarchive_{inquiry_id}", use_container_width=True):
                    if unarchive_inquiry(inquiry_id):
                        st.success("Restored")
                        st.rerun()
                if st.button("🗑️ Delete Permanently", key=f"hard_del_{inquiry_id}", use_container_width=True):
                    if delete_inquiry(inquiry_id):
                        st.success("Deleted")
                        st.rerun()
            else:
                if st.button("Archive", key=f"archive_{inquiry_id}", use_container_width=True):
                    if archive_inquiry(inquiry_id):
                        st.success("Archived")
                        st.rerun()

    # ============================================================
    # TABS
    # ============================================================
    tab_review, tab_response, tab_archived = st.tabs([
        f"Awaiting Review ({len(awaiting_review)})",
        f"Awaiting Response ({len(awaiting_response)})",
        f"Archived ({len(archived)})"
    ])

    with tab_review:
        render_horizontal_tiles(awaiting_review, "No inquiries awaiting review.", tab_key="review")

    with tab_response:
        render_horizontal_tiles(awaiting_response, "No inquiries awaiting customer response.", tab_key="response")

    with tab_archived:
        render_horizontal_tiles(archived, "No archived conversations.", tab_key="archived").


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
