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

    # Add DEBUG logging before execution
    logger.debug(f"[Neo4j] ⇢ {query}  params={_mask_params(params)}")

    try:
        # Neo4j Python driver uses transaction_timeout config, but we add an
        # application-level asyncio timeout for overall request control.
        # Note: session.run itself doesn't take a timeout directly in recent versions.
        # Timeout needs to be configured on the transaction or session level if needed
        # for the driver to manage it internally. The asyncio.wait_for here acts as
        # a safeguard for the entire operation within the session context.
        # Add detailed logging immediately before the driver call
        logger.debug(f"Executing session.run with: query='{query}', params={_mask_params(params)}")
        result: Result = await asyncio.wait_for(
            session.run(query, params),
            timeout=timeout_ms / 1000.0 # asyncio.wait_for uses seconds
        )

        # Eagerly fetch results to ensure query completion within timeout
        results_list = [record.data() async for record in result]
        summary = await result.consume()
        summary_dict = summary.counters.__dict__ if summary and summary.counters else {}
        # Add DEBUG logging after consume
        logger.debug(f"[Neo4j] ⇠ counters={summary.counters}  plan={summary.plan if summary else None}")

    except asyncio.TimeoutError:
        logger.error(f"Query timed out after {timeout_ms}ms: {query}")
        # Attempt to cancel the query on the server? (Complex, often relies on transaction termination)
        raise TimeoutError(f"Query execution exceeded timeout of {timeout_ms}ms.")
    except ClientError as e:
        logger.error(f"Neo4j ClientError: {e.message} (Code: {e.code}) for query: {query}")
        # Specific handling for read/write errors in wrong mode might be useful
        if "Write operations are not allowed" in e.message:
             raise PermissionError(f"Write operation attempted in read-only session: {query}") from e

        # --- REMOVED GDS YIELD Auto-Retry Logic ---
        # Let the original ClientError (e.g., Unknown procedure output) propagate
        # back to the agent for better diagnosis. The agent should fix the YIELD clause.

        raise # Re-raise original client error
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
            # 1. Try APOC using apoc.meta.schema()
            logger.info("Attempting schema fetch using apoc.meta.schema()...")
            apoc_query = "CALL apoc.meta.schema() YIELD value RETURN value" # Use recommended procedure
            results, _ = await _execute_cypher_session(session, apoc_query, {}, timeout_ms)

            if results and isinstance(results[0].get('value'), dict):
                # Process the schema map returned by apoc.meta.schema()
                schema_map = results[0]['value']
                schema_parts = []
                # Extract Node Labels and Properties
                for label, data in schema_map.items():
                    if data.get('type') == 'node':
                        properties = ', '.join([f"{prop}: {details.get('type', 'UNKNOWN')}" for prop, details in data.get('properties', {}).items()])
                        schema_parts.append(f"Node: (:{label} {{{properties}}})")

                # Extract Relationship Types and Properties (More Robust Parsing from apoc.meta.schema)
                rel_details = {} # Store details per relationship type {rel_type: {'properties': {prop: type}, 'connections': set((start_label, end_label))}}
                
                # First pass: Collect all relationship types and their properties from the schema map
                for item_name, item_data in schema_map.items():
                    # Relationships are described under node entries in apoc.meta.schema
                    if item_data.get('type') == 'node':
                        start_node_label = item_name # The key is the node label
                        for rel_name, rel_info in item_data.get('relationships', {}).items():
                            rel_type = rel_info.get('type')
                            if not rel_type: continue
                            
                            # Initialize if first time seeing this rel_type
                            if rel_type not in rel_details:
                                rel_details[rel_type] = {'properties': {}, 'connections': set()}
                                
                            # Merge properties (take the union of properties seen across different connections)
                            for prop, details in rel_info.get('properties', {}).items():
                                if prop not in rel_details[rel_type]['properties']:
                                    rel_details[rel_type]['properties'][prop] = details.get('type', 'UNKNOWN')
                                    
                            # Record connection pattern (start_label, end_label)
                            # Note: apoc.meta.schema provides labels connected *to* the current node label
                            end_node_labels = rel_info.get('labels', [])
                            direction = rel_info.get('direction', 'out')
                            
                            for end_label in end_node_labels:
                                if direction == 'out':
                                    rel_details[rel_type]['connections'].add((start_node_label, end_label))
                                elif direction == 'in':
                                     rel_details[rel_type]['connections'].add((end_label, start_node_label))
                                # Ignore 'both' direction for simplicity in this representation

                # Format relationship schema parts
                for rel_type, details in sorted(rel_details.items()):
                     properties = ', '.join([f"{prop}: {ptype}" for prop, ptype in sorted(details['properties'].items())])
                     # Show one example connection pattern like (:Start)-[:TYPE]->(:End)
                     example_conn = next(iter(details['connections']), ('?', '?'))
                     example_connection = f"(:{example_conn[0]})-[r:{rel_type}]->(:{example_conn[1]})"
                     schema_parts.append(f"Relationship: {example_connection} {{{properties}}}")

                # Check if we actually found relationship details via APOC
                found_rels_via_apoc = any(part.startswith("Relationship:") for part in schema_parts)

                if schema_parts and found_rels_via_apoc:
                    # Combine node and relationship parts, then sort for consistent output
                    combined_schema = sorted([part for part in schema_parts if part.startswith("Node:")]) + \
                                      sorted([part for part in schema_parts if part.startswith("Relationship:")])
                    schema_info = "\n".join(combined_schema)
                    status = "success"
                    logger.info("Schema fetched successfully using apoc.meta.schema() (including relationships).")
                elif schema_parts and not found_rels_via_apoc:
                     logger.warning("apoc.meta.schema() call succeeded and returned node data, but NO relationship data. Proceeding to fallback for relationships.")
                     # Keep node data, but status remains 'error' to trigger fallback
                     schema_info = "\n".join(sorted([part for part in schema_parts if part.startswith("Node:")]))
                     # status remains 'error' to trigger fallback below
                elif not schema_parts:
                    logger.info("apoc.meta.schema() call succeeded but returned no schema data (database likely empty). Proceeding to fallback.")
                    # Set schema_info to indicate empty, but proceed to fallback. Status remains 'error' for now.
                    schema_info = "No schema elements found via APOC."
                # If schema_map wasn't a dict, status is already 'error'
            else: # This case handles if results[0].get('value') was not a dict
                 logger.warning("apoc.meta.schema() call did not return the expected dictionary structure.")
                 # Proceed to fallback, status remains 'error'

        except ClientError as e:
            # Modify line 163 condition if needed:
            if "Unknown function 'apoc.meta.schema'" in str(e) or "NoSuchProcedureException" in str(e):
                 logger.warning("APOC not found or `apoc.meta.schema` procedure unavailable. Falling back to SHOW commands.")
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
                # Note: Running multiple queries sequentially here.
                # Use CALL db.* procedures which are generally more reliable than SHOW commands
                labels_query = "CALL db.labels() YIELD label RETURN collect(label) AS labels"
                rels_query = "CALL db.relationshipTypes() YIELD relationshipType RETURN collect(relationshipType) AS rel_types"
                # Getting all property keys might be less useful than properties per type,
                # but let's keep it simple for the fallback for now.
                # A more detailed fallback could use CALL db.schema.nodeTypeProperties() etc.
                props_query = "CALL db.propertyKeys() YIELD propertyKey RETURN collect(propertyKey) AS prop_keys"

                labels_res, _ = await _execute_cypher_session(session, labels_query, {}, timeout_ms)
                rels_res, _ = await _execute_cypher_session(session, rels_query, {}, timeout_ms)
                props_res, _ = await _execute_cypher_session(session, props_query, {}, timeout_ms)

                # Extract results safely
                labels = labels_res[0]['labels'] if labels_res and labels_res[0] and 'labels' in labels_res[0] else []
                rel_types = rels_res[0]['rel_types'] if rels_res and rels_res[0] and 'rel_types' in rels_res[0] else []
                prop_keys = props_res[0]['prop_keys'] if props_res and props_res[0] and 'prop_keys' in props_res[0] else []

                # Combine the results into a user-friendly string
                schema_parts = []
                if labels:
                    schema_parts.append(f"Node Labels: {sorted(labels)}")
                if rel_types:
                    schema_parts.append(f"Relationship Types: {sorted(rel_types)}")
                if prop_keys:
                     schema_parts.append(f"Property Keys (All): {sorted(prop_keys)}")

                if schema_parts:
                     # If APOC failed but returned partial node info, prepend it
                     if isinstance(schema_info, str) and schema_info.startswith("Node:"):
                          schema_info = schema_info + "\n" + "\n".join(schema_parts)
                     else: # Otherwise, just use the fallback info
                          schema_info = "\n".join(schema_parts)
                     status = "success"
                     logger.info("Schema fetched successfully using CALL db.* fallback procedures.")
                else:
                    # Fallback also failed to find anything
                    logger.info("Fallback schema fetch using CALL db.* also returned no data (database likely empty).")
                    # If APOC also found nothing, report success with empty message.
                    # If APOC found nodes but no rels, keep the node info and report success.
                    if schema_info == "No schema elements found via APOC.":
                        schema_info = "No schema elements found (database is empty)."
                    # If schema_info contains node data from APOC, keep it.
                    # Otherwise (e.g., APOC failed), use the empty message.
                    elif not schema_info.startswith("Node:"):
                         schema_info = "No schema elements found (database is empty)."

                    status = "success" # Report success even if empty

            except (ClientError, TimeoutError, Exception) as e:
                logger.error(f"Fallback schema fetch using CALL db.* failed: {e}")
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
    # Add multi-statement guardrail
    if ";" in query.strip().rstrip(";"):
        logger.error(f"Multi-statement query detected and rejected: {query}")
        return {"status": "error", "data": "Only one Cypher statement per call is allowed."}

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
            logger.debug(f"Calling _execute_cypher_session from run_cypher with: query='{query}', params={_mask_params(params)}") # Add logging here
            results, summary = await _execute_cypher_session(session, query, params, timeout_ms)

            # Format response based on access mode (write includes summary)
            is_gds_call = "CALL GDS." in query.upper()
            if access_mode == "WRITE":
                # Refined assertion: Only treat zero counters as error for non-GDS, non-MERGE queries.
                # MERGE returning zero counters is valid if the data already exists.
                is_merge_query = "MERGE " in query.strip().upper() # Simple check for MERGE keyword
                if not is_gds_call and not is_merge_query and not any(summary.values()):
                    logger.warning(f"Non-GDS, non-MERGE write query succeeded but returned zero counters (e.g., MATCH...SET found no nodes): {query}")
                    # Log warning but proceed to return success, as the query itself didn't fail.
                elif not is_gds_call and is_merge_query and not any(summary.values()):
                     logger.info(f"MERGE query succeeded with zero counters (data likely already existed): {query}")
                     # For MERGE, zero counters means success (data existed), so proceed.

                # For GDS calls or successful writes/merges, return results and summary
                response_data = {"results": results, "summary": summary}
            else: # READ mode
                # Read mode (including GDS reads like .stream or .list) just returns results
                response_data = results

            return {"status": "success", "data": response_data}

    except (PermissionError, ClientError) as e: # Catch specific write-in-read error or other client errors
        logger.error(f"Neo4j Client Error during run_cypher: {e}")
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