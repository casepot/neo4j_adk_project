# src/app/gauntlet_data.py
"""
Data management for the Neo4j Gauntlet.

This module handles:
1. Database reset and initialization
2. Verification of challenge completion criteria
3. Fallback data creation for challenge prerequisites
4. Test data generation

Each challenge has specific data requirements and verification methods.
"""

import asyncio
import datetime
from typing import Dict, List, Any, Optional, Tuple, Callable, Awaitable, Union

# Types for the direct_cypher function
DirectCypherFunc = Callable[[str, Optional[Dict[str, Any]], bool], Awaitable[Dict[str, Any]]]

# --- Challenge 2: Company Structure Setup Queries ---
COMPANY_SETUP_QUERIES = [
    # Create Departments
    """
    CREATE (:Department {name: 'Engineering', budget: 1500000, location: 'Building A'})
    CREATE (:Department {name: 'Marketing', budget: 800000, location: 'Building B'})
    CREATE (:Department {name: 'Sales', budget: 1200000, location: 'Building B'})
    CREATE (:Department {name: 'Human Resources', budget: 500000, location: 'Building A'})
    """,
    
    # Create Employees
    """
    CREATE (:Employee {name: 'Alice Smith', title: 'CTO', hire_date: '2019-01-15', salary: 185000, id: 'E001'})
    CREATE (:Employee {name: 'Bob Johnson', title: 'Engineering Manager', hire_date: '2020-03-01', salary: 145000, id: 'E002'})
    CREATE (:Employee {name: 'Carol Williams', title: 'Senior Developer', hire_date: '2021-05-10', salary: 125000, id: 'E003'})
    CREATE (:Employee {name: 'Dave Brown', title: 'Junior Developer', hire_date: '2022-09-01', salary: 85000, id: 'E004'})
    CREATE (:Employee {name: 'Eve Davis', title: 'Marketing Director', hire_date: '2021-02-15', salary: 140000, id: 'E005'})
    CREATE (:Employee {name: 'Frank Miller', title: 'Sales Director', hire_date: '2021-01-20', salary: 150000, id: 'E006'})
    CREATE (:Employee {name: 'Grace Wilson', title: 'HR Manager', hire_date: '2022-04-01', salary: 110000, id: 'E007'})
    CREATE (:Employee {name: 'Heidi Moore', title: 'Sales Representative', hire_date: '2022-07-15', salary: 75000, id: 'E008'})
    """,
    
    # Create WORKS_IN relationships (Split into individual queries)
    "MATCH (e:Employee {name: 'Alice Smith'}), (d:Department {name: 'Engineering'}) CREATE (e)-[:WORKS_IN {since: '2019-01-15'}]->(d)",
    "MATCH (e:Employee {name: 'Bob Johnson'}), (d:Department {name: 'Engineering'}) CREATE (e)-[:WORKS_IN {since: '2020-03-01'}]->(d)",
    "MATCH (e:Employee {name: 'Carol Williams'}), (d:Department {name: 'Engineering'}) CREATE (e)-[:WORKS_IN {since: '2021-05-10'}]->(d)",
    "MATCH (e:Employee {name: 'Dave Brown'}), (d:Department {name: 'Engineering'}) CREATE (e)-[:WORKS_IN {since: '2022-09-01'}]->(d)",
    "MATCH (e:Employee {name: 'Eve Davis'}), (d:Department {name: 'Marketing'}) CREATE (e)-[:WORKS_IN {since: '2021-02-15'}]->(d)",
    "MATCH (e:Employee {name: 'Frank Miller'}), (d:Department {name: 'Sales'}) CREATE (e)-[:WORKS_IN {since: '2021-01-20'}]->(d)",
    "MATCH (e:Employee {name: 'Grace Wilson'}), (d:Department {name: 'Human Resources'}) CREATE (e)-[:WORKS_IN {since: '2022-04-01'}]->(d)",
    "MATCH (e:Employee {name: 'Heidi Moore'}), (d:Department {name: 'Sales'}) CREATE (e)-[:WORKS_IN {since: '2022-07-15'}]->(d)",
    
    # Create REPORTS_TO relationships (Split into individual queries)
    "MATCH (e1:Employee {name: 'Bob Johnson'}), (e2:Employee {name: 'Alice Smith'}) CREATE (e1)-[:REPORTS_TO {since: '2020-03-01'}]->(e2)",
    "MATCH (e1:Employee {name: 'Carol Williams'}), (e2:Employee {name: 'Bob Johnson'}) CREATE (e1)-[:REPORTS_TO {since: '2021-05-10'}]->(e2)",
    "MATCH (e1:Employee {name: 'Dave Brown'}), (e2:Employee {name: 'Carol Williams'}) CREATE (e1)-[:REPORTS_TO {since: '2022-09-01'}]->(e2)",
    "MATCH (e1:Employee {name: 'Eve Davis'}), (e2:Employee {name: 'Alice Smith'}) CREATE (e1)-[:REPORTS_TO {since: '2021-02-15'}]->(e2)",
    "MATCH (e1:Employee {name: 'Frank Miller'}), (e2:Employee {name: 'Alice Smith'}) CREATE (e1)-[:REPORTS_TO {since: '2021-01-20'}]->(e2)",
    "MATCH (e1:Employee {name: 'Grace Wilson'}), (e2:Employee {name: 'Alice Smith'}) CREATE (e1)-[:REPORTS_TO {since: '2022-04-01'}]->(e2)",
    "MATCH (e1:Employee {name: 'Heidi Moore'}), (e2:Employee {name: 'Frank Miller'}) CREATE (e1)-[:REPORTS_TO {since: '2022-07-15'}]->(e2)"
]

