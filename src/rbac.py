# src/rbac.py
"""
Role-Based Access Control (RBAC) for Neo4j ADK Tools.

Defines:
- A central registry of available tool capabilities.
- Named roles mapped to specific sets of capabilities.
- A factory function `build_agent_tools` to generate the appropriate
  list of ADK tools for a given role, optionally configuring
  Neo4j impersonation and read routing.
"""

from typing import Dict, List, Literal, Optional, Callable, Coroutine, Any
from google.adk.tools import BaseTool, FunctionTool # BaseTool covers FunctionTool and LongRunningFunctionTool

# Import the ADK tool objects created in neo4j_adk_tools.py
# Use a relative import assuming rbac.py is in the same directory level as neo4j_adk_tools.py
try:
    from .neo4j_adk_tools import ALL_ADK_TOOLS   # NEW: Import the map directly
    # Also need the original read wrapper for the routing check
    from .wrappers import wrapped_read_neo4j_cypher # Import from wrappers now
except ImportError:
    # Fallback for different execution contexts
    from src.neo4j_adk_tools import ALL_ADK_TOOLS # type: ignore # Use absolute path
    from src.wrappers import wrapped_read_neo4j_cypher # type: ignore # Use absolute path


# ----------------------------------------------------------------------------------
# 1 · Capability registry (Uses the ADK Tool objects directly)
# ----------------------------------------------------------------------------------
# The keys are the capability names used in ROLE_CAPABILITIES.
# The values are the actual ADK BaseTool objects.
CAPABILITIES = ALL_ADK_TOOLS               # NEW: Assign the imported map


# ----------------------------------------------------------------------------------
# 2 · Human-friendly roles and their associated capabilities
# ----------------------------------------------------------------------------------
Role = Literal["explorer", "auditor", "builder", "admin"]

# Maps role names to a list of capability *names* they should have access to.
# Maps role names to a list of capability *names* (matching keys in ALL_ADK_TOOLS)
ROLE_CAPABILITIES: Dict[Role, List[str]] = {
    # read-only, no GDS
    "explorer": ["get_schema", "read_cypher"],

    # read + analytics but cannot mutate
    "auditor" : ["get_schema", "read_cypher", "run_gds_procedure"],

    # full CRUD + analytics
    "builder" : ["get_schema", "read_cypher", "write_cypher", "run_gds_procedure"],

    # identical to builder today, reserved for future super-powers
    "admin"   : ["get_schema", "read_cypher", "write_cypher", "run_gds_procedure"],

    # Example of adding a new role:
    # "writer_only": ["write"],
}


# ----------------------------------------------------------------------------------
# 3 · Factory to build the tool list for any role
# ----------------------------------------------------------------------------------
def build_agent_tools(
    role: Role,
    *,
    impersonated_user: Optional[str] = None,
    read_routing: bool = False,
) -> List[BaseTool]:
    """
    Builds a list of ADK tools suitable for the specified agent role.

    Optionally configures Neo4j impersonation and read routing for the
    generated tools by wrapping them.

    Parameters
    ----------
    role : Role
        The name of the role (e.g., "explorer", "builder"). Must be a key
        in ROLE_CAPABILITIES.
    impersonated_user : Optional[str], optional
        If provided, wraps tools to inject this username for Neo4j
        impersonation (Enterprise feature). Defaults to None.
    read_routing : bool, optional
        If True, wraps the 'read' tool (if present for the role) to inject
        `route_read=True`, potentially directing queries to follower replicas
        in a Neo4j cluster. Defaults to False.

    Returns
    -------
    List[BaseTool]
        A list of ADK BaseTool instances (FunctionTool or
        LongRunningFunctionTool) configured for the given role and options.

    Raises
    ------
    ValueError
        If the provided `role` is not found in ROLE_CAPABILITIES.
    """
    if role not in ROLE_CAPABILITIES:
        raise ValueError(f"Unknown role: '{role}'. Must be one of {list(ROLE_CAPABILITIES.keys())}")

    allowed_capability_names = ROLE_CAPABILITIES[role]
    agent_tools: List[BaseTool] = []

    for cap_name in allowed_capability_names:
        if cap_name not in CAPABILITIES:
            # This should ideally not happen if ROLE_CAPABILITIES is consistent
            # with CAPABILITIES, but good to have a check.
            print(f"Warning: Capability '{cap_name}' defined for role '{role}' but not found in CAPABILITIES registry. Skipping.")
            continue

        tool = CAPABILITIES[cap_name]

        # Check if we need to wrap this tool for impersonation or routing
        # Fix typo: "read" -> "read_cypher"
        needs_wrapper = impersonated_user or (read_routing and cap_name == "read_cypher")

        if needs_wrapper:
            # We need to wrap the original tool's execution logic.
            # The tool itself is likely a FunctionTool whose `func` points to `_runner`.
            # We need to wrap the `_runner` or, more directly, create a new
            # FunctionTool that calls the *original* wrapper with modified kwargs.

            # Get the original async wrapper function (e.g., wrapped_read_neo4j_cypher)
            # This relies on the structure established in neo4j_adk_tools.py
            # where _make_ft preserves the original function's identity somewhat.
            # A more robust way might be needed if _make_ft changes significantly.

            # Retrieve the original async function attached by _make_alias
            original_func = None
            if isinstance(tool, FunctionTool) and hasattr(tool.func, '_original_func'):
                original_func = getattr(tool.func, '_original_func', None)

            if not original_func or not callable(original_func):
                 # Raise an error if we cannot find the function to wrap.
                 # This indicates a problem with the tool registration in neo4j_adk_tools.py
                 raise ValueError(f"Could not find original callable function for tool '{cap_name}' to apply RBAC wrapper. Check _make_alias in neo4j_adk_tools.py.")


            # Create a new async function that calls the original wrapper
            # with the added impersonation/routing kwargs.
            # Fix closure capture bug: Add cap_name=cap_name as default arg
            async def _bound_runner(*args, original_async_func=original_func, cap_name=cap_name, **kwargs):
                # ADK passes tool inputs directly as keyword arguments to the runner.
                # We need to extract them from kwargs, excluding the 'tool_context' ADK adds.
                inner_args = {k: v for k, v in kwargs.items() if k != 'tool_context'}


                if impersonated_user:
                    inner_args.setdefault("db_impersonate", impersonated_user) # Use the correct kwarg name from wrappers.py

                # Check if this specific tool instance corresponds to the read tool
                # Fix typo: "read" -> "read_cypher"
                if read_routing and cap_name == "read_cypher":
                    inner_args.setdefault("route_read", True) # Use the correct kwarg name from wrappers.py

                # Call the *original* async wrapper function (e.g., wrapped_read_...)
                return await original_async_func(**inner_args)

            # Copy metadata for the new runner
            _bound_runner.__name__ = f"{original_func.__name__}_bound"
            _bound_runner.__doc__ = original_func.__doc__ # Keep original docs for LLM

            # Create a *new* FunctionTool with this bound runner
            bound_tool = FunctionTool(func=_bound_runner)
            agent_tools.append(bound_tool)

        else:
            # No wrapping needed, just add the original tool
            agent_tools.append(tool)

    return agent_tools