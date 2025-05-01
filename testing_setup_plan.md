# Neo4j ADK Project Testing Setup

This document explains the test infrastructure setup and how to run the tests for the Neo4j ADK project.

## Test Structure

The tests are organized in the `src/tests` directory:

1. **test_read_guard.py** - Tests that the read wrapper properly blocks write operations
2. **test_schema_fallback.py** - Tests schema fetching functionality and fallbacks
3. **test_write_ok.py** - Tests that legitimate write operations succeed

## Test Configuration

The testing infrastructure uses the following components:

- **pytest.ini** - Project-wide configuration for pytest
- **conftest.py** - Common test fixtures and setup/teardown functionality

### pytest.ini

The `pytest.ini` file configures pytest with:
- Asyncio test mode set to "auto" to properly handle async tests
- Logging settings for better test output visibility
- Test discovery settings to find all tests in the `src/tests` directory

### conftest.py

The `conftest.py` file provides:
- Automatic Neo4j driver initialization/shutdown for all tests
- Proper asyncio setup for the pytest-asyncio plugin
- Graceful handling of missing Neo4j connections

## Running the Tests

To run all tests:

```bash
python -m pytest
```

To run specific test files:

```bash
python -m pytest src/tests/test_read_guard.py
```

To run with detailed output:

```bash
python -m pytest -v
```

## Test Design Principles

1. **Isolation** - Tests are designed to run independently
2. **Graceful Degradation** - Tests that require an active Neo4j connection are skipped when it's not available
3. **Cleanup** - Test data is cleaned up after tests run

## Requirements

The tests require:

1. **Python Packages**:
   - pytest
   - pytest-asyncio
   - python-dotenv (to load Neo4j credentials from .env file)

2. **Optional Neo4j Database**:
   - While having a Neo4j database available allows for more complete testing, the tests are designed to skip database-dependent tests when a connection isn't possible.

## Environment Setup

The tests use environment variables for Neo4j configuration. You can set these in a `.env` file:

```
NEO4J_URI=bolt://localhost:7687
NEO4J_USERNAME=neo4j
NEO4J_PASSWORD=password
```

## Future Improvements

1. **Mocking** - Add proper mocking for the Neo4j driver to test even when a database is not available
2. **Schema Fallback Tests** - Implement the commented-out mock tests in `test_schema_fallback.py`
3. **Continuous Integration** - Set up CI pipeline with containerized Neo4j for complete testing
4. **Performance Tests** - Add performance/load tests for database operations