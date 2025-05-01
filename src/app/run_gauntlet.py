#!/usr/bin/env python3
# src/app/run_gauntlet.py
"""
Neo4j Gauntlet - A progressive series of database challenges for testing agent capabilities.

This module implements a sequence of interconnected Neo4j graph database tasks that build
upon each other to test various capabilities of ADK agents with Neo4j tools, including:
- Schema exploration
- Graph creation and data modeling
- Query capabilities
- Path navigation
- Graph analytics
- Data transformation

Each challenge feeds into the next, creating a comprehensive evaluation of both
the tools and the agents using them.
"""

import asyncio
import json
import os
import time
from datetime import datetime
from typing import Dict, List, Any, Optional, Tuple, Callable, Awaitable

# --- Import ADK components ---
try:
    from google.adk.agents import Agent
    from google.adk.runners import Runner
    from google.adk.sessions import InMemorySessionService
    from google.genai import types as genai_types
    from google import genai
    ADK_AVAILABLE = True
except ImportError as e:
    print(f"Warning: Failed to import ADK or GenAI components: {e}")
    print("Please ensure google-cloud-aiplatform and google-genai are installed in the correct environment.")
    # Define dummy classes/types for static analysis if ADK is not available
    Agent = type("Agent", (object,), {})
    Runner = type("Runner", (object,), {})
    InMemorySessionService = type("InMemorySessionService", (object,), {})
    genai_types = type("types", (object,), {"Content": dict, "Part": dict})
    # Define a dummy genai object with a dummy GenerativeModel attribute
    _dummy_genai_module = type("genai", (object,), {})
    _dummy_genai_module.GenerativeModel = type("GenerativeModel", (object,), {})
    genai = _dummy_genai_module
    ADK_AVAILABLE = False

# --- Import project components ---
try:
    from ..rbac import build_agent_tools, Role
    from ..agent import initialize_neo4j_driver, shutdown_neo4j_driver, get_driver
    from ..wrappers import wrapped_read_neo4j_cypher, wrapped_write_neo4j_cypher
except ImportError:
    # Fallback for direct execution or different structure
    print("Warning: Running run_gauntlet.py directly or project structure issue.")
    from src.rbac import build_agent_tools, Role
    from src.agent import initialize_neo4j_driver, shutdown_neo4j_driver, get_driver
    from src.wrappers import wrapped_read_neo4j_cypher, wrapped_write_neo4j_cypher

# Import the gauntlet_data instance for challenge-specific data setup and verification
try:
    # Import the instance named 'gauntlet_data' from the module
    from .gauntlet_data import gauntlet_data
except ImportError:
    try:
        # Fallback import
        from src.app.gauntlet_data import gauntlet_data
    except ImportError:
        print("Warning: gauntlet_data module/instance not found. Creating stub.")
        class GauntletDataStub: # Renamed to avoid potential confusion
            async def reset_database(self, direct_cypher):
                return {"status": "error", "data": "gauntlet_data module not found"}
            
            async def ensure_challenge_prerequisites(self, challenge_id, direct_cypher):
                return False
                
            async def verify_challenge(self, challenge_id, direct_cypher):
                return False, ["gauntlet_data module not found"]
        
        gauntlet_data = GauntletDataStub() # Instantiate the stub

# --- Configuration ---
# Create results directory if it doesn't exist
RESULTS_DIR = "gauntlet_results"
os.makedirs(RESULTS_DIR, exist_ok=True)

# ADK Session configuration
session_service = InMemorySessionService() if ADK_AVAILABLE else None
APP_NAME = "neo4j_adk_gauntlet"
USER_ID = "gauntlet_user"

# --- Direct Cypher Access ---
async def direct_cypher(query: str, params: Optional[Dict[str, Any]] = None, 
                        write_mode: bool = False) -> Dict[str, Any]:
    """Execute a Cypher query directly, bypassing the agent tools."""
    if write_mode:
        return await wrapped_write_neo4j_cypher(query=query, params=params)
    else:
        return await wrapped_read_neo4j_cypher(query=query, params=params)

# --- Database Reset ---
async def reset_database() -> Dict[str, Any]:
    """Reset the database to a clean state for gauntlet execution."""
    try:
        # This function now correctly calls the method on the imported instance
        return await gauntlet_data.reset_database(direct_cypher)
    except Exception as e:
        return {"status": "error", "data": f"Error resetting database: {str(e)}"}

