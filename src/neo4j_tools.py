# src/neo4j_tools.py
"""
Contains heavy-lifting helpers for Neo4j interactions:
- Timeout enforcement
- Read/Write access mode guards
- EXPLAIN plan checks (optional)
- Parameter masking for logging
- Centralized query execution logic
"""

import asyncio
import logging
from typing import Dict, Any, Optional, List, Tuple
# from neo4j import AsyncSession, Query, Result # Import later when driver is used
# from neo4j.exceptions import ClientError

# Placeholder for Neo4j driver (should be accessed via agent.py or similar)
# driver = None

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- Helper Functions ---

def _mask_params(params: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Masks sensitive parameters for logging."""
    if not params:
        return {}
    # Simple masking example, enhance as needed
    masked = {}
    for k, v in params.items():
        if "password" in k.lower() or "token" in k.lower() or "secret" in k.lower():
            masked[k] = "***MASKED***"
        else:
            masked[k] = v
    return masked

async def _log_query(query: str, params: Optional[Dict[str, Any]], db: Optional[str], impersonate: Optional[str]):
    """Logs query details with masked parameters."""
    log_params = _mask_params(params)
    log_msg = f"Executing Cypher (db={db or 'default'}, impersonate={impersonate or 'None'}): Query='{query}', Params={log_params}"
    logger.info(log_msg)
    # TODO: Add OpenTelemetry span creation here if needed

async def _check_explain_plan(session, query: str, params: Optional[Dict[str, Any]]) -> bool:
    """
    (Optional) Runs EXPLAIN on the query to check for potentially harmful operations
    before execution. Return True if safe, False otherwise.
    """
    # TODO: Implement EXPLAIN plan check logic if required.
    # This is complex and depends on specific rules (e.g., disallow full scans).
    # explain_query = f"EXPLAIN {query}"
    # try:
    #     result = await session.run(explain_query, params)
    #     plan = await result.single()
    #     # Analyze the plan (plan[0] usually contains the plan details)
    #     if "NodeByLabelScan" in str(plan[0]): # Example check
    #          logger.warning(f"Query plan includes NodeByLabelScan: {query}")
    #          # return False # If strictly disallowed
    # except Exception as e:
    #     logger.error(f"Failed to check EXPLAIN plan for query '{query}': {e}")
    #     return False # Fail safe
    return True # Default to safe for now

async def _execute_cypher_session(
    session, # : AsyncSession,
    query: str,
    params: Optional[Dict[str, Any]],
    timeout_ms: int
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """Executes a query within a session, handling timeout and results."""
    results_list = []
    summary_dict = {}

    try:
        # Neo4j Python driver handles timeouts via configuration,
        # but we can add an application-level asyncio timeout for stricter control.
        result = await asyncio.wait_for(
            session.run(query, params),
            timeout=timeout_ms / 1000.0 # asyncio.wait_for uses seconds
        ) # type: Result

        results_list = [record.data() async for record in result]
        summary = await result.consume() # type: Summary
        summary_dict = summary.counters.__dict__ # Get counters like nodes_created etc.

    except asyncio.TimeoutError:
        logger.error(f"Query timed out after {timeout_ms}ms: {query}")
        raise TimeoutError(f"Query execution exceeded timeout of {timeout_ms}ms.")
    # except ClientError as e:
    #     logger.error(f"Neo4j ClientError: {e.message} (Code: {e.code}) for query: {query}")
    #     raise # Re-raise client errors
    except Exception as e:
        logger.error(f"Error executing Cypher query '{query}': {e}")
        raise # Re-raise other errors

    return results_list, summary_dict


# --- Public API used by agent.py wrappers ---

async def get_schema(
    db: Optional[str] = None,
    impersonate: Optional[str] = None,
    timeout_ms: int = 15000
) -> Dict[str, Any]:
    """Fetches schema, handling APOC fallback and errors."""
    # TODO: Implement actual schema fetching logic
    # 1. Try APOC: `CALL apoc.meta.data()`
    # 2. If APOC fails or not present, fallback to:
    #    `SHOW NODE LABELS`, `SHOW RELATIONSHIP TYPES`, `SHOW PROPERTY KEYS`
    # 3. Format results consistently.
    # 4. Use _execute_cypher_session for running queries.
    await _log_query("SCHEMA FETCH", {}, db, impersonate)
    # Placeholder implementation
    try:
        # Simulate fetching schema
        await asyncio.sleep(0.1) # Simulate network delay
        schema_data = ["Schema: (:Label1)-[:REL]->(:Label2 {prop: 'string'})"] # Example data
        return {"status": "success", "data": schema_data}
    except Exception as e:
        logger.error(f"Failed to get schema (db={db}, impersonate={impersonate}): {e}")
        return {"status": "error", "data": str(e)}


async def run_cypher(
    query: str,
    params: Optional[Dict[str, Any]] = None,
    db: Optional[str] = None,
    impersonate: Optional[str] = None,
    timeout_ms: int = 15000,
    access_mode: str = "WRITE", # "READ" or "WRITE"
    route_read: bool = False # Only relevant for READ access_mode
) -> Dict[str, Any]:
    """
    Runs a Cypher query with specified access mode, timeout, and logging.
    Handles session creation and error reporting.
    """
    # TODO: Get driver instance properly (e.g., from agent.py or a shared module)
    # global driver
    # if not driver:
    #     return {"status": "error", "data": "Neo4j driver not initialized."}

    await _log_query(query, params, db, impersonate)

    session_params = {"database": db}
    if impersonate:
        session_params["impersonated_user"] = impersonate
    if access_mode == "READ":
        session_params["default_access_mode"] = "READ" # neo4j.READ_ACCESS
        # Note: Routing is often configured at the driver level, but explicit
        # session mode helps if driver uses mixed pools or for clarity.
        # The `route_read` parameter passed to the wrapper might influence
        # driver config or session choice if using separate read/write drivers.
    else:
         session_params["default_access_mode"] = "WRITE" # neo4j.WRITE_ACCESS

    # Placeholder for session management
    # async with driver.session(**session_params) as session:
    try:
        # Placeholder: Simulate session and execution
        logger.info(f"Simulating session with params: {session_params}")

        # 0. (Optional) Read Guard for READ mode
        if access_mode == "READ":
            # Basic check - more robust checks might involve EXPLAIN
            forbidden_keywords = ["CREATE", "MERGE", "SET", "DELETE", "REMOVE", "CALL GDS"] # Rough check
            if any(keyword in query.upper() for keyword in forbidden_keywords):
                 logger.error(f"Write operation attempted in READ mode: {query}")
                 return {"status": "error", "data": f"Write operations forbidden in read tool/session. Query: {query}"}

        # 1. (Optional) EXPLAIN Plan Check
        # if not await _check_explain_plan(session, query, params):
        #     return {"status": "error", "data": "Query failed EXPLAIN plan safety check."}

        # 2. Execute Query
        # results, summary = await _execute_cypher_session(session, query, params, timeout_ms)
        # Simulate execution:
        await asyncio.sleep(0.2) # Simulate query time
        if "error" in query.lower(): raise ValueError("Simulated query error")
        results = [{"result_key": "result_value"}] if "RETURN" in query.upper() else []
        summary = {"nodes_created": 1} if "CREATE" in query.upper() else {}

        # Format response based on access mode (write includes summary)
        if access_mode == "WRITE":
            response_data = {"results": results, "summary": summary}
        else: # READ mode
            response_data = results

        return {"status": "success", "data": response_data}

    except TimeoutError as e:
        return {"status": "error", "data": str(e)}
    # except ClientError as e:
    #     return {"status": "error", "data": f"Neo4j Error: {e.message} (Code: {e.code})"}
    except Exception as e:
        logger.exception(f"Unexpected error running Cypher (db={db}, impersonate={impersonate}): {query}")
        return {"status": "error", "data": f"Unexpected error: {str(e)}"}
    # finally:
        # Session is automatically closed by `async with`
        # print("Session closed (placeholder)")