# --- Challenge 5: Data Enrichment Setup Queries ---
DATA_ENRICHMENT_QUERIES = [
    # Create projects
    """
    CREATE (:Project {name: 'Database Migration', status: 'In Progress', deadline: '2025-06-30', budget: 250000, priority: 'High'})
    CREATE (:Project {name: 'Website Redesign', status: 'Planning', deadline: '2025-08-15', budget: 180000, priority: 'Medium'})
    CREATE (:Project {name: 'Mobile App Development', status: 'In Progress', deadline: '2025-07-30', budget: 320000, priority: 'High'})
    CREATE (:Project {name: 'Security Audit', status: 'Completed', deadline: '2025-04-15', budget: 85000, priority: 'Critical'})
    CREATE (:Project {name: 'Data Analytics Platform', status: 'Planning', deadline: '2025-09-30', budget: 275000, priority: 'Medium'})
    """,
    
    # Create skills
    """
    CREATE (:Skill {name: 'Python', category: 'Programming', demand: 'High'})
    CREATE (:Skill {name: 'Neo4j', category: 'Database', demand: 'Medium'})
    CREATE (:Skill {name: 'JavaScript', category: 'Programming', demand: 'High'})
    CREATE (:Skill {name: 'Project Management', category: 'Soft Skill', demand: 'High'})
    CREATE (:Skill {name: 'Machine Learning', category: 'Data Science', demand: 'Very High'})
    CREATE (:Skill {name: 'Product Design', category: 'Design', demand: 'Medium'})
    CREATE (:Skill {name: 'Sales Negotiation', category: 'Soft Skill', demand: 'Medium'})
    CREATE (:Skill {name: 'Cybersecurity', category: 'IT', demand: 'High'})
    """,
    
    # Connect employees to projects with roles (Split into individual queries)
    "MATCH (e:Employee {name: 'Alice Smith'}), (p:Project {name: 'Database Migration'}) CREATE (e)-[:WORKS_ON {role: 'Executive Sponsor', hoursPerWeek: 5}]->(p)",
    "MATCH (e:Employee {name: 'Bob Johnson'}), (p:Project {name: 'Database Migration'}) CREATE (e)-[:WORKS_ON {role: 'Project Manager', hoursPerWeek: 20}]->(p)",
    "MATCH (e:Employee {name: 'Carol Williams'}), (p:Project {name: 'Database Migration'}) CREATE (e)-[:WORKS_ON {role: 'Lead Developer', hoursPerWeek: 30}]->(p)",
    "MATCH (e:Employee {name: 'Dave Brown'}), (p:Project {name: 'Database Migration'}) CREATE (e)-[:WORKS_ON {role: 'Developer', hoursPerWeek: 40}]->(p)",
    "MATCH (e:Employee {name: 'Eve Davis'}), (p:Project {name: 'Website Redesign'}) CREATE (e)-[:WORKS_ON {role: 'Marketing Lead', hoursPerWeek: 25}]->(p)",
    "MATCH (e:Employee {name: 'Alice Smith'}), (p:Project {name: 'Data Analytics Platform'}) CREATE (e)-[:WORKS_ON {role: 'Technical Advisor', hoursPerWeek: 10}]->(p)",
    "MATCH (e:Employee {name: 'Carol Williams'}), (p:Project {name: 'Mobile App Development'}) CREATE (e)-[:WORKS_ON {role: 'Lead Developer', hoursPerWeek: 15}]->(p)",
    "MATCH (e:Employee {name: 'Dave Brown'}), (p:Project {name: 'Mobile App Development'}) CREATE (e)-[:WORKS_ON {role: 'Developer', hoursPerWeek: 20}]->(p)",
    "MATCH (e:Employee {name: 'Frank Miller'}), (p:Project {name: 'Data Analytics Platform'}) CREATE (e)-[:WORKS_ON {role: 'Business Sponsor', hoursPerWeek: 10}]->(p)",
    
    # Connect employees to skills with proficiency (Split into individual queries)
    "MATCH (e:Employee {name: 'Alice Smith'}), (s:Skill {name: 'Python'}) CREATE (e)-[:HAS_SKILL {proficiency: 4, yearsExperience: 8}]->(s)",
    "MATCH (e:Employee {name: 'Alice Smith'}), (s:Skill {name: 'Neo4j'}) CREATE (e)-[:HAS_SKILL {proficiency: 5, yearsExperience: 5}]->(s)",
    "MATCH (e:Employee {name: 'Alice Smith'}), (s:Skill {name: 'Project Management'}) CREATE (e)-[:HAS_SKILL {proficiency: 4, yearsExperience: 10}]->(s)",
    "MATCH (e:Employee {name: 'Bob Johnson'}), (s:Skill {name: 'Neo4j'}) CREATE (e)-[:HAS_SKILL {proficiency: 3, yearsExperience: 3}]->(s)",
    "MATCH (e:Employee {name: 'Bob Johnson'}), (s:Skill {name: 'Project Management'}) CREATE (e)-[:HAS_SKILL {proficiency: 4, yearsExperience: 7}]->(s)",
    "MATCH (e:Employee {name: 'Carol Williams'}), (s:Skill {name: 'Python'}) CREATE (e)-[:HAS_SKILL {proficiency: 5, yearsExperience: 6}]->(s)",
    "MATCH (e:Employee {name: 'Carol Williams'}), (s:Skill {name: 'Neo4j'}) CREATE (e)-[:HAS_SKILL {proficiency: 4, yearsExperience: 2}]->(s)",
    "MATCH (e:Employee {name: 'Carol Williams'}), (s:Skill {name: 'Machine Learning'}) CREATE (e)-[:HAS_SKILL {proficiency: 4, yearsExperience: 3}]->(s)",
    "MATCH (e:Employee {name: 'Dave Brown'}), (s:Skill {name: 'Python'}) CREATE (e)-[:HAS_SKILL {proficiency: 3, yearsExperience: 2}]->(s)",
    "MATCH (e:Employee {name: 'Dave Brown'}), (s:Skill {name: 'JavaScript'}) CREATE (e)-[:HAS_SKILL {proficiency: 4, yearsExperience: 3}]->(s)",
    "MATCH (e:Employee {name: 'Eve Davis'}), (s:Skill {name: 'Product Design'}) CREATE (e)-[:HAS_SKILL {proficiency: 5, yearsExperience: 8}]->(s)",
    "MATCH (e:Employee {name: 'Frank Miller'}), (s:Skill {name: 'Sales Negotiation'}) CREATE (e)-[:HAS_SKILL {proficiency: 5, yearsExperience: 12}]->(s)",
    "MATCH (e:Employee {name: 'Grace Wilson'}), (s:Skill {name: 'Project Management'}) CREATE (e)-[:HAS_SKILL {proficiency: 4, yearsExperience: 6}]->(s)",
    "MATCH (e:Employee {name: 'Heidi Moore'}), (s:Skill {name: 'Sales Negotiation'}) CREATE (e)-[:HAS_SKILL {proficiency: 3, yearsExperience: 3}]->(s)",

    # Connect projects to skills (Split into individual queries)
    "MATCH (p:Project {name: 'Database Migration'}), (s:Skill {name: 'Neo4j'}) CREATE (p)-[:REQUIRES_SKILL {importance: 5}]->(s)",
    "MATCH (p:Project {name: 'Database Migration'}), (s:Skill {name: 'Python'}) CREATE (p)-[:REQUIRES_SKILL {importance: 4}]->(s)",
    "MATCH (p:Project {name: 'Website Redesign'}), (s:Skill {name: 'JavaScript'}) CREATE (p)-[:REQUIRES_SKILL {importance: 5}]->(s)",
    "MATCH (p:Project {name: 'Website Redesign'}), (s:Skill {name: 'Product Design'}) CREATE (p)-[:REQUIRES_SKILL {importance: 5}]->(s)",
    "MATCH (p:Project {name: 'Mobile App Development'}), (s:Skill {name: 'JavaScript'}) CREATE (p)-[:REQUIRES_SKILL {importance: 4}]->(s)",
    "MATCH (p:Project {name: 'Mobile App Development'}), (s:Skill {name: 'Python'}) CREATE (p)-[:REQUIRES_SKILL {importance: 3}]->(s)",
    "MATCH (p:Project {name: 'Security Audit'}), (s:Skill {name: 'Cybersecurity'}) CREATE (p)-[:REQUIRES_SKILL {importance: 5}]->(s)",
    "MATCH (p:Project {name: 'Data Analytics Platform'}), (s:Skill {name: 'Python'}) CREATE (p)-[:REQUIRES_SKILL {importance: 5}]->(s)",
    "MATCH (p:Project {name: 'Data Analytics Platform'}), (s:Skill {name: 'Machine Learning'}) CREATE (p)-[:REQUIRES_SKILL {importance: 4}]->(s)"
]

