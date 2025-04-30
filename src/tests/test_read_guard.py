# src/tests/test_read_guard.py
"""
Tests the read guard mechanism in the read tool/wrapper.
Ensures that attempts to perform write operations via the read-only
interface are correctly blocked.
"""

import pytest
# Assuming pytest-asyncio is used for async tests
# pip install pytest pytest-asyncio

# Use relative imports if tests are run from the project root (e.g., using `pytest`)
try:
    from ..agent import wrapped_read_neo4j_cypher
    # May also need initialize/shutdown and potentially neo4j_tools if mocking driver directly
except ImportError:
    # Fallback if structure differs or run differently
    from agent import wrapped_read_neo4j_cypher # type: ignore

# Mark all tests in this module as async
pytestmark = pytest.mark.asyncio

# TODO: Add fixtures for initializing/shutting down the driver for tests
# @pytest.fixture(scope="module", autouse=True)
# async def manage_driver():
#     await initialize_neo4j_driver()
#     yield
#     await shutdown_neo4j_driver()

@pytest.mark.parametrize("write_query", [
    "CREATE (:TestNode {name: 'read_guard_test'})",
    "MERGE (:TestNode {id: 123}) SET n.updated = timestamp()",
    "MATCH (n {name: 'some_node'}) SET n.property = 'new_value'",
    "MATCH (n {name: 'to_delete'}) DETACH DELETE n",
    "CALL apoc.create.node(['Test'], {name:'apoc_test'})", # Example APOC write
    "CALL gds.graph.project('testGraph', 'Node', 'REL')", # GDS often needs write access
])
async def test_read_tool_blocks_writes(write_query):
    """
    Verify that various write operations fail when sent through the read wrapper.
    """
    print(f"\nTesting read guard with query: {write_query}")

    # Execute the write query using the read wrapper
    result = await wrapped_read_neo4j_cypher(query=write_query, params={})

    print(f"Result from read wrapper: {result}")

    # Assert that the operation failed
    assert result is not None, "Result should not be None"
    assert result.get("status") == "error", "Status should be 'error' for forbidden write"
    assert "forbidden" in result.get("data", "").lower() or \
           "write" in result.get("data", "").lower() or \
           "read-only" in result.get("data", "").lower(), \
           "Error message should indicate a write/read-only violation"

    # Optional: Verify that no data was actually written (requires query capability)
    # check_query = "MATCH (n:TestNode {name: 'read_guard_test'}) RETURN count(n) AS count"
    # check_result = await wrapped_read_neo4j_cypher(query=check_query, params={}) # Use read tool again
    # if check_result.get("status") == "success":
    #     assert check_result["data"][0]["count"] == 0, "Node should not have been created"


async def test_read_tool_allows_reads():
    """
    Verify that a simple read operation succeeds using the read wrapper.
    """
    read_query = "MATCH (n) RETURN count(n) AS count"
    print(f"\nTesting read tool allows query: {read_query}")

    result = await wrapped_read_neo4j_cypher(query=read_query, params={})

    print(f"Result from read wrapper: {result}")

    assert result is not None
    assert result.get("status") == "success", "Read query should succeed"
    assert isinstance(result.get("data"), list), "Result data should be a list"
    # Add more specific checks based on expected read result if necessary

# Add more tests as needed, e.g., testing routing behavior if applicable