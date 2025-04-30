# ADK Integration Lessons from the Neo4j Project

This document captures key learnings about Google ADK usage discovered during the development and debugging of the Neo4j integration kit. These insights may be helpful for other ADK-based projects.

## Async Execution and Event Handling

### 1. Runner Execution Methods

The ADK `Runner` provides both synchronous and asynchronous execution APIs:

- `runner.run()` - Returns a generator that must be consumed in a synchronous context
- `runner.run_async()` - Returns an async generator for use with `async for` in an asynchronous context

```python
# INCORRECT - Using synchronous run() in an async context
async def run_query(runner, query, user_id, session_id):
    async for event in runner.run(user_id=user_id, session_id=session_id, new_message=content):
        # This raises: TypeError: 'async for' requires an object with __aiter__ method, got generator
        pass

# CORRECT - Using run_async() in an async context
async def run_query(runner, query, user_id, session_id):
    async for event in runner.run_async(user_id=user_id, session_id=session_id, new_message=content):
        # This works correctly
        pass
```

### 2. Event Processing

ADK events should be processed using the documented event methods:

```python
async for event in runner.run_async(user_id=user_id, session_id=session_id, new_message=content):
    # Get tool calls the LLM is making
    tool_calls = event.get_function_calls()
    
    # Get responses from tools that were executed
    tool_responses = event.get_function_responses()
    
    # Check if this is the final response in this turn
    if event.is_final_response():
        final_answer = event.content.parts[0].text
        break
```

Previous versions of the ADK may have used different methods like `is_llm_response()` which are no longer available.

## Session Management

### 1. Explicit Session Creation Required

The ADK `Runner` requires sessions to be explicitly created before they can be used:

```python
# Create a session service
session_service = InMemorySessionService()

# Must create a session before the first run
session_service.create_session(
    app_name="my_app",
    user_id="user_123",
    session_id="session_456"
)

# Now you can run queries with this session ID
runner = Runner(agent=my_agent, app_name="my_app", session_service=session_service)
await run_query(runner, "My query", "user_123", "session_456")
```

Without the explicit `create_session()` call, you'll get a `ValueError: Session not found` error.

## Tool Design for ADK

### 1. FunctionTool Structure

When creating ADK tools that wrap existing functions:

```python
def _ft_query_params(async_fn: AsyncWrapperFuncQueryParams) -> FunctionTool:
    """Creates FunctionTool exposing only query and params to LLM."""
    async def _runner(*, query: str, params: Optional[Dict[str, Any]] = None,
                      tool_context: Any) -> Dict[str, Any]:
        try:
            # We explicitly pass only query and params here.
            return await async_fn(query=query, params=params)
        except Exception as e:
            func_name = getattr(async_fn, '__name__', 'unknown function')
            err_msg = f"Unexpected error in {func_name}: {e}"
            return {"status": "error", "data": err_msg}

    # Copy the function's name and doc for LLM visibility
    _runner.__name__ = getattr(async_fn, '__name__', '_unknown_adk_runner')
    _runner.__doc__  = getattr(async_fn, '__doc__', 'ADK Tool Runner')
    return FunctionTool(func=_runner)
```

Key points:
- Create a wrapper function that handles errors specifically for ADK usage
- Pass the `tool_context` parameter (ADK requires this)
- Copy over the `__name__` and `__doc__` attributes so the LLM sees proper documentation
- Return standardized response objects that can be easily parsed

### 2. Error Handling in Tools

ADK tools should always catch and handle exceptions to return properly formatted error responses:

```python
try:
    # Tool logic here
    return {"status": "success", "data": result}
except Exception as e:
    return {"status": "error", "data": str(e)}
```

This prevents the ADK from crashing when a tool fails and provides actionable error information to the LLM.

## Package Structure Considerations

### 1. Circular Import Prevention

ADK projects often involve multiple components that need to reference each other. Carefully structure your code to avoid circular imports:

```
src/
├── __init__.py            # Make src a proper package
├── agent.py               # Driver initialization 
├── wrappers.py            # Core implementation functions
├── specialized_tools.py   # Tools that use wrappers
└── tool_registry.py       # Registry that imports tools
```

- Keep initialization logic separate from implementation
- Use clear dependency direction (e.g., registry imports tools, not vice versa)
- Consider using dependency injection where appropriate

### 2. Package Management

Always use proper package structure with `__init__.py` files to enable relative imports:

```python
# Without __init__.py files, this fails:
from .wrappers import my_function

# With __init__.py files, this works:
from .wrappers import my_function
```

## Content Type Handling

The `google.genai` library and ADK expect specific content formats:

```python
from google.genai import types as genai_types

# Create properly structured content object
content = genai_types.Content(
    role="user",
    parts=[genai_types.Part(text=query)]
)

# Pass to runner
runner.run_async(user_id=user_id, session_id=session_id, new_message=content)
```

It's easy to get these structures wrong when migrating between versions.

## Async/Await Patterns

ADK heavily uses async patterns, which requires careful management of:

1. **Function Declarations**: `async def` for all handler functions
2. **Execution**: `await` all async calls properly
3. **Context**: Use `async with` for async context managers like Neo4j sessions
4. **Event Loop Management**: Run the top-level async function with `asyncio.run(main())`

---

These learnings stem from direct experience integrating Neo4j with the Google ADK. We hope they help you avoid similar pitfalls in your own ADK project development.