"""Supervisor agent that routes tickets to appropriate agents."""

from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage
from langchain_core.prompts import ChatPromptTemplate
from typing import Literal


def create_supervisor_agent(llm: ChatOpenAI):
    """Create a supervisor agent that routes to other agents."""
    
    def supervisor_agent(state: dict) -> dict:
        """Route the ticket to the appropriate agent based on current state.
        
        Returns:
            Updated state with routing decision in 'next_agent' key
        """
        messages = state.get("messages", [])
        if not messages:
            print("DEBUG: Supervisor - No messages, ending")  # Debug line
            return {"next_agent": "end"}
        
        print(f"DEBUG: Supervisor - Messages: {len(messages)}, Classification: {state.get('classification')}, Resolution attempted: {state.get('resolution_attempted', False)}")  # Debug line
        
        # Get the last user message
        last_message = messages[-1].content if messages and hasattr(messages[-1], 'content') else ""
        
        # Check if we already have a classification
        classification = state.get("classification")
        resolution_attempted = state.get("resolution_attempted", False)
        escalation_requested = state.get("escalation_requested", False)
        escalated = state.get("escalated", False)
        
        # If already escalated, end
        if escalated:
            return {"next_agent": "end"}
        
        # If escalation was requested, go to escalation agent
        if escalation_requested:
            return {"next_agent": "escalation"}
        
        # If we don't have a classification yet, route to classifier
        if not classification:
            print("DEBUG: Supervisor - Routing to classifier")  # Debug line
            return {"next_agent": "classifier"}
        
        # If we have classification but haven't attempted resolution, route to resolver
        if classification and not resolution_attempted:
            print("DEBUG: Supervisor - Routing to resolver")  # Debug line
            return {"next_agent": "resolver"}
        
        # If resolution was attempted, check if we need to continue or end
        if resolution_attempted:
            # Find the last HumanMessage (user's input) to check their intent
            from langchain_core.messages import HumanMessage
            human_messages = [msg for msg in messages if isinstance(msg, HumanMessage)]
            if human_messages:
                last_user_message = human_messages[-1].content.lower() if hasattr(human_messages[-1], 'content') else ""
                # Check if user explicitly wants escalation
                if any(word in last_user_message for word in ["escalate", "human", "agent", "manager", "supervisor", "speak to"]):
                    return {"next_agent": "escalation", "escalation_requested": True}
                # If user says thanks or seems satisfied, end
                if any(word in last_user_message for word in ["thanks", "thank you", "solved", "resolved", "helpful", "perfect", "great"]):
                    return {"next_agent": "end"}
            
            # After resolution, end the workflow (user can send another message if needed)
            # This allows the resolver's response to be returned to the user
            return {"next_agent": "end"}
        
        # Default: end
        return {"next_agent": "end"}
    
    return supervisor_agent

