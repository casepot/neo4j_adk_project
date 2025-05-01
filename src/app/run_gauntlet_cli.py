#!/usr/bin/env python3
# src/app/run_gauntlet_cli.py
"""
Command-line interface for running the Neo4j Gauntlet.

This script provides a user-friendly way to run the Neo4j Gauntlet with various
configuration options, including running individual challenges, resetting the database,
enabling/disabling fallbacks, and more.

Example usage:
  # Run the full gauntlet
  python src/app/run_gauntlet_cli.py

  # Run just challenges 3-5
  python src/app/run_gauntlet_cli.py --start 3 --end 5

  # Reset the database before running
  python src/app/run_gauntlet_cli.py --reset

  # Disable automatic fallbacks
  python src/app/run_gauntlet_cli.py --no-fallback

  # Just reset the database without running any challenges
  python src/app/run_gauntlet_cli.py --reset-only

  # Run a specific challenge
  python src/app/run_gauntlet_cli.py --challenge 4
"""

import asyncio
import argparse
import os
import time
import sys
from typing import List, Dict, Any, Optional

# Add the project root to path if running directly
if __name__ == "__main__":
    # Get the absolute path of the script
    script_path = os.path.abspath(__file__)
    
    # Get the directory containing the script
    script_dir = os.path.dirname(script_path)
    
    # Get the project root (two levels up from the script)
    project_root = os.path.dirname(os.path.dirname(script_dir))
    
    # Add the project root to sys.path if it's not already there
    if project_root not in sys.path:
        sys.path.insert(0, project_root)

# Import the main gauntlet running functions
try:
    # Import the global session_service along with other functions
    from src.app.run_gauntlet import run_gauntlet, reset_database, run_challenge, session_service
    from src.app.run_gauntlet import initialize_neo4j_driver, shutdown_neo4j_driver
    from src.agent import get_driver
except ImportError:
    print("Error: Could not import gauntlet functions. Make sure you're running this script from the project root.")
    sys.exit(1)

def print_banner() -> None:
    """Print a fancy banner for the Neo4j Gauntlet CLI."""
    banner = r"""
    ███╗   ██╗███████╗ ██████╗ ██╗  ██╗     ██╗     ██████╗  █████╗ ██╗   ██╗███╗   ██╗████████╗██╗     ███████╗████████╗
    ████╗  ██║██╔════╝██╔═══██╗██║  ██║     ██║    ██╔════╝ ██╔══██╗██║   ██║████╗  ██║╚══██╔══╝██║     ██╔════╝╚══██╔══╝
    ██╔██╗ ██║█████╗  ██║   ██║███████║     ██║    ██║  ███╗███████║██║   ██║██╔██╗ ██║   ██║   ██║     █████╗     ██║   
    ██║╚██╗██║██╔══╝  ██║   ██║╚════██║     ██║    ██║   ██║██╔══██║██║   ██║██║╚██╗██║   ██║   ██║     ██╔══╝     ██║   
    ██║ ╚████║███████╗╚██████╔╝     ██║     ██║    ╚██████╔╝██║  ██║╚██████╔╝██║ ╚████║   ██║   ███████╗███████╗   ██║   
    ╚═╝  ╚═══╝╚══════╝ ╚═════╝      ╚═╝     ╚═╝     ╚═════╝ ╚═╝  ╚═╝ ╚═════╝ ╚═╝  ╚═══╝   ╚═╝   ╚══════╝╚══════╝   ╚═╝   
                                                                                                                          
    A progressive series of Neo4j database challenges for testing agent capabilities
    ------------------------------------------------------------------------------------------------
    """
    print(banner)

def print_challenge_info() -> None:
    """Print information about each challenge in the gauntlet."""
    challenges = [
        (1, "Schema Exploration", "explorer", "Explore database schema"),
        (2, "Company Structure Creation", "builder", "Build organizational graph"),
        (3, "Basic Querying", "explorer", "Perform basic company queries"),
        (4, "Relationship Navigation", "explorer", "Analyze organizational relationships"),
        (5, "Data Enrichment", "builder", "Add projects and skills"),
        (6, "Graph Analytics Setup", "auditor", "Set up and run basic graph analytics"),
        (7, "Advanced Analytics", "auditor", "Perform complex graph analysis"),
        (8, "Data Transformation", "builder", "Refactor and optimize graph"),
        (9, "Final Integration", "admin", "Solve a complex business problem")
    ]
    
    print("\nAvailable Challenges:")
    print("--------------------")
    for id, name, role, desc in challenges:
        print(f"{id}. {name} [{role}] - {desc}")
    print()

async def run_reset_only() -> None:
    """Reset the database without running any challenges."""
    print("\nResetting Neo4j database...")
    await initialize_neo4j_driver()
    result = await reset_database()
    await shutdown_neo4j_driver()
    
    if result["status"] == "success":
        print("✅ Database reset successfully!")
    else:
        print(f"❌ Error resetting database: {result.get('data', 'Unknown error')}")

async def check_neo4j_connection() -> bool:
    """
    Check if Neo4j connection is available.
    Returns True if connection successful, False otherwise.
    """
    print("Checking Neo4j connection...")
    try:
        await initialize_neo4j_driver()
        driver = get_driver()
        if not driver:
            print("❌ Neo4j driver could not be initialized.")
            return False
            
        # Try a simple test query
        from src.wrappers import wrapped_read_neo4j_cypher
        result = await wrapped_read_neo4j_cypher("RETURN 1 as test")
        
        if result["status"] != "success":
            print(f"❌ Neo4j connection test failed: {result['data']}")
            return False
            
        print("✅ Neo4j connection successful!")
        return True
        
    except Exception as e:
        print(f"❌ Neo4j connection error: {e}")
        return False
    finally:
        await shutdown_neo4j_driver()

