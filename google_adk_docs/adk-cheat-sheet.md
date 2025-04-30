# Google ADK Python: Comprehensive Reference

## 1. Core Concepts

Google ADK (Agent Development Kit) is a framework for building, composing, and orchestrating LLM-powered agents. Key concepts include:

- **Agents**: Autonomous units that can reason, make decisions, and take actions
- **Tools**: Functions or capabilities that agents can use
- **Sessions**: Conversation threads maintaining state and history
- **Events**: The communication protocol between system components
- **Runners**: Orchestrators that manage agent execution and maintain state

## 2. Agent Types

### LlmAgent

The foundation agent type powered by a language model:

```python
from google.adk.agents import LlmAgent

agent = LlmAgent(
    name="my_agent",                          # Required: Unique identifier
    model="gemini-2.0-flash",                 # LLM to use
    instruction="You are a helpful assistant", # System prompt
    description="Handles general questions",   # For agent selection
    tools=[],                                  # Tools this agent can use
    output_key=None,                           # State key to store response
    include_contents="full",                   # History inclusion (full, none, last)
    before_agent_callback=None,                # Hooks for agent lifecycle
    after_agent_callback=None,
    before_model_callback=None,
    after_model_callback=None,
    before_tool_callback=None,
    after_tool_callback=None
)
```

### SequentialAgent

Runs sub-agents in order, passing the same session state through the chain:

```python
from google.adk.agents import SequentialAgent

pipeline = SequentialAgent(
    name="process_pipeline",
    sub_agents=[agent1, agent2, agent3],  # Executed in order
    description="Process input through multiple steps"
)
```

### ParallelAgent

Executes sub-agents concurrently, potentially improving performance:

```python
from google.adk.agents import ParallelAgent

parallel_agent = ParallelAgent(
    name="concurrent_tasks",
    sub_agents=[
        search_agent,   # Each agent stores results in different state keys
        calculate_agent,
        lookup_agent
    ],
    description="Run multiple independent tasks concurrently"
)

# Important: Each agent should write to unique state keys to avoid
# race conditions, e.g.:
# search_agent.output_key = "search_results"
# calculate_agent.output_key = "calculation_result"
```

### LoopAgent

Executes sub-agents repeatedly until a termination condition is met:

```python
from google.adk.agents import LoopAgent
from google.adk.events import Event, EventActions

class CheckerAgent(BaseAgent):
    """Custom agent that checks if a condition is met and signals completion."""
    async def _run_async_impl(self, ctx):
        condition_met = ctx.session.state.get("quality_score", 0) >= 8.0
        yield Event(
            author=self.name,
            actions=EventActions(escalate=condition_met),  # Signal to exit loop
            content=None
        )

iterative_agent = LoopAgent(
    name="iterative_improvement",
    sub_agents=[
        improvement_agent,  # Improves something and stores in state
        scoring_agent,      # Rates improvement and stores score
        CheckerAgent(name="termination_checker")  # Decides when to stop
    ],
    max_iterations=5,  # Optional hard limit on iterations
    description="Iteratively improves until quality threshold met"
)
```

## 3. Agent Hierarchy and Communication

### Parent-Child Relationships

Agents form a tree structure through the `sub_agents` property:

```python
# parent_agent     (root)
# ├── child_agent1
# │   └── grandchild_agent
# └── child_agent2
```

Properties:
- Each agent has at most one parent (`agent.parent_agent`)
- `sub_agents` creates parent-child relationships automatically
- Child agents inherit certain properties from parents (state, context)

### Communication Mechanisms

1. **Shared State**: Primary method - write to/read from `session.state`

```python
# Agent A: Write to state
context.session.state["shared_data"] = "This will be visible to Agent B"

# Agent B: Read from state
data = context.session.state.get("shared_data")
```

2. **Agent Transfer**: LLM agent delegates to a sub-agent

```python
# In LlmAgent, the LLM can output:
# "I need to transfer this to the specialist"
# This generates: FunctionCall(name='transfer_to_agent', args={'agent_name': 'specialist'})

# Handled by the framework, transfers control to the named agent
```