# --- Challenge 6: Graph Analytics Setup Queries ---
# These are the queries that would be executed directly to bootstrap the GDS environment
ANALYTICS_SETUP_QUERIES = [
    # Create graph projection
    """
    CALL gds.graph.project(
      'company-graph',
      ['Employee', 'Department', 'Project', 'Skill'],
      {
        REPORTS_TO: {orientation: 'UNDIRECTED'},
        WORKS_IN: {orientation: 'UNDIRECTED'},
        WORKS_ON: {orientation: 'UNDIRECTED'},
        HAS_SKILL: {orientation: 'UNDIRECTED'}
      }
    )
    """,
    
    # Run and write degree centrality
    """
    CALL gds.degree.write('company-graph', {
      writeProperty: 'connectionScore',
      concurrency: 4
    })
    """,
    
    # Add betweenness centrality 
    """
    CALL gds.betweenness.write('company-graph', {
      writeProperty: 'betweennessScore',
      concurrency: 4
    })
    """
]

# --- Challenge 8: Data Transformation Setup ---
TRANSFORMATION_SETUP_QUERIES = [
    # Create team structure based on analytics
    """
    CREATE (:Team {name: 'Core Engineering Team', focus: 'Database and Backend'})
    CREATE (:Team {name: 'Frontend Team', focus: 'UI/UX and Client Applications'})
    CREATE (:Team {name: 'Business Solutions Team', focus: 'Sales and Analytics'})
    """,
    
    # Add team leaders (Split into individual queries)
    "MATCH (e:Employee {name: 'Bob Johnson'}) SET e:TeamLead",
    "MATCH (e:Employee {name: 'Eve Davis'}) SET e:TeamLead",
    "MATCH (e:Employee {name: 'Frank Miller'}) SET e:TeamLead",
    
    # Connect employees to teams (Split into individual queries)
    "MATCH (e:Employee {name: 'Bob Johnson'}), (t:Team {name: 'Core Engineering Team'}) CREATE (e)-[:LEADS]->(t)",
    "MATCH (e:Employee {name: 'Carol Williams'}), (t:Team {name: 'Core Engineering Team'}) CREATE (e)-[:MEMBER_OF]->(t)",
    "MATCH (e:Employee {name: 'Dave Brown'}), (t:Team {name: 'Core Engineering Team'}) CREATE (e)-[:MEMBER_OF]->(t)",
    "MATCH (e:Employee {name: 'Eve Davis'}), (t:Team {name: 'Frontend Team'}) CREATE (e)-[:LEADS]->(t)",
    "MATCH (e:Employee {name: 'Frank Miller'}), (t:Team {name: 'Business Solutions Team'}) CREATE (e)-[:LEADS]->(t)",
    "MATCH (e:Employee {name: 'Heidi Moore'}), (t:Team {name: 'Business Solutions Team'}) CREATE (e)-[:MEMBER_OF]->(t)"
]

