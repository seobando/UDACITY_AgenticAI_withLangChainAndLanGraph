"""RAG tool for retrieving knowledge base articles."""

import os
import json
from typing import List, Optional, Dict, Any
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
                JSON string with structured knowledge base results.
            """
            return json.dumps({
                "success": False,
                "error": "No knowledge base articles available.",
                "articles": []
            })
        
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
                JSON string with structured knowledge base results including article titles and excerpts.
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
                return json.dumps({
                    "success": False,
                    "query": query,
                    "articles": [],
                    "message": "No relevant information found in the knowledge base."
                })
            
            # Sort by score and return top 3
            results.sort(key=lambda x: x[0], reverse=True)
            top_results = results[:3]
            
            articles_list = []
            for score, article in top_results:
                # Create excerpt (first 200 chars)
                excerpt = article['content'][:200] + "..." if len(article['content']) > 200 else article['content']
                articles_list.append({
                    "title": article['title'],
                    "excerpt": excerpt,
                    "content": article['content'],
                    "tags": article['tags'],
                    "relevance_score": score,
                })
            
            return json.dumps({
                "success": True,
                "query": query,
                "articles": articles_list,
                "count": len(articles_list)
            })
        
        return search_knowledge_base
    
    @tool
    def search_knowledge_base(query: str) -> str:
        """Search the knowledge base for information about CultPass.
        
        Args:
            query: The search query about CultPass features, policies, or procedures.
        
        Returns:
            JSON string with structured knowledge base results including article titles and excerpts.
        """
        try:
            # Try with score first, fallback to without score
            try:
                docs_with_scores = vectorstore.similarity_search_with_score(query, k=3)
                docs = docs_with_scores
                has_scores = True
            except AttributeError:
                # Fallback if method doesn't exist
                docs = vectorstore.similarity_search(query, k=3)
                has_scores = False
            
            if not docs:
                return json.dumps({
                    "success": False,
                    "query": query,
                    "articles": [],
                    "message": "No relevant information found in the knowledge base."
                })
            
            articles_list = []
            for item in docs:
                if has_scores:
                    doc, score = item
                else:
                    doc = item
                    score = 0.5  # Default score if not available
                # Extract title from doc content (format: "Title: ...\nContent: ...")
                content = doc.page_content
                title = "Unknown"
                article_content = content
                
                if "Title:" in content:
                    parts = content.split("Content:", 1)
                    if len(parts) == 2:
                        title = parts[0].replace("Title:", "").strip()
                        article_content = parts[1].strip()
                
                # Create excerpt
                excerpt = article_content[:200] + "..." if len(article_content) > 200 else article_content
                
                articles_list.append({
                    "title": title,
                    "excerpt": excerpt,
                    "content": article_content,
                    "relevance_score": float(1.0 - score) if score < 1.0 else 0.9,  # Convert distance to similarity
                })
            
            return json.dumps({
                "success": True,
                "query": query,
                "articles": articles_list,
                "count": len(articles_list)
            })
        except Exception as e:
            # Fallback to keyword matching if vector search fails
            return json.dumps({
                "success": False,
                "query": query,
                "articles": [],
                "error": f"Error searching knowledge base: {str(e)}"
            })
    
    return search_knowledge_base

