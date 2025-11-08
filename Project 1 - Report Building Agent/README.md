# Document Assistant - Report Building Agent

A sophisticated document processing system built with LangChain and LangGraph that uses a multi-agent architecture to handle Q&A, summarization, and calculation tasks on financial and healthcare documents.

## Table of Contents

- [Overview](#overview)
- [Architecture](#architecture)
- [Implementation Decisions](#implementation-decisions)
- [State and Memory Management](#state-and-memory-management)
- [Structured Outputs](#structured-outputs)
- [Example Conversations](#example-conversations)
- [Installation](#installation)
- [Usage](#usage)
- [Project Structure](#project-structure)

## Overview

This document assistant intelligently routes user requests to specialized agents:
- **Q&A Agent**: Answers specific questions about document content with source citations
- **Summarization Agent**: Creates comprehensive summaries and extracts key points
- **Calculation Agent**: Performs mathematical operations on document data

The system maintains conversation context across turns and tracks document references throughout the session.

## Architecture

The system uses LangGraph to create a stateful workflow that processes user requests through the following pipeline:

```
User Input → classify_intent → [qa_agent | summarization_agent | calculation_agent] → update_memory → END
```

### Workflow Graph

1. **classify_intent**: Analyzes user input and conversation history to determine intent
2. **Agent Nodes**: Specialized agents handle specific task types
3. **update_memory**: Summarizes conversation and tracks active documents
4. **State Persistence**: Uses `InMemorySaver` checkpointer to maintain state across invocations

## Implementation Decisions

### 1. Multi-Agent Architecture

**Decision**: Separate specialized agents for different task types rather than a single general-purpose agent.

**Rationale**:
- Each agent can have tailored system prompts optimized for its specific task
- Easier to maintain and extend individual agent capabilities
- Clear separation of concerns improves debugging and testing
- Allows for different structured output schemas per agent type

**Implementation**: Intent classification routes to specialized agents (`qa_agent`, `summarization_agent`, `calculation_agent`) each with distinct prompts and response schemas.

### 2. Structured Output Enforcement

**Decision**: Use Pydantic models with `llm.with_structured_output()` for all LLM responses.

**Rationale**:
- Guarantees type safety and consistent response formats
- Eliminates need for error-prone string parsing
- Provides clear validation and error messages
- Enables better IDE support and documentation

**Implementation**: Each agent enforces structured output:
- `UserIntent` for intent classification
- `AnswerResponse` for Q&A tasks
- `SummarizationResponse` for summarization tasks
- `CalculationResponse` for calculation tasks
- `UpdateMemoryResponse` for memory updates

### 3. State Reducers for Accumulation

**Decision**: Use `operator.add` reducer for `actions_taken` field to accumulate node execution history.

**Rationale**:
- Tracks the complete execution path through the graph
- Useful for debugging and understanding agent behavior
- Demonstrates LangGraph's reducer pattern for list accumulation

**Implementation**:
```python
actions_taken: Annotated[List[str], operator.add]
```

Each node appends its name to this list, creating a trace of execution.

### 4. Persistent Memory with Checkpointer

**Decision**: Use `InMemorySaver` checkpointer to persist state across workflow invocations.

**Rationale**:
- Maintains conversation context without manual state management
- Enables multi-turn conversations with memory
- Thread-based isolation allows multiple concurrent sessions
- Foundation for future database-backed persistence

**Implementation**: 
- Workflow compiled with `checkpointer=InMemorySaver()`
- Each session uses a unique `thread_id` (session_id) for state isolation
- State automatically loaded and saved on each invocation

### 5. Tool-Based Document Access

**Decision**: Expose document operations through LangChain tools rather than direct function calls.

**Rationale**:
- LLMs can intelligently decide when and how to use tools
- Tools provide clear descriptions that guide LLM behavior
- Enables logging and monitoring of tool usage
- Follows LangChain best practices for agent tooling

**Implementation**: Four tools available to agents:
- `document_search`: Find documents by keyword, type, or amount
- `document_reader`: Read full content of specific documents
- `calculator`: Safely evaluate mathematical expressions
- `document_statistics`: Get collection-level statistics

### 6. Safe Calculator Implementation

**Decision**: Use regex validation before `eval()` to prevent code injection.

**Rationale**:
- `eval()` is necessary for flexible expression evaluation
- Security validation restricts to safe mathematical operations only
- Clear error messages guide users to correct usage

**Implementation**: 
- Regex pattern: `^[\d\s\+\-\*\/\(\)\.]+$` (only numbers and basic operators)
- Comprehensive error handling for division by zero and invalid expressions
- All tool usage logged for audit trail

### 7. Dual Memory System

**Decision**: Maintain both LangGraph checkpointer state and file-based session storage.

**Rationale**:
- Checkpointer provides runtime state persistence
- File storage enables session resumption across application restarts
- Separation allows independent evolution of each system

**Implementation**:
- LangGraph state: Managed by `InMemorySaver` with thread_id
- Session files: JSON files in `./sessions/` directory with `SessionState` schema

## State and Memory Management

### AgentState Structure

The `AgentState` TypedDict defines the complete state that flows through the workflow:

```python
class AgentState(TypedDict):
    # Current conversation
    user_input: Optional[str]           # Current user message
    messages: Annotated[List[BaseMessage], add_messages]  # Conversation history
    
    # Intent and routing
    intent: Optional[UserIntent]        # Classified intent
    next_step: str                      # Next node to execute
    
    # Memory and context
    conversation_summary: str           # Summarized conversation history
    active_documents: Optional[List[str]]  # Document IDs referenced
    
    # Current task state
    current_response: Optional[Dict[str, Any]]  # Agent's structured response
    tools_used: List[str]               # Tools invoked in this turn
    
    # Session management
    session_id: Optional[str]
    user_id: Optional[str]
    
    # Execution tracking
    actions_taken: Annotated[List[str], operator.add]  # Nodes executed
```

### State Flow Through Workflow

1. **Initial State** (in `assistant.py`):
   - User input set
   - Previous conversation summary loaded from checkpointer
   - Active documents from session restored
   - Messages initialized (empty for new conversations)

2. **Intent Classification**:
   - Updates: `intent`, `next_step`, `actions_taken`

3. **Agent Execution** (qa/summarization/calculation):
   - Updates: `messages`, `current_response`, `tools_used`, `next_step`, `actions_taken`
   - Agents use ReAct pattern with tool calling

4. **Memory Update**:
   - LLM summarizes conversation history
   - Extracts active document IDs
   - Updates: `conversation_summary`, `active_documents`, `next_step`

5. **State Persistence**:
   - Checkpointer saves state with thread_id
   - Session file updated with conversation history and document context

### Memory Reducers

#### Message Reducer (`add_messages`)
- **Type**: `Annotated[List[BaseMessage], add_messages]`
- **Behavior**: Appends new messages to existing list
- **Purpose**: Maintains complete conversation history with proper message ordering

#### Actions Reducer (`operator.add`)
- **Type**: `Annotated[List[str], operator.add]`
- **Behavior**: Concatenates lists (e.g., `["a"] + ["b"] = ["a", "b"]`)
- **Purpose**: Tracks execution path: `["classify_intent", "qa_agent", "update_memory"]`

### Checkpointer Configuration

The checkpointer is configured with:
- **Thread ID**: Unique per session (`session_id`)
- **Configurable Values**: LLM instance and tools (passed via config)
- **State Retrieval**: `workflow.get_state(config)` loads previous state

### Memory Update Process

The `update_memory` function:
1. Retrieves conversation history from state
2. Uses LLM with structured output to generate summary
3. Extracts active document IDs from conversation
4. Updates state with new summary and document list

This ensures each turn has an up-to-date summary for context, preventing token bloat from long conversation histories.

## Structured Outputs

### Why Structured Outputs?

Structured outputs ensure:
- **Type Safety**: Responses match expected schema
- **Consistency**: Same fields always present
- **Validation**: Pydantic validates data types and constraints
- **Reliability**: No parsing errors from malformed JSON

### Implementation Pattern

All structured outputs follow this pattern:

```python
# 1. Define Pydantic schema
class AnswerResponse(BaseModel):
    question: str
    answer: str
    sources: List[str]
    confidence: float = Field(ge=0.0, le=1.0)
    timestamp: datetime

# 2. Configure LLM with structured output
structured_llm = llm.with_structured_output(AnswerResponse)

# 3. Invoke and get typed response
response: AnswerResponse = structured_llm.invoke(prompt)
# response.question, response.answer, etc. are now typed
```

### Schema Definitions

#### UserIntent
Used by `classify_intent` to route requests:
```python
class UserIntent(BaseModel):
    intent_type: Literal["qa", "summarization", "calculation", "unknown"]
    confidence: float  # 0.0 to 1.0
    reasoning: str
```

#### AnswerResponse
Used by `qa_agent` for question answering:
```python
class AnswerResponse(BaseModel):
    question: str
    answer: str
    sources: List[str]  # Document IDs
    confidence: float
    timestamp: datetime
```

#### SummarizationResponse
Used by `summarization_agent`:
```python
class SummarizationResponse(BaseModel):
    original_length: int
    summary: str
    key_points: List[str]
    document_ids: List[str]
    timestamp: datetime
```

#### CalculationResponse
Used by `calculation_agent`:
```python
class CalculationResponse(BaseModel):
    expression: str
    result: float
    explanation: str
    units: Optional[str]
    timestamp: datetime
```

#### UpdateMemoryResponse
Used by `update_memory`:
```python
class UpdateMemoryResponse(BaseModel):
    summary: str
    document_ids: List[str]
```

### ReAct Agent Structured Output

The specialized agents use `create_react_agent` with `response_format`:

```python
agent = create_react_agent(
    model=llm_with_tools,
    tools=tools,
    response_format=AnswerResponse,  # Enforces structured output
)
```

This ensures the final agent response (after tool calls) conforms to the schema.

### Error Handling

If structured output fails:
- Pydantic validation errors are raised
- LLM may retry with corrected format
- Errors propagate to `process_message` for user notification

## Example Conversations

### Example 1: Q&A Agent - Document Question

**User**: "What's the total amount in invoice INV-001?"

**Execution Flow**:
1. `classify_intent` → Intent: `qa` (confidence: 0.95)
2. `qa_agent` → Uses `document_reader` tool → Reads INV-001
3. `update_memory` → Summarizes conversation

**Assistant Response**:
```
🤖 Assistant: The total amount in invoice INV-001 is $22,000.00. This includes:
- Subtotal: $20,000
- Tax (10%): $2,000

INTENT: qa
SOURCES: INV-001
TOOLS USED: document_reader
CONVERSATION SUMMARY: User asked about total amount in invoice INV-001. Assistant provided the breakdown showing $22,000 total.
```

**State Updates**:
- `intent`: `UserIntent(intent_type="qa", confidence=0.95, ...)`
- `current_response`: `AnswerResponse(question="...", answer="...", sources=["INV-001"], ...)`
- `active_documents`: `["INV-001"]`
- `actions_taken`: `["classify_intent", "qa_agent", "update_memory"]`

---

### Example 2: Summarization Agent - Document Summary

**User**: "Summarize all contracts"

**Execution Flow**:
1. `classify_intent` → Intent: `summarization` (confidence: 0.92)
2. `summarization_agent` → Uses `document_search` (type="contract") → Finds CON-001
3. `summarization_agent` → Uses `document_reader` → Reads CON-001
4. `update_memory` → Updates summary with contract information

**Assistant Response**:
```
🤖 Assistant: Here's a summary of all contracts:

**Service Agreement (CON-001)**
- Parties: DocDacity Solutions Inc. and Healthcare Partners LLC
- Duration: 12 months
- Monthly Fee: $15,000
- Total Contract Value: $180,000
- Services: Document Processing Platform, 24/7 Support, Analytics Reports, Compliance Monitoring
- Termination: 60 days written notice

Key Points:
- High-value long-term contract
- Comprehensive service package
- Flexible termination terms

INTENT: summarization
SOURCES: CON-001
TOOLS USED: document_search, document_reader
CONVERSATION SUMMARY: User requested summary of all contracts. Assistant provided comprehensive summary of CON-001 including value, duration, and key terms.
```

**State Updates**:
- `intent`: `UserIntent(intent_type="summarization", ...)`
- `current_response`: `SummarizationResponse(summary="...", key_points=[...], document_ids=["CON-001"], ...)`
- `active_documents`: `["CON-001"]`
- `tools_used`: `["document_search", "document_reader"]`

---

### Example 3: Calculation Agent - Mathematical Operation

**User**: "What's 10% of the total in invoice INV-002?"

**Execution Flow**:
1. `classify_intent` → Intent: `calculation` (confidence: 0.98)
2. `calculation_agent` → Uses `document_reader` → Reads INV-002 (total: $69,300)
3. `calculation_agent` → Uses `calculator` → Calculates `69300 * 0.10`
4. `update_memory` → Updates with calculation result

**Assistant Response**:
```
🤖 Assistant: 10% of the total in invoice INV-002 ($69,300.00) is $6,930.00.

Calculation Details:
- Expression: 69300 * 0.10
- Result: 6930.0
- Explanation: Multiply the invoice total by 0.10 to get 10%

INTENT: calculation
SOURCES: INV-002
TOOLS USED: document_reader, calculator
CONVERSATION SUMMARY: User asked for 10% of invoice INV-002 total. Assistant retrieved invoice ($69,300) and calculated 10% = $6,930.
```

**State Updates**:
- `intent`: `UserIntent(intent_type="calculation", ...)`
- `current_response`: `CalculationResponse(expression="69300 * 0.10", result=6930.0, ...)`
- `active_documents`: `["INV-002"]`
- `tools_used`: `["document_reader", "calculator"]`

---

### Example 4: Multi-Turn Conversation with Memory

**Turn 1**:
**User**: "Show me invoices over $50,000"

**Execution**:
- Intent: `qa`
- Tools: `document_search` (amount > $50,000)
- Found: INV-002 ($69,300), INV-003 ($214,500)

**Response**: Lists both invoices with details

**State After Turn 1**:
- `active_documents`: `["INV-002", "INV-003"]`
- `conversation_summary`: "User searched for invoices over $50,000. Found INV-002 ($69,300) and INV-003 ($214,500)."

---

**Turn 2** (Conversation continues):
**User**: "What's the sum of those?"

**Execution**:
- Intent: `calculation`
- Context: Previous summary mentions INV-002 and INV-003
- Tools: `document_reader` (both invoices) → `calculator` (69300 + 214500)

**Response**: "The sum of invoices INV-002 and INV-003 is $283,800.00"

**State After Turn 2**:
- `active_documents`: `["INV-002", "INV-003"]` (maintained from previous turn)
- `conversation_summary`: "User first searched for invoices over $50,000, finding INV-002 and INV-003. Then calculated their sum: $283,800."
- `actions_taken`: `["classify_intent", "calculation_agent", "update_memory"]` (new turn)

**Key Memory Features Demonstrated**:
- Conversation summary provides context for "those invoices"
- Active documents persist across turns
- State loaded from checkpointer at start of Turn 2

---

### Example 5: Complex Calculation with Document Data

**User**: "Calculate the average of all invoice totals"

**Execution Flow**:
1. Intent: `calculation`
2. `document_search` → Finds all invoices (INV-001, INV-002, INV-003)
3. `document_reader` → Reads each invoice to get totals
4. `calculator` → Calculates `(22000 + 69300 + 214500) / 3`

**Response**:
```
🤖 Assistant: The average of all invoice totals is $101,933.33.

Calculation:
- Invoice INV-001: $22,000.00
- Invoice INV-002: $69,300.00
- Invoice INV-003: $214,500.00
- Sum: $305,800.00
- Average: $305,800.00 / 3 = $101,933.33

INTENT: calculation
SOURCES: INV-001, INV-002, INV-003
TOOLS USED: document_search, document_reader, calculator
```

---

### Example 6: Intent Classification Edge Case

**User**: "Tell me about invoice INV-001"

**Execution**:
- Intent classification considers: Is this Q&A or summarization?
- Decision: `qa` (user asking for information, not requesting summary format)
- Confidence: 0.88

**Note**: Intent classification uses conversation history. A follow-up like "Now summarize it" would route to `summarization_agent`.

---

## Installation

### Prerequisites
- Python 3.9+
- OpenAI API key

### Setup

1. **Clone and navigate to project**:
```bash
cd "Project 1 - Report Building Agent"
```

2. **Create virtual environment**:
```bash
python -m venv venv
# Windows
venv\Scripts\activate
# Linux/Mac
source venv/bin/activate
```

3. **Install dependencies**:
```bash
pip install -r requirements.txt
```

4. **Create `.env` file**:
```bash
OPENAI_API_KEY=your_api_key_here
```

## Usage

### Starting the Assistant

```bash
python main.py
```

### Available Commands

- `/help` - Show help message
- `/docs` - List all available documents
- `/quit` - Exit the assistant

### Example Session

```
============================================================
DocDacity Intelligent Document Assistant
============================================================

 INITIALIZING ASSISTANT...
Session started: abc123-def456-ghi789

AVAILABLE COMMANDS:
  /help     - Show this help message
  /docs     - List available documents
  /quit     - Exit the assistant

Enter Message: What's the total in invoice INV-001?

Processing...

🤖 Assistant: The total amount in invoice INV-001 is $22,000.00...

INTENT: qa
SOURCES: INV-001
TOOLS USED: document_reader
CONVERSATION SUMMARY: User asked about total in invoice INV-001...
```

## Project Structure

```
Project 1 - Report Building Agent/
├── src/
│   ├── __init__.py
│   ├── schemas.py          # Pydantic models for structured outputs
│   ├── retrieval.py        # Document retrieval and search
│   ├── tools.py            # LangChain tools (calculator, document ops)
│   ├── prompts.py          # Prompt templates for each agent
│   ├── agent.py            # LangGraph workflow definition
│   └── assistant.py        # Main DocumentAssistant class
├── sessions/               # Saved session files (JSON)
├── logs/                   # Tool usage logs
├── main.py                 # Entry point
├── requirements.txt        # Python dependencies
└── README.md              # This file
```

## Key Files Explained

### `src/agent.py`
- Defines `AgentState` TypedDict
- Implements workflow nodes (classify_intent, agents, update_memory)
- Creates and compiles LangGraph workflow with checkpointer

### `src/assistant.py`
- `DocumentAssistant` class manages sessions and workflow invocation
- Handles state initialization and session persistence
- Provides high-level API for processing messages

### `src/schemas.py`
- All Pydantic models for structured outputs
- `DocumentChunk` for retrieval results
- Response schemas for each agent type

### `src/tools.py`
- Tool definitions using `@tool` decorator
- `ToolLogger` for usage tracking
- Calculator with security validation

### `src/prompts.py`
- System prompts for each agent type
- Intent classification prompt
- Memory summary prompt

### `src/retrieval.py`
- `SimulatedRetriever` with sample documents
- Search methods (keyword, type, amount-based)
- Document statistics

## Technical Highlights

- **Type Safety**: Full type hints and Pydantic validation
- **State Management**: LangGraph reducers and checkpointer
- **Tool Integration**: LangChain tools with automatic logging
- **Error Handling**: Comprehensive try-catch blocks with user-friendly messages
- **Session Persistence**: Both in-memory (checkpointer) and file-based storage
- **Security**: Input validation for calculator tool

## Future Enhancements

Potential improvements:
- Vector database integration for semantic search
- Database-backed checkpointer for production
- Streaming responses for better UX
- Multi-modal document support (images, PDFs)
- User authentication and authorization
- Advanced analytics and reporting

---

**Built with**: LangChain, LangGraph, OpenAI GPT-4, Pydantic