# --- Verification Queries by Challenge ---
VERIFICATION_QUERIES = {
    # Challenge 1: No verification needed for schema exploration
    1: [
        # Just verify an empty database
        """
        MATCH (n)
        RETURN count(n) as nodeCount
        """
    ],
    
    # Challenge 2: Company Structure Creation
    2: [
        # Check departments were created
        """
        MATCH (d:Department)
        RETURN count(d) as departmentCount
        """,
        
        # Check employees were created
        """
        MATCH (e:Employee)
        RETURN count(e) as employeeCount
        """,
        
        # Check relationships exist
        """
        MATCH (:Employee)-[r:WORKS_IN]->(:Department)
        RETURN count(r) as worksInCount
        """,
        
        """
        MATCH (:Employee)-[r:REPORTS_TO]->(:Employee)
        RETURN count(r) as reportsToCount
        """
    ],
    
    # Challenge 3 & 4 don't modify the database, they just query
    3: [
        # Just verify the company structure exists
        """
        MATCH (d:Department)
        RETURN count(d) as departmentCount
        """,
        
        """
        MATCH (e:Employee)
        RETURN count(e) as employeeCount
        """
    ],
    
    4: [
        # Same as Challenge 3 - just verify the company structure
        """
        MATCH (d:Department)
        RETURN count(d) as departmentCount
        """,
        
        """
        MATCH (e:Employee)
        RETURN count(e) as employeeCount
        """
    ],
    
    # Challenge 5: Data Enrichment
    5: [
        # Check projects were created
        """
        MATCH (p:Project)
        RETURN count(p) as projectCount
        """,
        
        # Check skills were created
        """
        MATCH (s:Skill)
        RETURN count(s) as skillCount
        """,
        
        # Check new relationships exist
        """
        MATCH (:Employee)-[r:WORKS_ON]->(:Project)
        RETURN count(r) as worksOnCount
        """,
        
        """
        MATCH (:Employee)-[r:HAS_SKILL]->(:Skill)
        RETURN count(r) as hasSkillCount
        """,
        
        """
        MATCH (:Project)-[r:REQUIRES_SKILL]->(:Skill)
        RETURN count(r) as requiresSkillCount
        """
    ],
    
    # Challenge 6: Graph Analytics Setup
    6: [
        # Check for connection scores
        """
        MATCH (n) 
        WHERE n.connectionScore IS NOT NULL
        RETURN count(n) as nodesWithConnectionScore
        """,
        
        # Check for betweenness scores
        """
        MATCH (n) 
        WHERE n.betweennessScore IS NOT NULL
        RETURN count(n) as nodesWithBetweennessScore
        """
    ],
    
    # Challenge 7: Advanced Analytics - only verifies prerequisites
    7: [
        # Just check that the analytics properties exist
        """
        MATCH (n) 
        WHERE n.connectionScore IS NOT NULL
        RETURN count(n) as nodesWithConnectionScore
        """
    ],
    
    # Challenge 8: Data Transformation
    8: [
        # Check for team structure
        """
        MATCH (t:Team)
        RETURN count(t) as teamCount
        """,
        
        # Check for team lead label
        """
        MATCH (e:Employee:TeamLead)
        RETURN count(e) as teamLeadCount
        """,
        
        # Check for team relationships
        """
        MATCH (:Employee)-[r:LEADS]->(:Team)
        RETURN count(r) as leadsCount
        """,
        
        """
        MATCH (:Employee)-[r:MEMBER_OF]->(:Team)
        RETURN count(r) as memberOfCount
        """
    ],
    
    # Challenge 9: Final Integration
    9: [
        # Check for team structure from Challenge 8
        """
        MATCH (t:Team)
        RETURN count(t) as teamCount
        """,
        
        # Check for new projects
        """
        MATCH (p:Project)
        WHERE p.status = 'New' OR p.status = 'Planning'
        RETURN count(p) as newProjectCount
        """
    ]
}

