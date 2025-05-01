# Neo4j Gauntlet - Implementation Plan for Fixes

**Document Purpose:** This document provides a detailed technical specification for fixing issues identified during the Neo4j Gauntlet LLM agent test. It is intended for a coding agent to implement directly. All necessary context, code changes, rationale, and verification steps are included.

**Target Files:**
*   `src/neo4j_tools.py`
*   `src/wrappers.py`
*   `src/neo4j_adk_tools.py`
*   `src/app/run_gauntlet.py`

**Assumptions:** The implementing agent understands Python, asynchronous programming (`asyncio`), basic Neo4j Cypher, and the structure of the project files listed above.

---

## Phase 1: Tool & Environment Fixes (Highest Priority)

### 1. Fix Silent Write Failures (Failure #2)

*   **Goal:** Ensure `write_cypher` operations either succeed and report accurate summaries, or fail explicitly, preventing the agent from proceeding on false assumptions.
*   **File:** `src/neo4j_tools.py`
*   **Function:** `_execute_cypher_session`

*   **Implementation Details:**
    *   **Add Detailed Logging:**
        *   Inside the `try` block, *before* `result = await asyncio.wait_for(...)`:
            ```python
            logger.debug(f"Attempting to execute query in session: {query} with params: {params}")
            ```
        *   Inside the `try` block, *after* `summary = await result.consume()`:
            ```python
            # Log the raw summary object for detailed inspection
            raw_summary_details = repr(summary) if summary else "None"
            logger.debug(f"Query execution consumed. Raw Summary: {raw_summary_details}")
            # Log the extracted counters dictionary
            logger.debug(f"Extracted summary counters: {summary_dict}")
            ```
        *   Ensure the logger level is configured appropriately (e.g., `DEBUG`) during testing to capture these messages. Check `logging.basicConfig` at the top of `neo4j_tools.py`.
    *   **Implement Write Verification (Optional but Recommended):**
        *   **Location:** Modify the `run_cypher` function in `src/neo4j_tools.py`.
        *   **Logic:** After the successful execution block for `access_mode == "WRITE"` (around line 254), *before* returning the success dictionary:
            ```python
            # --- BEGIN ADDED VERIFICATION BLOCK ---
            if access_mode == "WRITE" and not summary: # Check if summary is empty or has no counters
                 logger.warning(f"Write query succeeded but returned empty summary/counters: {query}")
                 # NOTE: Implementing a generic verification query is complex.
                 # For this specific gauntlet, we know the problematic queries involve creating
                 # relationships like WORKS_ON, HAS_SKILL. A simple verification might be:
                 # verification_query = "MATCH ()-[r]->() RETURN count(r) AS rel_count" # Example: Check total rel count change (brittle)
                 # Or, derive from the original query if possible.
                 # Given the complexity, we will rely on enhanced agent prompting (Phase 2)
                 # and improved logging for now. If silent writes persist, revisit this.
                 # Consider adding a flag to enable/disable this check.
                 pass # Placeholder - Verification logic deferred
            # --- END ADDED VERIFICATION BLOCK ---
            ```
    *   **Enhance Error Handling:**
        *   Review the `except` blocks in `_execute_cypher_session` (lines 98-113). Ensure they comprehensively catch errors that might occur during `result.consume()`. The current `except Exception as e:` should cover most cases, but be mindful of potential specific exceptions related to transaction commit phases if documented by the Neo4j driver.
        *   **Action:** No immediate code change required here unless driver documentation suggests specific commit-phase exceptions to catch separately. **Consult Neo4j Python Driver documentation** regarding exceptions raised during `Result.consume()` or implicit transaction commits.

*   **Design Rationale:** Logging helps diagnose the root cause (driver bug vs. query logic). Explicit verification (if implemented) provides a safety net. Relying on agent prompting is a less invasive initial fix.
*   **Guidance:** Focus on adding the detailed logging first. Test thoroughly with the specific queries that failed (`WORKS_ON`, `HAS_SKILL` creation from Challenge 5) to see if the logs reveal why the summary counters are empty.

### 2. Fix GDS Schema Fetch Error (Failure #5)

*   **Goal:** Make schema fetching more robust by using a more reliable APOC call.
*   **File:** `src/neo4j_tools.py`
*   **Function:** `get_schema`

