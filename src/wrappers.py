# src/wrappers.py
"""
Contains the Neo4j wrapper functions previously in agent.py.
These handle the direct interaction with the Neo4j driver via neo4j_tools.
"""

from typing import Dict, Any, Optional, List, Union
from neo4j.time import DateTime # Import DateTime

# Import the driver access function and the core tool functions
try:
    # Use absolute imports relative to src
    from src.agent import get_driver
    from src import neo4j_tools
except ImportError:
    # Fallback for potential execution context issues (less likely now)
    from src.agent import get_driver # type: ignore # Use absolute path
    from src import neo4j_tools # type: ignore # Use absolute path


# --- Core Neo4j Wrappers ---

async def wrapped_get_neo4j_schema(
    db: Optional[str] = None,
    db_impersonate: Optional[str] = None,
    timeout_ms: int = 15000,
    **kwargs: Any
) -> Dict[str, Any]:
    """
    Fetches the Neo4j schema (node labels, relationship types, property keys).
    Uses APOC procedures if available, otherwise falls back to system catalogs.

    Parameters:
        db (Optional[str]): Target database name. Defaults to Neo4j default.
        db_impersonate (Optional[str]): Neo4j user to impersonate (Enterprise).
        timeout_ms (int): Query timeout in milliseconds.
        **kwargs: Catches unused ADK context args.

    Returns:
        Dict[str, Any]: {"status": "success"|"error", "data": [schema_info]|error_message}
    """
    driver = get_driver() # Get driver instance
    if not driver:
        return {"status": "error", "data": "Neo4j driver not initialized."}
    print(f"Executing wrapped_get_neo4j_schema(db={db}, impersonate={db_impersonate}, timeout={timeout_ms})")
    return await neo4j_tools.get_schema(
        driver=driver,
        db=db,
        impersonate=db_impersonate,
        timeout_ms=timeout_ms
    )


async def wrapped_read_neo4j_cypher(
    query: str,
    params: Optional[Dict[str, Any]] = None,
    db: Optional[str] = None,
    db_impersonate: Optional[str] = None,
    timeout_ms: int = 15000,
    route_read: bool = False, # Specific to read
    **kwargs: Any
) -> Dict[str, Any]:
    """
    Executes a **single** read-only Cypher query against Neo4j using a READ session.
    Prevents any database mutations.
    **IMPORTANT:** Only one Cypher statement is allowed per call. Multi-statement queries
    separated by semicolons (;) are not supported and will cause errors.

    Parameters:
        query (str): The Cypher query to execute.
        params (Optional[Dict[str, Any]]): Parameters for the query.
        db (Optional[str]): Target database name.
        db_impersonate (Optional[str]): Neo4j user to impersonate (Enterprise).
        timeout_ms (int): Query timeout in milliseconds.
        route_read (bool): If True, attempt to route to follower replicas (Enterprise).
        **kwargs: Catches unused ADK context args.

    Returns:
        Dict[str, Any]: {"status": "success"|"error", "data": [query_results]|error_message}
    """
    driver = get_driver() # Get driver instance
    if not driver:
        return {"status": "error", "data": "Neo4j driver not initialized."}
    print(f"Executing wrapped_read_neo4j_cypher(query='{query}', params={params}, db={db}, impersonate={db_impersonate}, timeout={timeout_ms}, route_read={route_read})")
    # Basic client-side check (belt-and-suspenders) - the real check is in neo4j_tools
    if any(op in query.upper() for op in ["CREATE", "MERGE", "DELETE", "SET", "REMOVE", "CALL"]):
        # Allow CALL for read-only procedures like db.schema.visualization() or specific GDS reads if needed,
        # but generally safer to block CALL in the pure read wrapper unless explicitly designed for.
        # A more robust check might parse the query or use EXPLAIN.
        # For now, we rely on the access_mode="READ" in neo4j_tools.
        pass # Let neo4j_tools handle the access mode enforcement

    return await neo4j_tools.run_cypher(
        driver=driver,
        query=query,
        params=params,
        db=db,
        impersonate=db_impersonate,
        timeout_ms=timeout_ms,
        access_mode="READ",
        route_read=route_read
    )


async def wrapped_write_neo4j_cypher(
    query: str,
    params: Optional[Dict[str, Any]] = None,
    db: Optional[str] = None,
    db_impersonate: Optional[str] = None,
    timeout_ms: int = 15000,
    **kwargs: Any
) -> Dict[str, Any]:
    """
    Executes a **single** Cypher query that may mutate the graph, using a WRITE session.
    Returns both query results and summary statistics (counters).
    **IMPORTANT:** Only one Cypher statement is allowed per call. Multi-statement queries
    separated by semicolons (;) are not supported and will cause errors.

    Parameters:
        query (str): The Cypher query to execute.
        params (Optional[Dict[str, Any]]): Parameters for the query.
        db (Optional[str]): Target database name.
        db_impersonate (Optional[str]): Neo4j user to impersonate (Enterprise).
        timeout_ms (int): Query timeout in milliseconds.
        **kwargs: Catches unused ADK context args.

    Returns:
        Dict[str, Any]: {"status": "success"|"error", "data": {"results": [...], "summary": {...counters...}}|error_message}
    """
    driver = get_driver() # Get driver instance
    if not driver:
        return {"status": "error", "data": "Neo4j driver not initialized."}
    print(f"Executing wrapped_write_neo4j_cypher(query='{query}', params={params}, db={db}, impersonate={db_impersonate}, timeout={timeout_ms})")
    return await neo4j_tools.run_cypher(
        driver=driver,
        query=query,
        params=params,
        db=db,
        impersonate=db_impersonate,
        timeout_ms=timeout_ms,
        access_mode="WRITE"
    )


