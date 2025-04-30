# src/app/fastapi_lifespan.py
"""
Provides lifespan event handlers for FastAPI applications,
ensuring resources like the Neo4j driver are initialized on startup
and properly shut down on exit.
"""

from contextlib import asynccontextmanager
from typing import AsyncGenerator

# Use relative imports assuming structure src/app, src/agent
try:
    from ..agent import initialize_neo4j_driver, shutdown_neo4j_driver
except ImportError:
    # Fallback for different execution contexts
    from agent import initialize_neo4j_driver, shutdown_neo4j_driver # type: ignore

# Requires FastAPI to be installed: pip install fastapi
try:
    from fastapi import FastAPI
except ImportError:
    FastAPI = None # type: ignore # Make type checker happy if FastAPI not installed


@asynccontextmanager
async def lifespan(app: "FastAPI") -> AsyncGenerator[None, None]:
    """
    Async context manager for FastAPI lifespan events.

    Usage in your FastAPI app:
    ```python
    from fastapi import FastAPI
    from .fastapi_lifespan import lifespan

    app = FastAPI(lifespan=lifespan)

    @app.get("/")
    async def root():
        return {"message": "Hello World"}
    ```

    Args:
        app (FastAPI): The FastAPI application instance (passed automatically).

    Yields:
        None: Yields control back to FastAPI between startup and shutdown.
    """
    print("Application startup: Initializing Neo4j driver...")
    await initialize_neo4j_driver()
    print("Neo4j driver initialization complete.")

    yield  # Application runs here

    print("Application shutdown: Closing Neo4j driver...")
    await shutdown_neo4j_driver()
    print("Neo4j driver shutdown complete.")


# Example of how to use it if running a FastAPI app directly
# (This part wouldn't typically be in this file but shows usage)
if __name__ == "__main__" and FastAPI:
    import uvicorn

    # Example FastAPI app using the lifespan manager
    example_app = FastAPI(lifespan=lifespan)

    @example_app.get("/")
    async def read_root():
        return {"message": "FastAPI app with Neo4j lifespan management"}

    print("Starting example FastAPI server with lifespan management...")
    # Note: Running this directly requires .env to be configured
    # and dependencies (fastapi, uvicorn, python-dotenv, neo4j-driver) installed.
    # uvicorn.run(example_app, host="0.0.0.0", port=8000)
    print("To run the example server, uncomment the uvicorn.run line and ensure")
    print("all dependencies and the .env file are set up correctly.")
    print("Example server setup finished (commented out by default).")

elif __name__ == "__main__":
     print("FastAPI is not installed. Cannot run example server.")
     print("Install with: pip install fastapi uvicorn")