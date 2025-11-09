"""Memory and persistence management for UDA-Hub."""

import os
import uuid
from typing import List, Dict, Optional, Any
from datetime import datetime
from sqlalchemy import create_engine
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage
from utils import get_session
import sys
sys.path.append(os.path.join(os.path.dirname(__file__), ".."))
from data.models import udahub


def _get_udahub_engine():
    """Get engine for UDA-Hub core database."""
    db_path = os.path.join(os.path.dirname(__file__), "../data/core/udahub.db")
    return create_engine(f"sqlite:///{db_path}", echo=False)


def save_conversation_to_database(
    ticket_id: str,
    account_id: str,
    user_id: str,
    messages: List[BaseMessage],
    classification: Optional[Dict[str, Any]] = None,
    resolution_status: Optional[str] = None,
) -> None:
    """
    Save conversation history to database.
    
    Args:
        ticket_id: The ticket/thread ID
        account_id: Account ID (e.g., 'cultpass')
        user_id: User ID (external user ID from CultPass)
        messages: List of messages in the conversation
        classification: Classification data if available
        resolution_status: Status of resolution (resolved, escalated, etc.)
    """
    engine = _get_udahub_engine()
    
    with get_session(engine) as session:
        # Get or create user
        user = session.query(udahub.User).filter_by(
            account_id=account_id,
            external_user_id=user_id,
        ).first()
        
        if not user:
            # Create user if doesn't exist
            user = udahub.User(
                user_id=str(uuid.uuid4()),
                account_id=account_id,
                external_user_id=user_id,
                user_name=f"User {user_id}",  # Default name
            )
            session.add(user)
            session.flush()  # Get the user_id
        
        # Get or create ticket
        ticket = session.query(udahub.Ticket).filter_by(
            ticket_id=ticket_id
        ).first()
        
        if not ticket:
            ticket = udahub.Ticket(
                ticket_id=ticket_id,
                account_id=account_id,
                user_id=user.user_id,
                channel="chat",
            )
            session.add(ticket)
            session.flush()
        
        # Get or create ticket metadata
        metadata = session.query(udahub.TicketMetadata).filter_by(
            ticket_id=ticket_id
        ).first()
        
        if not metadata:
            metadata = udahub.TicketMetadata(
                ticket_id=ticket_id,
                status="open",
                main_issue_type=classification.get("issue_type") if classification else None,
                tags=classification.get("tags") if classification else None,
            )
            session.add(metadata)
        else:
            # Update metadata if classification available
            if classification:
                metadata.main_issue_type = classification.get("issue_type")
                metadata.tags = classification.get("tags")
                metadata.updated_at = datetime.now()
            
            # Update status
            if resolution_status:
                metadata.status = resolution_status
                metadata.updated_at = datetime.now()
        
        # Save messages (only save new messages not already in database)
        # Get existing messages for this ticket
        existing_messages = {
            (msg.role.name, msg.content[:500] if msg.content else "")  # Use first 500 chars for comparison
            for msg in session.query(udahub.TicketMessage).filter_by(ticket_id=ticket_id).all()
        }
        
        for msg in messages:
            # Determine role
            if isinstance(msg, HumanMessage):
                role = udahub.RoleEnum.user
            elif isinstance(msg, AIMessage):
                role = udahub.RoleEnum.ai
            else:
                role = udahub.RoleEnum.system
            
            # Get message content
            msg_content = msg.content if hasattr(msg, 'content') else str(msg)
            msg_key = (role.name, msg_content[:500])
            
            # Check if message already exists (avoid duplicates)
            if msg_key not in existing_messages:
                message = udahub.TicketMessage(
                    message_id=str(uuid.uuid4()),
                    ticket_id=ticket_id,
                    role=role,
                    content=msg_content,
                )
                session.add(message)
                existing_messages.add(msg_key)  # Track added message