async def run_single_challenge(challenge_id: int, auto_fallback: bool = True) -> None:
    """Run a single challenge from the gauntlet."""
    print(f"\nRunning Challenge {challenge_id} independently...")
    
    from src.app.run_gauntlet import (
        create_agent, CHALLENGES, initialize_neo4j_driver, 
        shutdown_neo4j_driver, direct_cypher, verify_database_state
    )
    # Import the instance, not the module
    from src.app.gauntlet_data import gauntlet_data
    from google.adk.runners import Runner
    # No longer need to import InMemorySessionService here, we use the global one
    
    # Initialize driver
    await initialize_neo4j_driver()
    
    # Get challenge definition
    challenge = next((c for c in CHALLENGES if c["id"] == challenge_id), None)
    if not challenge:
        print(f"❌ Challenge {challenge_id} not found!")
        await shutdown_neo4j_driver()
        return
    
    # Setup prerequisite data
    if auto_fallback:
        print(f"Setting up prerequisites for challenge {challenge_id}...")
        prereqs_ok = await gauntlet_data.ensure_challenge_prerequisites(challenge_id, direct_cypher)
        if not prereqs_ok:
            print("❌ Failed to set up prerequisites.")
            await shutdown_neo4j_driver()
            return
    
    # Create agent and session
    print(f"Creating agent for role: {challenge['role']}...")
    try:
        # Using placeholder model name
        llm_model_name = "gemini-2.0-flash"
        agent = create_agent(challenge["role"], llm_model_name)
        # session_service = InMemorySessionService() # REMOVE local instance creation
        # Use the imported global session_service
        runner = Runner(agent=agent, app_name="neo4j_adk_gauntlet", session_service=session_service)
        
        # Create session using the imported global session_service
        session_id = f"gauntlet_single_{challenge_id}"
        # Ensure session creation uses the imported global session_service instance
        session_service.create_session(app_name="neo4j_adk_gauntlet", user_id="gauntlet_user", session_id=session_id)
    except Exception as e:
        print(f"❌ Error creating agent: {e}")
        await shutdown_neo4j_driver()
        return
    
    # Run the challenge
    try:
        # We need to create appropriate agents dictionary for the run_challenge function
        agents = {challenge["role"]: agent}
        runners = {challenge["role"]: runner}
        
        # Run the challenge
        result = await run_challenge(challenge_id, agents, runners, {})
        
        # Print summary
        if "evaluation" in result:
            print(f"\n✅ Challenge {challenge_id} complete!")
            print(f"Score: {result['evaluation']['score']}/10")
            print("Feedback:")
            for feedback in result['evaluation']['feedback']:
                print(f"  • {feedback}")
            
            # Check for fallback use
            if result["post_state"].get("used_fallback", False):
                print("\n⚠️ Note: Fallback data was used because the agent didn't complete the challenge successfully.")
        else:
            print(f"\n❌ Challenge {challenge_id} failed: {result.get('message', 'Unknown error')}")
    except Exception as e:
        print(f"❌ Error running challenge: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await shutdown_neo4j_driver()

async def main() -> None:
    """Main entry point with improved CLI."""
    # Create argument parser
    parser = argparse.ArgumentParser(
        description="Run the Neo4j Gauntlet - A series of progressive database challenges",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    
    # Add arguments
    parser.add_argument("--start", type=int, default=1, help="Starting challenge ID")
    parser.add_argument("--end", type=int, default=9, help="Ending challenge ID")
    parser.add_argument("--challenge", type=int, help="Run a single challenge (overrides start/end)")
    parser.add_argument("--reset", action="store_true", help="Reset database before running")
    parser.add_argument("--reset-only", action="store_true", help="Just reset the database, don't run challenges")
    parser.add_argument("--no-fallback", action="store_true", help="Disable automatic fallback data creation")
    parser.add_argument("--list", action="store_true", help="List all available challenges")
    parser.add_argument("--check-connection", action="store_true", help="Check Neo4j connection and exit")
    
    # Parse arguments
    args = parser.parse_args()
    
    # Print banner
    print_banner()
    
    # Handle special cases first
    if args.list:
        print_challenge_info()
        return
        
    if args.check_connection:
        connection_ok = await check_neo4j_connection()
        sys.exit(0 if connection_ok else 1)
        
    if args.reset_only:
        await run_reset_only()
        return
    
    # Validate arguments
    if args.start < 1 or args.start > 9:
        print("Error: --start must be between 1 and 9")
        sys.exit(1)
        
    if args.end < 1 or args.end > 9:
        print("Error: --end must be between 1 and 9")
        sys.exit(1)
        
    if args.start > args.end:
        print("Error: --start must be less than or equal to --end")
        sys.exit(1)
        
    if args.challenge is not None and (args.challenge < 1 or args.challenge > 9):
        print("Error: --challenge must be between 1 and 9")
        sys.exit(1)
    
    # Reset database if requested
    if args.reset:
        await run_reset_only()
    
    # Run single challenge or range
    if args.challenge is not None:
        await run_single_challenge(args.challenge, not args.no_fallback)
    else:
        # Run the gauntlet with specified range
        print(f"\nRunning Neo4j Gauntlet challenges {args.start}-{args.end}")
        print(f"Auto-fallback: {'Disabled' if args.no_fallback else 'Enabled'}")
        
        # Run the gauntlet
        await run_gauntlet(args.start, args.end, not args.no_fallback)
        
if __name__ == "__main__":
    # Ensure asyncio event loop runs the main function
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nGauntlet execution interrupted by user.")
    except Exception as e:
        print(f"\nError running gauntlet: {e}")
        import traceback
        traceback.print_exc()