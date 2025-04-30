# src/neo4j_tools.py
"""
Contains heavy-lifting helpers for Neo4j interactions:
- Timeout enforcement
- Read/Write access mode guards
- Parameter masking for logging
- Centralized query execution logic
- Schema fetching with APOC fallback
"""

import asyncio
import logging
from typing import Dict, Any, Optional, List, Tuple
from neo4j import (
    AsyncSession, Query, Result, ResultSummary, AsyncDriver, # Changed Summary to ResultSummary
    READ_ACCESS, WRITE_ACCESS
)
from neo4j.exceptions import ClientError, ServiceUnavailable, AuthError

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- Helper Functions ---

def _mask_params(params: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Masks sensitive parameters for logging."""
    if not params:
        return {}
    masked = {}
    for k, v in params.items():
        # Mask common sensitive keys and values that look like tokens/keys
        if any(sensitive in k.lower() for sensitive in ["password", "token", "secret", "apikey", "credential"]):
            masked[k] = "***MASKED***"
        elif isinstance(v, str) and (v.startswith("sk-") or v.startswith("pk-") or len(v) > 40): # Basic check for API keys
             masked[k] = "***MASKED***"
        else:
            masked[k] = v
    return masked

async def _log_query(query: str, params: Optional[Dict[str, Any]], db: Optional[str], impersonate: Optional[str], access_mode: str):
    """Logs query details with masked parameters."""
    log_params = _mask_params(params)
    log_msg = (f"Executing Cypher (db={db or 'default'}, impersonate={impersonate or 'None'}, mode={access_mode}): "
               f"Query='{query}', Params={log_params}")
    logger.info(log_msg)
    # TODO: Add OpenTelemetry span creation here if needed

async def _check_explain_plan(session: AsyncSession, query: str, params: Optional[Dict[str, Any]]) -> bool:
    """
    (Optional) Runs EXPLAIN on the query to check for potentially harmful operations
    before execution. Return True if safe, False otherwise.
    Currently a placeholder returning True.
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
    session: AsyncSession,
    query: str,
    params: Optional[Dict[str, Any]],
    timeout_ms: int
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """Executes a query within a session, handling timeout and results."""
    results_list = []
    summary_dict = {}
    summary: Optional[ResultSummary] = None # Changed Summary to ResultSummary

    try:
        # Neo4j Python driver uses transaction_timeout config, but we add an
        # application-level asyncio timeout for overall request control.
        # Note: session.run itself doesn't take a timeout directly in recent versions.
        # Timeout needs to be configured on the transaction or session level if needed
        # for the driver to manage it internally. The asyncio.wait_for here acts as
        # a safeguard for the entire operation within the session context.
        result: Result = await asyncio.wait_for(
            session.run(query, params),
            timeout=timeout_ms / 1000.0 # asyncio.wait_for uses seconds
        )

        # Eagerly fetch results to ensure query completion within timeout
        results_list = [record.data() async for record in result]
        summary = await result.consume()
        summary_dict = summary.counters.__dict__ if summary and summary.counters else {}

    except asyncio.TimeoutError:
        logger.error(f"Query timed out after {timeout_ms}ms: {query}")
        # Attempt to cancel the query on the server? (Complex, often relies on transaction termination)
        raise TimeoutError(f"Query execution exceeded timeout of {timeout_ms}ms.")
    except ClientError as e:
        logger.error(f"Neo4j ClientError: {e.message} (Code: {e.code}) for query: {query}")
        # Specific handling for read/write errors in wrong mode might be useful
        if "Write operations are not allowed" in e.message:
             raise PermissionError(f"Write operation attempted in read-only session: {query}") from e
        raise # Re-raise client errors
    except (ServiceUnavailable, AuthError) as e:
         logger.error(f"Neo4j connection/auth error: {e}")
         raise # Re-raise critical connection errors
    except Exception as e:
        logger.error(f"Error executing Cypher query '{query}': {type(e).__name__}: {e}")
        raise # Re-raise other errors

    return results_list, summary_dict


# --- Public API used by agent.py wrappers ---

async def get_schema(
    driver: AsyncDriver,
    db: Optional[str] = None,
    impersonate: Optional[str] = None,
    timeout_ms: int = 15000
) -> Dict[str, Any]:
    """Fetches schema, trying APOC first, then falling back to SHOW commands."""
    await _log_query("SCHEMA FETCH", {}, db, impersonate, "READ")

    session_params = {"database": db, "default_access_mode": READ_ACCESS}
    if impersonate:
        session_params["impersonated_user"] = impersonate

    schema_info = "Schema information could not be retrieved."
    status = "error"

    async with driver.session(**session_params) as session:
        try:
            # 1. Try APOC
            logger.info("Attempting schema fetch using APOC...")
            apoc_query = "CALL apoc.meta.data() YIELD label, property, type, relationship, other RETURN *"
            results, _ = await _execute_cypher_session(session, apoc_query, {}, timeout_ms)
            # Basic formatting, could be more structured
            schema_parts = []
            for record in results:
                schema_parts.append(f"Node: (:{record['label']} {{{record['property']}: {record['type']}}})")
                if record.get('relationship') and record.get('other'):
                     # Simplified representation, apoc.meta.data structure is complex
                     other_labels = ', '.join(record['other'])
                     schema_parts.append(f"Relationship: (:{record['label']})-[:{record['relationship']}]->(:{other_labels})")
            if schema_parts:
                 schema_info = "\n".join(list(set(schema_parts))) # Use set to remove duplicates from yield format
                 status = "success"
                 logger.info("Schema fetched successfully using APOC.")
            else:
                 logger.warning("APOC call succeeded but returned no schema data.")
                 # Proceed to fallback

        except ClientError as e:
            if "Unknown function 'apoc.meta.data'" in str(e) or "NoSuchProcedureException" in str(e):
                logger.warning("APOC not found or `apoc.meta.data` procedure unavailable. Falling back to SHOW commands.")
                # Proceed to fallback
            else:
                logger.error(f"APOC schema fetch failed with unexpected ClientError: {e}")
                schema_info = f"APOC Error: {e.message}"
                # Don't proceed to fallback if it's a general error
                return {"status": "error", "data": schema_info}
        except TimeoutError as e:
             logger.error(f"APOC schema fetch timed out: {e}")
             return {"status": "error", "data": str(e)}
        except Exception as e:
            logger.error(f"APOC schema fetch failed with unexpected error: {e}")
            schema_info = f"Unexpected APOC Error: {str(e)}"
            # Don't proceed to fallback if it's a general error
            return {"status": "error", "data": schema_info}

        # 2. Fallback to SHOW commands if APOC failed or returned nothing
        if status != "success":
            logger.info("Attempting schema fetch using SHOW commands...")
            try:
                # Combine SHOW commands into a single conceptual fetch
                # Note: Running multiple queries sequentially here. Consider parallel execution if performance critical.
                labels_query = "SHOW NODE LABELS YIELD label RETURN collect(label) AS labels"
                rels_query = "SHOW RELATIONSHIP TYPES YIELD relationshipType RETURN collect(relationshipType) AS rel_types"
                props_query = "SHOW PROPERTY KEYS YIELD propertyKey RETURN collect(propertyKey) AS prop_keys" # Less useful without context

                labels_res, _ = await _execute_cypher_session(session, labels_query, {}, timeout_ms)
                rels_res, _ = await _execute_cypher_session(session, rels_query, {}, timeout_ms)
                props_res, _ = await _execute_cypher_session(session, props_query, {}, timeout_ms)

                labels = labels_res[0]['labels'] if labels_res else []
                rel_types = rels_res[0]['rel_types'] if rels_res else []
                prop_keys = props_res[0]['prop_keys'] if props_res else [] # All property keys in the DB

                schema_info = (f"Node Labels: {labels}\n"
                               f"Relationship Types: {rel_types}\n"
                               f"Property Keys (All): {prop_keys}")
                status = "success"
                logger.info("Schema fetched successfully using SHOW commands.")

            except (ClientError, TimeoutError, Exception) as e:
                logger.error(f"Fallback schema fetch using SHOW commands failed: {e}")
                schema_info = f"Fallback Schema Error: {str(e)}"
                status = "error"

    return {"status": status, "data": schema_info}


async def run_cypher(
    driver: AsyncDriver,
    query: str,
    params: Optional[Dict[str, Any]] = None,
    db: Optional[str] = None,
    impersonate: Optional[str] = None,
    timeout_ms: int = 15000,
    access_mode: str = "WRITE", # "READ" or "WRITE"
    route_read: bool = False # Influences driver config, not directly used here post-init
) -> Dict[str, Any]:
    """
    Runs a Cypher query with specified access mode, timeout, and logging.
    Handles session creation and error reporting.
    """
    await _log_query(query, params, db, impersonate, access_mode)

    session_params = {"database": db}
    if impersonate:
        session_params["impersonated_user"] = impersonate

    neo4j_access_mode = WRITE_ACCESS
    if access_mode == "READ":
        neo4j_access_mode = READ_ACCESS
        # Note: Routing (`route_read`) is typically configured at the Driver level
        # based on cluster topology awareness. Explicit routing hints per-session
        # are less common in the Python driver compared to setting access mode.
        # If using Enterprise Edition with read replicas, ensure the driver's
        # routing table is up-to-date.

    session_params["default_access_mode"] = neo4j_access_mode

    try:
        async with driver.session(**session_params) as session:
            # 1. (Optional) EXPLAIN Plan Check - currently disabled placeholder
            # if not await _check_explain_plan(session, query, params):
            #     return {"status": "error", "data": "Query failed EXPLAIN plan safety check."}

            # 2. Execute Query
            results, summary = await _execute_cypher_session(session, query, params, timeout_ms)

            # Format response based on access mode (write includes summary)
            if access_mode == "WRITE":
                response_data = {"results": results, "summary": summary}
            else: # READ mode
                response_data = results

            return {"status": "success", "data": response_data}

    except (PermissionError, ClientError) as e: # Catch specific write-in-read error or other client errors
        return {"status": "error", "data": f"Neo4j Client Error: {str(e)}"}
    except TimeoutError as e:
        return {"status": "error", "data": str(e)}
    except (ServiceUnavailable, AuthError) as e:
         # Critical errors, might indicate config issues
         logger.exception(f"Neo4j connection/auth error running Cypher (db={db}, impersonate={impersonate}): {query}")
         return {"status": "error", "data": f"Neo4j Connection/Auth Error: {str(e)}"}
    except Exception as e:
        logger.exception(f"Unexpected error running Cypher (db={db}, impersonate={impersonate}): {query}")
        return {"status": "error", "data": f"Unexpected error: {type(e).__name__}: {str(e)}"}