*   **Implementation Details:**
    *   **Modify APOC Query:**
        *   Replace the line `apoc_query = "CALL apoc.meta.data() YIELD label, property, type, rel, other RETURN *"` (line 141) with:
            ```python
            # Recommended: Use apoc.meta.schema()
            apoc_query = "CALL apoc.meta.schema() YIELD value RETURN value"
            ```
    *   **Update APOC Result Parsing:**
        *   Replace the parsing logic (lines 143-156) with logic appropriate for `apoc.meta.schema()`'s output. The output is a nested map representing the schema.
            ```python
            # --- BEGIN REPLACEMENT for lines 143-156 ---
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

                # Extract Relationship Types and Properties (Simplified)
                # Note: apoc.meta.schema() structure for relationships is complex, showing connections.
                # This is a simplified representation focusing on type and properties.
                rel_types_seen = set()
                for label, data in schema_map.items():
                     if data.get('type') == 'node':
                         for rel_info in data.get('relationships', {}).values():
                             rel_type = rel_info.get('type')
                             if rel_type and rel_type not in rel_types_seen:
                                 rel_types_seen.add(rel_type)
                                 properties = ', '.join([f"{prop}: {details.get('type', 'UNKNOWN')}" for prop, details in rel_info.get('properties', {}).items()])
                                 schema_parts.append(f"Relationship: -[:{rel_type} {{{properties}}}]->")

                if schema_parts:
                    schema_info = "\n".join(sorted(list(set(schema_parts)))) # Use set for uniqueness
                    status = "success"
                    logger.info("Schema fetched successfully using apoc.meta.schema().")
                else:
                    logger.warning("apoc.meta.schema() call succeeded but returned no schema data.")
                    # Proceed to fallback
            else:
                 logger.warning("apoc.meta.schema() call did not return the expected dictionary structure.")
                 # Proceed to fallback
            # --- END REPLACEMENT ---
            ```
    *   **Update APOC Error Handling:**
        *   Modify the `except ClientError` block (lines 162-170) to check for errors related to `apoc.meta.schema` if necessary (though `NoSuchProcedureException` should still be relevant).
            ```python
            # Modify line 163 condition if needed:
            if "Unknown function 'apoc.meta.schema'" in str(e) or "NoSuchProcedureException" in str(e):
                 logger.warning("APOC not found or `apoc.meta.schema` procedure unavailable. Falling back to SHOW commands.")
                 # Proceed to fallback
            # ... rest of the block
            ```
    *   **Retain Fallback:** Ensure the fallback logic using `SHOW` commands (lines 181-207) remains unchanged.

*   **Design Rationale:** `apoc.meta.schema()` is generally preferred for schema inspection over `apoc.meta.data()`. Retaining the `SHOW` command fallback ensures functionality if APOC is not installed or the procedure is unavailable.
*   **Guidance:** Test this change against a Neo4j instance with APOC installed. Verify the parsed output format. Also test against an instance *without* APOC to ensure the fallback still works correctly. **Consult APOC Documentation** for the exact output structure of `apoc.meta.schema()` for the target version.

### 3. Fix GDS Procedure YIELD Errors (Failure #6)

*   **Goal:** Prevent GDS calls from failing due to incorrect `YIELD` clauses, either by providing better guidance or making the tool more resilient.
*   **Files:** `src/neo4j_tools.py`, `src/wrappers.py` (or `src/neo4j_adk_tools.py`)

