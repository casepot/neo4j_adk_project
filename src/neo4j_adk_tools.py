# src/neo4j_adk_tools.py
"""
ADK-ready FunctionTools for Neo4j that expose *only* the arguments the
LLM should care about:

    • SchemaTool          – takes **no** parameters
    • CypherReadTool      – (query:str, params:dict|None)
    • CypherWriteTool     – (query:str, params:dict|None)
    • GdsTool             – (query:str, params:dict|None)

Internal knobs like timeout_ms, db override, impersonation, follower
routing stay available but are *not* in the public signature.
"""

from typing import Optional, Dict, Any, Coroutine, Callable
from google.adk.tools import FunctionTool, BaseTool

# --- Pydantic Serialization Fix for Neo4j Temporal Types ---
# Register a custom serializer for neo4j.time.DateTime to prevent errors
# when ADK tries to serialize tool results containing these types.
try:
    from pydantic.json import ENCODERS_BY_TYPE
    from neo4j.time import DateTime
    ENCODERS_BY_TYPE[DateTime] = lambda dt: dt.iso_format()
    print("Registered custom Pydantic serializer for neo4j.time.DateTime")
except ImportError:
    print("Warning: Could not import pydantic or neo4j.time; DateTime serialization fix not applied.")
# --- End Pydantic Fix ---
# Import the original async wrapper functions
# Note: Ensure agent.py is structured correctly for these imports
try:
    from .wrappers import ( # Import from the new wrappers file
        wrapped_get_neo4j_schema,
        wrapped_read_neo4j_cypher,
        wrapped_write_neo4j_cypher,
        wrapped_run_gds_cypher,
    )
except ImportError:
    # Fallback for direct execution or different project structures
    from src.wrappers import ( # type: ignore # Use absolute path
        wrapped_get_neo4j_schema,
        wrapped_read_neo4j_cypher,
        wrapped_write_neo4j_cypher,
        wrapped_run_gds_cypher,
    )

# Type alias for the async wrapper functions
AsyncWrapperFunc = Callable[..., Coroutine[Any, Any, Dict[str, Any]]]
AsyncWrapperFuncNoArgs = Callable[[], Coroutine[Any, Any, Dict[str, Any]]]
AsyncWrapperFuncQueryParams = Callable[..., Coroutine[Any, Any, Dict[str, Any]]]


# ────────────────────────────────────────────────────────────────
#  Helper – wrap a coroutine in a FunctionTool while exposing only
#           (query, params) or () to the LLM.
# ────────────────────────────────────────────────────────────────
def _ft_no_args(async_fn: AsyncWrapperFuncNoArgs) -> FunctionTool:
    """Creates FunctionTool with no arguments exposed to LLM."""
    async def _runner(*, tool_context: Any) -> Dict[str, Any]:
        # Call the underlying wrapper, which might accept optional kwargs internally,
        # but none are passed from the LLM signature here.
        try:
            return await async_fn()
        except Exception as e:
            func_name = getattr(async_fn, '__name__', 'unknown function')
            err_msg = f"Unexpected error in {func_name}: {e}"
            # Consider logging this error
            return {"status": "error", "data": err_msg}

    # Derive the tool name from the wrapped function, removing 'wrapped_' prefix
    tool_name = getattr(async_fn, '__name__', '_unknown_adk_runner_no_args').replace('wrapped_', '')
    _runner.__name__ = f"{tool_name}_runner" # Make runner name distinct for clarity
    _runner.__doc__  = getattr(async_fn, '__doc__', 'ADK Tool Runner (No Args)')
    # Explicitly set the FunctionTool name for ADK stability
    return FunctionTool(func=_runner)


def _ft_query_params(async_fn: AsyncWrapperFuncQueryParams) -> FunctionTool:
    """Creates FunctionTool exposing only query and params to LLM."""
    async def _runner(*, query: str, params: Optional[Dict[str, Any]] = None,
                      tool_context: Any) -> Dict[str, Any]:
        # Call the underlying wrapper, passing only query and params.
        # Internal optional args like timeout_ms, db, impersonate in the
        # original wrapper function (e.g., wrapped_read_neo4j_cypher)
        # will take their default values unless overridden internally later (e.g., in rbac).
        try:
            # We explicitly pass only query and params here.
            return await async_fn(query=query, params=params)
        except TypeError as e:
            func_name = getattr(async_fn, '__name__', 'unknown function')
            err_msg = f"TypeError calling {func_name}: {e}. Received query='{query}', params={params}"
            return {"status": "error", "data": err_msg}
        except Exception as e:
            func_name = getattr(async_fn, '__name__', 'unknown function')
            err_msg = f"Unexpected error in {func_name}: {e}. Received query='{query}', params={params}"
            return {"status": "error", "data": err_msg}

    # Derive the tool name from the wrapped function, removing 'wrapped_' prefix
    tool_name = getattr(async_fn, '__name__', '_unknown_adk_runner_query_params').replace('wrapped_', '')
    # Explicitly set the runner's __name__ which ADK uses for the tool name if 'name' kwarg is absent
    _runner.__name__ = tool_name
    _runner.__doc__  = getattr(async_fn, '__doc__', 'ADK Tool Runner (Query/Params)')
    return FunctionTool(func=_runner) # Remove 'name' kwarg

