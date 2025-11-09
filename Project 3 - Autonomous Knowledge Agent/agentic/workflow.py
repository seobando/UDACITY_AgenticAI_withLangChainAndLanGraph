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
    _next_agent: str  # Internal routing decision (not persisted)


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
        print("DEBUG: supervisor_node called in workflow")
        result = supervisor(state)
        print(f"DEBUG: supervisor returned: {result}")
        # Get next_agent from result (don't pop, keep it for state)
        next_agent = result.get("next_agent", "end")
        # Store next_agent in state for routing function (use a key that will be in state)
        result["_next_agent"] = next_agent
        print(f"DEBUG: supervisor_node routing to: {next_agent}, setting _next_agent in result")
        return result
    
    # Wrap nodes with debugging
    def classifier_node(state: AgentState) -> dict:
        print("DEBUG: classifier_node called in workflow")
        result = classifier(state)
        print(f"DEBUG: classifier returned: {result}")
        return result
    
    def resolver_node(state: AgentState) -> dict:
        print("DEBUG: resolver_node called in workflow")
        result = resolver(state)
        print(f"DEBUG: resolver returned: {result}")
        return result
    
    def escalation_node(state: AgentState) -> dict:
        print("DEBUG: escalation_node called in workflow")
        result = escalation(state)
        print(f"DEBUG: escalation returned: {result}")
        return result
    
    # Add nodes
    workflow.add_node("supervisor", supervisor_node)
    workflow.add_node("classifier", classifier_node)
    workflow.add_node("resolver", resolver_node)
    workflow.add_node("escalation", escalation_node)
    
    # Set entry point
    workflow.set_entry_point("supervisor")
    
    # Add conditional edges from supervisor
    def route_from_supervisor(state: AgentState) -> Literal["classifier", "resolver", "escalation", "end"]:
        """Route based on supervisor decision stored in state."""
        # Check both _next_agent and next_agent (in case it wasn't removed)
        route = state.get("_next_agent") or state.get("next_agent", "end")
        print(f"DEBUG: route_from_supervisor - state keys: {list(state.keys())}, _next_agent: {state.get('_next_agent')}, next_agent: {state.get('next_agent')}")
        print(f"DEBUG: route_from_supervisor returning: {route}")
        return route
    
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