*   **Implementation Details:**
    *   **Implement YIELD Error Retry (Recommended):**
        *   **File:** `src/neo4j_tools.py`
        *   **Function:** `_execute_cypher_session`
        *   **Logic:** Modify the `except ClientError as e:` block (around line 102).
            ```python
            # --- BEGIN MODIFICATION for except ClientError ---
            except ClientError as e:
                logger.error(f"Neo4j ClientError: {e.message} (Code: {e.code}) for query: {query}")
                # Specific handling for read/write errors in wrong mode might be useful
                if "Write operations are not allowed" in e.message:
                    raise PermissionError(f"Write operation attempted in read-only session: {query}") from e

                # --- ADDED: Handle GDS YIELD errors ---
                # Check for common YIELD error messages (adjust patterns as needed)
                yield_error_patterns = ["Unknown procedure output", "Unknown field", "Unable to resolve"]
                is_yield_error = any(pattern in str(e.message) for pattern in yield_error_patterns) and " YIELD " in query.upper()

                if is_yield_error:
                    logger.warning(f"Potential GDS YIELD error detected for query: {query}. Attempting retry without YIELD clause.")
                    # Construct query without YIELD
                    yield_clause_index = query.upper().find(" YIELD ")
                    if yield_clause_index != -1:
                        query_without_yield = query[:yield_clause_index]
                        logger.info(f"Retrying GDS query without YIELD: {query_without_yield}")
                        try:
                            # Retry execution (call recursively or duplicate logic carefully)
                            # IMPORTANT: Avoid infinite recursion. Only retry once.
                            # Re-executing the core logic here, simplified:
                            result_retry: Result = await asyncio.wait_for(
                                session.run(query_without_yield, params),
                                timeout=timeout_ms / 1000.0
                            )
                            results_list_retry = [record.data() async for record in result_retry] # Likely empty
                            summary_retry = await result_retry.consume()
                            summary_dict_retry = summary_retry.counters.__dict__ if summary_retry and summary_retry.counters else {}
                            logger.info(f"GDS retry without YIELD succeeded. Summary: {summary_dict_retry}")
                            # Return the summary from the retry, results likely empty
                            return results_list_retry, summary_dict_retry
                        except Exception as retry_e:
                            logger.error(f"GDS retry without YIELD failed: {retry_e}")
                            # Fall through to re-raise the original error
                    else:
                         logger.error("Could not strip YIELD clause for retry.")
                # --- END ADDED ---

                raise # Re-raise original client error if not handled or retry failed
            # --- END MODIFICATION ---
            ```
    *   **Update Tool Documentation:**
        *   **File:** `src/wrappers.py` (docstring for `wrapped_run_gds_cypher`) OR `src/neo4j_adk_tools.py` (if using ADK descriptions).
        *   **Action:** Add examples of correct `YIELD` clauses.
        *   **Text:**
            ```text
            [...]
            Note: GDS procedure YIELD clauses are version-specific. If you encounter 'Unknown procedure output' errors, try removing the YIELD clause or consult the documentation for the specific GDS version in use.
            Common Examples (CHECK YOUR GDS VERSION):
            - For `gds.louvain.stats`: `YIELD communityCount, modularity`
            - For `gds.louvain.write`: `YIELD nodePropertiesWritten, communityCount`
            - For `gds.nodeSimilarity.stream`: `YIELD node1, node2, similarity`
            - For `gds.nodeSimilarity.write`: `YIELD nodesCompared, relationshipsWritten`
            [...]
            ```
        *   **Guidance:** **Crucially, replace the example YIELD clauses above with the *actual correct clauses* for the specific Neo4j and GDS versions used in the test environment.** This requires checking the environment's GDS documentation.

*   **Design Rationale:** Retrying without YIELD allows procedures like `.write` modes to complete their primary function (modifying the graph) even if the agent can't stream detailed results. Documentation provides essential guidance to the agent.
*   **Guidance:** The retry logic adds complexity; test it carefully. The most critical part is updating the documentation with *accurate* YIELD examples for the target environment. **Consult GDS Documentation** for the specific version being used.

### 4. Clarify Multi-Statement Limitation (Failure #1)

*   **Goal:** Explicitly inform the agent that tools expect single Cypher statements.
*   **File:** `src/wrappers.py`
*   **Function:** Docstring for `wrapped_write_neo4j_cypher` (and potentially `wrapped_read_neo4j_cypher`, `wrapped_run_gds_cypher`).

*   **Implementation Details:**
    *   **Update Docstring:** Add a clear note near the top of the docstring.
    *   **Text:**
        ```python
        """
        Executes a **single** Cypher query that may mutate the graph, using a WRITE session.
        **IMPORTANT:** Only one Cypher statement is allowed per call. Multi-statement queries
        separated by semicolons (;) are not supported and will cause errors.
        Returns both query results and summary statistics (counters).
        [...]
        """
        ```
    *   Apply a similar note to other Cypher-executing wrappers (`wrapped_read_neo4j_cypher`, `wrapped_run_gds_cypher`) for consistency.

*   **Design Rationale:** Prevents the agent from attempting unsupported operations based on incorrect assumptions.
*   **Guidance:** Simple text change. Ensure it's prominent in the docstring.

---

## Phase 2: Agent Prompting & Logic Fixes