# --- Challenge Verification ---
async def verify_database_state(challenge_id: int) -> Tuple[bool, List[str]]:
    """
    Verify that the database state matches what's expected after a challenge.
    Returns (success, feedback_list).
    """
    try:
        # This function now correctly calls the method on the imported instance
        return await gauntlet_data.verify_challenge(challenge_id, direct_cypher)
    except Exception as e:
        return False, [f"Error during verification: {str(e)}"]

# --- Agent Creation Function ---
def create_agent(role: Role, model: Any) -> Agent:
    """Creates an ADK Agent with tools based on the specified role."""
    if not ADK_AVAILABLE:
        print(f"ADK not available, returning dummy agent for role: {role}")
        return Agent()  # Return dummy agent

    print(f"Building tools for role: {role}")
    agent_tools = build_agent_tools(role)
    print(f"Tools built for {role}: {[t.func.__name__ for t in agent_tools if hasattr(t, 'func')]}")

    # Define agent instructions based on role - enhanced for gauntlet
    instructions = {
        "explorer": """You are a Neo4j Graph Explorer assistant.
You can query database schema and read data, but cannot make any changes.
Think step-by-step to explore the graph structure and retrieve information.
Be precise and thorough in your explanations of what you find.""",

        "auditor": """You are a Neo4j Graph Analytics assistant.
You can query the schema, read data, and run GDS analytics procedures.
You cannot make direct changes to the graph structure.
Focus on extracting insights through analytics and communicating them clearly.
Think step-by-step when designing analytics approaches.""",

        "builder": """You are a Neo4j Graph Builder assistant.
You can read, write, and modify the database, including creating new nodes and relationships.
Follow data modeling best practices when designing graph structures.
Think step-by-step when implementing database changes.
Verify your changes after making them.""",

        "admin": """You are a Neo4j Database Administrator assistant.
You have full access to read, write, and analyze the Neo4j database.
You can solve complex problems requiring all aspects of database management.
Think step-by-step through problems that might require multiple database operations.
Always validate your work by checking the results of your operations.""",
    }

    agent = Agent(
        model=model,  # Pass the actual initialized model object here
        name=f"neo4j_{role}_agent",
        instruction=instructions.get(role, "Interact with the Neo4j database."),
        tools=agent_tools,
    )
    print(f"Agent created for role: {role}")
    return agent

# --- Helper to Run Query ---
async def run_query(
    runner: Runner, 
    query: str, 
    user_id: str, 
    session_id: str,
    capture_logs: bool = True
) -> Dict[str, Any]:
    """
    Sends a query to the agent via the runner and returns detailed execution info.
    Returns a dictionary with the final response, logs, and metadata.
    """
    if not ADK_AVAILABLE or not runner:
        print(f"ADK Runner not available. Skipping query: {query}")
        return {"status": "error", "logs": [], "final_response": "ADK Runner not available"}

    print(f"\n--- Running Query via Agent: '{query}' ---")
    content = genai_types.Content(role="user", parts=[genai_types.Part(text=query)])
    final_response = ""
    logs = []
    tool_calls_list = []
    tool_responses_list = []
    
    try:
        # ADK Runner returns an async generator
        start_time = time.time()
        async for event in runner.run_async(user_id=user_id, session_id=session_id, new_message=content):
            # Check for different event types based on content
            tool_calls = event.get_function_calls()
            tool_responses = event.get_function_responses()

            if tool_calls:
                # Handle tool call requests
                for call in tool_calls:
                    tool_call_info = f"Tool call requested: {call.name}({call.args})"
                    print(tool_call_info)
                    if capture_logs:
                        logs.append({"type": "tool_call", "name": call.name, 
                                    "args": call.args, "timestamp": time.time()})
                        tool_calls_list.append({"name": call.name, "args": call.args})
            elif tool_responses:
                # Handle tool responses
                for response in tool_responses:
                    # Ensure response content is serializable for printing
                    response_content_str = str(response.response)  # Basic string conversion
                    log_msg = f"Tool response received: {response.name} -> {response_content_str[:200]}..."
                    print(log_msg)
                    if capture_logs:
                        logs.append({"type": "tool_response", "name": response.name, 
                                    "response": response_content_str, "timestamp": time.time()})
                        tool_responses_list.append({"name": response.name, "response": response_content_str})
            elif event.content and event.content.parts and event.content.parts[0].text:
                # Handle text responses (intermediate or final)
                thought_text = event.content.parts[0].text
                print(f"LLM thought/response chunk: {thought_text}")
                if capture_logs:
                    logs.append({"type": "thought", "text": thought_text, "timestamp": time.time()})

            # Check specifically for the final response to the user for this turn
            if event.is_final_response():
                if event.content and event.content.parts and event.content.parts[0].text:
                    final_response = event.content.parts[0].text
                    print(f"Final Agent Response: {final_response}")
                # Optionally handle other final response types (e.g., raw tool results if skip_summarization=True)
                # elif tool_responses and event.actions and event.actions.skip_summarization:
                #     final_response = str(tool_responses[0].response) # Example: Use raw tool response
                #     print(f"Final Agent Response (Raw Tool): {final_response}")
                break  # Exit after getting the final response
        
        execution_time = time.time() - start_time
        
        result = {
            "status": "success",
            "final_response": final_response,
            "execution_time": execution_time,
            "logs": logs if capture_logs else [],
            "tool_calls": tool_calls_list,
            "tool_responses": tool_responses_list
        }
        
    except Exception as e:
        print(f"Error running query '{query}': {e}")
        import traceback
        traceback.print_exc()  # Print full traceback for debugging
        result = {
            "status": "error",
            "error": str(e),
            "final_response": "",
            "logs": logs if capture_logs else []
        }

    if not final_response:
        print("No final response received from the agent.")
    print("--- Query Execution Finished ---")
    return result

