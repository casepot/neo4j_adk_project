# Plan to Address LLM Halting Before Tool Call (Principle-Based) - v3

## Problem Summary

The LLM agent, when faced with multi-step tasks involving code generation (e.g., Cypher) and execution, sometimes fails to invoke the necessary tool call after generating the code, halting its execution prematurely. This was observed specifically in Challenge 5.

## Investigation Findings

Analysis of ADK documentation and code suggests the issue stems from LLM planning/execution consistency or interpretation of instructions, rather than ADK state management. The agent understands *what* code to generate but fails to follow through with the *action* of calling the tool to execute it before moving on.

## Proposed Solution Steps (Incorporating ADK Best Practices & Principles)

1.  **Define Expected Trajectory for Verification (Ref: `agent_evaluation.md`)**
    *   For testing purposes, formalize the expected sequence of actions and tool calls for a representative task like Challenge 5. This serves as the benchmark to verify if the agent correctly applies the general principles.
    *   *Optional but Recommended:* Use ADK's evaluation framework (`.test.json`, `.evalset.json`) to define this expected trajectory, focusing on `expected_tool_use`.

2.  **Refine Agent Prompt (`src/app/run_gauntlet.py` - relevant roles) with General Principles (Ref: `full_tutorial.md`)**
    *   **Goal:** Instill general best practices for task execution involving code generation and tool use, applicable to *any* similar task, not just Challenge 5.
    *   **Principle 1: Plan-then-Execute:** Instruct the agent: "Always formulate a clear plan outlining the steps you will take before starting execution."
    *   **Principle 2: Tool Call Immediacy:** Add a core instruction like: "**Crucial Execution Rule:** When your plan involves generating code (like Cypher) or data that requires execution or persistence, you MUST call the appropriate tool (e.g., `write_cypher`, `read_cypher`, `run_gds_procedure`) as the *very next action*. Complete the execution of the current step's code before planning or performing the next logical step in your task."
    *   **Principle 3: State Awareness:** Instruct the agent: "Assume data and state resulting from previously successful operations (tool calls, setup steps) are present. Do not redundantly verify or recreate data unless the task explicitly requires it."
    *   **Principle 4: Plan Completion:** Instruct the agent: "Ensure you execute all steps outlined in your plan for the current user request, including all necessary tool calls, before concluding your response."
    *   *(Minor Check)* Briefly review relevant tool docstrings (`write_cypher`, etc. in `neo4j_adk_tools.py`) for clarity, ensuring they don't contradict these principles.

3.  **Testing and Verification (Ref: `testing.md`, `agent_evaluation.md`)**
    *   Execute the Gauntlet (or specific challenging tasks like C5) using the standard runner (`run_gauntlet.py` / `run_gauntlet_cli.py`).
    *   **Verify Trajectory against Principles:** Analyze the execution logs/events. Does the agent consistently call the appropriate tool immediately after generating code for that step? Compare the actual trajectory for the test case (e.g., C5) against the expected trajectory defined in Step 1.
    *   *(If using eval framework)* Measure improvement using `tool_trajectory_avg_score`.
    *   *Debugging:* Use `adk api_server` / `curl` or observability tools if needed to inspect the event stream or agent state during execution.

4.  **Contingency (If Principles are Not Followed Consistently)**
    *   **Model Exploration:** Test different LLM versions/parameters. Some models might adhere to principles better than others.
    *   **Prompt Iteration:** Further refine the wording of the principles in the prompt.
    *   **ADK Runner Logging/Observability:** Investigate deeper ADK logging or utilize Callbacks/observability tools for more detailed tracing.

## Goal

Improve the agent's general reliability for tasks involving code generation and tool execution by embedding core operational principles into its instructions, ensuring it consistently calls necessary tools immediately after generating the relevant code/data. Verify this improved reliability using specific test cases like Challenge 5.