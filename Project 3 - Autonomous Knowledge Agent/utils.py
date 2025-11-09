# reset_udahub.py
import os
from sqlalchemy import create_engine, Engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.declarative import declarative_base
from contextlib import contextmanager
from langchain_core.messages import (
    SystemMessage,
    HumanMessage,
    AIMessage,
)
from langgraph.graph.state import CompiledStateGraph


Base = declarative_base()

def reset_db(db_path: str, echo: bool = True):
    """Drops the existing udahub.db file and recreates all tables."""

    # Remove the file if it exists
    if os.path.exists(db_path):
        os.remove(db_path)
        print(f"✅ Removed existing {db_path}")

    # Create a new engine and recreate tables
    engine = create_engine(f"sqlite:///{db_path}", echo=echo)
    Base.metadata.create_all(engine)
    print(f"✅ Recreated {db_path} with fresh schema")


@contextmanager
def get_session(engine: Engine):
    Session = sessionmaker(bind=engine)
    session = Session()
    try:
        yield session
        session.commit()
    except:
        session.rollback()
        raise
    finally:
        session.close()


def model_to_dict(instance):
    """Convert a SQLAlchemy model instance to a dictionary."""
    return {
        column.name: getattr(instance, column.name)
        for column in instance.__table__.columns
    }

def send_message(agent: CompiledStateGraph, message: str, ticket_id: str = "1", verbose: bool = True):
    """
    Send a single message to the agent and get a response.
    Jupyter-friendly version that works better than the interactive chat_interface.
    
    Args:
        agent: The LangGraph orchestrator
        message: The user's message
        ticket_id: The conversation thread ID (default: "1")
        verbose: Whether to print the conversation (default: True)
    
    Returns:
        The assistant's response as a string
    """
    if not message.strip():
        return "Please provide a message."
    
    # Prepare input with just the new message
    # State will be loaded from checkpointer
    trigger = {
        "messages": [HumanMessage(content=message)],
    }
    
    config = {
        "configurable": {
            "thread_id": ticket_id,
        }
    }
    
    try:
        if verbose:
            print(f"User: {message}\n")
        
        result = agent.invoke(input=trigger, config=config)
        
        # Get the last AI message
        messages = result.get("messages", [])
        if messages:
            # Find the last AIMessage (skip HumanMessage and SystemMessage)
            ai_messages = [msg for msg in messages if isinstance(msg, AIMessage)]
            
            if ai_messages:
                # Get the most recent AI message
                response = ai_messages[-1].content
                if verbose:
                    print(f"Assistant: {response}\n")
                return response
            else:
                # Debug: show what messages we have
                if verbose:
                    print(f"Debug: No AIMessage found. Message types: {[type(msg).__name__ for msg in messages]}\n")
                    print(f"Debug: Last message: {messages[-1]}\n")
                
                # Fallback: get last message content (but warn if it's a HumanMessage)
                last_msg = messages[-1]
                if isinstance(last_msg, HumanMessage):
                    # This means the workflow didn't produce a response
                    response = "I'm processing your request, but didn't receive a response. Please try again."
                elif hasattr(last_msg, 'content'):
                    response = last_msg.content
                else:
                    response = str(last_msg)
                
                if verbose:
                    print(f"Assistant: {response}\n")
                
                return response
        else:
            response = "I'm processing your request..."
            if verbose:
                print(f"Assistant: {response}\n")
            return response
            
    except Exception as e:
        error_msg = f"I encountered an error: {str(e)}"
        if verbose:
            print(f"Assistant: {error_msg}\n")
            import traceback
            traceback.print_exc()
            print("Please try rephrasing your question or contact support directly.\n")
        return error_msg


def chat_interface(agent:CompiledStateGraph, ticket_id:str):
    """Interactive chat interface for the agent."""
    print("UDA-Hub Customer Support Agent")
    print("Type 'quit', 'exit', or 'q' to end the conversation.\n")
    
    while True:
        user_input = input("User: ")
        if user_input.lower() in ["quit", "exit", "q"]:
            print("Assistant: Goodbye! Thank you for contacting CultPass support.")
            break
        
        if not user_input.strip():
            continue
        
        # Prepare input with just the new message
        # State will be loaded from checkpointer
        trigger = {
            "messages": [HumanMessage(content=user_input)],
        }
        
        config = {
            "configurable": {
                "thread_id": ticket_id,
            }
        }
        
        try:
            result = agent.invoke(input=trigger, config=config)
            
            # Get the last AI message
            messages = result.get("messages", [])
            if messages:
                # Find the last AIMessage
                from langchain_core.messages import AIMessage
                ai_messages = [msg for msg in messages if isinstance(msg, AIMessage)]
                if ai_messages:
                    print(f"Assistant: {ai_messages[-1].content}\n")
                else:
                    # Fallback: print last message content
                    last_msg = messages[-1]
                    if hasattr(last_msg, 'content'):
                        print(f"Assistant: {last_msg.content}\n")
                    else:
                        print(f"Assistant: {str(last_msg)}\n")
            else:
                print("Assistant: I'm processing your request...\n")
                
        except Exception as e:
            print(f"Assistant: I encountered an error: {str(e)}\n")
            print("Please try rephrasing your question or contact support directly.\n")