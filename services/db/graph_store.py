#!/usr/bin/env python3
"""
Production Graph Database Service using Neo4j
Replaces SQLite-based graph storage with enterprise Neo4j.
"""

import os
import logging
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime
import json

# Production graph database
try:
    from neo4j import GraphDatabase, Driver
    from neo4j.exceptions import ServiceUnavailable, TransactionError
    NEO4J_AVAILABLE = True
except ImportError:
    NEO4J_AVAILABLE = False
    print("Installing Neo4j driver...")
    os.system("pip install neo4j")
    try:
        from neo4j import GraphDatabase, Driver
        from neo4j.exceptions import ServiceUnavailable, TransactionError
        NEO4J_AVAILABLE = True
    except ImportError:
        NEO4J_AVAILABLE = False

logger = logging.getLogger(__name__)

class ProductionGraphStore:
    """Production graph database using Neo4j."""
    
    def __init__(self, uri: str = "neo4j://localhost:7687", 
                 user: str = "neo4j", password: str = "password",
                 database: str = "aml"):
        """Initialize Neo4j connection."""
        if not NEO4J_AVAILABLE:
            raise RuntimeError("Neo4j driver not available. Install with: pip install neo4j")
        
        self.uri = uri
        self.user = user
        self.password = password
        self.database = database
        self.driver: Optional[Driver] = None
        
        logger.info(f"Initializing production Neo4j graph store: {uri}")
    
    def connect(self):
        """Establish Neo4j connection."""
        try:
            self.driver = GraphDatabase.driver(
                self.uri, 
                auth=(self.user, self.password),
                max_connection_lifetime=3600,
                max_connection_pool_size=50,
                connection_acquisition_timeout=60
            )
            
            # Verify connectivity
            with self.driver.session(database=self.database) as session:
                result = session.run("RETURN 1 AS test")
                test_value = result.single()["test"]
                if test_value != 1:
                    raise RuntimeError("Neo4j connectivity test failed")
            
            logger.info("Neo4j connection established successfully")
            
        except ServiceUnavailable as e:
            logger.error(f"Neo4j service unavailable: {e}")
            raise
        except Exception as e:
            logger.error(f"Neo4j connection failed: {e}")
            raise
    
    def close(self):
        """Close Neo4j connection."""
        if self.driver:
            self.driver.close()
            logger.info("Neo4j connection closed")
    
    def __enter__(self):
        """Context manager entry."""
        self.connect()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()
    
    def create_constraints_and_indexes(self):
        """Create Neo4j constraints and indexes for optimal performance."""
        constraints_and_indexes = [
            # Entity constraints
            "CREATE CONSTRAINT entity_key_unique IF NOT EXISTS FOR (e:Entity) REQUIRE e.key IS UNIQUE",
            "CREATE CONSTRAINT table_name_unique IF NOT EXISTS FOR (t:Table) REQUIRE (t.owner, t.name) IS UNIQUE",
            "CREATE CONSTRAINT column_name_unique IF NOT EXISTS FOR (c:Column) REQUIRE (c.owner, c.table_name, c.name) IS UNIQUE",
            "CREATE CONSTRAINT view_name_unique IF NOT EXISTS FOR (v:View) REQUIRE (v.owner, v.name) IS UNIQUE",
            
            # Performance indexes
            "CREATE INDEX entity_type_idx IF NOT EXISTS FOR (e:Entity) ON (e.entity_type)",
            "CREATE INDEX entity_owner_idx IF NOT EXISTS FOR (e:Entity) ON (e.owner)",
            "CREATE INDEX entity_name_idx IF NOT EXISTS FOR (e:Entity) ON (e.name)",
            "CREATE INDEX table_owner_idx IF NOT EXISTS FOR (t:Table) ON (t.owner)",
            "CREATE INDEX column_table_idx IF NOT EXISTS FOR (c:Column) ON (c.table_name)",
            "CREATE INDEX relationship_type_idx IF NOT EXISTS FOR ()-[r]-() ON (r.relationship_type)",
            
            # Text search indexes
            "CREATE FULLTEXT INDEX entity_search_idx IF NOT EXISTS FOR (e:Entity) ON EACH [e.name, e.description, e.comments]",
            "CREATE FULLTEXT INDEX table_search_idx IF NOT EXISTS FOR (t:Table) ON EACH [t.name, t.comments, t.tablespace_name]",
            "CREATE FULLTEXT INDEX column_search_idx IF NOT EXISTS FOR (c:Column) ON EACH [c.name, c.data_type, c.comments]"
        ]
        
        with self.driver.session(database=self.database) as session:
            for statement in constraints_and_indexes:
                try:
                    session.run(statement)
                    logger.info(f"Applied: {statement}")
                except Exception as e:
                    logger.warning(f"Failed to apply: {statement} - {e}")
    
    def clear_database(self):
        """Clear all data from the graph database."""
        with self.driver.session(database=self.database) as session:
            session.run("MATCH (n) DETACH DELETE n")
            logger.info("🗑️ Neo4j database cleared")
    
    def add_entity(self, entity: Dict[str, Any]) -> str:
        """Add an entity to the graph."""
        entity_type = entity.get('entity_type', 'Entity')
        
        # Create node with multiple labels
        labels = ['Entity']
        if entity_type == 'table':
            labels.append('Table')
        elif entity_type == 'column':
            labels.append('Column')
        elif entity_type == 'view':
            labels.append('View')
        elif entity_type == 'constraint':
            labels.append('Constraint')
        elif entity_type == 'index':
            labels.append('Index')
        
        # Prepare properties
        entity_key = entity.get('entity_key')
        if not entity_key:
            raise ValueError(f"Entity must have an 'entity_key' field: {entity}")
        
        # Determine the name field based on entity type
        name_field = ''
        if entity_type == 'table':
            name_field = entity.get('table_name', '')
        elif entity_type == 'view':
            name_field = entity.get('view_name', '')
        elif entity_type == 'column':
            name_field = entity.get('column_name', '')
        else:
            name_field = entity.get('name', '')
        
        properties = {
            'key': entity_key,
            'entity_type': entity_type,
            'name': name_field,
            'owner': entity.get('owner', ''),
            'created_at': datetime.utcnow().isoformat(),
            'updated_at': datetime.utcnow().isoformat()
        }
        
        # Add type-specific properties
        for key, value in entity.items():
            if key not in ['entity_key', 'entity_type'] and value is not None:
                # Convert complex types to JSON strings
                if isinstance(value, (dict, list)):
                    properties[key] = json.dumps(value)
                else:
                    properties[key] = str(value)
        
        # Create Cypher query
        labels_str = ':'.join(labels)
        cypher = f"""
        MERGE (e:{labels_str} {{key: $key}})
        SET e += $properties
        RETURN e.key AS entity_key
        """
        
        with self.driver.session(database=self.database) as session:
            result = session.run(cypher, key=properties['key'], properties=properties)
            return result.single()["entity_key"]
    
    def add_relationship(self, source_key: str, target_key: str, 
                        relationship_type: str, properties: Dict[str, Any] = None) -> str:
        """Add a relationship between entities."""
        if properties is None:
            properties = {}
        
        # Add metadata
        properties.update({
            'relationship_type': relationship_type,
            'created_at': datetime.utcnow().isoformat()
        })
        
        cypher = """
        MATCH (source:Entity {key: $source_key})
        MATCH (target:Entity {key: $target_key})
        MERGE (source)-[r:RELATED_TO {relationship_type: $relationship_type}]->(target)
        SET r += $properties
        RETURN id(r) AS relationship_id
        """
        
        with self.driver.session(database=self.database) as session:
            result = session.run(
                cypher,
                source_key=source_key,
                target_key=target_key,
                relationship_type=relationship_type,
                properties=properties
            )
            return str(result.single()["relationship_id"])
    
    def find_entity(self, entity_key: str) -> Optional[Dict[str, Any]]:
        """Find an entity by key."""
        cypher = """
        MATCH (e:Entity {key: $entity_key})
        RETURN e
        """
        
        with self.driver.session(database=self.database) as session:
            result = session.run(cypher, entity_key=entity_key)
            record = result.single()
            if record:
                return dict(record["e"])
            return None
    
    def find_related_entities(self, entity_key: str, relationship_types: List[str] = None,
                            direction: str = "both", max_depth: int = 2) -> List[Dict[str, Any]]:
        """Find entities related to the given entity."""
        # Build relationship filter
        rel_filter = ""
        if relationship_types:
            type_conditions = " OR ".join([f"r.relationship_type = '{rt}'" for rt in relationship_types])
            rel_filter = f"WHERE {type_conditions}"
        
        # Build direction clause
        if direction == "outgoing":
            relationship_pattern = "-[r:RELATED_TO]->"
        elif direction == "incoming":
            relationship_pattern = "<-[r:RELATED_TO]-"
        else:  # both
            relationship_pattern = "-[r:RELATED_TO]-"
        
        cypher = f"""
        MATCH (source:Entity {{key: $entity_key}})
        MATCH (source){relationship_pattern}(target:Entity)
        {rel_filter}
        RETURN DISTINCT target, r
        LIMIT 100
        """
        
        with self.driver.session(database=self.database) as session:
            result = session.run(cypher, entity_key=entity_key)
            
            related_entities = []
            for record in result:
                entity_data = dict(record["target"])
                relationship_data = dict(record["r"])
                
                related_entities.append({
                    "entity": entity_data,
                    "relationship": relationship_data,
                    "relationship_type": relationship_data.get("relationship_type")
                })
            
            return related_entities
    
    def search_entities(self, query: str, entity_types: List[str] = None, 
                       limit: int = 20) -> List[Dict[str, Any]]:
        """Search entities using full-text search."""
        # Build entity type filter
        type_filter = ""
        if entity_types:
            type_conditions = " OR ".join([f"e.entity_type = '{et}'" for et in entity_types])
            type_filter = f"WHERE {type_conditions}"
        
        cypher = f"""
        CALL db.index.fulltext.queryNodes('entity_search_idx', $query)
        YIELD node AS e, score
        {type_filter}
        RETURN e, score
        ORDER BY score DESC
        LIMIT $limit
        """
        
        with self.driver.session(database=self.database) as session:
            result = session.run(cypher, query=query, limit=limit)
            
            entities = []
            for record in result:
                entity_data = dict(record["e"])
                entity_data["search_score"] = record["score"]
                entities.append(entity_data)
            
            return entities
    
    def get_graph_statistics(self) -> Dict[str, Any]:
        """Get comprehensive graph statistics."""
        statistics_queries = {
            "total_nodes": "MATCH (n) RETURN count(n) AS count",
            "total_relationships": "MATCH ()-[r]-() RETURN count(r) AS count",
            "entity_types": """
                MATCH (e:Entity)
                RETURN e.entity_type AS type, count(e) AS count
                ORDER BY count DESC
            """,
            "relationship_types": """
                MATCH ()-[r:RELATED_TO]->()
                RETURN r.relationship_type AS type, count(r) AS count
                ORDER BY count DESC
            """,
            "owners": """
                MATCH (e:Entity)
                WHERE e.owner IS NOT NULL
                RETURN e.owner AS owner, count(e) AS count
                ORDER BY count DESC
                LIMIT 10
            """
        }
        
        stats = {}
        
        with self.driver.session(database=self.database) as session:
            # Simple counts
            for stat_name, query in statistics_queries.items():
                if stat_name in ["entity_types", "relationship_types", "owners"]:
                    result = session.run(query)
                    stats[stat_name] = [dict(record) for record in result]
                else:
                    result = session.run(query)
                    stats[stat_name] = result.single()["count"]
        
        return stats
    
    def find_path(self, source_key: str, target_key: str, max_depth: int = 5) -> List[Dict[str, Any]]:
        """Find shortest path between two entities."""
        cypher = """
        MATCH (source:Entity {key: $source_key})
        MATCH (target:Entity {key: $target_key})
        MATCH path = shortestPath((source)-[*1..{max_depth}]-(target))
        RETURN [node IN nodes(path) | node.key] AS node_keys,
               [rel IN relationships(path) | rel.relationship_type] AS relationship_types,
               length(path) AS path_length
        """.format(max_depth=max_depth)
        
        with self.driver.session(database=self.database) as session:
            result = session.run(cypher, source_key=source_key, target_key=target_key)
            
            paths = []
            for record in result:
                paths.append({
                    "node_keys": record["node_keys"],
                    "relationship_types": record["relationship_types"],
                    "path_length": record["path_length"]
                })
            
            return paths
    
    def get_entity_neighborhood(self, entity_key: str, radius: int = 2) -> Dict[str, Any]:
        """Get the neighborhood of an entity (nodes and relationships within radius)."""
        cypher = f"""
        MATCH (center:Entity {{key: $entity_key}})
        MATCH (center)-[*1..{radius}]-(neighbor:Entity)
        WITH center, collect(DISTINCT neighbor) AS neighbors
        MATCH (n1)-[r]-(n2)
        WHERE n1 IN ([center] + neighbors) AND n2 IN ([center] + neighbors)
        RETURN center,
               neighbors,
               collect(DISTINCT {{
                   source: n1.key,
                   target: n2.key,
                   type: r.relationship_type,
                   properties: properties(r)
               }}) AS relationships
        """
        
        with self.driver.session(database=self.database) as session:
            result = session.run(cypher, entity_key=entity_key)
            record = result.single()
            
            if not record:
                return {"center": None, "neighbors": [], "relationships": []}
            
            return {
                "center": dict(record["center"]),
                "neighbors": [dict(neighbor) for neighbor in record["neighbors"]],
                "relationships": record["relationships"]
            }

