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

# Import logging and memory
from agentic.logging_config import setup_logging, get_logger
from agentic.memory import save_conversation_to_database, save_resolved_issue

# Setup logging
logger = setup_logging()


class AgentState(TypedDict, total=False):
    """State for the agent workflow."""
    messages: Annotated[list[BaseMessage], add]
    classification: dict | None
    resolution_attempted: bool
    escalation_requested: bool
    escalated: bool
    _next_agent: str  # Internal routing decision (not persisted)
    _thread_id: str  # Thread ID for logging and persistence
    _user_id: str  # User ID for persistence
    _account_id: str  # Account ID for persistence


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
        thread_id = state.get("_thread_id", "unknown")
        logger.info(
            "Supervisor node called",
            extra={
                "agent": "supervisor",
                "thread_id": thread_id,
                "messages_count": len(state.get("messages", [])),
                "has_classification": state.get("classification") is not None,
            }
        )
        
        result = supervisor(state)
        next_agent = result.get("next_agent", "end")
        result["_next_agent"] = next_agent
        
        logger.info(
            "Supervisor routing decision",
            extra={
                "agent": "supervisor",
                "thread_id": thread_id,
                "routing_decision": next_agent,
                "classification": state.get("classification"),
                "resolution_attempted": state.get("resolution_attempted", False),
            }
        )
        
        return result
    
    # Wrap nodes with logging
    def classifier_node(state: AgentState) -> dict:
        thread_id = state.get("_thread_id", "unknown")
        logger.info(
            "Classifier node called",
            extra={
                "agent": "classifier",
                "thread_id": thread_id,
            }
        )
        
        result = classifier(state)
        
        if result.get("classification"):
            logger.info(
                "Ticket classified",
                extra={
                    "agent": "classifier",
                    "thread_id": thread_id,
                    "classification": result["classification"],
                }
            )
        
        return result
    
    def resolver_node(state: AgentState) -> dict:
        thread_id = state.get("_thread_id", "unknown")
        logger.info(
            "Resolver node called",
            extra={
                "agent": "resolver",
                "thread_id": thread_id,
                "classification": state.get("classification"),
            }
        )
        
        result = resolver(state)
        
        logger.info(
            "Resolution attempted",
            extra={
                "agent": "resolver",
                "thread_id": thread_id,
                "resolution_attempted": result.get("resolution_attempted", False),
                "escalation_requested": result.get("escalation_requested", False),
            }
        )
        
        return result
    
    def escalation_node(state: AgentState) -> dict:
        thread_id = state.get("_thread_id", "unknown")
        logger.info(
            "Escalation node called",
            extra={
                "agent": "escalation",
                "thread_id": thread_id,
                "classification": state.get("classification"),
            }
        )
        
        result = escalation(state)
        
        logger.info(
            "Ticket escalated",
            extra={
                "agent": "escalation",
                "thread_id": thread_id,
                "outcome": "escalated",
            }
        )
        
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
        route = state.get("_next_agent") or state.get("next_agent", "end")
        thread_id = state.get("_thread_id", "unknown")
        
        logger.debug(
            "Routing from supervisor",
            extra={
                "agent": "supervisor",
                "thread_id": thread_id,
                "routing_decision": route,
            }
        )
        
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