# --- Helper for Serialization ---
def _convert_neo4j_types(data: Any) -> Any:
    """Recursively converts Neo4j temporal types in results to strings."""
    if isinstance(data, list):
        return [_convert_neo4j_types(item) for item in data]
    elif isinstance(data, dict):
        return {k: _convert_neo4j_types(v) for k, v in data.items()}
    elif isinstance(data, DateTime):
        try:
            # Attempt to convert to ISO format string
            return data.iso_format()
        except AttributeError:
            # Fallback if iso_format is not available or fails
            return str(data)
    # Add conversions for other Neo4j types (Date, Duration, Point) if needed
    # elif isinstance(data, neo4j.time.Date): return data.iso_format()
    # elif isinstance(data, neo4j.time.Duration): return str(data) # Or format as needed
    # elif isinstance(data, neo4j.spatial.Point): return {"srid": data.srid, "x": data.x, "y": data.y, "z": data.z}
    else:
        return data

async def wrapped_run_gds_cypher(
    query: Optional[str] = None,
    params: Optional[Dict[str, Any]] = None,
    procedure: Optional[str] = None,
    parameters: Optional[Dict[str, Any]] = None,
    db: Optional[str] = None,
    db_impersonate: Optional[str] = None,
    timeout_ms: int = 60000, # Longer default for GDS
    **kwargs: Any
) -> Dict[str, Any]:
    """
    Executes a **single** Cypher query intended for the Neo4j Graph Data Science library,
    allowing invocation via either a full `query` string or a `procedure` name
    with structured `parameters`. Uses a WRITE session as GDS procedures often require it.

    **IMPORTANT:** Only one Cypher statement is allowed per call. Multi-statement queries
    separated by semicolons (;) are not supported and will cause errors.

    Note: GDS procedure YIELD clauses are version-specific. If you encounter 'Unknown procedure output' errors,
    the tool will attempt to retry without the YIELD clause. If that also fails, consult the documentation
    for the specific GDS version in use.
    Common Examples (CHECK YOUR GDS VERSION):
    - For `gds.louvain.stats`: `YIELD communityCount, modularity`
    - For `gds.louvain.write`: `YIELD nodePropertiesWritten, communityCount`
    - For `gds.nodeSimilarity.stream`: `YIELD node1, node2, similarity`
    - For `gds.nodeSimilarity.write`: `YIELD nodesCompared, relationshipsWritten`

    Parameters:
        query (Optional[str]): The full GDS Cypher query (e.g., CALL gds...). Use this OR procedure/parameters.
        params (Optional[Dict[str, Any]]): Parameters for the query if using the `query` argument.
        procedure (Optional[str]): The GDS procedure name (e.g., "gds.graph.project"). Use this OR query.
        parameters (Optional[Dict[str, Any]]): Parameters for the procedure if using the `procedure` argument.
        db (Optional[str]): Target database name.
        db_impersonate (Optional[str]): Neo4j user to impersonate (Enterprise).
        timeout_ms (int): Query timeout in milliseconds (longer default).
        **kwargs: Catches unused ADK context args.

    Returns:
        Dict[str, Any]: {"status": "success"|"error", "data": [gds_results]|error_message}
    """
    driver = get_driver() # Get driver instance
    if not driver:
        return {"status": "error", "data": "Neo4j driver not initialized."}

    final_query: Optional[str] = query
    final_params: Optional[Dict[str, Any]] = params

    if not final_query:
        # Build a Cypher CALL from procedure/parameters
        if not procedure:
            return {"status": "error", "data": "Must supply either `query` or (`procedure`, `parameters`)."}
        # Use the 'parameters' dict as the params for the constructed query
        final_params = parameters
        # Construct the CALL string, using parameter keys
        param_str = ", ".join(f"${k}" for k in final_params or {})
        final_query = f"CALL {procedure}({param_str})"
        print(f"Executing wrapped_run_gds_cypher(procedure='{procedure}', parameters={final_params}, db={db}, impersonate={db_impersonate}, timeout={timeout_ms})")
    else:
        # Using the provided query string
        print(f"Executing wrapped_run_gds_cypher(query='{final_query}', params={final_params}, db={db}, impersonate={db_impersonate}, timeout={timeout_ms})")

    if not final_query: # Should not happen if logic above is correct, but safety check
         return {"status": "error", "data": "Internal error: Failed to determine query string."}

    # GDS almost always requires WRITE access, even for read-like projections if they materialize graphs
    result = await neo4j_tools.run_cypher(
        driver=driver,
        query=final_query,
        params=final_params,
        db=db,
        impersonate=db_impersonate,
        timeout_ms=timeout_ms,
        access_mode="WRITE"
    )

    # Convert Neo4j specific types in the result data before returning
    if result.get("status") == "success" and "data" in result:
        result["data"] = _convert_neo4j_types(result["data"])

    return result