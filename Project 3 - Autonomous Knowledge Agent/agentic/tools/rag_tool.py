"""RAG tool for retrieving knowledge base articles."""

import os
from typing import List, Optional
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from langchain_core.tools import tool
from langchain_openai import OpenAIEmbeddings
from langchain_community.vectorstores import FAISS
from langchain_text_splitters import RecursiveCharacterTextSplitter

from data.models import udahub
from utils import get_session


def _get_knowledge_base(account_id: str = "cultpass") -> List[dict]:
    """Retrieve all knowledge base articles for an account."""
    db_path = os.path.join(os.path.dirname(__file__), "../../data/core/udahub.db")
    engine = create_engine(f"sqlite:///{db_path}", echo=False)
    
    with get_session(engine) as session:
        articles = session.query(udahub.Knowledge).filter_by(
            account_id=account_id
        ).all()
        
        return [
            {
                "title": article.title,
                "content": article.content,
                "tags": article.tags,
            }
            for article in articles
        ]


def create_rag_tool(account_id: str = "cultpass"):
    """Create a RAG tool for knowledge base retrieval."""
    
    # Get knowledge base articles
    articles = _get_knowledge_base(account_id)
    
    if not articles:
        # Return a simple tool that says no knowledge base available
        @tool
        def search_knowledge_base(query: str) -> str:
            """Search the knowledge base for information about CultPass.
            
            Args:
                query: The search query about CultPass features, policies, or procedures.
            
            Returns:
                Relevant information from the knowledge base.
            """
            return "No knowledge base articles available."
        
        return search_knowledge_base
    
    # Create embeddings and vector store
    texts = [f"Title: {a['title']}\nContent: {a['content']}\nTags: {a['tags']}" 
             for a in articles]
    
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=1000,
        chunk_overlap=200
    )
    
    splits = text_splitter.create_documents(texts)
    
    try:
        embeddings = OpenAIEmbeddings()
        vectorstore = FAISS.from_documents(splits, embeddings)
    except Exception as e:
        # Fallback to simple keyword matching if embeddings fail
        print(f"Warning: Could not create vector store: {e}. Using keyword matching.")
        
        @tool
        def search_knowledge_base(query: str) -> str:
            """Search the knowledge base for information about CultPass.
            
            Args:
                query: The search query about CultPass features, policies, or procedures.
            
            Returns:
                Relevant information from the knowledge base.
            """
            query_lower = query.lower()
            results = []
            
            for article in articles:
                score = 0
                # Simple keyword matching
                if query_lower in article['title'].lower():
                    score += 3
                if query_lower in article['content'].lower():
                    score += 2
                if article['tags'] and query_lower in article['tags'].lower():
                    score += 1
                
                if score > 0:
                    results.append((score, article))
            
            if not results:
                return "No relevant information found in the knowledge base."
            
            # Sort by score and return top 3
            results.sort(key=lambda x: x[0], reverse=True)
            top_results = results[:3]
            
            response = "Relevant information from knowledge base:\n\n"
            for score, article in top_results:
                response += f"**{article['title']}**\n{article['content']}\n\n"
            
            return response
        
        return search_knowledge_base
    
    @tool
    def search_knowledge_base(query: str) -> str:
        """Search the knowledge base for information about CultPass.
        
        Args:
            query: The search query about CultPass features, policies, or procedures.
        
        Returns:
            Relevant information from the knowledge base.
        """
        try:
            docs = vectorstore.similarity_search(query, k=3)
            if not docs:
                return "No relevant information found in the knowledge base."
            
            response = "Relevant information from knowledge base:\n\n"
            for doc in docs:
                response += f"{doc.page_content}\n\n"
            
            return response
        except Exception as e:
            return f"Error searching knowledge base: {str(e)}"
    
    return search_knowledge_base

