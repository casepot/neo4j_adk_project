# Neo4j ADK v1.0 Integration Kit

This repository provides a baseline structure and production-ready code for integrating Neo4j with Google's Agent Development Kit (ADK). It includes role-based access control (RBAC) and best-practice wrappers for common Neo4j operations.

## High-Level Architecture

```
┌─────────────────────────────┐
│  LLM Agent (Gemini / etc.)  │
│  ├── sees FunctionTools     │
│  └── role = explorer|…      │
└────────────┬────────────────┘
             │  call
┌────────────▼────────────────┐
│  ADK FunctionTool shim      │
│  (schema/read/write/gds)    │
└────────────┬────────────────┘
             │  await
┌────────────▼────────────────┐
│  Neo4j wrapper              │
│  • read/write guards        │
│  • EXPLAIN plan check       │
│  • timeout, param masking   │
└────────────┬────────────────┘
             │  bolt
┌────────────▼────────────────┐
│  Neo4j cluster / Aura       │
└─────────────────────────────┘
```

- **Wrappers (`neo4j_tools.py`, `agent.py`)**: Centralize database interaction, error handling, security checks (read/write guards), and logging.
- **FunctionTool Shim (`neo4j_adk_tools.py`)**: Makes each wrapper a first-class ADK tool, exposing only `query` and `params` (or no arguments) to the LLM.
- **RBAC Factory (`rbac.py`)**: Controls which tools each agent role can access, preventing code duplication.

## Features

- **Standardized Tools**: Provides ADK `FunctionTool` instances for:
    - `schema`: Fetching database schema.
    - `read`: Executing read-only Cypher queries.
    - `write`: Executing Cypher queries that may mutate the graph.
    - `gds`: Executing Cypher queries for the Graph Data Science library.
- **Role-Based Access Control**: Pre-defined roles (`explorer`, `auditor`, `builder`, `admin`) with easily configurable capabilities.
- **Neo4j Best Practices**: Includes read/write session separation, timeout handling, and hooks for impersonation and read routing (Enterprise features).
- **Extensibility**: Clear structure for adding new tools and capabilities.
- **Optional Long-Running Tool**: Example `pagerank.py` demonstrates streaming progress for long GDS tasks using `LongRunningFunctionTool`.

## Design Philosophy

### Why Split Read and Write Tools?

The separation of `read` and `write` tools, while seemingly adding complexity, is a deliberate design choice based on several principles:

1.  **Principle of Least Privilege**: Agents can be granted *only* the `read` tool if their purpose is exploration or query planning, preventing accidental or malicious mutations.
2.  **Safer Multi-Tenant Scaling (Neo4j Enterprise)**: Distinct read/write sessions make it trivial to route read traffic to follower replicas and write traffic to leader nodes, improving performance and resilience.
3.  **Predictable Agent Reasoning**: The agent (and the developer) doesn't need to guess if a query might implicitly perform a write; the tool's capability is explicit.

### Cypher Complexity is Not Limited

It's crucial to understand that this split **does not limit the complexity of the Cypher queries** you can execute. The underlying wrappers can handle complex queries involving `UNWIND`, sub-queries, `MERGE`, `CALL { GDS }`, etc. The only limitations are:
    - **Access Mode**: The `read` tool uses a read-only session, preventing mutations.
    - **Timeouts**: Configurable timeouts (defaults in `agent.py`) prevent runaway queries.

### Handling Mixed Read/Write Queries

Queries that both read and write (e.g., `MERGE...RETURN`, `MATCH...SET...RETURN`, GDS write-back) are valid Cypher. These **must** be executed using the `write` tool, as any mutation requires a write transaction. The `write` tool is designed to return both query results and summary statistics (like nodes created/deleted).

### Merging Tools (Optional)

If the safety guarantees of the split are not required for a specific use case, you can:
    - Grant a role only the `write` capability (as it handles reads too).
    - Create a custom facade tool that always calls the `wrapped_write_neo4j_cypher` function.

However, consider the trade-offs: increased security risk, loss of operational routing benefits, and potentially less clear observability. The RBAC mechanism provides the recommended way to manage these capabilities per agent role.

## Repository Structure

```text
neo4j_adk_project/
├─ requirements.txt               # Project dependencies
├─ .env.example                   # Environment variable template
├─ README.md                      # This file
└─ src/
   ├─ agent.py                    # DB bootstrap + core wrappers
   ├─ neo4j_tools.py              # Low-level Neo4j helpers
   ├─ neo4j_adk_tools.py          # ADK FunctionTool shims
   ├─ rbac.py                     # RBAC configuration and factory
   ├─ long_running/
   │   └─ pagerank.py             # Optional: Long-running tool demo
   ├─ app/
   │   ├─ __init__.py
   │   ├─ fastapi_lifespan.py     # Optional: FastAPI integration hooks
   │   └─ run_example.py          # Example script to run agents
   └─ tests/
       ├─ test_read_guard.py      # Tests for read-only enforcement
       ├─ test_write_ok.py        # Tests for successful writes
       └─ test_schema_fallback.py # Tests for schema fetching
```

## Quick Start

1.  **Clone/Copy**: Get the project files into your environment.
2.  **Navigate**: `cd /path/to/neo4j_adk_project`
3.  **Environment**:
    ```bash
    python -m venv .venv
    source .venv/bin/activate  # On Windows use `.venv\Scripts\activate`
    ```
4.  **Install Dependencies**:
    ```bash
    pip install -r requirements.txt
    # You'll likely need: neo4j google-cloud-aiplatform google-generativeai python-dotenv pytest pytest-asyncio
    ```
5.  **Configure Credentials**:
    ```bash
    cp .env.example .env
    # Edit .env with your Neo4j URI, User, Password, and Database
    # Also add GOOGLE_API_KEY if running the example with Gemini
    ```
6.  **Run Example**:
    ```bash
    python -m src.app.run_example
    # (Ensure you are in the neo4j_adk_project directory or adjust python path)
    ```
    This will:
    - Initialize the Neo4j driver (placeholder logic).
    - Create 'explorer' and 'builder' agents using the RBAC factory.
    - Run sample queries demonstrating read/write access control.
    - Shut down the driver.

## Known Unknowns / TODO Hooks

- **Cluster Routing Policy**: Implement logic if using read replicas (`route_read=True`).
- **Impersonation Mapping**: Enhance mapping from external auth (e.g., JWT) to Neo4j users.
- **Observability**: Integrate OpenTelemetry or other tracing within `neo4j_tools._log_query`.
- **Schema Cache**: Consider Redis or similar if schema introspection becomes slow.
- **Implementation Details**: Fill in TODOs in the code, especially actual Neo4j driver/LLM initialization and error handling in `agent.py` and `neo4j_tools.py`.