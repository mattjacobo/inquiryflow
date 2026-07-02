"""
InquiryFlow Phase 1 — Streamlit Dashboard
... (your original docstring)
"""
import streamlit as st
from datetime import datetime
from typing import Optional, Any
import os
from workflow import process_inquiry, InquiryState
from dotenv import load_dotenv
from rag_utils import process_and_store_documents
from settings_utils import load_settings, save_settings, regenerate_knowledge_base
from prompts import classifier_prompt, drafter_prompt, ai_coach_prompt
import tempfile
from langchain_openai import ChatOpenAI
from langchain_core.output_parsers import StrOutputParser, JsonOutputParser

load_dotenv()


def safe_str(val: Any, default: str = "—") -> str:
    """Safely convert any value to a clean title-cased string."""
    if val is None or val == "":
        return default
    try:
        return str(val).strip().title()
    except Exception:
        return default


def get_field(obj: Any, key: str, default: str = "—") -> str:
    """Safely get a field from dict, Pydantic model, or dataclass."""
    if obj is None:
        return default
    if isinstance(obj, dict):
        val = obj.get(key, default)
    else:
        # Works for Pydantic models and dataclasses
        val = getattr(obj, key, default)
    return safe_str(val)


# Initialize session state
if "current_page" not in st.session_state:
    st.session_state.current_page = "Dashboard"
if "settings" not in st.session_state:
    st.session_state.settings = load_settings()
if "coach_messages" not in st.session_state:
    st.session_state.coach_messages = []
if "current_result" not in st.session_state:
    st.session_state.current_result = None

st.set_page_config(
    page_title="InquiryFlow — Phase 1",
    page_icon="🚗",
    layout="wide"
)

st.title("InquiryFlow — Phase 1.5 MVP")
st.caption("AI drafts. You approve. Customers get fast, professional responses.")

# ============================================================
# SIDEBAR NAVIGATION
# ============================================================
with st.sidebar:
    st.header("Navigation")
    pages = ["Dashboard", "Settings"]
    st.session_state.current_page = st.radio(
        "Go to",
        pages,
        index=pages.index(st.session_state.current_page),
        label_visibility="collapsed"
    )
    st.divider()
    st.caption("Phase 1.5 • Human-in-the-loop by design • Built for maintainability")

# AI Coach LLM
llm_coach = ChatOpenAI(model="gpt-4o", temperature=0.3)

# ============================================================
# MAIN CONTENT AREA
# ============================================================
if st.session_state.current_page == "Dashboard":
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
        process_btn = st.button("Process Inquiry →", type="primary", use_container_width=True)

    # Processing
    if process_btn and inquiry_text.strip():
        with st.spinner("Analyzing inquiry and drafting response..."):
            try:
                result: InquiryState = process_inquiry(
                    original_text=inquiry_text.strip(),
                    customer_name=customer_name.strip() or None
                )
                st.session_state.current_result = result
                st.session_state.sample_inquiry = ""
            except Exception as e:
                st.error(f"Error processing inquiry: {e}")
                st.session_state.current_result = None

    # Results Display
    result = st.session_state.get("current_result")

    if result:
        st.divider()
        st.subheader("2. AI Analysis & Draft (Ready for your review)")

        # === SAFE METRICS ROW ===
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Customer Type", get_field(result, "customer_type"))
        m2.metric("Category", get_field(result, "category").replace("_", " "))
        m3.metric("Urgency", get_field(result, "urgency"))
        m4.metric("Status", get_field(result, "status").replace("_", " "))

        st.divider()

        left, right = st.columns([1, 1.3])
        with left:
            st.markdown("**AI Summary** (for your quick understanding)")
            st.info(get_field(result, "summary", "No summary generated."))

            with st.expander("View grounding context (what AI was allowed to use)"):
                st.text(get_field(result, "retrieved_context", "No context retrieved."))

        with right:
            st.markdown("**Draft Response** (edit as needed)")
            current_draft = get_field(result, "draft_response", "")
            edited_draft = st.text_area(
                "Editable draft — this is what the customer will see after you approve",
                value=current_draft,
                height=220,
                key="draft_editor"
            )
            if edited_draft != current_draft:
                if isinstance(result, dict):
                    result["human_edited_draft"] = edited_draft
                else:
                    result.human_edited_draft = edited_draft
                st.session_state.current_result = result

        st.divider()

        # === ACTION BUTTONS ===
        btn_col1, btn_col2, btn_col3 = st.columns([1, 1, 2])

        with btn_col1:
            if st.button("✅ Approve & Log", type="primary", use_container_width=True):
                final_text = st.session_state.get("draft_editor", edited_draft)
                st.success("Response approved and logged (simulated in Phase 1).")
                st.balloons()
                with st.expander("What will be sent to customer (final version)"):
                    st.code(final_text, language="text")

                # Clear result for next inquiry
                if st.button("Process Another Inquiry", use_container_width=True):
                    st.session_state.current_result = None
                    st.rerun()

        with btn_col2:
            if st.button("Request More Info from Customer", use_container_width=True):
                st.info("This would trigger a follow-up message workflow (Phase 2 feature).")

        with btn_col3:
            st.caption("All actions are logged for audit and continuous improvement. "
                       "In production this writes to Supabase with full traceability.")

    else:
        st.info("Paste an inquiry above and click **Process Inquiry →** to see the AI analysis and draft.")

