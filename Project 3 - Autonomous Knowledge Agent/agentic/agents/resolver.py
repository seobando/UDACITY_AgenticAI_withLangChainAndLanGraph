"""Resolver agent that attempts to resolve tickets using tools."""

from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, AIMessage, HumanMessage
from langchain_core.tools import Tool
from typing import List


def create_resolver_agent(llm: ChatOpenAI, tools: List[Tool]):
    """Create a resolver agent that uses tools to resolve tickets."""
    
    # Bind tools to the LLM
    llm_with_tools = llm.bind_tools(tools)
    
    system_prompt = (
        "You are a helpful customer support agent for CultPass. "
        "Your goal is to resolve customer issues efficiently and accurately. "
        "Use the available tools to look up information, search the knowledge base, "
        "and provide helpful responses to customers.\n\n"
        "Guidelines:\n"
        "- Always be polite and professional\n"
        "- Use tools to get accurate information before responding\n"
        "- If you cannot resolve an issue, suggest escalating to human support\n"
        "- For login issues, guide users through password reset\n"
        "- For subscription questions, check their subscription status first\n"
        "- For reservation issues, look up their reservations\n"
        "- Only process refunds if explicitly approved (use refund tool with caution)\n"
        "- Provide clear, actionable solutions\n"
    )
    
    def resolver_agent(state: dict) -> dict:
        """Attempt to resolve the ticket using available tools."""
        print("DEBUG: Resolver agent called")  # Debug line
        messages = state.get("messages", [])
        classification = state.get("classification", {})
        
        print(f"DEBUG: Messages count: {len(messages)}, Classification: {classification}")  # Debug line
        
        if not messages:
            print("DEBUG: No messages, returning empty")  # Debug line
            return {"messages": [], "resolution_attempted": True}
        
        # Get the current ticket/question
        current_message = messages[-1]
        print(f"DEBUG: Current message: {current_message.content[:50] if hasattr(current_message, 'content') else 'No content'}")  # Debug line
        
        # Add context about the classification
        context_message = ""
        if classification:
            context_message = (
                f"Ticket Classification: {classification.get('issue_type', 'unknown')} "
                f"(Urgency: {classification.get('urgency', 'medium')}, "
                f"Confidence: {classification.get('confidence', 0.5):.2f})\n"
                f"Summary: {classification.get('summary', 'N/A')}\n\n"
            )
        
        # Build the conversation for the LLM
        conversation_messages = [
            SystemMessage(content=system_prompt + context_message),
            current_message
        ]
        
        try:
            print("DEBUG: Invoking LLM with tools...")  # Debug line
            # Get initial response from LLM (may include tool calls)
            response = llm_with_tools.invoke(conversation_messages)
            print(f"DEBUG: LLM response received: {type(response)}, has content: {hasattr(response, 'content')}")  # Debug line
            
            # Ensure we have a valid response
            if not response:
                print("DEBUG: No response from LLM")  # Debug line
                return {
                    "messages": [AIMessage(content="I'm having trouble processing your request. Please try again.")],
                    "resolution_attempted": True,
                }
            
            # If the response includes tool calls, execute them
            tool_calls = getattr(response, 'tool_calls', None) or []
            if tool_calls:
                # Add the AI message with tool calls to conversation
                conversation_messages.append(response)
                
                # Execute each tool call
                for tool_call in tool_calls:
                    # Handle both dict and object formats
                    if isinstance(tool_call, dict):
                        tool_name = tool_call.get("name", "")
                        tool_args = tool_call.get("args", {})
                        tool_call_id = tool_call.get("id", "")
                    else:
                        tool_name = getattr(tool_call, "name", "")
                        tool_args = getattr(tool_call, "args", {})
                        tool_call_id = getattr(tool_call, "id", "")
                    
                    # Find the tool
                    tool = None
                    for t in tools:
                        if t.name == tool_name:
                            tool = t
                            break
                    
                    if tool:
                        try:
                            # Execute the tool
                            tool_result = tool.invoke(tool_args)
                            
                            # Add tool result to conversation
                            from langchain_core.messages import ToolMessage
                            conversation_messages.append(
                                ToolMessage(
                                    content=str(tool_result),
                                    tool_call_id=tool_call_id or ""
                                )
                            )
                        except Exception as e:
                            # Add error message
                            from langchain_core.messages import ToolMessage
                            conversation_messages.append(
                                ToolMessage(
                                    content=f"Error executing tool: {str(e)}",
                                    tool_call_id=tool_call_id or ""
                                )
                            )
                
                # Get final response after tool execution
                final_response = llm_with_tools.invoke(conversation_messages)
                
                # Extract just the final AI message content
                if final_response and hasattr(final_response, 'content') and final_response.content:
                    return {
                        "messages": [AIMessage(content=final_response.content)],
                        "resolution_attempted": True,
                    }
                else:
                    # If final response is empty, use a default message
                    return {
                        "messages": [AIMessage(content="I've looked up the information, but I'm having trouble formulating a response. Please try rephrasing your question.")],
                        "resolution_attempted": True,
                    }
            
            # If no tool calls, return the response directly
            if response and hasattr(response, 'content') and response.content:
                print(f"DEBUG: Returning AI response (no tools): {response.content[:100]}")  # Debug line
                return {
                    "messages": [AIMessage(content=response.content)],
                    "resolution_attempted": True,
                }
            elif response and hasattr(response, 'content'):
                # Response exists but content is empty
                return {
                    "messages": [AIMessage(content="I understand your question. Let me help you with that.")],
                    "resolution_attempted": True,
                }
            
            # Fallback response
            return {
                "messages": [AIMessage(content="I'm working on resolving your issue. Please provide more details.")],
                "resolution_attempted": True,
            }
            
        except Exception as e:
            print(f"Error in resolver agent: {e}")
            import traceback
            traceback.print_exc()
            return {
                "messages": [AIMessage(content=f"I encountered an error while processing your request: {str(e)}. Let me escalate this to human support.")],
                "resolution_attempted": True,
                "escalation_requested": True,
            }
    
    return resolver_agent