def get_conversation_history(
    user_id: str,
    account_id: str = "cultpass",
    limit: int = 10
) -> List[Dict[str, Any]]:
    """
    Retrieve conversation history for a user.
    
    Args:
        user_id: External user ID
        account_id: Account ID
        limit: Maximum number of recent tickets to retrieve
    
    Returns:
        List of conversation histories with messages
    """
    engine = _get_udahub_engine()
    
    with get_session(engine) as session:
        # Find user
        user = session.query(udahub.User).filter_by(
            account_id=account_id,
            external_user_id=user_id,
        ).first()
        
        if not user:
            return []
        
        # Get recent tickets for this user
        tickets = session.query(udahub.Ticket).filter_by(
            account_id=account_id,
            user_id=user.user_id,
        ).order_by(udahub.Ticket.created_at.desc()).limit(limit).all()
        
        histories = []
        for ticket in tickets:
            # Get messages for this ticket
            messages = session.query(udahub.TicketMessage).filter_by(
                ticket_id=ticket.ticket_id
            ).order_by(udahub.TicketMessage.created_at.asc()).all()
            
            # Get metadata
            metadata = session.query(udahub.TicketMetadata).filter_by(
                ticket_id=ticket.ticket_id
            ).first()
            
            histories.append({
                "ticket_id": ticket.ticket_id,
                "created_at": ticket.created_at.isoformat() if ticket.created_at else None,
                "status": metadata.status if metadata else "unknown",
                "issue_type": metadata.main_issue_type if metadata else None,
                "messages": [
                    {
                        "role": msg.role.name,
                        "content": msg.content,
                        "created_at": msg.created_at.isoformat() if msg.created_at else None,
                    }
                    for msg in messages
                ]
            })
        
        return histories


def get_user_preferences(user_id: str, account_id: str = "cultpass") -> Dict[str, Any]:
    """
    Get user preferences and resolved issues from conversation history.
    
    Args:
        user_id: External user ID
        account_id: Account ID
    
    Returns:
        Dictionary with preferences and resolved issues
    """
    histories = get_conversation_history(user_id, account_id, limit=20)
    
    preferences = {
        "resolved_issues": [],
        "common_issues": {},
        "preferred_resolution_method": None,
    }
    
    # Analyze history
    for history in histories:
        if history["status"] == "resolved":
            preferences["resolved_issues"].append({
                "ticket_id": history["ticket_id"],
                "issue_type": history["issue_type"],
                "resolved_at": history["created_at"],
            })
        
        if history["issue_type"]:
            issue_type = history["issue_type"]
            preferences["common_issues"][issue_type] = preferences["common_issues"].get(issue_type, 0) + 1
    
    return preferences


def save_resolved_issue(
    ticket_id: str,
    issue_type: str,
    resolution_summary: str,
    account_id: str = "cultpass"
) -> None:
    """
    Save a resolved issue for long-term memory.
    
    Args:
        ticket_id: Ticket ID
        issue_type: Type of issue
        resolution_summary: Summary of how it was resolved
        account_id: Account ID
    """
    # This could be extended to a separate resolved_issues table
    # For now, we rely on ticket metadata status
    engine = _get_udahub_engine()
    
    with get_session(engine) as session:
        metadata = session.query(udahub.TicketMetadata).filter_by(
            ticket_id=ticket_id
        ).first()
        
        if metadata:
            metadata.status = "resolved"
            metadata.updated_at = datetime.now()
            # Could add resolution_summary to metadata if we extend the schema


def get_historical_context(user_id: str, current_issue_type: str, account_id: str = "cultpass") -> str:
    """
    Get historical context for a user based on current issue type.
    
    Args:
        user_id: External user ID
        current_issue_type: Current issue being addressed
        account_id: Account ID
    
    Returns:
        Formatted historical context string
    """
    preferences = get_user_preferences(user_id, account_id)
    histories = get_conversation_history(user_id, account_id, limit=5)
    
    context_parts = []
    
    # Add resolved similar issues
    similar_resolved = [
        issue for issue in preferences["resolved_issues"]
        if issue.get("issue_type") == current_issue_type
    ]
    
    if similar_resolved:
        context_parts.append(
            f"User has previously resolved {len(similar_resolved)} similar {current_issue_type} issue(s)."
        )
    
    # Add common issues
    if preferences["common_issues"]:
        most_common = max(preferences["common_issues"].items(), key=lambda x: x[1])
        context_parts.append(
            f"User's most common issue type is {most_common[0]} ({most_common[1]} occurrences)."
        )
    
    # Add recent conversation context
    if histories:
        recent_tickets = histories[:3]  # Last 3 tickets
        context_parts.append(f"User has {len(recent_tickets)} recent support interactions.")
    
    return " ".join(context_parts) if context_parts else ""