3. **Agent as Tool**: Explicitly call another agent as a tool

```python
specialist_tool = AgentTool(agent=specialist_agent)
main_agent = LlmAgent(
    name="main_agent",
    tools=[specialist_tool]  # Can call specialist directly
)

# LLM generates: FunctionCall(name='specialist', args={'query': 'Help with X'})
# Specialist processes query, returns result to main_agent
```

4. **Structured Data in State**: For complex data sharing

```python
# Store structured data in state
context.session.state["analysis"] = {
    "sentiment": "positive",
    "key_entities": ["product", "customer"],
    "priority": "high"
}

# Next agent can access the structure
analysis = context.session.state.get("analysis", {})
if analysis.get("priority") == "high":
    # Prioritized handling
```

## 4. State and Session Management

### State Scopes

ADK offers different state scopes with prefixes:

```python
# Session-scoped (default)
context.session.state["key"] = "value"  # Available in current session only

# User-scoped 
context.session.state["user:preference"] = "dark_mode"  # Available across all sessions for this user

# App-scoped
context.session.state["app:version"] = "1.0.2"  # Global across all sessions

# Temporary (for current invocation only)
context.session.state["temp:calculation"] = 42  # Not persisted in history
```

### State Delta Tracking

State changes are tracked in `event.actions.state_delta`:

```python
# When an agent or tool modifies state
context.session.state["key"] = "value"

# The change is recorded in the corresponding event
# event.actions.state_delta = {"key": "value"}

# The Runner uses this to update the session state
```

### Session Services

Different implementations for persistence:

```python
# In-memory (no persistence)
from google.adk.sessions import InMemorySessionService
session_service = InMemorySessionService()

# Database-backed (SQL persistence)
from google.adk.sessions import DatabaseSessionService
session_service = DatabaseSessionService(db_url="sqlite:///./sessions.db")

# Session Lifecycle
session = session_service.create_session(app_name="my_app", user_id="user123")
session = session_service.get_session(app_name="my_app", user_id="user123", session_id="abc123")
session_service.delete_session(app_name="my_app", user_id="user123", session_id="abc123")
```

## 5. Events and Callbacks System

### Event Structure

Events are the primary communication protocol:

```python
from google.adk.events import Event, EventActions

event = Event(
    author="agent_name",           # Who created this event
    content=types.Content(...),    # Message content (text, function calls)
    actions=EventActions(          # Side effects
        state_delta={"key": "value"},  # State changes
        artifact_delta={"file.txt": 1},  # Artifact changes
        escalate=False,            # Signal to exit loops
        transfer_to_agent=None,    # Agent to transfer to
        skip_summarization=False   # Skip tool result summarization
    ),
    invocation_id="abc123",        # Unique ID for this invocation
    id="event_123",                # Unique ID for this event
    branch="main"                  # Execution branch
)
```

### Callback Hooks

Callbacks allow intercepting and modifying agent behavior:

```python
def before_agent_callback(callback_context):
    """Called before agent executes."""
    # Inspect state, potentially short-circuit agent
    if callback_context.state.get("skip_agent", False):
        return types.Content(parts=[types.Part(text="Agent skipped.")])
    return None  # Proceed with normal execution

def after_agent_callback(callback_context):
    """Called after agent completes."""
    # Modify output or perform cleanup
    return None  # Use original agent output

def before_model_callback(callback_context, llm_request):
    """Called before LLM request is sent."""
    # Modify prompt, params, or short-circuit LLM call
    return None  # Proceed with (possibly modified) llm_request

def after_model_callback(callback_context, llm_response):
    """Called after LLM response is received."""
    # Inspect or modify LLM response
    return None  # Use original (or modified) llm_response

def before_tool_callback(tool, args, tool_context):
    """Called before tool execution."""
    # Validate args, potentially skip tool execution
    return None  # Execute tool with (possibly modified) args
    # Or: return {"result": "Cached result"}  # Skip tool execution

def after_tool_callback(tool, args, tool_context, tool_response):
    """Called after tool execution."""
    # Process or modify tool result
    return None  # Use original (or modified) tool_response
```