# --- Expected results for verification queries ---
EXPECTED_RESULTS = {
    1: [
        {"nodeCount": 0}  # Empty database for Challenge 1
    ],
    2: [
        {"departmentCount": {"min": 3, "ideal": 4}},
        {"employeeCount": {"min": 6, "ideal": 8}},
        {"worksInCount": {"min": 6, "ideal": 8}},
        {"reportsToCount": {"min": 5, "ideal": 7}}
    ],
    3: [
        {"departmentCount": {"min": 3, "ideal": 4}},
        {"employeeCount": {"min": 6, "ideal": 8}}
    ],
    4: [
        {"departmentCount": {"min": 3, "ideal": 4}},
        {"employeeCount": {"min": 6, "ideal": 8}}
    ],
    5: [
        {"projectCount": {"min": 4, "ideal": 5}},
        {"skillCount": {"min": 6, "ideal": 8}},
        {"worksOnCount": {"min": 6, "ideal": 9}},
        {"hasSkillCount": {"min": 10, "ideal": 15}},
        {"requiresSkillCount": {"min": 6, "ideal": 9}}
    ],
    6: [
        {"nodesWithConnectionScore": {"min": 5, "ideal": 20}},
        {"nodesWithBetweennessScore": {"min": 5, "ideal": 20}}
    ],
    7: [
        {"nodesWithConnectionScore": {"min": 5, "ideal": 20}}
    ],
    8: [
        {"teamCount": {"min": 2, "ideal": 3}},
        {"teamLeadCount": {"min": 2, "ideal": 3}},
        {"leadsCount": {"min": 2, "ideal": 3}},
        {"memberOfCount": {"min": 3, "ideal": 5}}
    ],
    9: [
        {"teamCount": {"min": 2, "ideal": 3}},
        {"newProjectCount": {"min": 2, "ideal": 2}}
    ]
}


