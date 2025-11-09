"""LangGraph workflow orchestrator for UDA-Hub multi-agent system."""

from typing import TypedDict, Annotated, Literal
from operator import add
from langchain_openai import ChatOpenAI
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver

# Import agents
from agentic.agents import (
    create_supervisor_agent,
    create_classifier_agent,
    create_resolver_agent,
    create_escalation_agent,
)

# Import tools
from agentic.tools import (
    create_rag_tool,
    create_user_lookup_tool,
    create_subscription_lookup_tool,
    create_reservation_lookup_tool,
    create_experience_lookup_tool,
    create_refund_tool,
)


class AgentState(TypedDict, total=False):
    """State for the agent workflow."""
    messages: Annotated[list[BaseMessage], add]
    classification: dict | None
    resolution_attempted: bool
    escalation_requested: bool
    escalated: bool


def create_orchestrator():
    """Create the main orchestrator workflow."""
    
    # Initialize LLM
    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
    
    # Create tools
    tools = [
        create_rag_tool(),
        create_user_lookup_tool(),
        create_subscription_lookup_tool(),
        create_reservation_lookup_tool(),
        create_experience_lookup_tool(),
        create_refund_tool(),
    ]
    
    # Create agents
    supervisor = create_supervisor_agent(llm)
    classifier = create_classifier_agent(llm)
    resolver = create_resolver_agent(llm, tools)
    escalation = create_escalation_agent(llm)
    
    # Create the graph
    workflow = StateGraph(AgentState)
    
    # Helper function to wrap supervisor and extract routing
    def supervisor_node(state: AgentState) -> dict:
        """Supervisor node that updates state and determines routing."""
        result = supervisor(state)
        # Extract next_agent before returning state updates
        next_agent = result.pop("next_agent", "end")
        # Store next_agent in state for routing function
        result["_next_agent"] = next_agent
        return result
    
    # Add nodes
    workflow.add_node("supervisor", supervisor_node)
    workflow.add_node("classifier", classifier)
    workflow.add_node("resolver", resolver)
    workflow.add_node("escalation", escalation)
    
    # Set entry point
    workflow.set_entry_point("supervisor")
    
    # Add conditional edges from supervisor
    def route_from_supervisor(state: AgentState) -> Literal["classifier", "resolver", "escalation", "end"]:
        """Route based on supervisor decision stored in state."""
        return state.get("_next_agent", "end")
    
    workflow.add_conditional_edges(
        "supervisor",
        route_from_supervisor,
        {
            "classifier": "classifier",
            "resolver": "resolver",
            "escalation": "escalation",
            "end": END,
        }
    )
    
    # After classifier, go back to supervisor to route to resolver
    workflow.add_edge("classifier", "supervisor")
    
    # After resolver, go back to supervisor to check if escalation needed
    workflow.add_edge("resolver", "supervisor")
    
    # After escalation, end
    workflow.add_edge("escalation", END)
    
    # Compile with checkpointer
    checkpointer = MemorySaver()
    app = workflow.compile(checkpointer=checkpointer)
    
    return app


# Create the orchestrator instance
orchestrator = create_orchestrator()
