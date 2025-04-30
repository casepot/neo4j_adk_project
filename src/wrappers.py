# src/wrappers.py
"""
Contains the Neo4j wrapper functions previously in agent.py.
These handle the direct interaction with the Neo4j driver via neo4j_tools.
"""

from typing import Dict, Any, Optional

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
    Executes a read-only Cypher query against Neo4j using a READ session.
    Prevents any database mutations.

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
    Executes a Cypher query that may mutate the graph, using a WRITE session.
    Returns both query results and summary statistics (counters).

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


async def wrapped_run_gds_cypher(
    query: str,
    params: Optional[Dict[str, Any]] = None,
    db: Optional[str] = None,
    db_impersonate: Optional[str] = None,
    timeout_ms: int = 60000, # Longer default for GDS
    **kwargs: Any
) -> Dict[str, Any]:
    """
    Executes a Cypher query intended for the Neo4j Graph Data Science library.
    Uses a WRITE session as GDS procedures often require it (e.g., writing results back).

    Parameters:
        query (str): The GDS Cypher query (e.g., CALL gds...).
        params (Optional[Dict[str, Any]]): Parameters for the query.
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
    print(f"Executing wrapped_run_gds_cypher(query='{query}', params={params}, db={db}, impersonate={db_impersonate}, timeout={timeout_ms})")
    # GDS almost always requires WRITE access, even for read-like projections if they materialize graphs
    return await neo4j_tools.run_cypher(
        driver=driver,
        query=query,
        params=params,
        db=db,
        impersonate=db_impersonate,
        timeout_ms=timeout_ms,
        access_mode="WRITE"
    )