*   **Goal:** Improve the agent's internal reasoning and error handling based on tool outputs.
*   **File:** `src/app/run_gauntlet.py`
*   **Location:** Inside the `create_agent` function, within the `instructions` dictionary for relevant roles.

### 5. Improve Agent Write Verification Logic (Failure #3)

*   **Roles:** `builder`, `admin`
*   **Implementation Details:**
    *   **Add Instruction Text:** Append the following to the existing instructions for the specified roles:
        ```text

        **CRITICAL WRITE VERIFICATION:** After executing a write query (e.g., using `write_cypher`), always inspect the `summary` field in the tool's response. If the `status` is 'success' but the `summary` is empty or shows zero nodes/relationships created/modified when you expected changes, **treat this as a potential silent failure.** Do not assume the write was successful. You MUST attempt to verify the write by using `read_cypher` to query the data you intended to create/modify *before* proceeding with subsequent steps that depend on that data. If verification fails, report the discrepancy.
        ```

*   **Design Rationale:** Forces the agent to be more critical of "successful" write operations that don't report expected changes in the summary.
*   **Guidance:** Ensure this text is added clearly and prominently within the prompt.

### 6. Improve Agent Debugging Strategy (Failure #4)

*   **Roles:** `explorer`, `builder`, `auditor`, `admin` (Add to all)
*   **Implementation Details:**
    *   **Add Instruction Text:** Append the following to the existing instructions for all roles:
        ```text

        **DEBUGGING FAILED QUERIES:** If a query fails or returns unexpected empty results using `read_cypher` or `run_gds_procedure`, retry it **at most once**. If it fails again, **DO NOT** retry the exact same query repeatedly. Instead, formulate simpler diagnostic queries to isolate the problem. For example, if a query matching `(a)-[r]->(b)` fails, first try querying `MATCH (a) RETURN count(a)`, then `MATCH (b) RETURN count(b)`, then `MATCH ()-[r]->() RETURN count(r)` to see which element might be missing or incorrect. Break down the problem.
        ```

*   **Design Rationale:** Prevents wasted cycles and encourages a more systematic debugging approach.
*   **Guidance:** Add consistently across all relevant role prompts.

### 7. Ensure Agent Knows Schema Fallback (Failure #5 Recovery)

*   **Roles:** `explorer`, `auditor`, `admin`
*   **Implementation Details:**
    *   **Add Instruction Text:** Append the following to the existing instructions for the specified roles:
        ```text

        **SCHEMA TOOL FALLBACK:** If the primary schema tool (`get_schema`) fails or returns an error (e.g., related to APOC procedures), you can attempt to retrieve basic schema information as a fallback. Use the `read_cypher` tool to run separate queries like `SHOW NODE LABELS`, `SHOW RELATIONSHIP TYPES`, and `SHOW PROPERTY KEYS`. Report the results from these commands.
        ```

*   **Design Rationale:** Provides the agent with a documented workaround if the primary tool fails.
*   **Guidance:** Ensure this complements the existing instructions for schema exploration.

---

## Phase 3: Test Harness Fixes

### 8. Fix Tool Name Verification (Failure #8)

*   **Goal:** Correctly evaluate whether the agent used the expected *type* of tool, even if the reported name differs.
*   **File:** `src/app/run_gauntlet.py`
*   **Function:** `run_challenge` (within the evaluation logic, lines 549-567)

