"""Resolver agent that attempts to resolve tickets using tools."""

from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, AIMessage, HumanMessage
from langchain_core.tools import Tool
from typing import List
from agentic.logging_config import get_logger
from agentic.memory import get_historical_context

logger = get_logger()


def create_resolver_agent(llm: ChatOpenAI, tools: List[Tool]):
    """Create a resolver agent that uses tools to resolve tickets."""
    
    # Bind tools to the LLM
    llm_with_tools = llm.bind_tools(tools)
    
    system_prompt = (
        "You are a helpful customer support agent for CultPass. "
        "Your goal is to resolve customer issues efficiently and accurately. "
        "IMPORTANT: You MUST always call search_knowledge_base first before answering any question. "
        "All responses must be grounded in knowledge base articles.\n\n"
        "Guidelines:\n"
        "- ALWAYS call search_knowledge_base tool first for every customer question\n"
        "- Tool responses are in JSON format - parse them to extract structured data\n"
        "- For knowledge base results: Include the article title(s) and key information in your response\n"
        "- For database lookups: Format the structured data (user info, subscription details, etc.) clearly\n"
        "- If search_knowledge_base returns success=false or 'No relevant information found', you cannot answer and must escalate\n"
        "- Always be polite and professional\n"
        "- Use other tools (lookup_user, lookup_subscription, etc.) as needed for specific user data\n"
        "- Format tool results clearly in your response to the customer\n"
        "- If you cannot resolve an issue with knowledge base articles, suggest escalating to human support\n"
        "- Only process refunds if explicitly approved (use refund tool with caution)\n"
        "- Provide clear, actionable solutions based on knowledge base content\n"
    )
    
    def resolver_agent(state: dict) -> dict:
        """Attempt to resolve the ticket using available tools."""
        thread_id = state.get("_thread_id", "unknown")
        user_id = state.get("_user_id", "unknown")
        account_id = state.get("_account_id", "cultpass")
        
        messages = state.get("messages", [])
        classification = state.get("classification", {})
        
        logger.debug(
            "Resolver agent processing",
            extra={
                "agent": "resolver",
                "thread_id": thread_id,
                "messages_count": len(messages),
                "classification": classification,
            }
        )
        
        if not messages:
            return {"messages": [], "resolution_attempted": True}
        
        # Get the current ticket/question
        current_message = messages[-1]
        
        # Get historical context for personalized responses
        historical_context = ""
        if classification and user_id != "unknown":
            issue_type = classification.get("issue_type", "unknown")
            historical_context = get_historical_context(user_id, issue_type, account_id)
        
        # Add context about the classification
        context_message = ""
        if classification:
            context_message = (
                f"Ticket Classification: {classification.get('issue_type', 'unknown')} "
                f"(Urgency: {classification.get('urgency', 'medium')}, "
                f"Confidence: {classification.get('confidence', 0.5):.2f})\n"
                f"Summary: {classification.get('summary', 'N/A')}\n"
            )
            
            if historical_context:
                context_message += f"\nHistorical Context: {historical_context}\n"
            
            context_message += "\n"
        
        # Build the conversation for the LLM
        conversation_messages = [
            SystemMessage(content=system_prompt + context_message),
            current_message
        ]
        
        # Find the search_knowledge_base tool
        kb_tool = None
        for t in tools:
            if t.name == "search_knowledge_base":
                kb_tool = t
                break
        
        # Track if KB was searched and results
        kb_searched = False
        kb_results = None
        kb_has_results = False
        
        try:
            # ENFORCE KB GROUNDING: Always search KB first
            if kb_tool and current_message and hasattr(current_message, 'content'):
                query = current_message.content
                try:
                    logger.info(
                        "Enforcing KB grounding - searching knowledge base",
                        extra={
                            "agent": "resolver",
                            "thread_id": thread_id,
                            "query": query[:100],
                        }
                    )
                    
                    kb_results = kb_tool.invoke({"query": query})
                    kb_searched = True
                    
                    # Parse KB results (JSON format)
                    try:
                        import json
                        kb_data = json.loads(str(kb_results)) if isinstance(kb_results, str) else kb_results
                        if isinstance(kb_data, str):
                            kb_data = json.loads(kb_data)
                        
                        # Check if KB returned successful results
                        if kb_data.get("success") and kb_data.get("articles") and len(kb_data.get("articles", [])) > 0:
                            kb_has_results = True
                        else:
                            kb_has_results = False
                    except (json.JSONDecodeError, AttributeError):
                        # Fallback: check string content
                        if kb_results and "No relevant information found" not in str(kb_results) and "success" not in str(kb_results).lower():
                            kb_has_results = True
                        else:
                            kb_has_results = False
                    
                    if kb_has_results:
                        # Add KB results to conversation
                        from langchain_core.messages import ToolMessage
                        conversation_messages.append(
                            ToolMessage(
                                content=str(kb_results),
                                tool_call_id="kb_search_enforced"
                            )
                        )
                        logger.info(
                            "KB search completed with results",
                            extra={
                                "agent": "resolver",
                                "thread_id": thread_id,
                                "kb_has_results": True,
                            }
                        )
                    else:
                        kb_has_results = False
                        logger.warning(
                            "KB search returned no results - will escalate",
                            extra={
                                "agent": "resolver",
                                "thread_id": thread_id,
                                "kb_has_results": False,
                            }
                        )
                except Exception as e:
                    logger.error(
                        "KB search error",
                        extra={
                            "agent": "resolver",
                            "thread_id": thread_id,
                            "error": str(e),
                        }
                    )
                    kb_has_results = False
            
            # Check confidence - low confidence should escalate
            confidence = classification.get("confidence", 1.0) if classification else 1.0
            if confidence < 0.5:
                logger.info(
                    "Low confidence classification - escalating",
                    extra={
                        "agent": "resolver",
                        "thread_id": thread_id,
                        "confidence": confidence,
                    }
                )
                return {
                    "messages": [AIMessage(content="I'm not confident I can help with this issue. Let me escalate this to a human agent who can assist you better.")],
                    "resolution_attempted": True,
                    "escalation_requested": True,
                }
            
            # If KB search found no results, escalate
            if kb_searched and not kb_has_results:
                logger.info(
                    "No KB results found - escalating",
                    extra={
                        "agent": "resolver",
                        "thread_id": thread_id,
                    }
                )
                return {
                    "messages": [AIMessage(content="I couldn't find relevant information in our knowledge base to help with your question. Let me escalate this to a human support agent who can assist you better.")],
                    "resolution_attempted": True,
                    "escalation_requested": True,
                }
            
            # Get initial response from LLM (may include additional tool calls)
            response = llm_with_tools.invoke(conversation_messages)
            
            # Ensure we have a valid response
            if not response:
                logger.warning(
                    "No response from LLM",
                    extra={
                        "agent": "resolver",
                        "thread_id": thread_id,
                    }
                )
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
                            logger.info(
                                "Tool invoked",
                                extra={
                                    "agent": "resolver",
                                    "thread_id": thread_id,
                                    "tool_name": tool_name,
                                    "tool_args": tool_args,
                                }
                            )
                            
                            # Execute the tool
                            tool_result = tool.invoke(tool_args)
                            
                            logger.info(
                                "Tool execution completed",
                                extra={
                                    "agent": "resolver",
                                    "thread_id": thread_id,
                                    "tool_name": tool_name,
                                    "tool_result_length": len(str(tool_result)),
                                }
                            )
                            
                            # Add tool result to conversation
                            from langchain_core.messages import ToolMessage
                            conversation_messages.append(
                                ToolMessage(
                                    content=str(tool_result),
                                    tool_call_id=tool_call_id or ""
                                )
                            )
                        except Exception as e:
                            logger.error(
                                "Tool execution error",
                                extra={
                                    "agent": "resolver",
                                    "thread_id": thread_id,
                                    "tool_name": tool_name,
                                    "error": str(e),
                                }
                            )
                            
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
            logger.error(
                "Resolver agent error",
                extra={
                    "agent": "resolver",
                    "thread_id": thread_id,
                    "error": str(e),
                },
                exc_info=True
            )
            return {
                "messages": [AIMessage(content=f"I encountered an error while processing your request: {str(e)}. Let me escalate this to human support.")],
                "resolution_attempted": True,
                "escalation_requested": True,
            }
    
    return resolver_agent

