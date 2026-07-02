"""
InquiryFlow Phase 1 — LangGraph Workflow
"""

from typing import TypedDict, Optional
from langchain_openai import ChatOpenAI
from langchain_core.output_parsers import JsonOutputParser, StrOutputParser
from langgraph.graph import StateGraph, END

from prompts import classifier_prompt, drafter_prompt
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
        "summary": result.get("summary", "Unable to summarize."),
        "status": "pending_review"
    }


def retrieve_context_node(state: InquiryState) -> dict:
    query = state.get("summary") or state["original_text"]
    context = retrieve_context(query, k=5)

    if not context:
        context = "We provide professional automotive services. Please provide more details about your vehicle."

    return {"retrieved_context": context}


def draft_node(state: InquiryState, settings: dict = None) -> dict:
    """
    Role in bigger picture:
    Produces the actual first message the customer will see (after human approval).
    Now respects service availability from Settings.
    """
    if settings is None:
        settings = {}

    # Get enabled services as a clean list
    enabled_services = []
    for category, services in settings.get("services", {}).items():
        for service, enabled in services.items():
            if enabled:
                enabled_services.append(service)

    unavailable_message = settings.get(
        "unavailable_service_message",
        "I'm sorry, but it looks like we currently do not offer that service. "
        "However, I will check with the boss for further confirmation."
    )

    chain = drafter_prompt | llm_drafter | StrOutputParser()

    draft = chain.invoke({
        "inquiry_text": state["original_text"],
        "summary": state.get("summary", ""),
        "retrieved_context": state.get("retrieved_context", ""),
        "enabled_services": ", ".join(enabled_services) if enabled_services else "None",
        "unavailable_service_message": unavailable_message
    })

    return {"draft_response": draft.strip()}


def build_workflow():
    workflow = StateGraph(InquiryState)
    workflow.add_node("classify", classify_node)
    workflow.add_node("retrieve_context", retrieve_context_node)
    # We removed draft_node from the graph for now
    workflow.set_entry_point("classify")
    workflow.add_edge("classify", "retrieve_context")
    # draft_node is now called manually in process_inquiry()
    workflow.add_edge("retrieve_context", END)
    return workflow.compile()


def process_inquiry(
    original_text: str, 
    customer_name: Optional[str] = None,
    settings: dict = None
) -> InquiryState:
    """
    High-level entry point used by the dashboard.
    Now accepts settings so the AI can respect service availability.
    """
    if settings is None:
        settings = {}

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
    }

    # We need to pass settings into the draft node.
    # Since LangGraph nodes don't easily accept extra args, we'll handle it manually here.
    final_state = app.invoke(initial_state)

    # Manually run draft_node with settings (workaround for now)
    draft_result = draft_node(final_state, settings=settings)
    final_state["draft_response"] = draft_result.get("draft_response", "")

    return final_state