"""
InquiryFlow Phase 1 — Streamlit Dashboard
This is the product surface the business owner interacts with every day.

Design goals (Bigger Picture):
- Make human review FAST and pleasant (critical for adoption).
- Show original inquiry + AI understanding + editable draft side-by-side.
- Make the "Approve" action feel safe and deliberate.
- Clean, professional appearance that builds trust in the system.
- Everything is logged so the business can later analyze what works.

Phase 1 keeps the UI intentionally simple so we can validate value quickly.
"""

import streamlit as st
from datetime import datetime
from typing import Optional
import os

from workflow import process_inquiry, InquiryState
from dotenv import load_dotenv
from rag_utils import process_and_store_documents
from settings_utils import load_settings, save_settings, regenerate_knowledge_base
from prompts import classifier_prompt, drafter_prompt, ai_coach_prompt
import tempfile

from langchain_openai import ChatOpenAI
from langchain_core.output_parsers import StrOutputParser

load_dotenv()

def safe_str(val, default="—"):
    """Safely convert any value to a clean title-cased string."""
    if val is None or val == "":
        return default
    try:
        return str(val).strip().title()
    except Exception:
        return default


@st.cache_data(ttl=300)  # cache results for 5 minutes
def get_classification_result(conversation_text: str):
    """Run your classifier/agent and return the result dict."""
    # ← Replace this comment with your existing logic
    result = run_classifier_or_agent(conversation_text)   # ← your function
    return result

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

    # Processing + Results
    if process_btn and inquiry_text.strip():
        with st.spinner("Analyzing inquiry and drafting response..."):
            result: InquiryState = process_inquiry(
                original_text=inquiry_text.strip(),
                customer_name=customer_name.strip() or None
            )
            st.session_state.current_result = result
            st.session_state.sample_inquiry = ""

    if "current_result" in st.session_state:
        result = st.session_state.current_result

        st.divider()
        st.subheader("2. AI Analysis & Draft (Ready for your review)")

        # Metrics row
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Customer Type", result.get("customer_type", "—").title())
        m2.metric("Category", result.get("category", "—").replace("_", " ").title())
        m3.metric("Urgency", result.get("urgency", "—").title())
        m4.metric("Status", result.get("status", "—").replace("_", " ").title())

        st.divider()

        left, right = st.columns([1, 1.3])

        with left:
            st.markdown("**AI Summary** (for your quick understanding)")
            st.info(result.get("summary", "No summary generated."))

            with st.expander("View grounding context (what AI was allowed to use)"):
                st.text(result.get("retrieved_context", "No context retrieved."))

        with right:
            st.markdown("**Draft Response** (edit as needed)")

            current_draft = result.get("draft_response", "")

            edited_draft = st.text_area(
                "Editable draft — this is what the customer will see after you approve",
                value=current_draft,
                height=220,
                key="draft_editor"
            )

            if edited_draft != current_draft:
                st.session_state.current_result["human_edited_draft"] = edited_draft

        st.divider()

        btn_col1, btn_col2, btn_col3 = st.columns([1, 1, 2])

        with btn_col1:
            if st.button("✅ Approve & Log", type="primary", use_container_width=True):
                final_text = st.session_state.get("draft_editor", edited_draft)
                st.success("Response approved and logged (simulated in Phase 1).")
                st.balloons()

                with st.expander("What will be sent to customer (final version)"):
                    st.code(final_text, language="text")

                if st.button("Process Another Inquiry"):
                    del st.session_state.current_result
                    st.rerun()

        with btn_col2:
            if st.button("Request More Info from Customer", use_container_width=True):
                st.info("This would trigger a follow-up message workflow (Phase 2 feature).")

        with btn_col3:
            st.caption("All actions are logged for audit and continuous improvement. "
                       "In production this writes to Supabase with full traceability.")

elif st.session_state.current_page == "Settings":
    st.subheader("⚙️ Settings & Maintenance")

    settings = st.session_state.settings

    st.markdown("**Tone & Communication Style**")
    settings["tone"] = st.text_area(
        "How should the AI sound when responding?",
        value=settings.get("tone", ""),
        height=100
    )

    st.markdown("**Service Roster**")
    st.write("Check the services your shop offers.")

    for category, sub_services in settings["services"].items():
        st.markdown(f"**{category}**")
        for service, enabled in sub_services.items():
            settings["services"][category][service] = st.checkbox(
                service,
                value=enabled,
                key=f"service_{category}_{service}"
            )

    col1, col2 = st.columns(2)
    with col1:
        if st.button("💾 Save Changes", type="primary", use_container_width=True):
            if save_settings(settings):
                if regenerate_knowledge_base(settings):
                    st.success("Settings saved and knowledge base regenerated!")
                    st.session_state.settings = settings
                else:
                    st.warning("Settings saved, but knowledge base regeneration had issues.")
            else:
                st.error("Failed to save settings to Supabase.")

    with col2:
        if st.button("Discard Changes", use_container_width=True):
            st.session_state.settings = load_settings()
            st.info("Changes discarded.")

    st.divider()

   # ============================================================
# AI COACH CHATBOX (Updated with Structured JSON)
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
            from langchain_core.output_parsers import JsonOutputParser

            chain = ai_coach_prompt | llm_coach | JsonOutputParser()
            result = chain.invoke({"user_message": prompt})

            message = result.get("message", "Done.")
            st.markdown(message)

            # === Apply Changes from JSON ===
            action = result.get("action")
            details = result.get("details", {})
            current_settings = st.session_state.settings
            changes_made = False

            if action == "update_tone" and "tone" in details:
                current_settings["tone"] = details["tone"]
                changes_made = True

            elif action == "toggle_service" and "service" in details:
                service_name = details["service"]
                enabled = details.get("enabled", True)
                for category, services in current_settings.get("services", {}).items():
                    if service_name in services:
                        current_settings["services"][category][service_name] = enabled
                        changes_made = True
                        break

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