class GauntletData:
    """
    Manages data for the Neo4j Gauntlet challenges.
    """
    
    async def reset_database(self, direct_cypher: DirectCypherFunc) -> Dict[str, Any]:
        """
        Reset the database to a clean state for a fresh gauntlet run.
        """
        print("Resetting database for Neo4j Gauntlet...")
        
        # 1. Check if GDS graph projection exists and drop it
        check_gds_query = "CALL gds.graph.exists('company-graph') YIELD exists"
        drop_gds_query = "CALL gds.graph.drop('company-graph') YIELD graphName"
        
        try:
            check_result = await direct_cypher(check_gds_query, {}, write_mode=False)
            if check_result["status"] == "success" and check_result["data"] and check_result["data"][0].get("exists"):
                print("Found existing GDS graph 'company-graph'. Dropping...")
                drop_result = await direct_cypher(drop_gds_query, {}, write_mode=True)
                if drop_result["status"] == "success":
                    print("GDS graph 'company-graph' dropped successfully.")
                else:
                    # Log error but proceed with main DB clear
                    print(f"Warning: Failed to drop GDS graph 'company-graph': {drop_result.get('data')}")
            elif check_result["status"] != "success":
                 # Log error but proceed with main DB clear
                 print(f"Warning: Failed to check for GDS graph 'company-graph': {check_result.get('data')}")
        except Exception as e:
             # Log error but proceed with main DB clear
             print(f"Warning: Exception during GDS graph check/drop: {e}")

        # 2. Clear everything in the main database
        delete_query = """
        MATCH (n)
        DETACH DELETE n
        """
        delete_result = await direct_cypher(delete_query, {}, write_mode=True)
        
        if delete_result["status"] != "success":
            return {
                "status": "error",
                "data": f"Error clearing main database: {delete_result.get('data', 'Unknown error')}"
            }
        
        print("Main database cleared successfully.")
        return {
            "status": "success",
            "data": "Database reset successful"
        }
    
    async def verify_challenge(self, challenge_id: int, direct_cypher: DirectCypherFunc) -> Tuple[bool, List[str]]:
        """
        Verify that a challenge has been completed successfully by checking database state.
        
        Args:
            challenge_id: The ID of the challenge to verify
            direct_cypher: Function to execute Cypher queries directly
            
        Returns:
            (success, feedback_list): Whether verification passed and detailed feedback
        """
        feedback = []
        verification_passed = True
        
        # Skip verification for non-existent challenges
        if challenge_id < 1 or challenge_id > 9:
            return True, ["No verification needed for this challenge ID"]
            
        # Special case for challenge 1 - just verify the database is empty
        if challenge_id == 0:
            result = await direct_cypher("MATCH (n) RETURN count(n) as nodeCount", {})
            if result["status"] == "success" and result["data"][0]["nodeCount"] == 0:
                return True, ["Database is empty as expected"]
            else:
                return False, ["Database is not empty - reset required"]
        
        # Get verification queries for this challenge
        queries = VERIFICATION_QUERIES.get(challenge_id, [])
        expected = EXPECTED_RESULTS.get(challenge_id, [])
        
        if not queries:
            return True, ["No specific verification criteria for this challenge"]
        
        # Run all verification queries
        for i, query in enumerate(queries):
            result = await direct_cypher(query, {})
            
            if result["status"] != "success":
                verification_passed = False
                feedback.append(f"❌ Error running verification query: {result.get('data')}")
                continue
                
            # Compare with expectations if we have them
            if i < len(expected):
                expected_result = expected[i]
                actual_result = result["data"][0]
                
                # For each expected property
                for prop, exp_value in expected_result.items():
                    if prop in actual_result:
                        actual_value = actual_result[prop]
                        
                        # Handle minimum/ideal expectations
                        if isinstance(exp_value, dict) and "min" in exp_value:
                            min_val = exp_value["min"]
                            ideal_val = exp_value.get("ideal", min_val)
                            
                            if actual_value >= ideal_val:
                                feedback.append(f"✅ Found {actual_value} {prop} (excellent, ideal: {ideal_val})")
                            elif actual_value >= min_val:
                                feedback.append(f"✓ Found {actual_value} {prop} (acceptable, min: {min_val}, ideal: {ideal_val})")
                                verification_passed = verification_passed and True
                            else:
                                feedback.append(f"❌ Found only {actual_value} {prop} (min required: {min_val})")
                                verification_passed = False
                        # Handle exact expectations
                        else:
                            if actual_value == exp_value:
                                feedback.append(f"✅ Found {prop} = {actual_value} as expected")
                            else:
                                feedback.append(f"❌ Expected {prop} = {exp_value}, found {actual_value}")
                                verification_passed = False
                    else:
                        feedback.append(f"❌ Property {prop} not found in verification results")
                        verification_passed = False
            else:
                # Just report raw results without expectations
                for k, v in result["data"][0].items():
                    feedback.append(f"ℹ️ {k}: {v}")
        
        # Add some specific detailed feedback for certain challenges
        if challenge_id == 2 and verification_passed:
            hierarchy_query = """
            MATCH path=(e1:Employee)-[:REPORTS_TO*]->(e2:Employee)
            WHERE NOT (e2)-[:REPORTS_TO]->()
            RETURN e2.name as topManager, count(DISTINCT e1) as reportingChain
            """
            result = await direct_cypher(hierarchy_query, {})
            if result["status"] == "success" and len(result["data"]) > 0:
                top_manager = result["data"][0]["topManager"]
                chain_size = result["data"][0]["reportingChain"]
                feedback.append(f"✅ Successfully found management hierarchy with {top_manager} at the top and {chain_size} reporting employees")
            else:
                feedback.append("⚠️ Created basic structure but couldn't find complete management hierarchy")
        
        # Return overall result
        return verification_passed, feedback
    
    async def ensure_challenge_prerequisites(self, challenge_id: int, direct_cypher: DirectCypherFunc) -> bool:
        """
        Ensures all prerequisites for a challenge are met.
        If not, attempts to set them up using fallbacks.
        
        Args:
            challenge_id: The ID of the challenge to prepare for
            direct_cypher: Function to execute Cypher queries directly
            
        Returns:
            bool: True if prerequisites are now met, False otherwise
        """
        # Define prerequisites mapping
        prerequisites = {
            1: [],  # No prerequisites for challenge 1
            2: [],  # No prerequisites for challenge 2
            3: [2],  # Challenge 3 requires challenge 2
            4: [2],  # Challenge 4 requires challenge 2
            5: [2],  # Challenge 5 requires challenge 2
            6: [5],  # Challenge 6 requires challenge 5
            7: [6],  # Challenge 7 requires challenge 6
            8: [6],  # Challenge 8 requires challenge 6
            9: [8],  # Challenge 9 requires challenge 8
        }
        
        # Get prerequisites for this challenge
        prereqs = prerequisites.get(challenge_id, [])
        if not prereqs:
            return True  # No prerequisites needed
        
        # Check and setup each prerequisite
        for prereq_id in prereqs:
            # Check if prerequisite is already met
            prereq_success, _ = await self.verify_challenge(prereq_id, direct_cypher)
            
            if not prereq_success:
                print(f"Prerequisite {prereq_id} not met, setting up fallback data...")
                # Set up prerequisites based on challenge
                if prereq_id == 2:
                    await self.setup_company_structure(direct_cypher)
                elif prereq_id == 5:
                    await self.setup_data_enrichment(direct_cypher)
                elif prereq_id == 6:
                    await self.setup_analytics(direct_cypher)
                elif prereq_id == 8:
                    await self.setup_transformation(direct_cypher)
                
                # Verify again after setup
                prereq_success, _ = await self.verify_challenge(prereq_id, direct_cypher)
                if not prereq_success:
                    print(f"Failed to set up prerequisite {prereq_id}")
                    return False
        
        return True
    
    # --- Helper methods for setting up fallback data ---
    
    async def setup_company_structure(self, direct_cypher: DirectCypherFunc) -> bool:
        """Sets up the company structure needed for Challenge 2."""
        print("Setting up fallback data for company structure...")
        
        for query in COMPANY_SETUP_QUERIES:
            result = await direct_cypher(query, {}, write_mode=True)
            if result["status"] != "success":
                print(f"Error setting up company structure: {result.get('data')}")
                return False
        
        print("Company structure fallback setup complete.")
        return True
    
    async def setup_data_enrichment(self, direct_cypher: DirectCypherFunc) -> bool:
        """Sets up the data enrichment (projects/skills) needed for Challenge 5."""
        print("Setting up fallback data for data enrichment...")
        
        # First ensure company structure exists
        company_structure_exists, _ = await self.verify_challenge(2, direct_cypher)
        if not company_structure_exists:
            success = await self.setup_company_structure(direct_cypher)
            if not success:
                return False
        
        # Now add projects and skills
        for query in DATA_ENRICHMENT_QUERIES:
            result = await direct_cypher(query, {}, write_mode=True)
            if result["status"] != "success":
                print(f"Error setting up data enrichment: {result.get('data')}")
                return False
        
        print("Data enrichment fallback setup complete.")
        return True
    
    async def setup_analytics(self, direct_cypher: DirectCypherFunc) -> bool:
        """Sets up the GDS analytics environment needed for Challenge 6."""
        print("Setting up fallback data for graph analytics...")
        
        # Ensure data enrichment exists
        data_enrichment_exists, _ = await self.verify_challenge(5, direct_cypher)
        if not data_enrichment_exists:
            success = await self.setup_data_enrichment(direct_cypher)
            if not success:
                return False
        
        # Now set up GDS analytics
        try:
            for query in ANALYTICS_SETUP_QUERIES:
                result = await direct_cypher(query, {}, write_mode=True)
                if result["status"] != "success":
                    print(f"Error setting up analytics: {result.get('data')}")
                    return False
        except Exception as e:
            print(f"Exception during GDS setup: {e}")
            return False
        
        print("Analytics fallback setup complete.")
        return True
    
    async def setup_transformation(self, direct_cypher: DirectCypherFunc) -> bool:
        """Sets up the team transformation needed for Challenge 8."""
        print("Setting up fallback data for team transformation...")
        
        # Ensure analytics data exists
        analytics_exists, _ = await self.verify_challenge(6, direct_cypher)
        if not analytics_exists:
            success = await self.setup_analytics(direct_cypher)
            if not success:
                return False
        
        # Now set up team transformation
        for query in TRANSFORMATION_SETUP_QUERIES:
            result = await direct_cypher(query, {}, write_mode=True)
            if result["status"] != "success":
                print(f"Error setting up team transformation: {result.get('data')}")
                return False
        
        print("Team transformation fallback setup complete.")
        return True


# Create a singleton instance
gauntlet_data = GauntletData()