Attach to agents:

```python
agent = LlmAgent(
    name="agent_with_callbacks",
    before_agent_callback=before_agent_callback,
    after_agent_callback=after_agent_callback,
    before_model_callback=before_model_callback,
    after_model_callback=after_model_callback,
    before_tool_callback=before_tool_callback,
    after_tool_callback=after_tool_callback
)
```

## 6. Running Agents

### Runner Initialization

```python
from google.adk.runners import Runner

runner = Runner(
    agent=root_agent,             # Top-level agent
    session_service=session_service,
    app_name="my_app"
)
```

### Synchronous Execution (Simpler)

```python
events = runner.run(
    user_id="user123",
    session_id=session.id,
    new_message=types.Content(role='user', parts=[types.Part(text="Hello")])
)

# Process events after completion
for event in events:
    if event.is_final_response():
        print(f"Final response: {event.content.parts[0].text}")
```

### Asynchronous Execution (Recommended)

```python
async for event in runner.run_async(
    user_id="user123",
    session_id=session.id,
    new_message=user_message
):
    # Process events as they occur
    if event.is_final_response():
        final_text = event.content.parts[0].text
    elif event.partial:
        # Handle streaming chunks
        partial_text = event.content.parts[0].text
    elif event.get_function_calls():
        # Tool/Function call
        function_name = event.get_function_calls()[0].name
    elif event.get_function_responses():
        # Tool/Function result
        function_result = event.get_function_responses()[0].response
```

## 7. Best Practices and Considerations

### Agent Design

- **Single Responsibility**: Each agent should have one clear purpose
- **Clear Instructions**: Be specific about agent roles and when to use tools
- **Thoughtful Composition**: Choose appropriate agent types for the task
  - SequentialAgent: For ordered, dependent steps
  - ParallelAgent: For independent tasks (careful with state)
  - LoopAgent: For iterative refinement with explicit termination
- **Testability**: Design agents to be individually testable

### State Management

- **State Key Conventions**: Use consistent naming patterns for state keys
- **Avoid Race Conditions**: With ParallelAgent, use separate state keys per sub-agent
- **Explicit State Dependencies**: Document what state keys each agent reads/writes
- **State Scoping**: Use appropriate prefixes (no prefix, user:, app:, temp:)

### Tool Design

- **Function Signatures**: Clear input/output types with good docstrings
- **Error Handling**: Robust error handling within tools
- **Idempotency**: Prefer idempotent tools when possible
- **Tool Selection**: Provide diverse tools but not too many (cognitive load)

### Performance

- **Parallel Where Possible**: Use ParallelAgent for independent operations
- **Minimize LLM Calls**: Merge related operations when reasonable
- **Careful State Size**: Keep state reasonably sized, especially with many turns

### Security and Safety

- **Input Validation**: Validate inputs in tools and callbacks
- **Permissions**: Use callbacks to enforce access controls
- **Sensitive Data**: Don't store sensitive data in session state (not encrypted)

### Debugging

- **Event Logging**: Log events for debugging complex agent interactions
- **State Snapshots**: Periodically save state snapshots for analysis
- **Step-by-Step Tracing**: Use verbose logging in development

### Production Readiness

- **Persistent Sessions**: Use DatabaseSessionService for production
- **Error Recovery**: Implement strategies for handling LLM errors
- **Monitoring**: Track key metrics like turns per session, tool usage frequency
- **Versioning**: Version your agent definitions for backwards compatibility

### Common Pitfalls

- **Unclear Responsibilities**: Overlapping agent roles cause confusion
- **Overcomplex Tools**: Too many or complex tools overwhelm LLMs
- **Stale State**: Old state values causing inconsistent behavior
- **Missing Termination Conditions**: LoopAgent without clear exit criteria
- **Memory Leaks**: Unbounded session growth over many turns