-- ============================================
-- InquiryFlow Supabase Schema (Phase 1.5)
-- ============================================

-- Enable pgvector extension for RAG
create extension if not exists vector;

-- ============================================
-- KNOWLEDGE CHUNKS (RAG)
-- ============================================
create table if not exists knowledge_chunks (
    id uuid primary key default gen_random_uuid(),
    content text not null,
    metadata jsonb default '{}'::jsonb,
    embedding vector(1536),
    created_at timestamptz default now()
);

-- Create index for vector similarity search
create index if not exists knowledge_chunks_embedding_idx 
on knowledge_chunks 
using hnsw (embedding vector_cosine_ops);

-- ============================================
-- APP SETTINGS
-- ============================================
create table if not exists app_settings (
    id int primary key default 1,
    data jsonb not null default '{}'::jsonb,
    updated_at timestamptz default now()
);

-- ============================================
-- INQUIRIES (for future persistence)
-- ============================================
create table if not exists inquiries (
    id uuid primary key default gen_random_uuid(),
    original_text text not null,
    customer_name text,
    customer_type text,
    category text,
    urgency text,
    summary text,
    draft_response text,
    final_response text,
    status text default 'pending_review',
    created_at timestamptz default now()
);

-- ============================================
-- AUDIT LOG
-- ============================================
create table if not exists audit_logs (
    id uuid primary key default gen_random_uuid(),
    inquiry_id uuid references inquiries(id),
    action text not null,
    actor text default 'system',
    details jsonb default '{}'::jsonb,
    created_at timestamptz default now()
);

-- Comments for documentation
comment on table knowledge_chunks is 'Chunked business knowledge with embeddings for RAG.';
comment on table app_settings is 'Application configuration (services, tone, etc.).';
comment on table inquiries is 'Customer inquiries and how they were handled.';
comment on table audit_logs is 'History of all actions for audit and improvement.';
