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

    _runner.__name__ = getattr(async_fn, '__name__', '_unknown_adk_runner_no_args')
    _runner.__doc__  = getattr(async_fn, '__doc__', 'ADK Tool Runner (No Args)')
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

    _runner.__name__ = getattr(async_fn, '__name__', '_unknown_adk_runner_query_params')
    _runner.__doc__  = getattr(async_fn, '__doc__', 'ADK Tool Runner (Query/Params)')
    return FunctionTool(func=_runner)

# ────────────────────────────────────────────────────────────────
#  Public ADK tools
# ────────────────────────────────────────────────────────────────
SchemaTool: FunctionTool      = _ft_no_args(wrapped_get_neo4j_schema)
CypherReadTool: FunctionTool  = _ft_query_params(wrapped_read_neo4j_cypher)
CypherWriteTool: FunctionTool = _ft_query_params(wrapped_write_neo4j_cypher)
GdsTool: FunctionTool         = _ft_query_params(wrapped_run_gds_cypher)

# Dictionary mapping capability names to the ADK Tool objects
ALL_ADK_TOOLS: Dict[str, BaseTool] = {
    "schema": SchemaTool,
    "read"  : CypherReadTool,
    "write" : CypherWriteTool,
    "gds"   : GdsTool,
    # Add future tools here, following the appropriate pattern
    # e.g., if PageRankTool takes specific args like graph_name:
    # PageRankTool = _ft_pagerank_args(pagerank_generator)
}

# Example for LongRunningFunctionTool if needed (adjust helper signature)
# try:
#     from .long_running.pagerank import pagerank_generator, PageRankTool
#     ALL_ADK_TOOLS["pagerank"] = PageRankTool # Assuming PageRankTool is already correctly defined
# except ImportError:
#     pass # Optional tool not present