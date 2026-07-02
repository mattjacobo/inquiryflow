"""
InquiryFlow - RAG Utilities for Stage 1.5
Handles uploading, chunking, embedding, and storing knowledge base documents in Supabase.
"""

import os
from typing import List
from dotenv import load_dotenv
from langchain_community.document_loaders import PyPDFLoader, TextLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_openai import OpenAIEmbeddings
from langchain_community.vectorstores import SupabaseVectorStore
from supabase import create_client, Client

load_dotenv()

# Supabase setup
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

if SUPABASE_URL and SUPABASE_KEY:
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
else:
    supabase = None

embeddings = OpenAIEmbeddings(model="text-embedding-3-small")


def get_vectorstore():
    """Returns a SupabaseVectorStore instance if credentials are available."""
    if not supabase:
        return None
    return SupabaseVectorStore(
        client=supabase,
        embedding=embeddings,
        table_name="knowledge_chunks",
        query_name="match_knowledge_chunks",  # You may need to create this function in Supabase later
    )


def process_and_store_documents(file_paths: List[str], metadata: dict = None):
    """
    Process uploaded files, chunk them, embed, and store in Supabase.
    Returns number of chunks stored.
    """
    if not supabase:
        raise ValueError("Supabase credentials not found in .env")

    docs = []
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=1000,
        chunk_overlap=200,
        length_function=len,
    )

    for file_path in file_paths:
        if file_path.lower().endswith(".pdf"):
            loader = PyPDFLoader(file_path)
        else:
            loader = TextLoader(file_path, encoding="utf-8")

        loaded_docs = loader.load()
        for doc in loaded_docs:
            if metadata:
                doc.metadata.update(metadata)
        chunks = text_splitter.split_documents(loaded_docs)
        docs.extend(chunks)

    if not docs:
        return 0

    vectorstore = get_vectorstore()
    if vectorstore:
        vectorstore.add_documents(docs)
        return len(docs)
    else:
        return 0


def retrieve_context(query: str, k: int = 5) -> str:
    """
    Retrieve relevant context from Supabase vector store.
    Falls back to empty string if not available.
    """
    vectorstore = get_vectorstore()
    if not vectorstore:
        return ""

    try:
        docs = vectorstore.similarity_search(query, k=k)
        context = "\n\n".join([doc.page_content for doc in docs])
        return context
    except Exception as e:
        print(f"RAG retrieval error: {e}")
        return ""