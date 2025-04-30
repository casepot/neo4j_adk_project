# src/long_running/pagerank.py
"""
Demonstrates a LongRunningFunctionTool for a potentially long-running
GDS task like PageRank, streaming progress updates back to the agent.
"""

import asyncio
import time
import itertools
from typing import Dict, Any, AsyncGenerator, Optional

from google.adk.tools import LongRunningFunctionTool

# Import the GDS wrapper - adjust path if necessary
try:
    from ..agent import wrapped_run_gds_cypher
except ImportError:
    # Fallback if run directly or structure differs
    from agent import wrapped_run_gds_cypher # type: ignore


async def pagerank_generator(
    graph_name: str,
    write_property: str = "pagerank", # Changed from write_prop for clarity
    max_iterations: int = 100,
    damping_factor: float = 0.85,
    timeout_ms: int = 300000, # 5 minutes default for potentially long job
    db: Optional[str] = None,
    db_impersonate: Optional[str] = None,
    **kwargs: Any # Catch extra ADK args
) -> AsyncGenerator[Dict[str, Any], None]:
    """
    Runs Neo4j GDS PageRank, yielding incremental progress updates.

    This simulates a long-running process by yielding status updates
    before finally calling the actual GDS procedure via the wrapper.
    In a production scenario, the progress updates might come from
    polling `gds.job.list()` or a similar mechanism.

    Parameters:
        graph_name (str): The name of the projected graph in GDS.
        write_property (str): The node property name to store PageRank scores.
        max_iterations (int): Maximum PageRank iterations.
        damping_factor (float): PageRank damping factor.
        timeout_ms (int): Timeout for the final GDS query execution.
        db (Optional[str]): Target database name.
        db_impersonate (Optional[str]): Neo4j user to impersonate.
        **kwargs: Catches unused ADK context args.

    Yields:
        Dict[str, Any]: Progress dictionaries with "status" and "message" or "progress".

    Returns:
        Dict[str, Any]: Final result dictionary with "status" and "gds_result".
    """
    yield {"status": "pending", "message": f"Scheduling GDS PageRank job for graph '{graph_name}'..."}
    await asyncio.sleep(1) # Simulate scheduling delay

    # Construct the GDS Cypher query
    # Use parameters for safety and flexibility
    gds_query = f"""
    CALL gds.pageRank.write($graph_name, {{
        maxIterations: $max_iterations,
        dampingFactor: $damping_factor,
        writeProperty: $write_property
    }})
    YIELD nodePropertiesWritten, ranIterations, computeMillis, didConverge
    """
    gds_params = {
        "graph_name": graph_name,
        "max_iterations": max_iterations,
        "damping_factor": damping_factor,
        "write_property": write_property,
    }

    # --- Simulation of Progress Updates ---
    # In a real scenario, you might initiate the job asynchronously
    # (e.g., gds.pageRank.mutate.estimate + gds.pageRank.stream)
    # and poll gds.job.list() or use a callback mechanism.
    # Here, we just simulate time passing.
    total_simulated_time = 15 # seconds
    update_interval = 3 # seconds
    num_updates = total_simulated_time // update_interval

    for i in range(num_updates):
        await asyncio.sleep(update_interval)
        progress_pct = int(((i + 1) / num_updates) * 100)
        yield {"status": "running", "progress": f"{progress_pct}%", "message": f"Iteration {i+1}/{num_updates}..."}
        if progress_pct >= 100:
            break
    # --- End Simulation ---

    yield {"status": "running", "progress": "100%", "message": "Executing final GDS write..."}

    # Execute the actual GDS query using the existing wrapper
    try:
        final_result = await wrapped_run_gds_cypher(
            query=gds_query,
            params=gds_params,
            db=db,
            db_impersonate=db_impersonate,
            timeout_ms=timeout_ms,
            **kwargs # Pass any remaining kwargs
        )
        # Return the result from the wrapper, wrapped in a final status dict
        # The wrapper already returns {"status": ..., "data": ...}
        # We might want to adjust the structure slightly for the LongRunningTool's final return
        if final_result.get("status") == "success":
             return {"status": "completed", "gds_result": final_result.get("data")}
        else:
             return {"status": "failed", "error": final_result.get("data", "Unknown GDS execution error")}

    except Exception as e:
        # Catch errors during the final execution
        return {"status": "failed", "error": f"Error during GDS execution: {str(e)}"}


# Create the LongRunningFunctionTool instance
PageRankTool = LongRunningFunctionTool(func=pagerank_generator)

# Note: To make this tool available to agents, it needs to be:
# 1. Added to the `ALL_ADK_TOOLS` dictionary in `neo4j_adk_tools.py`
#    (e.g., `ALL_ADK_TOOLS["pagerank"] = PageRankTool`)
# 2. Added to the desired roles in `ROLE_CAPABILITIES` in `rbac.py`
#    (e.g., `"auditor": ["schema", "read", "gds", "pagerank"]`)