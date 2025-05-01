# src/agent.py
"""
Contains DB bootstrap logic and the original Neo4j wrapper functions.
These wrappers handle the direct interaction with the Neo4j driver.
"""

import os
from typing import Dict, Any, Optional
from dotenv import load_dotenv
from neo4j import AsyncGraphDatabase, AsyncDriver

# Import neo4j_tools - ensure it exists and has the required functions
try:
    # Use absolute import (relative to src)
    from src import neo4j_tools
except ImportError:
    print("Warning: neo4j_tools.py not found or has import errors. Wrapper functions will rely on placeholder implementations.")
    # Define dummy functions if neo4j_tools is missing, to allow agent.py to load
    class neo4j_tools:
        @staticmethod
        async def get_schema(**kwargs): return {"status": "error", "data": "neo4j_tools not implemented"}
        @staticmethod
        async def run_cypher(**kwargs): return {"status": "error", "data": "neo4j_tools not implemented"}


# Global Neo4j driver instance
driver: Optional[AsyncDriver] = None

# --- Function to safely access the driver ---
def get_driver() -> Optional[AsyncDriver]:
    """Returns the initialized global driver instance."""
    return driver
# --- End Function ---

async def initialize_neo4j_driver():
    """Initializes the Neo4j driver based on environment variables."""
    global driver
    if driver:
        print("Neo4j driver already initialized.")
        return

    load_dotenv()
    NEO4J_URI = os.getenv("NEO4J_URI")
    NEO4J_USER = os.getenv("NEO4J_USER")
    NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD")

    # --- Add Env Var Logging ---
    print(f"DEBUG: Loaded NEO4J_URI: {NEO4J_URI}")
    print(f"DEBUG: Loaded NEO4J_USER: {NEO4J_USER}")
    print(f"DEBUG: Loaded NEO4J_PASSWORD: {NEO4J_PASSWORD}") # Print actual password for debugging
    # --- End Env Var Logging ---

    if not NEO4J_URI or not NEO4J_USER or not NEO4J_PASSWORD:
        print("Error: Neo4j connection details (URI, USER, PASSWORD) not found in environment variables.")
        # In a real app, you might raise an exception here
        return

    # --- Add Retry Logic ---
    import asyncio
    max_retries = 5
    retry_delay_seconds = 3
    for attempt in range(max_retries):
        try:
            print(f"Attempting to connect to Neo4j at {NEO4J_URI} as user {NEO4J_USER}... (Attempt {attempt + 1}/{max_retries})")
            driver = AsyncGraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
            # Remove the config argument from verify_connectivity
            await driver.verify_connectivity()
            print("Neo4j driver initialized successfully.")
            break # Exit loop on success
        except Exception as e:
            print(f"Error initializing Neo4j driver (Attempt {attempt + 1}/{max_retries}): {e}")
            driver = None # Ensure driver is None on failure
            if attempt < max_retries - 1:
                print(f"Retrying in {retry_delay_seconds} seconds...")
                await asyncio.sleep(retry_delay_seconds)
            else:
                print("Max connection retries reached. Failed to initialize Neo4j driver.")
                # Optionally, re-raise the last exception or handle failure appropriately
                # raise e # Example: re-raise the last exception
    # --- End Retry Logic ---

async def shutdown_neo4j_driver():
    """Closes the Neo4j driver connection."""
    global driver
    if driver:
        print("Closing Neo4j driver...")
        await driver.close()
        driver = None
        print("Neo4j driver closed.")
    else:
        print("Neo4j driver was not initialized or already closed.")


# Wrapper functions have been moved to src/wrappers.py to break import cycle.