class AMLGraphBuilder:
    """Build production AML relationship graphs in Neo4j."""
    
    def __init__(self, graph_store: ProductionGraphStore):
        self.graph_store = graph_store
    
    def build_table_column_relationships(self, catalog_entities: List[Dict[str, Any]]):
        """Build relationships between tables and their columns."""
        logger.info("Building table-column relationships...")
        
        # Group entities by type
        tables = [e for e in catalog_entities if e.get('entity_type') == 'table']
        columns = [e for e in catalog_entities if e.get('entity_type') == 'column']
        
        relationships_created = 0
        
        for column in columns:
            table_owner = column.get('owner')
            table_name = column.get('table_name')
            
            # Find matching table
            table_key = f"table:{table_owner}.{table_name}"
            column_key = column.get('entity_key')
            
            if table_key and column_key:
                try:
                    self.graph_store.add_relationship(
                        source_key=table_key,
                        target_key=column_key,
                        relationship_type="HAS_COLUMN",
                        properties={
                            "column_position": column.get('column_id'),
                            "data_type": column.get('data_type'),
                            "nullable": column.get('nullable')
                        }
                    )
                    relationships_created += 1
                except Exception as e:
                    logger.warning(f"Failed to create table-column relationship: {e}")
        
        logger.info(f"Created {relationships_created} table-column relationships")
    
    def build_foreign_key_relationships(self, catalog_entities: List[Dict[str, Any]]):
        """Build foreign key relationships."""
        logger.info("Building foreign key relationships...")
        
        constraints = [e for e in catalog_entities if e.get('entity_type') == 'constraint' 
                      and e.get('constraint_type') == 'R']  # Foreign keys
        
        relationships_created = 0
        
        for constraint in constraints:
            try:
                # For FK constraints, we need to query the constraint details
                # This is a simplified version - in production you'd query DBA_CONS_COLUMNS
                source_table_key = f"table:{constraint.get('owner')}.{constraint.get('table_name')}"
                
                # Add constraint entity and relationships
                constraint_key = constraint.get('entity_key')
                
                if source_table_key and constraint_key:
                    self.graph_store.add_relationship(
                        source_key=source_table_key,
                        target_key=constraint_key,
                        relationship_type="HAS_CONSTRAINT",
                        properties={
                            "constraint_type": constraint.get('constraint_type'),
                            "status": constraint.get('status')
                        }
                    )
                    relationships_created += 1
                    
            except Exception as e:
                logger.warning(f"Failed to create FK relationship: {e}")
        
        logger.info(f"Created {relationships_created} foreign key relationships")
    
    def build_schema_relationships(self, catalog_entities: List[Dict[str, Any]]):
        """Build schema-level relationships."""
        logger.info("Building schema relationships...")
        
        # Group by owner (schema)
        owners = {}
        for entity in catalog_entities:
            owner = entity.get('owner')
            if owner:
                if owner not in owners:
                    owners[owner] = []
                owners[owner].append(entity)
        
        relationships_created = 0
        
        for owner, entities in owners.items():
            # Create schema node
            schema_key = f"schema:{owner}"
            schema_entity = {
                'entity_key': schema_key,
                'entity_type': 'schema',
                'name': owner,
                'owner': owner,
                'entity_count': len(entities)
            }
            
            self.graph_store.add_entity(schema_entity)
            
            # Link entities to schema
            for entity in entities:
                try:
                    self.graph_store.add_relationship(
                        source_key=schema_key,
                        target_key=entity.get('entity_key'),
                        relationship_type="CONTAINS",
                        properties={
                            "entity_type": entity.get('entity_type')
                        }
                    )
                    relationships_created += 1
                except Exception as e:
                    logger.warning(f"Failed to create schema relationship: {e}")
        
        logger.info(f"Created {relationships_created} schema relationships")