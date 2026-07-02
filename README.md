# InquiryFlow Phase 1 — Pragmatic MVP

**Goal**: Build a maintainable, commercially viable AI-powered inquiry management system for rapidly growing SMBs (starting with automotive services).  
The system dramatically reduces response time while **never** letting AI make commitments to customers without explicit human approval.

This Phase 1 focuses on the highest-ROI slice:
- Fast ingestion + classification + summarization
- Grounded draft responses (RAG over business knowledge base)
- Clean human-in-the-loop approval dashboard
- Full audit trail

Everything is designed for **maintainability**, **trust**, and **fast iteration** toward a sellable SaaS product.

---

## Why This Architecture (Bigger Picture)

### Business Problem We’re Solving
SMB owners are overwhelmed by Instagram/DM/email inquiries. Slow responses kill conversions. Hiring more staff is expensive. Full auto-pilot AI is too risky (hallucinations on pricing/scope destroy trust and create legal exposure).

**InquiryFlow’s differentiation**: AI does the heavy lifting (categorize, summarize, research, draft) → Human stays in complete control of anything sent to a customer. This builds trust and makes adoption safe.

### Why LangGraph + Streamlit + Supabase
- **LangGraph**: Stateful orchestration with native checkpoints and interrupts. Perfect for human approval gates. Excellent debugging and auditability — critical when money and reputation are on the line. More maintainable long-term than ad-hoc scripts or simpler frameworks.
- **Streamlit**: Python-native, lets us build a beautiful, intuitive dashboard extremely fast. The dashboard is the “control center” — this is what the business owner interacts with daily. Clean UX here determines whether they trust and keep using the system.
- **Supabase (Postgres + pgvector)**: Handles multi-tenancy, authentication, structured data (inquiries), and vector embeddings for RAG in one place. Easy to scale from MVP to production. Matches the stack you already planned.

### Human-in-the-Loop (HITL) Philosophy
Every customer-facing output **must** pass through a human. This is non-negotiable for commercial viability in service businesses. The dashboard makes this fast and pleasant, not a burden.

---

## Project Structure
