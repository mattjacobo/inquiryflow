-- InquiryFlow Phase 1 Database Schema
-- Designed for maintainability, auditability, and future multi-tenancy.
-- Run this in Supabase SQL Editor after creating your project and enabling pgvector.

-- Enable vector extension (required for RAG)
create extension if not exists vector;

-- ============================================
-- TENANTS (Businesses using InquiryFlow)
-- ============================================
create table if not exists tenants (
    id uuid primary key default gen_random_uuid(),
    name text not null,
    slug text unique not null,                    -- e.g. "elite-auto-detailing"
    created_at timestamptz default now(),
    settings jsonb default '{}'::jsonb            -- future: tone preferences, pricing rules, etc.
);

-- ============================================
-- INQUIRIES (Core records)
-- ============================================
create table if not exists inquiries (
    id uuid primary key default gen_random_uuid(),
    tenant_id uuid references tenants(id) on delete cascade,
    
    -- Raw input
    original_text text not null,
    source text default 'manual',                 -- manual, instagram, email, webform, etc.
    customer_name text,
    customer_contact text,                        -- phone, IG handle, email
    
    -- AI-generated structured data
    customer_type text check (customer_type in ('new', 'existing', 'unknown')),
    category text,                                -- e.g. 'brake_service', 'audio_install', 'general_inquiry'
    summary text,
    urgency text check (urgency in ('low', 'medium', 'high')),
    
    -- Draft & approval
    draft_response text,
    final_response text,
    status text default 'pending_review' check (status in (
        'pending_review', 'approved', 'sent', 'rejected', 'needs_more_info'
    )),
    
    -- Metadata
    created_at timestamptz default now(),
    reviewed_at timestamptz,
    reviewed_by text,                             -- future: user id or name
    metadata jsonb default '{}'::jsonb            -- store confidence scores, token usage, etc.
);

-- ============================================
-- KNOWLEDGE BASE (RAG source)
-- ============================================
create table if not exists knowledge_chunks (
    id uuid primary key default gen_random_uuid(),
    tenant_id uuid references tenants(id) on delete cascade,
    
    content text not null,                        -- the actual text chunk
    metadata jsonb default '{}'::jsonb,           -- source file, page, service name, etc.
    embedding vector(1536),                       -- OpenAI text-embedding-3-small dimension
    
    created_at timestamptz default now()
);

-- Create index for fast similarity search
create index if not exists knowledge_chunks_embedding_idx 
    on knowledge_chunks using ivfflat (embedding vector_cosine_ops);

-- ============================================
-- AUDIT LOG (Critical for trust & improvement)
-- ============================================
create table if not exists audit_logs (
    id uuid primary key default gen_random_uuid(),
    tenant_id uuid references tenants(id),
    inquiry_id uuid references inquiries(id),
    action text not null,                         -- 'classified', 'drafted', 'approved', 'edited', 'sent'
    actor text default 'system',                  -- 'system' or human user name/id
    details jsonb default '{}'::jsonb,            -- before/after, reasoning, etc.
    created_at timestamptz default now()
);

-- ============================================
-- Helpful Views (for dashboard queries)
-- ============================================
create or replace view pending_inquiries as
select 
    id,
    original_text,
    customer_name,
    category,
    summary,
    urgency,
    draft_response,
    created_at
from inquiries
where status = 'pending_review'
order by 
    case urgency 
        when 'high' then 1 
        when 'medium' then 2 
        else 3 
    end,
    created_at asc;

comment on table inquiries is 'Central record of every customer inquiry and how it was handled. Enables analytics and continuous improvement.';
comment on table knowledge_chunks is 'Chunked business knowledge (services, FAQs, case studies) with embeddings for RAG. Ground truth for all AI suggestions.';
comment on table audit_logs is 'Complete history of every action. Essential for trust, debugging, and later training better models.';