# --- Challenge Definitions ---
CHALLENGES = [
    {
        "id": 1,
        "name": "Schema Exploration",
        "role": "explorer",
        "description": "Explore the database schema. The database should be empty or have minimal data.",
        "task": "What is the current schema of the database? List all node labels, relationship types, and property keys.",
        "evaluation_criteria": [
            "Correctly identifies the database is empty or reports minimal existing schema",
            "Uses appropriate tools for schema exploration",
            "Provides a clear explanation of what schema information means"
        ],
        "setup_description": "Empty database",
        "expected_outcome": "A report confirming the database is empty or listing minimal schema",
        "expected_tools": ["get_schema"],
        "expected_response_patterns": ["empty", "no node labels", "no relationship types", "schema is empty"]
    },
    {
        "id": 2,
        "name": "Company Structure Creation",
        "role": "builder",
        "description": "Create a company organizational structure in the graph",
        "task": """Create a simple company structure in the database with the following elements:
1. Create 3 department nodes with label 'Department' and name property: Engineering, Marketing, and Sales
2. Create 6 employee nodes with label 'Employee' and properties for name, title, and hire_date
3. Create WORKS_IN relationships between employees and their departments
4. Create REPORTS_TO relationships between employees to establish a management hierarchy
5. Verify the structure you've created by running appropriate queries

Use realistic values for employee properties. Make sure at least one employee is a manager with other employees reporting to them.""",
        "evaluation_criteria": [
            "Creates all department nodes correctly",
            "Creates employee nodes with appropriate properties",
            "Establishes both BELONGS_TO and REPORTS_TO relationships",
            "Verifies the created structure with queries",
            "Follows good data modeling practices"
        ],
        "setup_description": "Empty database",
        "expected_outcome": "A connected graph with departments, employees, and relationships",
        "expected_tools": ["write_cypher"]
    },
    {
        "id": 3,
        "name": "Basic Querying",
        "role": "explorer",
        "description": "Perform basic queries on the company structure",
        "task": """Using the company structure that's been created, answer the following questions:
1. How many employees are in each department?
2. Who are the managers in the company?
3. Find all employees who were hired in the last 2 years
4. List all departments and their managers""",
        "evaluation_criteria": [
            "Correctly counts employees per department",
            "Identifies managers based on REPORTS_TO relationships",
            "Successfully filters employees by hire date",
            "Finds department managers through relationship navigation"
        ],
        "setup_description": "Company structure with departments, employees, and relationships",
        "expected_outcome": "Accurate answers to all queries based on the existing data",
        "expected_tools": ["read_cypher"],
        "expected_response_patterns": ["department", "count", "manager", "hired", "engineering", "marketing", "sales"]
    },
    {
        "id": 4,
        "name": "Relationship Navigation",
        "role": "explorer",
        "description": "Navigate complex relationships to answer business questions",
        "task": """Answer these more complex questions about the organizational structure:
1. Who is the highest-level manager in the company? (i.e., who has no one they report to)
2. What is the reporting chain from the lowest-level employee to the top manager?
3. Are there any employees who are in one department but report to a manager in another department?
4. Find the department with the deepest management hierarchy""",
        "evaluation_criteria": [
            "Identifies the top manager correctly",
            "Traces complete reporting chains through the graph",
            "Finds cross-department reporting relationships",
            "Analyzes hierarchy depth by department"
        ],
        "setup_description": "Company structure with hierarchy established",
        "expected_outcome": "Detailed analysis of the organizational hierarchy",
        "expected_tools": ["read_cypher"]
    },
    {
        "id": 5,
        "name": "Data Enrichment",
        "role": "builder",
        "description": "Enrich the graph with projects and skills data",
        "task": """Enhance the company graph with the following additions:
1. Create 4 Project nodes with properties for name, status, and start_date
2. Create WORKS_ON relationships between employees and projects, with a 'role' property
3. Add Skill nodes and HAS_SKILL relationships between employees and skills, with a 'level' property (1-5)
4. Connect projects with REQUIRES_SKILL relationships to skills
5. Perform a query that finds which employees are best suited for a specific project based on their skills""",
        "evaluation_criteria": [
            "Creates all required node types and relationships",
            "Uses appropriate properties on relationships",
            "Maintains consistency with existing data model",
            "Successfully queries the enhanced graph to match employees to projects"
        ],
        "setup_description": "Company structure with departments and employees",
        "expected_outcome": "An enriched graph with projects, skills, and new relationship types",
        "expected_tools": ["write_cypher"]
    },
    {
        "id": 6,
        "name": "Graph Analytics Setup",
        "role": "auditor",
        "description": "Set up and run basic graph analytics on the company structure",
        "task": """Perform these graph analytics tasks:
1. Create a native projection for the organizational structure (departments, employees, reporting relationships)
2. Run betweenness centrality to identify key employees in the communication flow
3. Compute degree centrality to find the most connected employees
4. Analyze the results: Who are the most central employees based on these measures?""",
        "evaluation_criteria": [
            "Successfully creates appropriate graph projections",
            "Correctly runs centrality algorithms",
            "Interprets results meaningfully",
            "Explains the business significance of the findings"
        ],
        "setup_description": "Company graph with departments, employees, projects, and skills",
        "expected_outcome": "Analytics results identifying key employees in the organization",
        "expected_tools": ["run_gds_procedure", "read_cypher"]
    },
    {
        "id": 7,
        "name": "Advanced Analytics",
        "role": "auditor",
        "description": "Perform advanced graph analytics to identify communities and similarities",
        "task": """Run and analyze these advanced graph algorithms:
1. Use a community detection algorithm to identify logical teams or groups beyond formal departments
2. Run a node similarity algorithm to find employees with similar skill sets
3. Perform pathfinding to determine optimal collaboration paths between departments
4. Provide recommendations based on your findings: How might the organization improve collaboration?""",
        "evaluation_criteria": [
            "Successfully executes community detection",
            "Computes meaningful similarity metrics",
            "Performs pathfinding between organizational units",
            "Provides actionable recommendations based on results"
        ],
        "setup_description": "Company graph with centrality scores",
        "expected_outcome": "Community groupings, similarity clusters, and collaboration recommendations",
        "expected_tools": ["run_gds_procedure", "read_cypher"]
    },
    {
        "id": 8,
        "name": "Data Transformation",
        "role": "builder",
        "description": "Transform and optimize the graph based on analytics findings",
        "task": """Based on the previous analytics, modify the graph to optimize the organizational structure:
1. Create new Team nodes based on the detected communities
2. Establish MEMBER_OF relationships between employees and these teams
3. Create new COLLABORATES_WITH relationships between employees who share multiple projects or skills
4. Update any employees who should change departments based on the analytics
5. Verify the new structure with queries that show the improved organizational alignment""",
        "evaluation_criteria": [
            "Creates new organizational structures based on analytics",
            "Establishes meaningful new relationships",
            "Makes justifiable changes to employee-department assignments",
            "Demonstrates improvement through comparative queries"
        ],
        "setup_description": "Company graph with analytics results",
        "expected_outcome": "Transformed graph with new teams and collaboration structures",
        "expected_tools": ["write_cypher", "read_cypher"]
    },
    {
        "id": 9,
        "name": "Final Integration",
        "role": "admin",
        "description": "Solve a complex business problem using the entire graph",
        "task": """The company needs to form optimal teams for two new strategic projects. Use the graph to:
1. Identify two new strategic projects the company should pursue based on current skills and projects
2. Determine the ideal team composition for each project, considering skills, current workload, and collaboration networks
3. Identify any skill gaps that need to be addressed for these projects
4. Create the new project nodes, team allocations, and any other structures needed
5. Run a final analysis that demonstrates the expected effectiveness of your proposed teams""",
        "evaluation_criteria": [
            "Formulates reasonable new projects based on the graph data",
            "Creates optimal team compositions using multiple factors",
            "Identifies and addresses skill gaps",
            "Implements the new structures in the database",
            "Provides convincing analysis of team effectiveness"
        ],
        "setup_description": "Optimized company graph with teams",
        "expected_outcome": "New projects with assigned teams and effectiveness analysis",
        "expected_tools": ["read_cypher", "write_cypher", "run_gds_procedure", "get_schema"]
    }
]

