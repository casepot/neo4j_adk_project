# src/app/run_example.py
"""
Example script demonstrating how to create and run ADK agents
with different roles using the RBAC factory and Neo4j tools.
"""

import asyncio
import os
from dotenv import load_dotenv
from typing import List, Dict, Any

# --- Attempt to import ADK and GenAI components ---
try:
    from google.adk.agents import Agent
    from google.adk.runners import Runner
    from google.adk.sessions import InMemorySessionService
    from google.genai import types as genai_types # ✔ new import path
    from google import genai # ✔ Correct import for the new SDK
    ADK_AVAILABLE = True
except ImportError as e: # Capture the exception object
    print(f"Warning: Failed to import ADK or GenAI components: {e}") # Print the specific error
    print("Please ensure google-cloud-aiplatform and google-genai are installed in the correct environment.")
    # Define dummy classes/types for static analysis if ADK is not available
    Agent = type("Agent", (object,), {})
    Runner = type("Runner", (object,), {})
    InMemorySessionService = type("InMemorySessionService", (object,), {})
    genai_types = type("types", (object,), {"Content": dict, "Part": dict}) # type: ignore
    # Define a dummy genai object with a dummy GenerativeModel attribute
    _dummy_genai_module = type("genai", (object,), {})
    _dummy_genai_module.GenerativeModel = type("GenerativeModel", (object,), {}) # type: ignore
    genai = _dummy_genai_module # Assign dummy module to genai
    ADK_AVAILABLE = False

# --- Import project components ---
try:
    from ..rbac import build_agent_tools, Role
    from ..agent import initialize_neo4j_driver, shutdown_neo4j_driver
except ImportError:
    # Fallback for direct execution or different structure
    print("Warning: Running run_example.py directly or project structure issue.")
    from src.rbac import build_agent_tools, Role # type: ignore # Use absolute path
    from src.agent import initialize_neo4j_driver, shutdown_neo4j_driver # type: ignore # Use absolute path

# --- Configuration ---
load_dotenv() # Load environment variables from .env file

# Placeholder for LLM - replace with actual model initialization
# Example using Gemini (requires API key configured)
# from google import genai # Import already handled above
# GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
# if not GOOGLE_API_KEY:
#     print("Warning: GOOGLE_API_KEY environment variable not set.")
#     # Provide a dummy model if key is missing and ADK is available
#     llm_model = None if not ADK_AVAILABLE else "gemini-dummy" # Or handle error
# else:
#     genai.configure(api_key=GOOGLE_API_KEY)
#     llm_model = genai.GenerativeModel('gemini-1.5-flash-latest') # ✔ Use genai.GenerativeModel

llm_model_name = "gemini-2.0-flash" # Placeholder name

# ADK Session configuration
session_service = InMemorySessionService() if ADK_AVAILABLE else None
APP_NAME = "neo4j_adk_demo_app"
USER_ID = "test_user_01"
SESSION_ID = "test_session_01"


# --- Agent Creation Function ---
def create_agent(role: Role, model: Any) -> Agent:
    """Creates an ADK Agent with tools based on the specified role."""
    if not ADK_AVAILABLE:
        print(f"ADK not available, returning dummy agent for role: {role}")
        return Agent() # Return dummy agent

    print(f"Building tools for role: {role}")
    agent_tools = build_agent_tools(role) # Add impersonation/routing here if needed
    print(f"Tools built for {role}: {[t.func.__name__ for t in agent_tools if hasattr(t, 'func')]}")

    # Define agent instructions based on role
    instructions = {
        "explorer": "You are a helpful assistant that can query Neo4j database schema and read data. You cannot make any changes.",
        "auditor": "You are an analytical assistant. You can query Neo4j schema, read data, and run GDS analytics procedures. You cannot make direct changes to the graph structure.",
        "builder": "You are a powerful assistant capable of reading and writing to the Neo4j database, including running GDS procedures. Use your capabilities responsibly.",
        "admin": "You are an administrative assistant with full access to read, write, and analyze the Neo4j database.",
    }

    agent = Agent(
        model=model, # Pass the actual initialized model object here
        name=f"neo4j_{role}_agent",
        instruction=instructions.get(role, "Interact with the Neo4j database."),
        tools=agent_tools,
    )
    print(f"Agent created for role: {role}")
    return agent

