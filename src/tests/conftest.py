# src/tests/conftest.py
"""
Fixtures and configuration for pytest tests.
"""

import pytest
import pytest_asyncio
import asyncio
import os
from dotenv import load_dotenv

# Try to load environment variables from .env file
load_dotenv()

# Import driver initialization and shutdown functions with fallbacks
try:
    from ..agent import initialize_neo4j_driver, shutdown_neo4j_driver
except ImportError:
    try:
        from src.agent import initialize_neo4j_driver, shutdown_neo4j_driver
    except ImportError:
        # Create mock functions if not available
        async def initialize_neo4j_driver(**kwargs):
            print("Mock initialize_neo4j_driver called - no real driver initialized")
            return None

        async def shutdown_neo4j_driver():
            print("Mock shutdown_neo4j_driver called - no real driver to shutdown")
            return None


# This fixture will be used by all tests in the module
@pytest_asyncio.fixture(scope="module", autouse=True)
async def manage_neo4j_driver():
    """
    Initialize the Neo4j driver at the beginning of the test session
    and shut it down at the end.
    
    This fixture handles connection failures gracefully to allow tests to run
    with appropriate skips when a database is not available.
    """
    print("\nInitializing Neo4j driver for test session...")
    
    try:
        # Try to initialize the driver with environment variables
        # We could pass specific test database credentials here if needed
        await initialize_neo4j_driver()
        print("Neo4j driver initialized successfully.")
    except Exception as e:
        print(f"Warning: Failed to initialize Neo4j driver: {e}")
        print("Tests will run with appropriate skips when DB operations are required.")
    
    # Yield control back to the tests
    yield
    
    # Teardown after all tests complete
    print("\nShutting down Neo4j driver after test session...")
    try:
        await shutdown_neo4j_driver()
        print("Neo4j driver shut down successfully.")
    except Exception as e:
        print(f"Warning: Error during Neo4j driver shutdown: {e}")


# Configure pytest-asyncio to use the event loop fixture
# Create a module-scoped event loop for our tests
@pytest.fixture(scope="module")
def event_loop():
    """
    Create an event loop for each test module.
    """
    policy = asyncio.get_event_loop_policy()
    loop = policy.new_event_loop()
    yield loop
    loop.close()