# --- Challenge Runner ---
async def run_challenge(
    challenge_id: int,
    agents: Dict[str, Agent],
    runners: Dict[str, Runner],
    challenge_states: Dict[int, Dict[str, Any]],
    auto_fallback: bool = True
) -> Dict[str, Any]:
    """
    Run a single challenge and return its result.
    
    Args:
        challenge_id: ID of the challenge to run
        agents: Dictionary of agents by role
        runners: Dictionary of runners by role
        challenge_states: Dictionary of previous challenge states
        auto_fallback: Whether to use automatic fallback if prerequisite data is missing
    
    Returns:
        Dictionary with challenge results
    """
    challenge = next((c for c in CHALLENGES if c["id"] == challenge_id), None)
    if not challenge:
        return {"status": "error", "message": f"Challenge {challenge_id} not found"}
    
    challenge_role = challenge["role"]
    if challenge_role not in agents or challenge_role not in runners:
        return {
            "status": "error", 
            "message": f"Agent for role '{challenge_role}' not available"
        }
    
    print(f"\n{'=' * 80}")
    print(f"CHALLENGE {challenge_id}: {challenge['name']} ({challenge_role} role)")
    print(f"{'=' * 80}")
    print(f"Description: {challenge['description']}")
    print(f"Task: {challenge['task']}")
    print(f"{'=' * 80}\n")
    
    # Ensure session exists
    session_id = f"gauntlet_{challenge_id}"
    try:
        session_service.create_session(app_name=APP_NAME, user_id=USER_ID, session_id=session_id)
        print(f"Created session: {session_id}")
    except Exception as e:
        print(f"Session may already exist: {e}")
    
    # Check pre-challenge database state
    pre_check_success, pre_check_feedback = await verify_database_state(challenge_id - 1)
    used_fallback = False
    
    if not pre_check_success and auto_fallback:
        print(f"Pre-challenge check failed: {pre_check_feedback}")
        print("Attempting to set up prerequisite data automatically...")
        
        # Use the imported gauntlet_data instance to set up prerequisites
        prereqs_success = await gauntlet_data.ensure_challenge_prerequisites(challenge_id, direct_cypher)
        if prereqs_success:
            print("✅ Prerequisite data setup successful!")
            used_fallback = True
        else:
            print("❌ Failed to set up prerequisites. Challenge may fail.")
    
    # Capture pre-challenge state (can be used for comparison)
    pre_state = {}
    
    # Run the actual challenge
    start_time = time.time()
    result = await run_query(
        runners[challenge_role], 
        challenge["task"], 
        USER_ID, 
        session_id,
        capture_logs=True
    )
    execution_time = time.time() - start_time
    
    # Check post-challenge database state
    verification_success, verification_feedback = await verify_database_state(challenge_id)
    
    # Evaluate the challenge
    score = 0
    evaluation_feedback = list(verification_feedback) # Start with verification feedback
    
    # 1. Basic Success Check (Agent Response + DB Verification)
    if result["status"] == "success" and verification_success:
        score = 7 # Base score for successful execution and correct state
        evaluation_feedback.append("✅ Agent responded and database state verified.")
    elif result["status"] == "success":
        score = 3 # Partial score if agent responded but DB state is wrong
        evaluation_feedback.append("⚠️ Agent responded but database state verification failed.")
    else:
        score = 0 # No score if agent failed to respond
        evaluation_feedback.append(f"❌ Agent failed to respond or encountered an error: {result.get('error', 'Unknown')}")
        
    # 2. Tool Usage Check
    expected_tools = challenge.get("expected_tools", [])
    actual_tool_calls = result.get("tool_calls", [])
    actual_tool_names = {call["name"] for call in actual_tool_calls}
    
    used_expected_tool = False
    if expected_tools:
        for tool_name in expected_tools:
            if tool_name in actual_tool_names:
                used_expected_tool = True
                evaluation_feedback.append(f"✅ Used expected tool: {tool_name}")
                break # Only need one match
        if not used_expected_tool:
            evaluation_feedback.append(f"❌ Did not use any expected tools: {expected_tools}. Used: {actual_tool_names or 'None'}")
            score = max(0, score - 2) # Penalize for not using expected tools
        else:
            score = min(10, score + 3) # Bonus for using expected tools
    else:
        evaluation_feedback.append("ℹ️ No specific tools expected for this challenge.")
        
    # 3. Response Content Check (Simple Keyword/Pattern Matching)
    expected_patterns = challenge.get("expected_response_patterns", [])
    final_response_text = result.get("final_response", "").lower()
    response_matched = False
    if expected_patterns and final_response_text:
        for pattern in expected_patterns:
            if pattern.lower() in final_response_text:
                response_matched = True
                evaluation_feedback.append(f"✅ Response contains expected pattern: '{pattern}'")
                break
        if not response_matched:
            evaluation_feedback.append(f"❌ Response did not contain expected patterns like: {expected_patterns}")
            score = max(0, score - 1) # Minor penalty if response content is off
        else:
            score = min(10, score + 1) # Minor bonus if response content matches
    elif expected_patterns:
        evaluation_feedback.append("⚠️ No final response text received to check against expected patterns.")
        score = max(0, score - 1)
    else:
        evaluation_feedback.append("ℹ️ No specific response patterns expected for this challenge.")

    # Ensure score is within bounds
    score = min(10, max(0, score))
    
    # Record the post-challenge state
    post_state = {
        "verification_success": verification_success,
        "verification_feedback": verification_feedback,
        "used_fallback": used_fallback
    }
    
    # Format the results
    challenge_result = {
        "challenge_id": challenge_id,
        "name": challenge["name"],
        "role": challenge_role,
        "task": challenge["task"],
        "timestamp": datetime.now().isoformat(),
        "execution_time": execution_time,
        "response": result.get("final_response", ""),
        "status": "success" if verification_success else "partial" if result["status"] == "success" else "failed",
        "pre_state": pre_state,
        "post_state": post_state,
        "logs": result.get("logs", []),
        "evaluation": {
            "score": score,
            "feedback": evaluation_feedback # Use the combined feedback
        }
    }
    
    # Save results to file
    results_file = os.path.join(RESULTS_DIR, f"challenge_{challenge_id}_result.json")
    with open(results_file, "w") as f:
        json.dump(challenge_result, f, indent=2)
        
    print(f"\nChallenge {challenge_id} completed with score: {score}/10")
    for feedback in evaluation_feedback: # Print combined feedback
        print(f"  • {feedback}")
    
    # Ensure we have correct data for the next challenge if this one failed
    if not verification_success and auto_fallback and challenge_id < len(CHALLENGES):
        print("\nSetting up correct data for next challenge...")
        # Use the imported gauntlet_data instance to set up prerequisites for the next challenge
        next_prereqs_success = await gauntlet_data.ensure_challenge_prerequisites(challenge_id + 1, direct_cypher)
        if next_prereqs_success:
            print("✅ Data setup for next challenge successful")
        else:
            print("❌ Failed to set up data for next challenge")
    
    # Store this challenge's state for future challenges
    challenge_states[challenge_id] = post_state
    
    return challenge_result

