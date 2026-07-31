"""
InquiryFlow Phase 1 — LangGraph Workflow
"""

from typing import TypedDict, Optional
from langchain_openai import ChatOpenAI
from langchain_core.output_parsers import JsonOutputParser, StrOutputParser
from langgraph.graph import StateGraph, END

from prompts import classifier_prompt, drafter_prompt, vehicle_verification_prompt
from rag_utils import retrieve_context


class InquiryState(TypedDict):
    inquiry_id: Optional[str]
    original_text: str
    customer_name: Optional[str]
    customer_type: Optional[str]
    category: Optional[str]
    urgency: Optional[str]
    summary: Optional[str]
    retrieved_context: Optional[str]
    draft_response: Optional[str]
    human_edited_draft: Optional[str]
    status: str
    reviewed_by: Optional[str]


llm = ChatOpenAI(model="gpt-4o-mini", temperature=0.2)
llm_drafter = ChatOpenAI(model="gpt-4o", temperature=0.3)


def classify_node(state: InquiryState) -> dict:
    chain = classifier_prompt | llm | JsonOutputParser()
    result = chain.invoke({"inquiry_text": state["original_text"]})
    return {
        "customer_type": result.get("customer_type", "unknown"),
        "category": result.get("category", "other"),
        "urgency": result.get("urgency", "medium"),
        "summary": result.get("summary", ""),
        "quote_snippet": result.get("quote_snippet", ""),
        "status": "pending_review",
    }


import re

def extract_vehicle_candidate(text: str) -> str:
    """Pull a likely Year Make Model phrase for verification."""
    if not text:
        return ""
    match = re.search(
        r"\b((?:19|20)\d{2}\s+[A-Za-z][A-Za-z0-9 \-]{1,40})",
        text
    )
    if match:
        return match.group(1).strip()
    return text[:500]


def retrieve_context_node(state: InquiryState) -> dict:
    query = state.get("summary") or state["original_text"]
    context = retrieve_context(query, k=5)
    if not context:
        context = "We provide professional automotive services. Please provide more details about your vehicle."
    return {"retrieved_context": context}


def draft_node(
    state: InquiryState,
    settings: dict = None,
    vehicle_verification: dict = None
) -> dict:
    """
    Produces the response the customer will see (after human approval).
    Now respects service availability and vehicle verification.
    """
    if settings is None:
        settings = {}
    if vehicle_verification is None:
        vehicle_verification = {}

    # Build list of enabled services
    enabled_services = []
    for category, services in settings.get("services", {}).items():
        if isinstance(services, dict):
            for service, enabled in services.items():
                if enabled:
                    enabled_services.append(service)

    unavailable_message = settings.get(
        "unavailable_service_message",
        "I'm sorry, but it looks like we currently do not offer that service. "
        "However, I will check with the boss for further confirmation."
    )

    # Create a clear note about vehicle verification for the prompt
    if (
        vehicle_verification.get("vehicle_exists") is True
        and vehicle_verification.get("confidence") == "high"
    ):
        vehicle_note = f"Verified vehicle: {vehicle_verification.get('normalized_vehicle')}"
    else:
        vehicle_note = (
            "Vehicle could not be verified with high confidence. "
            "Politely ask the customer to confirm the exact year, make, and model "
            "before giving specific advice."
        )

    chain = drafter_prompt | llm_drafter | StrOutputParser()

    draft = chain.invoke({
        "inquiry_text": state["original_text"],
        "summary": state.get("summary", ""),
        "retrieved_context": state.get("retrieved_context", ""),
        "enabled_services": ", ".join(enabled_services) if enabled_services else "None",
        "unavailable_service_message": unavailable_message,
        "vehicle_note": vehicle_note,
    })

    return {"draft_response": draft.strip()}


def build_workflow():
    workflow = StateGraph(InquiryState)
    workflow.add_node("classify", classify_node)
    workflow.add_node("retrieve_context", retrieve_context_node)
    workflow.set_entry_point("classify")
    workflow.add_edge("classify", "retrieve_context")
    workflow.add_edge("retrieve_context", END)
    return workflow.compile()

def verify_vehicle(vehicle_text: str) -> dict:
    """
    Strict LLM-only check whether a vehicle exists.
    Returns a normalized result with confidence.
    """
    if not vehicle_text or len(vehicle_text.strip()) < 5:
        return {
            "vehicle_exists": False,
            "confidence": "low",
            "normalized_vehicle": None,
            "reason": "Insufficient vehicle information provided."
        }

    try:
        chain = vehicle_verification_prompt | llm_verifier | JsonOutputParser()
        result = chain.invoke({"vehicle_text": vehicle_text.strip()})

        # Force safe defaults
        return {
            "vehicle_exists": bool(result.get("vehicle_exists", False)),
            "confidence": result.get("confidence", "low"),
            "normalized_vehicle": result.get("normalized_vehicle"),
            "reason": result.get("reason", "")
        }
    except Exception as e:
        print(f"Vehicle verification failed: {e}")
        return {
            "vehicle_exists": False,
            "confidence": "low",
            "normalized_vehicle": None,
            "reason": "Verification error"
        }


def process_inquiry(
    original_text: str,
    customer_name: Optional[str] = None,
    settings: dict = None
) -> InquiryState:
    """
    High-level entry point used by the dashboard and email intake.
    Vehicle verification runs first as a prerequisite.
    """
    # Safety check - use defaults if settings are invalid
    if settings is None or not isinstance(settings.get("services"), dict):
        from settings_utils import get_default_settings
        print("Warning: Invalid or missing settings. Using defaults.")
        settings = get_default_settings()

    # ============================================
    # 1. VEHICLE VERIFICATION (prerequisite)
    # ============================================
    vehicle_verification = verify_vehicle(original_text)

    # ============================================
    # 2. Run the rest of the workflow
    # ============================================
    app = build_workflow()

    initial_state: InquiryState = {
        "original_text": original_text,
        "customer_name": customer_name,
        "inquiry_id": None,
        "customer_type": None,
        "category": None,
        "urgency": None,
        "summary": None,
        "retrieved_context": None,
        "draft_response": None,
        "human_edited_draft": None,
        "status": "pending_review",
        "reviewed_by": None,
        "vehicle_verification": vehicle_verification,
    }

    final_state = app.invoke(initial_state)

    # Run draft_node with settings + verification result
    draft_result = draft_node(
        final_state,
        settings=settings,
        vehicle_verification=vehicle_verification
    )
    final_state["draft_response"] = draft_result.get("draft_response", "")
    final_state["vehicle_verification"] = vehicle_verification

    return final_state