*   **Implementation Details:**
    *   **Create Reverse Tool Map:** Before the loop checking `expected_tools`, create a mapping from the actual function/tool names reported by ADK back to the generic names used in `expected_tools`.
        ```python
        # --- BEGIN ADDITION before line 553 ---
        # Import the tools dictionary if not already available in scope
        from src.neo4j_adk_tools import ALL_ADK_TOOLS # Adjust import path if needed

        # Create a reverse map: {reported_name: generic_name}
        # This assumes call.name matches the FunctionTool's func.__name__ or similar identifier
        # We need to determine what ADK actually puts in call.name. Let's assume it's related to the FunctionTool object or its wrapped function.
        # Example assuming call.name is like 'wrapped_write_neo4j_cypher':
        reverse_tool_map = {}
        for generic_name, tool_obj in ALL_ADK_TOOLS.items():
             if hasattr(tool_obj, 'func') and hasattr(tool_obj.func, '__name__'):
                 reported_name = tool_obj.func.__name__ # Or the actual key ADK uses
                 reverse_tool_map[reported_name] = generic_name
             # Add handling for other tool types if necessary

        logger.debug(f"Reverse tool map created: {reverse_tool_map}") # Use logger

        actual_tool_calls = result.get("tool_calls", [])
        # Map reported names to generic names
        actual_generic_tool_names = set()
        for call in actual_tool_calls:
            reported_name = call.get("name")
            generic_name = reverse_tool_map.get(reported_name)
            if generic_name:
                actual_generic_tool_names.add(generic_name)
            else:
                logger.warning(f"Could not map reported tool name '{reported_name}' to a generic name.")
                actual_generic_tool_names.add(reported_name) # Keep original if no mapping found

        logger.debug(f"Actual generic tool names used: {actual_generic_tool_names}")
        # --- END ADDITION ---

        # --- BEGIN MODIFICATION for lines 553-564 ---
        used_expected_tool = False
        if expected_tools:
            for tool_name in expected_tools:
                # Compare against the mapped generic names
                if tool_name in actual_generic_tool_names:
                    used_expected_tool = True
                    evaluation_feedback.append(f"✅ Used expected tool type: {tool_name} (Reported as: {[n for n, g in reverse_tool_map.items() if g == tool_name]})")
                    break # Only need one match
            if not used_expected_tool:
                evaluation_feedback.append(f"❌ Did not use any expected tool types: {expected_tools}. Used types: {actual_generic_tool_names or 'None'}")
                score = max(0, score - 2) # Penalize for not using expected tools
            else:
                score = min(10, score + 3) # Bonus for using expected tools
        # --- END MODIFICATION ---
        ```
    *   **Determine Actual `call.name`:** The critical part is finding out what identifier the ADK `event.get_function_calls()` actually provides in `call.name`. It might be the `FunctionTool` object's name, the wrapped function's `__name__`, or something else. **Inspect the `logs` output** from a test run (specifically the `tool_call` entries) or **consult Google ADK documentation** on `Runner.run_async` events and `FunctionCall` objects to confirm the exact identifier being reported. Adjust the `reverse_tool_map` creation accordingly.

*   **Design Rationale:** Compares the *intended capability* (generic name) rather than the specific implementation detail (reported name), making the test harness evaluation more robust to internal naming conventions.
*   **Guidance:** The accuracy of the `reverse_tool_map` is key. Verify the reported `call.name` from ADK logs before finalizing the mapping logic.

---

## Phase 4: Cascading Failure Resolution

### 9. Address Data Transformation Failure (Failure #7)

*   **Goal:** Ensure Challenge 8 can run successfully once its prerequisite data from Challenge 7 is available.
*   **File:** N/A (Verification Step)

*   **Implementation Details:**
    *   No direct code changes are required for Failure #7 itself.
    *   **Verification:** After implementing and testing the fixes for Failure #6 (GDS YIELD Errors), run the full gauntlet, paying close attention to Challenges 7 and 8.
    *   **Check:**
        *   Does Challenge 7 now complete successfully, producing the expected analytics results (e.g., community IDs written to nodes, similarity scores/relationships created)?
        *   Does Challenge 8 subsequently run without complaining about missing input data?
        *   Does the final verification for Challenge 8 (`verify_database_state(8)`) pass?

*   **Design Rationale:** This failure is a direct consequence of the GDS errors. Fixing the root cause (Failure #6) should resolve this cascading issue.
*   **Guidance:** Focus on verifying the successful execution and state changes in Challenges 7 and 8 post-fix.

---

**Final Checklist & Considerations:**

*   [ ] **Logging Levels:** Ensure appropriate logging levels (`DEBUG`, `INFO`, `WARNING`) are used and configured correctly for diagnosis.
*   [ ] **Neo4j/GDS Versions:** Confirm the target Neo4j and GDS versions for the test environment. Update documentation (especially GDS YIELD examples) accordingly. **Consult relevant Neo4j/GDS documentation.**
*   [ ] **ADK Version/Behavior:** Confirm the ADK version and how tool names are reported in events. **Consult Google ADK documentation.**
*   [ ] **Testing:** Test each fix individually where possible. Run the full gauntlet (Challenges 5-8 at minimum) to verify end-to-end correctness.
*   [ ] **Code Style/Linting:** Ensure all code changes adhere to project formatting and linting standards.
*   [ ] **Configuration:** Check if any environment variables (`.env`) or `docker-compose.yml` settings affect Neo4j/GDS versions or APOC availability.

