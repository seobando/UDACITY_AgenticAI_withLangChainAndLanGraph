"""Classifier agent that classifies support tickets."""

from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage
from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field
from typing import Optional


class TicketClassification(BaseModel):
    """Classification of a support ticket."""
    issue_type: str = Field(
        description="The type of issue: 'login', 'subscription', 'reservation', 'billing', 'technical', 'other'"
    )
    urgency: str = Field(
        description="Urgency level: 'low', 'medium', 'high', 'critical'"
    )
    confidence: float = Field(
        description="Confidence in classification (0.0 to 1.0)"
    )
    tags: Optional[str] = Field(
        default=None,
        description="Relevant tags for the ticket"
    )
    summary: str = Field(
        description="Brief summary of the issue"
    )


def create_classifier_agent(llm: ChatOpenAI):
    """Create a classifier agent that classifies support tickets."""
    
    classification_prompt = ChatPromptTemplate.from_messages([
        SystemMessage(content=(
            "You are a ticket classification agent for CultPass customer support. "
            "Your job is to analyze customer support tickets and classify them accurately. "
            "Classify tickets into one of these categories: "
            "- login: Issues with account access, passwords, authentication\n"
            "- subscription: Questions about subscription status, tiers, quotas, cancellation\n"
            "- reservation: Issues with booking, canceling, or managing reservations\n"
            "- billing: Payment issues, refunds, billing questions\n"
            "- technical: App issues, QR codes, technical problems\n"
            "- other: Anything that doesn't fit the above categories\n\n"
            "Also assess urgency: low, medium, high, or critical.\n"
            "Provide a confidence score between 0.0 and 1.0.\n"
            "Extract relevant tags and provide a brief summary."
        )),
        ("human", "Classify this ticket: {ticket_content}")
    ])
    
    def classifier_agent(state: dict) -> dict:
        """Classify the ticket and update state."""
        messages = state.get("messages", [])
        if not messages:
            return {"classification": None}
        
        # Get the ticket content from the last user message
        ticket_content = messages[-1].content if messages else ""
        
        # Get conversation history for context
        conversation_context = "\n".join([
            f"{msg.__class__.__name__}: {msg.content}" 
            for msg in messages[:-1]  # Exclude the last message which is the current ticket
        ])
        
        if conversation_context:
            full_context = f"Previous conversation:\n{conversation_context}\n\nCurrent ticket: {ticket_content}"
        else:
            full_context = ticket_content
        
        # Classify using structured output
        llm_with_structure = llm.with_structured_output(TicketClassification)
        
        try:
            classification = llm_with_structure.invoke(
                classification_prompt.format_messages(ticket_content=full_context)
            )
            
            return {
                "classification": {
                    "issue_type": classification.issue_type,
                    "urgency": classification.urgency,
                    "confidence": classification.confidence,
                    "tags": classification.tags,
                    "summary": classification.summary,
                }
            }
        except Exception as e:
            # Fallback classification
            print(f"Error in classification: {e}")
            return {
                "classification": {
                    "issue_type": "other",
                    "urgency": "medium",
                    "confidence": 0.5,
                    "tags": None,
                    "summary": "Unable to classify automatically",
                }
            }
    
    return classifier_agent

