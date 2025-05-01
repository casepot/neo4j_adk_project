# Neo4j Gauntlet Fix & Upgrade Plan (v3)

This plan outlines the steps to resolve issues identified in the Neo4j Gauntlet testing framework, incorporating fixes from the gap analysis and necessary upgrades based on the upgrade playbook.

**Phase 1: Fix Environment & Core Tooling**

1.  **Update Docker Configuration (`docker-compose.yml`):**
    *   **Goal:** Ensure Neo4j Enterprise and the correct GDS plugin version are used to resolve GDS `ProcedureNotFound` errors.
    *   **Action:** Modify `docker-compose.yml`:
        *   Change `image: neo4j:5` to `image: neo4j:5.19-enterprise` (or the latest stable 5.x LTS enterprise tag).
        *   Change `NEO4JLABS_PLUGINS: '["apoc", "graph-data-science"]'` to `NEO4J_PLUGINS: '["apoc","gds"]'`.

2.  **Resolve Tool Naming Discrepancy (Strategy A in `src/app/run_gauntlet.py`):**
    *   **Goal:** Align Gauntlet's expected tool names with the actual tool names used by the agent to fix "tool not found" and "did not use expected tool" errors.
    *   **Action:** Modify `src/app/run_gauntlet.py`:
        *   Update the `expected_tools` list within each challenge definition (Lines ~352, 377, 397, 418, 439, 459, 479, 500, 522) to use the actual tool runner function names:
            *   `get_schema` -> `get_neo4j_schema_runner`
            *   `read_cypher` -> `read_neo4j_cypher`
            *   `write_cypher` -> `write_neo4j_cypher`
            *   `run_gds_procedure` -> `run_gds_cypher`
        *   Simplify the tool verification logic (around Lines ~625-677): Remove the `reverse_tool_map` creation and logic. Directly compare the `call.get("name")` from the agent's tool calls against the updated `expected_tools` list.

**Phase 2: Fix Gauntlet Data & Prompts**

3.  **Fix `:TeamLead` Cypher (`src/app/gauntlet_data.py`):**
    *   **Goal:** Correct the Cypher syntax causing "Variable already declared" errors in Neo4j 5.x fallback data for Challenge 8 prerequisites.
    *   **Action:** Modify lines ~326-328, 330-332, and 334-336 in `src/app/gauntlet_data.py` from `MERGE (e:TeamLead)` to `SET e:TeamLead`.

4.  **Update Agent Prompts/Instructions (`src/app/run_gauntlet.py`):**
    *   **Goal:** Ensure the agent uses correct GDS 2.x syntax and follows Cypher best practices based on examples.
    *   **Action:**
        *   Review and modify agent instructions in `src/app/run_gauntlet.py` (Lines ~165-225). Replace deprecated GDS 1.x procedure names (like `gds.community.louvain.*`) with their GDS 2.x equivalents (`gds.louvain.*`) and ensure correct `YIELD` clauses are shown in examples.
        *   Review task descriptions in `src/app/run_gauntlet.py` (e.g., Challenge 2, 5) and update any multi-statement Cypher examples to show single statements per tool call.

**Phase 3: Verification**

5.  **Re-run Gauntlet:**
    *   **Goal:** Confirm all fixes are effective.
    *   **Action:** Execute the Gauntlet test suite (e.g., via `run_gauntlet_cli.py`).
    *   **Check:**
        *   GDS procedures (Louvain, etc.) execute successfully.
        *   Challenge 8 prerequisite setup (TeamLead) passes.
        *   Tool usage verification passes for all relevant challenges.
        *   No cartesian product warnings related to fallback data.