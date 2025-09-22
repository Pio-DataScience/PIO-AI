#!/usr/bin/env python3
"""
Neo4j Setup Guide for AML Production Graph
Instructions to get Neo4j running and build the production graph.
"""

print("""
🚀 Neo4j Setup for AML Production Graph
=====================================

Your graph building script is ready! You just need Neo4j running.

Option 1: Docker (Recommended)
------------------------------
1. Start Docker Desktop
2. Run this command:

   docker run -d \\
     --name neo4j-aml \\
     -p 7474:7474 -p 7687:7687 \\
     -e NEO4J_AUTH=neo4j/production_password \\
     -e NEO4J_dbms_default__database=aml \\
     neo4j:latest

3. Wait ~30 seconds for Neo4j to start
4. Test: Open http://localhost:7474 (Browser UI)
   - Username: neo4j
   - Password: production_password

Option 2: Download Neo4j Community
----------------------------------
1. Download from: https://neo4j.com/download-center/
2. Extract and run: bin/neo4j start
3. Set password: bin/neo4j-admin set-initial-password production_password

🔥 Once Neo4j is Running:
=========================

# Build full production graph (recommended):
python scripts/43_build_production_graph.py --rebuild --batch-size 1000

# Or analyze existing graph:
python scripts/43_build_production_graph.py --analyze-only

# Or quick test:
python scripts/43_build_production_graph.py --skip-migration --test-queries "basic"

📊 What the Graph Will Include:
==============================
- 5,448+ table nodes (already harvested from Oracle)
- Column nodes with data types and relationships
- View nodes and dependencies  
- Foreign Key → Primary Key relationships
- AML-specific entity clustering
- Semantic similarity edges (planned)

🎯 Graph Capabilities After Build:
==================================
- Data lineage tracing
- Impact analysis (what breaks if I change X?)
- Schema exploration (find all tables related to customers)
- Pattern detection (find similar table structures)
- Business glossary navigation

Your catalog is loaded with AML data - let's build that graph! 🚀
""")