# --- Helper to Run Query ---
async def run_query(runner: Runner, query: str, user_id: str, session_id: str):
    """Sends a query to the agent via the runner and prints the final response."""
    if not ADK_AVAILABLE or not runner:
        print(f"ADK Runner not available. Skipping query: {query}")
        return

    print(f"\n--- Running Query via Agent: '{query}' ---")
    content = genai_types.Content(role="user", parts=[genai_types.Part(text=query)]) # Revert to constructor for compatibility
    final_response = ""
    try:
        # ADK Runner returns an async generator
        # Use run_async for async iteration
        async for event in runner.run_async(user_id=user_id, session_id=session_id, new_message=content):
            # Check for different event types based on content
            tool_calls = event.get_function_calls()
            tool_responses = event.get_function_responses()

            if tool_calls:
                 # Handle tool call requests
                 for call in tool_calls:
                     print(f"Tool call requested: {call.name}({call.args})")
            elif tool_responses:
                 # Handle tool responses
                 for response in tool_responses:
                     # Ensure response content is serializable for printing
                     response_content_str = str(response.response) # Basic string conversion
                     print(f"Tool response received: {response.name} -> {response_content_str[:200]}...") # Limit print length
            elif event.content and event.content.parts and event.content.parts[0].text:
                 # Handle text responses (intermediate or final)
                 print(f"LLM thought/response chunk: {event.content.parts[0].text}")

            # Check specifically for the final response to the user for this turn
            if event.is_final_response():
                if event.content and event.content.parts and event.content.parts[0].text:
                    final_response = event.content.parts[0].text
                    print(f"Final Agent Response: {final_response}")
                # Optionally handle other final response types (e.g., raw tool results if skip_summarization=True)
                # elif tool_responses and event.actions and event.actions.skip_summarization:
                #     final_response = str(tool_responses[0].response) # Example: Use raw tool response
                #     print(f"Final Agent Response (Raw Tool): {final_response}")
                break # Exit after getting the final response
    except Exception as e:
        print(f"Error running query '{query}': {e}")
        import traceback
        traceback.print_exc() # Print full traceback for debugging

    if not final_response:
        print("No final response received from the agent.")
    print("--- Query Execution Finished ---")
    return final_response


# --- Main Execution Block ---
async def main():
    """Initializes driver, creates agents, runs tests, and shuts down."""
    print("--- Starting ADK Neo4j Example ---")
    await initialize_neo4j_driver()

    if not ADK_AVAILABLE:
        print("ADK components not loaded. Cannot run agent examples.")
        await shutdown_neo4j_driver()
        return

    # Initialize the actual LLM model here if needed
    # llm = genai.GenerativeModel(llm_model_name) # ✔ Correct usage: genai.GenerativeModel
    llm = llm_model_name # Using placeholder name for now

    # Create Agents
    print("\n--- Creating Agents ---")
    try:
        explorer_agent = create_agent("explorer", llm)
        # auditor_agent = create_agent("auditor", llm) # Uncomment if needed
        builder_agent = create_agent("builder", llm)
    except ValueError as e:
        print(f"Error creating agents: {e}")
        await shutdown_neo4j_driver()
        return
    print("--- Agents Created ---")


    # --- Run Test Queries ---
    # Use the builder agent's runner for these examples
    builder_runner = Runner(agent=builder_agent, app_name=APP_NAME, session_service=session_service)
    explorer_runner = Runner(agent=explorer_agent, app_name=APP_NAME, session_service=session_service) # Separate runner for explorer

    # 1. Explorer: Try to get schema (should succeed)
    print(f"\nCreating session: {SESSION_ID + '_exp'}")
    session_service.create_session(app_name=APP_NAME, user_id=USER_ID, session_id=SESSION_ID + "_exp")
    await run_query(explorer_runner, "What is the database schema?", USER_ID, SESSION_ID + "_exp")

    # 2. Explorer: Try to create data (should fail due to RBAC/wrapper guard)
    #    The LLM should ideally explain *why* it failed based on the tool error.
    #    Session already created above.
    await run_query(explorer_runner, "Create a node (:Test {name:'ExplorerTest'})", USER_ID, SESSION_ID + "_exp")

    # 3. Builder: Try to create data (should succeed)
    print(f"\nCreating session: {SESSION_ID + '_bld'}")
    session_service.create_session(app_name=APP_NAME, user_id=USER_ID, session_id=SESSION_ID + "_bld")
    await run_query(builder_runner, "Create a node (:Test {name:'BuilderTest'}) and return its name.", USER_ID, SESSION_ID + "_bld")

    # 4. Builder: Read the data back (should succeed)
    #    Session already created above.
    await run_query(builder_runner, "Find the node with label Test and name 'BuilderTest' and return its name.", USER_ID, SESSION_ID + "_bld")

    # 5. Builder: Clean up the test node (should succeed)
    await run_query(builder_runner, "Match (n:Test {name:'BuilderTest'}) delete n", USER_ID, SESSION_ID + "_bld")


    print("\n--- Example Queries Finished ---")

    await shutdown_neo4j_driver()
    print("--- ADK Neo4j Example Finished ---")


if __name__ == "__main__":
    # Ensure asyncio event loop runs the main function
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nExecution interrupted by user.")
    finally:
        # Ensure driver shutdown is attempted even on error/interrupt
        # Note: If main() completed, shutdown already happened.
        # This is a fallback. A more robust solution might involve
        # signal handling or ensuring shutdown within main's finally block.
        print("Ensuring Neo4j driver is shut down (final check)...")
        # asyncio.run(shutdown_neo4j_driver()) # Running async shutdown again might need care
        print("Final shutdown check complete.")