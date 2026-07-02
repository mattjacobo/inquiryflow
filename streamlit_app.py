"""
InquiryFlow Phase 1.5 — Streamlit Dashboard
"""

import streamlit as st
from typing import Optional

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

# ====================== SESSION STATE ======================
if "current_page" not in st.session_state:
    st.session_state.current_page = "Dashboard"
if "settings" not in st.session_state:
    st.session_state.settings = load_settings()
if "coach_messages" not in st.session_state:
    st.session_state.coach_messages = []
# ============================================================

st.set_page_config(page_title="InquiryFlow — Phase 1.5", page_icon="🚗", layout="wide")

st.title("InquiryFlow — Phase 1.5 MVP")
st.caption("AI drafts. You approve. Customers get fast, professional responses.")

# ====================== SIDEBAR NAVIGATION ======================
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
        process_btn = st.button("Process Inquiry →", type="primary", use_container_width=True)

    # ============================================================
    # PROCESSING + RESULTS
    # ============================================================
    if process_btn and inquiry_text.strip():
        with st.spinner("Analyzing inquiry and drafting response..."):
            result: InquiryState = process_inquiry(
                original_text=inquiry_text.strip(),
                customer_name=customer_name.strip() or None,
                settings=st.session_state.settings          # ← Pass current settings
            )
            st.session_state.current_result = result
            st.session_state.sample_inquiry = ""  # clear sample after use

        # Show results
        if "current_result" in st.session_state:
            result = st.session_state.current_result

            st.divider()
            st.subheader("AI Analysis & Draft")

            # Clean Metrics
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

            # Summary + Draft
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

            # Action Buttons
            b1, b2, b3 = st.columns([1.2, 1.2, 2])
            with b1:
                if st.button("✅ Approve & Log", type="primary", use_container_width=True):
                    final_text = st.session_state.get("draft_editor", edited_draft)
                    st.success("Response approved and logged (simulated).")
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

elif st.session_state.current_page == "Settings":
    # ------------------ SETTINGS ------------------
    st.subheader("⚙️ Settings & Maintenance")

    settings = st.session_state.settings

    # Tone
    st.markdown("**Tone & Communication Style**")
    settings["tone"] = st.text_area(
        "How should the AI sound?",
        value=settings.get("tone", ""),
        height=100
    )

# --- Service Roster (Safer Version) ---
st.markdown("**Service Roster**")
st.write("Check the services your shop offers.")

services_data = settings.get("services", {})

if not isinstance(services_data, dict):
    st.error("Settings data is corrupted. Resetting to default services.")
    settings["services"] = get_default_settings()["services"]
    services_data = settings["services"]

for category, sub_services in services_data.items():
    if not isinstance(sub_services, dict):
        continue  # skip bad data

    st.markdown(f"**{category}**")
    for service, enabled in sub_services.items():
        settings["services"][category][service] = st.checkbox(
            service,
            value=bool(enabled),
            key=f"service_{category}_{service}"
        )

    # Save / Discard
    c1, c2 = st.columns(2)
    with c1:
        if st.button("💾 Save Changes", type="primary", use_container_width=True):
            if save_settings(settings) and regenerate_knowledge_base(settings):
                st.success("Settings saved and knowledge base regenerated!")
                st.session_state.settings = settings
            else:
                st.error("Failed to save settings.")

    with c2:
        if st.button("Discard Changes", use_container_width=True):
            st.session_state.settings = load_settings()
            st.info("Changes discarded.")

    st.divider()

# ============================================================
# AI COACH CHATBOX (Improved Hybrid Version)
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
            chain = ai_coach_prompt | llm_coach | StrOutputParser()
            response = chain.invoke({"user_message": prompt})
            st.markdown(response)

            # === Lightweight Change Detection ===
            changes_made = False
            lower_prompt = prompt.lower()
            current_settings = st.session_state.settings

            # Tone
            if any(word in lower_prompt for word in ["tone", "sound"]):
                if any(word in lower_prompt for word in ["friendly", "warm"]):
                    current_settings["tone"] = "Friendly, warm, and approachable."
                    changes_made = True
                elif any(word in lower_prompt for word in ["professional", "formal"]):
                    current_settings["tone"] = "Professional, clear, and respectful."
                    changes_made = True

            # Services
            for category, services in current_settings.get("services", {}).items():
                for service in services:
                    if service.lower() in lower_prompt:
                        if any(w in lower_prompt for w in ["add", "enable", "turn on"]):
                            current_settings["services"][category][service] = True
                            changes_made = True
                        elif any(w in lower_prompt for w in ["remove", "disable", "turn off"]):
                            current_settings["services"][category][service] = False
                            changes_made = True

            # Unavailable service message
            if any(phrase in lower_prompt for phrase in ["not offered", "not available", "unavailable", "check with the boss"]):
                if '"' in prompt:
                    import re
                    match = re.search(r'"([^"]*)"', prompt)
                    if match:
                        current_settings["unavailable_service_message"] = match.group(1)
                        changes_made = True

            if changes_made:
                st.session_state.settings = current_settings
                st.success("Coach updated your settings. Click **Save Changes** to apply them permanently.")

    st.session_state.coach_messages.append({"role": "assistant", "content": response})
 
    if st.button("Clear Coach Chat"):
        st.session_state.coach_messages = []
        st.rerun()

# ====================== FOOTER ======================
st.divider()
st.caption("Phase 1.5 • Real RAG + Structured Settings + AI Coach active")
