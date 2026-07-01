"""
InquiryFlow - RAG Utilities
Handles document processing, embedding, and retrieval from Supabase pgvector.
"""

import os
from dotenv import load_dotenv
from langchain_community.document_loaders import PyPDFLoader, TextLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_openai import OpenAIEmbeddings
from langchain_community.vectorstores import SupabaseVectorStore
from supabase import create_client, Client

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

if SUPABASE_URL and SUPABASE_KEY:
    supabase_client: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
else:
    supabase_client = None

embeddings = OpenAIEmbeddings(model="text-embedding-3-small")


def process_and_store_documents(file_paths):
    """Process uploaded documents and store embeddings in Supabase."""
    if not supabase_client:
        return 0

    all_chunks = []
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=1000,
        chunk_overlap=200
    )

    for file_path in file_paths:
        if file_path.endswith(".pdf"):
            loader = PyPDFLoader(file_path)
        else:
            loader = TextLoader(file_path, encoding="utf-8")

        docs = loader.load()
        chunks = text_splitter.split_documents(docs)
        all_chunks.extend(chunks)

    vector_store = SupabaseVectorStore.from_documents(
        all_chunks,
        embeddings,
        client=supabase_client,
        table_name="knowledge_chunks",
        query_name="match_documents"
    )

    return len(all_chunks)


def retrieve_context(query: str, k: int = 5) -> str:
    """Retrieve relevant context from Supabase vector store."""
    if not supabase_client:
        return ""

    vector_store = SupabaseVectorStore(
        client=supabase_client,
        embedding=embeddings,
        table_name="knowledge_chunks",
        query_name="match_documents"
    )

    docs = vector_store.similarity_search(query, k=k)
    context = "\n\n".join([doc.page_content for doc in docs])

    return context