# --- Main Gauntlet Runner ---
async def run_gauntlet(start_challenge: int = 1, end_challenge: int = 9, auto_fallback: bool = True) -> Dict[str, Any]:
    """
    Run a series of challenges in the Neo4j Gauntlet.
    
    Args:
        start_challenge: First challenge ID to run (1-based)
        end_challenge: Last challenge ID to run (inclusive)
        auto_fallback: Whether to use automatic fallback if prerequisite data is missing
        
    Returns:
        Dictionary with overall results
    """
    print(f"\n{'*' * 80}")
    print(f"* STARTING NEO4J GAUNTLET - Challenges {start_challenge}-{end_challenge}")
    print(f"{'*' * 80}")
    
    # Initialize database connection
    await initialize_neo4j_driver()
    
    if not ADK_AVAILABLE:
        print("ADK components not loaded. Cannot run agent examples.")
        await shutdown_neo4j_driver()
        return {"status": "error", "message": "ADK not available"}
    
    # Use the GLOBAL session_service defined at the top of the file
    # session_service = InMemorySessionService() # REMOVE local instance creation
    
    # Initialize the actual LLM model here if needed
    # llm = genai.GenerativeModel(llm_model_name)
    llm_model_name = "gemini-2.5-flash-preview-04-17"  # Placeholder name
    
    # Create Agents for all roles we'll need
    print("\n--- Creating Agents ---")
    agents = {}
    runners = {}
    try:
        for role in ["explorer", "builder", "auditor", "admin"]:
            agents[role] = create_agent(role, llm_model_name)
            # Ensure Runner uses the GLOBAL session_service instance
            runners[role] = Runner(agent=agents[role], app_name=APP_NAME, session_service=session_service)
    except ValueError as e:
        print(f"Error creating agents: {e}")
        await shutdown_neo4j_driver()
        return {"status": "error", "message": f"Error creating agents: {e}"}
    print("--- Agents Created ---")
    
    # Store results for each challenge
    results = []
    challenge_states = {}
    # Run each challenge in sequence
    for challenge_id in range(start_challenge, end_challenge + 1):
        # Create the session for this specific challenge run *using the GLOBAL service*
        session_id = f"gauntlet_{challenge_id}"
        try:
            # Ensure session creation uses the GLOBAL session_service instance
            session_service.create_session(app_name=APP_NAME, user_id=USER_ID, session_id=session_id)
            print(f"Created session for challenge {challenge_id}: {session_id}")
        except Exception as e:
            # It's okay if the session already exists (e.g., resuming)
            print(f"Session {session_id} may already exist: {e}")
            
        # Now run the challenge, passing the session_id implicitly via the runner
        result = await run_challenge(challenge_id, agents, runners, challenge_states, auto_fallback)
        results.append(result)
        
        
        # Maybe add a small break between challenges
        if challenge_id < end_challenge:
            print("\nPausing between challenges...")
            await asyncio.sleep(2)
    
    # Write overall results
    summary = {
        "timestamp": datetime.now().isoformat(),
        "challenges_run": end_challenge - start_challenge + 1,
        "start_challenge": start_challenge,
        "end_challenge": end_challenge,
        "auto_fallback_enabled": auto_fallback,
        "challenge_results": [
            {
                "id": r["challenge_id"],
                "name": r["name"],
                "status": r["status"],
                "score": r["evaluation"]["score"]
            }
            for r in results
        ],
        "total_score": sum(r["evaluation"]["score"] for r in results),
        "max_possible_score": 10 * len(results)
    }
    
    # Save summary
    summary_file = os.path.join(RESULTS_DIR, f"gauntlet_summary_{start_challenge}_to_{end_challenge}.json")
    with open(summary_file, "w") as f:
        json.dump(summary, f, indent=2)
    
    # Calculate overall score as percentage
    overall_percentage = (summary["total_score"] / summary["max_possible_score"]) * 100
    
    print(f"\n{'*' * 80}")
    print(f"* NEO4J GAUNTLET COMPLETE")
    print(f"* Overall Score: {summary['total_score']}/{summary['max_possible_score']} ({overall_percentage:.1f}%)")
    print(f"{'*' * 80}")
    
    # Clean up
    await shutdown_neo4j_driver()
    
    return {
        "status": "success",
        "summary": summary
    }

# --- Main Execution Block ---
if __name__ == "__main__":
    print("Running Neo4j Gauntlet...")
    try:
        asyncio.run(run_gauntlet())
    except KeyboardInterrupt:
        print("\nGauntlet execution interrupted by user.")
    finally:
        # Ensure driver shutdown
        print("Ensuring Neo4j driver is shut down (final check)...")
        try:
            asyncio.run(shutdown_neo4j_driver())
        except:
            pass
        print("Final shutdown check complete.")