elif st.session_state.current_page == "Settings":
    st.subheader("⚙️ Settings & Maintenance")
    settings = st.session_state.settings

    # --- Tone & Communication Style ---
    st.markdown("**Tone & Communication Style**")
    settings["tone"] = st.text_area(
        "How should the AI sound when responding?",
        value=settings.get("tone", ""),
        height=100,
        placeholder="e.g. Friendly, professional, and concise. Use the customer's name when possible."
    )

    # --- Service Roster ---
    st.markdown("**Service Roster**")
    st.write("Check the services your shop offers. These are used by the AI when drafting responses.")

    services = settings.get("services", {})

    if not services:
        st.warning("No services found yet.")
        if st.button("Load Default Services", use_container_width=True):
            settings["services"] = {
                "Maintenance": {
                    "Oil Change": True,
                    "Brake Service": True,
                    "Tire Rotation": True,
                    "Battery Replacement": True,
                },
                "Repairs": {
                    "Engine Repair": True,
                    "Transmission Service": True,
                    "Suspension Work": True,
                },
                "Diagnostics": {
                    "Check Engine Light": True,
                    "Electrical Diagnostics": True,
                }
            }
            st.session_state.settings = settings
            st.rerun()
    else:
        for category, sub_services in services.items():
            st.markdown(f"**{category}**")
            for service, enabled in list(sub_services.items()):
                settings["services"][category][service] = st.checkbox(
                    service,
                    value=enabled,
                    key=f"service_{category}_{service}"
                )

    st.divider()

    # --- Save / Discard Buttons ---
    col1, col2 = st.columns(2)
    with col1:
        if st.button("💾 Save Changes", type="primary", use_container_width=True):
            if save_settings(settings):
                if regenerate_knowledge_base(settings):
                    st.success("Settings saved and knowledge base regenerated!")
                    st.session_state.settings = settings
                else:
                    st.warning("Settings saved, but knowledge base regeneration had some issues.")
            else:
                st.error("Failed to save settings to Supabase.")

    with col2:
        if st.button("Discard Changes", use_container_width=True):
            st.session_state.settings = load_settings()
            st.info("Changes discarded. Reloaded from database.")
            st.rerun()

    st.divider()

# ============================================================
# AI COACH CHATBOX
# ============================================================
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
            chain = ai_coach_prompt | llm_coach | JsonOutputParser()
            result = chain.invoke({"user_message": prompt})
            message = result.get("message", "Done.")
            st.markdown(message)

            # Apply changes from JSON (your existing logic)
            action = result.get("action")
            details = result.get("details", {})
            current_settings = st.session_state.settings
            changes_made = False

            if action == "update_tone" and "tone" in details:
                current_settings["tone"] = details["tone"]
                changes_made = True
            elif action == "toggle_service" and "service" in details:
                # ... your existing toggle logic ...
                pass
            elif action == "update_unavailable_message" and "message" in details:
                current_settings["unavailable_service_message"] = details["message"]
                changes_made = True

            if changes_made:
                st.session_state.settings = current_settings
                st.success("Coach updated your settings. Click **Save Changes** to apply them permanently.")

    st.session_state.coach_messages.append({"role": "assistant", "content": message})

# Footer
st.divider()
st.caption("Phase 1.5 • Human-in-the-loop by design • Built for maintainability")
