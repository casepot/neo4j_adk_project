# Neo4j Gauntlet

A progressive series of database challenges for evaluating both our Neo4j ADK tools and the agents using them.

## Overview

The Neo4j Gauntlet consists of 9 increasingly complex challenges that build upon one another. Each challenge tests different agent capabilities and tool functionalities while constructing a realistic company knowledge graph.

## Challenges

1. **Schema Exploration** (Explorer Role)
   - Explore an empty database schema
   - Tests schema inspection capabilities
   
2. **Company Structure Creation** (Builder Role)
   - Create departments, employees, and organizational relationships
   - Tests graph creation and data modeling capabilities
   
3. **Basic Querying** (Explorer Role)
   - Query department headcounts, management information
   - Tests basic path navigation and aggregation
   
4. **Relationship Navigation** (Explorer Role)
   - Find complex paths and relationship patterns
   - Tests advanced path analysis and pattern matching
   
5. **Data Enrichment** (Builder Role)
   - Add projects and skills to the graph
   - Tests ability to extend an existing data model
   
6. **Graph Analytics Setup** (Auditor Role)
   - Set up GDS projections and run basic centrality algorithms
   - Tests use of Graph Data Science procedures
   
7. **Advanced Analytics** (Auditor Role)
   - Run community detection and similarity algorithms
   - Tests complex analytics and result interpretation
   
8. **Data Transformation** (Builder Role)
   - Refactor and optimize the graph based on analytics
   - Tests data transformation and schema evolution
   
9. **Final Integration** (Admin Role)
   - Solve a complex business problem using all available data
   - Tests holistic reasoning across multiple aspects of the graph

## Prerequisites

- Neo4j database (4.4+ recommended)
- Python 3.9+
- Required packages: 
  - `neo4j` driver
  - `google-adk` and `google-genai` (for agent functionality)
  - `python-dotenv` (for environment configuration)

## Setup

1. Clone the repository
2. Create a `.env` file with your Neo4j connection details:
   ```
   NEO4J_URI=bolt://localhost:7687
   NEO4J_USER=neo4j
   NEO4J_PASSWORD=your_password
   GOOGLE_API_KEY=your_api_key  # If using Gemini models
   ```
3. Install dependencies: `pip install -r requirements.txt`

## Running the Gauntlet

The Neo4j Gauntlet can be run using the provided CLI tool:

```bash
# Run the full gauntlet (all 9 challenges)
python src/app/run_gauntlet_cli.py

# Reset the database first
python src/app/run_gauntlet_cli.py --reset

# Run specific challenge range
python src/app/run_gauntlet_cli.py --start 3 --end 5

# Run a single challenge
python src/app/run_gauntlet_cli.py --challenge 4

# List all challenges
python src/app/run_gauntlet_cli.py --list

# Reset database without running challenges
python src/app/run_gauntlet_cli.py --reset-only

# Disable automatic fallbacks
python src/app/run_gauntlet_cli.py --no-fallback

# Check Neo4j connection
python src/app/run_gauntlet_cli.py --check-connection
```

## Fallback Mechanism

The gauntlet includes automatic fallback mechanisms to ensure progression through challenges. If an agent fails to complete a challenge successfully (particularly challenges that set up data required for later challenges), the system can automatically create the necessary data structures to allow testing of subsequent challenges.

This feature can be disabled with the `--no-fallback` flag.

## Results and Evaluation

Results for each challenge are stored in the `gauntlet_results` directory. They include:

- Individual challenge result files with detailed execution logs
- A summary JSON file with scores and feedback
- State snapshots before and after each challenge

Each challenge is scored on a scale of 0-10 based on:
- Tool selection (2 points)
- Response relevance (3 points)
- Database state correctness (3 points)
- Problem-solving approach (2 points)

## Extension and Customization

The gauntlet can be extended with additional challenges or customized by modifying:

- `src/app/run_gauntlet.py` - Main challenge definitions and execution logic
- `src/app/gauntlet_data.py` - Data initialization and verification helpers

## Troubleshooting

- **Database Connection Issues**: Ensure your Neo4j instance is running and credentials in `.env` are correct
- **Agent Creation Failures**: Verify Google API keys if using Gemini models
- **Challenge Progression Errors**: Use `--reset` to start with a clean database