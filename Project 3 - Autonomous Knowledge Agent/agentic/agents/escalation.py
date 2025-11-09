"""Escalation agent that handles ticket escalations."""

from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, AIMessage
from langchain_core.prompts import ChatPromptTemplate
from agentic.logging_config import get_logger

logger = get_logger()


def create_escalation_agent(llm: ChatOpenAI):
    """Create an escalation agent that handles escalated tickets."""
    
    escalation_prompt = ChatPromptTemplate.from_messages([
        SystemMessage(content=(
            "You are an escalation specialist for CultPass customer support. "
            "Your role is to handle tickets that need human intervention. "
            "You should:\n"
            "- Acknowledge the customer's concern\n"
            "- Summarize the issue clearly\n"
            "- Explain that a human agent will review the case\n"
            "- Provide a ticket reference if available\n"
            "- Set appropriate expectations for response time\n"
            "- Be empathetic and professional\n\n"
            "Create a clear summary that will help the human agent understand the issue quickly."
        )),
        ("human", "Ticket details: {ticket_content}\n\nClassification: {classification}\n\nResolution attempts: {resolution_attempts}")
    ])
    
    def escalation_agent(state: dict) -> dict:
        """Handle ticket escalation."""
        thread_id = state.get("_thread_id", "unknown")
        
        messages = state.get("messages", [])
        classification = state.get("classification", {})
        resolution_attempted = state.get("resolution_attempted", False)
        
        logger.info(
            "Escalation agent processing",
            extra={
                "agent": "escalation",
                "thread_id": thread_id,
                "classification": classification,
                "resolution_attempted": resolution_attempted,
            }
        )
        
        # Get ticket content
        ticket_content = messages[-1].content if messages else "No ticket content available"
        
        # Get conversation history
        conversation_history = "\n".join([
            f"{msg.__class__.__name__}: {msg.content[:200]}" 
            for msg in messages[:-1]
        ])
        
        classification_str = (
            f"Issue Type: {classification.get('issue_type', 'unknown')}, "
            f"Urgency: {classification.get('urgency', 'medium')}, "
            f"Summary: {classification.get('summary', 'N/A')}"
        ) if classification else "Not classified"
        
        resolution_attempts_str = (
            "Resolution was attempted but the issue requires human intervention."
            if resolution_attempted else
            "Issue was escalated before resolution attempt."
        )
        
        try:
            response = llm.invoke(
                escalation_prompt.format_messages(
                    ticket_content=ticket_content,
                    classification=classification_str,
                    resolution_attempts=resolution_attempts_str
                )
            )
            
            # Add ticket reference
            escalation_message = (
                f"{response.content}\n\n"
                f"**Ticket Reference:** ESC-{hash(ticket_content) % 10000:04d}\n"
                f"A human support agent will review your case and respond within 24 hours."
            )
            
            return {
                "messages": [AIMessage(content=escalation_message)],
                "escalation_requested": True,
                "escalated": True,
            }
            
        except Exception as e:
            logger.error(
                "Escalation agent error",
                extra={
                    "agent": "escalation",
                    "thread_id": thread_id,
                    "error": str(e),
                },
                exc_info=True
            )
            return {
                "messages": [AIMessage(
                    content=(
                        "I understand you need additional assistance. "
                        "I've escalated your ticket to our human support team. "
                        f"**Ticket Reference:** ESC-{hash(ticket_content) % 10000:04d}\n"
                        "A support agent will review your case and respond within 24 hours. "
                        "Thank you for your patience."
                    )
                )],
                "escalation_requested": True,
                "escalated": True,
            }
    
    return escalation_agent

