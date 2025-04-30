# src/tests/test_write_ok.py
"""
Tests that legitimate write operations succeed using the write tool/wrapper.
"""

import pytest
import uuid

# Assuming pytest-asyncio is used for async tests
# pip install pytest pytest-asyncio

# Use relative imports if tests are run from the project root
try:
    from ..agent import wrapped_write_neo4j_cypher, wrapped_read_neo4j_cypher
    # May also need initialize/shutdown
except ImportError:
    # Fallback
    from agent import wrapped_write_neo4j_cypher, wrapped_read_neo4j_cypher # type: ignore

# Mark all tests in this module as async
pytestmark = pytest.mark.asyncio

# TODO: Add fixtures for initializing/shutting down the driver for tests
# and potentially cleaning up test data.

@pytest.mark.parametrize("write_query, params, check_key, expected_count", [
    (
        "CREATE (n:WriteTest {id: $uuid, name: 'Test Write'}) RETURN n.id AS id",
        {"uuid": str(uuid.uuid4())},
        "nodes_created",
        1
    ),
    (
        "MERGE (n:WriteTest {id: $uuid}) ON CREATE SET n.name = 'Test Merge Create' ON MATCH SET n.name = 'Test Merge Match' RETURN n.name AS name",
        {"uuid": "merge_test_01"},
        "nodes_created", # Will be 1 on first run, 0 on subsequent if node exists
        1 # Check for creation specifically in this test structure
    ),
    (   # Example of write that also reads back data
        "MERGE (u:UserWriteTest {id: $uid}) SET u.lastUpdated = timestamp() RETURN u.id as userId",
        {"uid": "user_write_test_1"},
        "properties_set",
        1 # Expect lastUpdated property to be set
    )
])
async def test_write_tool_allows_writes(write_query, params, check_key, expected_count):
    """
    Verify that write operations succeed and report correct summaries.
    """
    test_id = params.get("uuid", params.get("uid", "unknown"))
    print(f"\nTesting write tool allows query (id={test_id}): {write_query}")

    # Execute the write query using the write wrapper
    result = await wrapped_write_neo4j_cypher(query=write_query, params=params)

    print(f"Result from write wrapper: {result}")

    # Assert success status
    assert result is not None, "Result should not be None"
    assert result.get("status") == "success", f"Write operation failed: {result.get('data')}"

    # Assert structure of successful data
    assert "data" in result, "Result should contain 'data' key"
    assert isinstance(result["data"], dict), "'data' should be a dictionary"
    assert "results" in result["data"], "'data' should contain 'results' key"
    assert "summary" in result["data"], "'data' should contain 'summary' key"
    assert isinstance(result["data"]["results"], list), "'results' should be a list"
    assert isinstance(result["data"]["summary"], dict), "'summary' should be a dictionary"

    # Assert summary counters reflect the write
    summary = result["data"]["summary"]
    assert summary.get(check_key, 0) >= expected_count, \
        f"Expected summary counter '{check_key}' to be at least {expected_count}, got: {summary.get(check_key, 0)}"

    # --- Optional: Cleanup ---
    # This is basic cleanup; fixtures are better for robust test isolation.
    cleanup_label = "WriteTest" if "WriteTest" in write_query else "UserWriteTest" if "UserWriteTest" in write_query else None
    if cleanup_label and test_id != "unknown":
        print(f"Cleaning up test node: {cleanup_label} {{id: '{test_id}'}}")
        cleanup_query = f"MATCH (n:{cleanup_label} {{id: $id}}) DETACH DELETE n"
        cleanup_result = await wrapped_write_neo4j_cypher(query=cleanup_query, params={"id": test_id})
        print(f"Cleanup result: {cleanup_result}")
        assert cleanup_result.get("status") == "success", "Cleanup query failed"


async def test_write_tool_returns_results():
    """
    Verify that the write tool returns results when the query includes RETURN.
    """
    node_id = f"return_test_{uuid.uuid4()}"
    write_query = "CREATE (n:ReturnTest {id: $id, value: 123}) RETURN n.id AS created_id, n.value AS created_value"
    params = {"id": node_id}
    print(f"\nTesting write tool returns results for query: {write_query}")

    result = await wrapped_write_neo4j_cypher(query=write_query, params=params)

    print(f"Result from write wrapper: {result}")

    assert result.get("status") == "success"
    assert "data" in result and "results" in result["data"]
    results_list = result["data"]["results"]
    assert isinstance(results_list, list)
    assert len(results_list) == 1, "Expected one result record"
    assert results_list[0].get("created_id") == node_id
    assert results_list[0].get("created_value") == 123

    # Cleanup
    print(f"Cleaning up test node: ReturnTest {{id: '{node_id}'}}")
    cleanup_query = "MATCH (n:ReturnTest {id: $id}) DETACH DELETE n"
    await wrapped_write_neo4j_cypher(query=cleanup_query, params={"id": node_id})