# ────────────────────────────────────────────────────────────────
#  Public ADK tools
# ────────────────────────────────────────────────────────────────
SchemaTool: FunctionTool      = _ft_no_args(wrapped_get_neo4j_schema)
CypherReadTool: FunctionTool  = _ft_query_params(wrapped_read_neo4j_cypher)
CypherWriteTool: FunctionTool = _ft_query_params(wrapped_write_neo4j_cypher)
GdsTool: FunctionTool         = _ft_query_params(wrapped_run_gds_cypher)

# ────────────────────────────────────────────────────────────────
#  Alias tools with legacy names (for compatibility / agent hallucination)
# ────────────────────────────────────────────────────────────────
# Helper function to create alias tools correctly
def _make_alias(original_async_fn: Callable, public_alias: str, expects_query: bool = True, is_gds: bool = False) -> FunctionTool:
    """
    Creates an alias FunctionTool with the specified public name.
    Crucially, it attaches the original async function to the runner for RBAC wrapping.
    """
    if is_gds:
        # Special signature for GDS tool to accept either query/params or procedure/parameters
        async def _runner(*,
                          query: Optional[str] = None,
                          params: Optional[Dict[str, Any]] = None,
                          procedure: Optional[str] = None,
                          parameters: Optional[Dict[str, Any]] = None,
                          tool_context: Any) -> Dict[str, Any]:
            # Call the underlying wrapper, passing all potential arguments
            try:
                # The wrapped_run_gds_cypher function handles the logic
                # of using query/params OR procedure/parameters.
                return await original_async_fn(
                    query=query,
                    params=params,
                    procedure=procedure,
                    parameters=parameters
                )
            except Exception as e:
                err_msg = f"Error in GDS alias tool '{public_alias}' calling '{original_async_fn.__name__}': {e}"
                # Log all potential args for debugging
                args_repr = f"query='{query}', params={params}, procedure='{procedure}', parameters={parameters}"
                err_msg += f" | Args: {{{args_repr}}}"
                return {"status": "error", "data": err_msg}
    elif expects_query:
        # Standard signature for tools expecting query/params
        async def _runner(*, query: str, params: Optional[Dict[str, Any]] = None,
                          tool_context: Any) -> Dict[str, Any]:
            try:
                return await original_async_fn(query=query, params=params)
            except Exception as e:
                err_msg = f"Error in alias tool '{public_alias}' calling '{original_async_fn.__name__}': {e}"
                err_msg += f" | Args: {{'query': '{query}', 'params': {params}}}"
                return {"status": "error", "data": err_msg}
    else:   # get_schema (expects no query args)
        async def _runner(*, tool_context: Any) -> Dict[str, Any]:
            try:
                return await original_async_fn()
            except Exception as e:
                err_msg = f"Error in alias tool '{public_alias}' calling '{original_async_fn.__name__}': {e}"
                return {"status": "error", "data": err_msg}

    # Set the public name for the runner function
    _runner.__name__ = public_alias
    # Copy the docstring from the original function for the LLM
    _runner.__doc__ = getattr(original_async_fn, '__doc__', f"Alias for {original_async_fn.__name__}")

    # Attach the original function to the runner for RBAC wrapper to find
    _runner._original_func = original_async_fn # type: ignore

    # Create the FunctionTool using only the 'func' argument
    return FunctionTool(func=_runner)

# --- Alias Tool Definitions using the helper ---
GetSchemaAlias: FunctionTool = _make_alias(
    original_async_fn=wrapped_get_neo4j_schema,
    public_alias="get_schema",
    expects_query=False # get_schema takes no query/params
)
ReadCypherAlias: FunctionTool = _make_alias(
    original_async_fn=wrapped_read_neo4j_cypher,
    public_alias="read_cypher",
    expects_query=True
)
WriteCypherAlias: FunctionTool = _make_alias(
    original_async_fn=wrapped_write_neo4j_cypher,
    public_alias="write_cypher",
    expects_query=True
)
RunGdsAlias: FunctionTool = _make_alias(
    original_async_fn=wrapped_run_gds_cypher,
    public_alias="run_gds_procedure",
    expects_query=False, # Set to False as it doesn't *require* query
    is_gds=True # Use the special GDS signature
)

# Dictionary mapping capability names (expected by tests/rbac) to the ADK Tool objects
# IMPORTANT: Map the legacy keys to the *new alias tools*
ALL_ADK_TOOLS: Dict[str, BaseTool] = {
    # Only expose the public alias tools under their canonical names.
    # RBAC/tests should refer to these names.
    "get_schema"        : GetSchemaAlias,
    "read_cypher"       : ReadCypherAlias,
    "write_cypher"      : WriteCypherAlias,
    "run_gds_procedure" : RunGdsAlias,

    # The non-alias tools (SchemaTool, CypherReadTool, etc.) are internal
    # implementation details and should not be directly exposed or used.

    # Add future tools here, ensuring they use the alias pattern if needed.
}

# Example for LongRunningFunctionTool if needed (adjust helper signature)
# try:
#     from .long_running.pagerank import pagerank_generator, PageRankTool
#     ALL_ADK_TOOLS["pagerank"] = PageRankTool # Assuming PageRankTool is already correctly defined
# except ImportError:
#     pass # Optional tool not present